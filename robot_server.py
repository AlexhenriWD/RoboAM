#!/usr/bin/env python3
"""
EVA ROBOT - NETWORK SERVER
Servidor WebSocket + Flask para controle remoto e streaming
"""

import asyncio
import json
import time
from typing import Set, Optional
from flask import Flask, render_template, Response, jsonify
from flask_socketio import SocketIO, emit
import cv2
import numpy as np
from pathlib import Path

# Imports internos
from robot_state import STATE, RobotMode
from hardware_config import CONFIG


# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'eva-robot-2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


# ============================================================================
# ROBOT SERVER
# ============================================================================

class RobotServer:
    """
    Servidor de rede do robô
    
    Funcionalidades:
    - WebSocket para comandos em tempo real
    - HTTP REST para consultas de estado
    - Stream de vídeo MJPEG
    - Broadcast de estado para clientes conectados
    """
    
    def __init__(self, robot_core, camera_system, safety_controller):
        self.robot = robot_core
        self.camera = camera_system
        self.safety = safety_controller
        
        # Clientes conectados
        self.connected_clients: Set = set()
        
        # Estado de broadcast
        self.broadcasting = False
        self.broadcast_interval = 0.1  # 10Hz
        
        print("✅ Robot Server inicializado")
    
    # ========================================
    # COMANDOS
    # ========================================
    
    def handle_drive_command(self, vx: float, vy: float, vz: float) -> dict:
        """
        Processa comando de movimento
        
        Args:
            vx: Forward/backward (-1.0 a 1.0)
            vy: Strafe left/right (-1.0 a 1.0)
            vz: Rotation (-1.0 a 1.0)
        """
        # Validar segurança
        safe, reason = self.safety.validate_drive_command(vx, vy, vz)
        
        if not safe:
            return {
                'status': 'blocked',
                'reason': reason
            }
        
        # Converter para PWM
        max_pwm = CONFIG.motors.DEFAULT_SPEED
        
        # Cinemática mecanum
        fl = int((vx + vy + vz) * max_pwm)
        bl = int((vx - vy + vz) * max_pwm)
        fr = int((vx - vy - vz) * max_pwm)
        br = int((vx + vy - vz) * max_pwm)
        
        # Aplicar
        try:
            self.robot.set_motor_model(fl, bl, fr, br)
            
            # Atualizar estado
            STATE.set_motors(fl, bl, fr, br)
            STATE.update(
                last_command=f"drive(vx={vx:.2f}, vy={vy:.2f}, vz={vz:.2f})",
                last_command_time=time.time()
            )
            
            # Heartbeat
            self.safety.heartbeat()
            
            # Trocar para câmera de navegação
            if self.camera and vx != 0:
                self.camera.switch_to_navigation()
            
            return {
                'status': 'ok',
                'motors': {'fl': fl, 'bl': bl, 'fr': fr, 'br': br}
            }
        
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def handle_head_command(self, yaw: Optional[int], pitch: Optional[int]) -> dict:
        """
        Processa comando de cabeça
        
        Args:
            yaw: Ângulo yaw (0-180)
            pitch: Ângulo pitch (0-180)
        """
        if not self.robot.arm:
            return {'status': 'error', 'error': 'Braço não disponível'}
        
        results = []
        
        # Yaw
        if yaw is not None:
            safe, reason = self.safety.validate_servo_command(0, yaw)
            
            if safe:
                try:
                    ok = self.robot.arm.move_smooth(0, yaw, step=2, step_delay=0.02)
                    results.append({'servo': 'yaw', 'angle': yaw, 'success': ok})
                    
                    if ok:
                        STATE.set_servo(0, yaw)
                except Exception as e:
                    results.append({'servo': 'yaw', 'error': str(e)})
            else:
                results.append({'servo': 'yaw', 'error': reason})
        
        # Pitch
        if pitch is not None:
            safe, reason = self.safety.validate_servo_command(1, pitch)
            
            if safe:
                try:
                    ok = self.robot.arm.move_smooth(1, pitch, step=2, step_delay=0.02)
                    results.append({'servo': 'pitch', 'angle': pitch, 'success': ok})
                    
                    if ok:
                        STATE.set_servo(1, pitch)
                except Exception as e:
                    results.append({'servo': 'pitch', 'error': str(e)})
            else:
                results.append({'servo': 'pitch', 'error': reason})
        
        # Trocar para câmera da cabeça
        if self.camera and (yaw is not None or pitch is not None):
            self.camera.switch_to_arm_camera()
        
        STATE.update(
            last_command=f"head(yaw={yaw}, pitch={pitch})",
            last_command_time=time.time()
        )
        
        return {
            'status': 'ok',
            'results': results
        }
    
    def handle_stop_command(self) -> dict:
        """Para todos os motores"""
        try:
            self.robot.stop()
            STATE.set_motors(0, 0, 0, 0)
            STATE.update(
                last_command="stop",
                last_command_time=time.time()
            )
            
            return {'status': 'ok'}
        
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def handle_emergency_stop(self, reason: str = "Manual") -> dict:
        """Emergency stop"""
        self.safety.trigger_emergency_stop(reason)
        STATE.trigger_emergency_stop(reason)
        
        return {'status': 'ok', 'message': 'Emergency stop acionado'}
    
    # ========================================
    # BROADCAST DE ESTADO
    # ========================================
    
    def start_broadcast(self):
        """Inicia broadcast de estado para clientes"""
        if self.broadcasting:
            return
        
        self.broadcasting = True
        socketio.start_background_task(self._broadcast_loop)
        print("📡 Broadcast de estado iniciado")
    
    def stop_broadcast(self):
        """Para broadcast"""
        self.broadcasting = False
        print("📡 Broadcast de estado parado")
    
    def _broadcast_loop(self):
        """Loop de broadcast (roda em background)"""
        while self.broadcasting:
            try:
                # Pegar estado
                state_dict = STATE.to_dict()
                
                # Broadcast para todos os clientes
                socketio.emit('state_update', state_dict, namespace='/')
                
                socketio.sleep(self.broadcast_interval)
            
            except Exception as e:
                print(f"❌ Erro no broadcast: {e}")
                socketio.sleep(1.0)


# ============================================================================
# INSTÂNCIA GLOBAL DO SERVIDOR
# ============================================================================

# Será inicializado no main.py
robot_server: Optional[RobotServer] = None


# ============================================================================
# ROTAS FLASK
# ============================================================================

@app.route('/')
def index():
    """Página principal"""
    return render_template('control.html')


@app.route('/status')
def status():
    """Status do robô (JSON)"""
    state_dict = STATE.to_dict()
    
    return jsonify({
        'status': 'ok',
        'timestamp': time.time(),
        'robot': state_dict
    })


@app.route('/video_feed')
def video_feed():
    """Stream de vídeo MJPEG"""
    
    def generate():
        while True:
            if robot_server and robot_server.camera:
                frame = robot_server.camera.get_frame()
            else:
                # Frame placeholder
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    frame, "Aguardando camera...", (150, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2
                )
            
            if frame is not None:
                # Badge com câmera ativa
                state = STATE.get_state()
                cam_text = state.active_camera.upper()
                color = (0, 255, 0) if cam_text == "WEBCAM" else (255, 100, 255)
                
                cv2.rectangle(frame, (10, 10), (150, 50), (0, 0, 0), -1)
                cv2.putText(frame, cam_text, (20, 40),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
                
                # Encode JPEG
                ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            
            time.sleep(0.033)  # ~30 FPS
    
    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# ============================================================================
# WEBSOCKET HANDLERS
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Cliente conectou"""
    print(f"🔗 Cliente conectado")
    
    # Enviar estado inicial
    state_dict = STATE.to_dict()
    
    emit('welcome', {
        'message': 'Conectado ao EVA Robot',
        'state': state_dict,
        'config': {
            'motors_max_speed': CONFIG.motors.MAX_SAFE_SPEED,
            'servos': {
                ch: {
                    'min': limits.min_angle,
                    'max': limits.max_angle,
                    'home': limits.home_angle
                }
                for ch, limits in CONFIG.servos.LIMITS.items()
            }
        }
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectou"""
    print(f"🔌 Cliente desconectado")
    
    # Parar robô por segurança
    if robot_server:
        robot_server.handle_stop_command()


@socketio.on('command')
def handle_command(data):
    """Recebe comando do cliente"""
    if not robot_server:
        emit('response', {'status': 'error', 'error': 'Servidor não inicializado'})
        return
    
    cmd = data.get('cmd')
    params = data.get('params', {})
    
    print(f"📨 CMD: {cmd} {params}")
    
    # Processar comando
    if cmd == 'drive':
        result = robot_server.handle_drive_command(
            vx=params.get('vx', 0),
            vy=params.get('vy', 0),
            vz=params.get('vz', 0)
        )
    
    elif cmd == 'head':
        result = robot_server.handle_head_command(
            yaw=params.get('yaw'),
            pitch=params.get('pitch')
        )
    
    elif cmd == 'stop':
        result = robot_server.handle_stop_command()
    
    elif cmd == 'estop':
        result = robot_server.handle_emergency_stop(
            reason=params.get('reason', 'Manual')
        )
    
    elif cmd == 'heartbeat':
        robot_server.safety.heartbeat()
        result = {'status': 'ok', 'timestamp': time.time()}
    
    else:
        result = {'status': 'error', 'error': f'Comando desconhecido: {cmd}'}
    
    # Enviar resposta
    emit('response', result)


# ============================================================================
# TEMPLATE HTML BÁSICO
# ============================================================================

def create_html_template():
    """Cria template HTML básico"""
    
    template_dir = Path(__file__).parent.parent / 'templates'
    template_dir.mkdir(exist_ok=True)
    
    html = """<!DOCTYPE html>
<html>
<head>
    <title>EVA Robot Control</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #1a1a1a;
            color: white;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .status { background: #2a2a2a; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .controls { background: #2a2a2a; padding: 20px; border-radius: 8px; }
        button {
            background: #4CAF50;
            border: none;
            color: white;
            padding: 15px 32px;
            margin: 5px;
            cursor: pointer;
            border-radius: 4px;
            font-size: 16px;
        }
        button:hover { background: #45a049; }
        button:active { transform: translateY(2px); }
        .estop { background: #f44336 !important; }
        #video { width: 100%; max-width: 640px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 EVA Robot Control</h1>
        
        <div class="status">
            <h3>Status</h3>
            <p>Conexão: <span id="status">Desconectado</span></p>
            <p>Modo: <span id="mode">-</span></p>
            <p>Bateria: <span id="battery">-</span>V</p>
        </div>
        
        <img id="video" src="/video_feed">
        
        <div class="controls">
            <h3>Controles</h3>
            <div>
                <button onclick="drive(1,0,0)">⬆️ Frente</button>
            </div>
            <div>
                <button onclick="drive(0,0,1)">⬅️ Esquerda</button>
                <button onclick="stop()">⏹️ PARAR</button>
                <button onclick="drive(0,0,-1)">➡️ Direita</button>
            </div>
            <div>
                <button onclick="drive(-1,0,0)">⬇️ Ré</button>
            </div>
            <div style="margin-top: 20px;">
                <button class="estop" onclick="estop()">🚨 EMERGENCY STOP</button>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        
        socket.on('connect', () => {
            document.getElementById('status').textContent = 'Conectado';
        });
        
        socket.on('disconnect', () => {
            document.getElementById('status').textContent = 'Desconectado';
        });
        
        socket.on('state_update', (state) => {
            document.getElementById('mode').textContent = state.mode;
            if (state.sensors.battery_v) {
                document.getElementById('battery').textContent = state.sensors.battery_v.toFixed(1);
            }
        });
        
        function drive(vx, vy, vz) {
            socket.emit('command', {
                cmd: 'drive',
                params: { vx, vy, vz }
            });
        }
        
        function stop() {
            socket.emit('command', { cmd: 'stop' });
        }
        
        function estop() {
            socket.emit('command', { cmd: 'estop' });
        }
        
        // Heartbeat a cada 1s
        setInterval(() => {
            socket.emit('command', { cmd: 'heartbeat' });
        }, 1000);
    </script>
</body>
</html>"""
    
    (template_dir / 'control.html').write_text(html, encoding='utf-8')
    print(f"✅ Template criado em {template_dir / 'control.html'}")


# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

def init_server(robot_core, camera_system, safety_controller):
    """Inicializa servidor"""
    global robot_server
    
    robot_server = RobotServer(robot_core, camera_system, safety_controller)
    robot_server.start_broadcast()
    
    # Criar template HTML
    create_html_template()
    
    return robot_server


def run_server(host='0.0.0.0', port=5000):
    """Roda servidor Flask+SocketIO"""
    print(f"\n🚀 Servidor iniciando em {host}:{port}")
    print(f"📱 Acesse: http://<IP_DO_RASPBERRY>:{port}\n")
    
    socketio.run(
        app,
        host=host,
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )