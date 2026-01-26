#!/usr/bin/env python3
"""
EVA FLASK SERVER - Sistema Dual de Câmeras Inteligente
✅ CORRIGIDO: Controles de movimento
✅ NOVO: Troca automática de câmeras
   - USB REDRAGON → Navegação (movimento do carro)
   - Pi Camera → Quando braço/cabeça se move

RODE NO RASPBERRY PI:
    python3 eva_flask_server.py

ACESSE DO PC:
    http://<IP_DO_RASPBERRY>:5000
"""

from flask import Flask, render_template, Response, jsonify
from flask_socketio import SocketIO, emit
import cv2
import time
import threading
import numpy as np
from pathlib import Path
import sys

# Hardware do robô
HARDWARE_PATH = Path(__file__).parent / 'hardware'
sys.path.insert(0, str(HARDWARE_PATH))

try:
    from motor import Ordinary_Car
    MOTOR_OK = True
except:
    MOTOR_OK = False
    print("⚠️ Motor não disponível")

try:
    from picamera2 import Picamera2
    PICAM_OK = True
except:
    PICAM_OK = False
    print("⚠️ PiCamera2 não disponível")

try:
    from arm_calibration import ArmController
    ARM_OK = True
except:
    ARM_OK = False
    print("⚠️ Braço não disponível")

# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'eva-robot-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==========================================
# SISTEMA DUAL DE CÂMERAS
# ==========================================

class DualCameraSystem:
    """
    Sistema inteligente com 2 câmeras:
    
    📹 USB REDRAGON → Navegação (movimento do carro)
    📷 Pi Camera → Manipulação (braço/cabeça ativa)
    
    Troca automática:
    - Movimento do carro → USB
    - Movimento do braço → Pi Camera
    - 3s sem movimento do braço → volta pra USB
    """
    
    def __init__(self):
        self.usb_camera = None
        self.pi_camera = None
        
        self.active_camera = "usb"  # Padrão: navegação
        self.running = False
        self.frame = None
        self.lock = threading.Lock()
        
        # Auto-switch
        self.last_arm_move_time = 0.0
        self.arm_idle_timeout = 3.0  # 3s sem mexer braço → volta USB
        
        print("\n📷 Inicializando sistema dual de câmeras...")
        self._init_cameras()
    
    def _init_cameras(self):
        """Inicializa ambas as câmeras"""
        
        # 1. USB REDRAGON (navegação)
        try:
            print("  🔧 Inicializando USB REDRAGON...")
            
            cap = cv2.VideoCapture(1)  # /dev/video1
            
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 15)
                
                ret, test_frame = cap.read()
                
                if ret and test_frame is not None:
                    self.usb_camera = cap
                    print("  ✅ USB REDRAGON OK (navegação)")
                else:
                    cap.release()
                    print("  ❌ USB não captura")
            else:
                print("  ❌ USB não abre")
        
        except Exception as e:
            print(f"  ❌ USB falhou: {e}")
        
        # 2. Pi Camera (braço/cabeça) - NÃO INICIA ainda
        if PICAM_OK:
            try:
                print("  🔧 Configurando Pi Camera...")
                
                self.pi_camera = Picamera2()
                
                config = self.pi_camera.create_preview_configuration(
                    main={"size": (640, 480), "format": "RGB888"}
                )
                
                self.pi_camera.configure(config)
                
                print("  ✅ Pi Camera configurada (ov5647)")
                # NÃO inicia ainda - só quando necessário
            
            except Exception as e:
                print(f"  ❌ Pi Camera falhou: {e}")
                self.pi_camera = None
    
    def start(self):
        """Inicia sistema de streaming"""
        if not self.usb_camera and not self.pi_camera:
            print("❌ Nenhuma câmera disponível")
            return False
        
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._auto_switch_loop, daemon=True).start()
        
        print(f"✅ Sistema dual iniciado (ativa: {self.active_camera.upper()})")
        return True
    
    def _capture_loop(self):
        """Loop de captura da câmera ativa"""
        print("📹 Loop de captura rodando...")
        
        frame_count = 0
        last_fps_time = time.time()
        
        pi_cam_active = False  # Estado da Pi Camera
        
        while self.running:
            try:
                frame = None
                
                # Decidir qual câmera usar
                if self.active_camera == "picam" and self.pi_camera:
                    # Pi Camera
                    
                    # Iniciar se necessário
                    if not pi_cam_active:
                        try:
                            self.pi_camera.start()
                            time.sleep(1.0)  # Estabilizar
                            pi_cam_active = True
                            print("📷 Pi Camera ATIVADA")
                        except Exception as e:
                            print(f"❌ Erro ao iniciar Pi Camera: {e}")
                            self.active_camera = "usb"  # Fallback
                            continue
                    
                    # Capturar
                    try:
                        frame = self.pi_camera.capture_array()
                        
                        if frame is not None and len(frame.shape) == 3:
                            # RGB → BGR
                            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    except Exception as e:
                        print(f"⚠️ Erro captura Pi Camera: {e}")
                
                else:
                    # USB Camera
                    
                    # Parar Pi Camera se estava ativa
                    if pi_cam_active:
                        try:
                            self.pi_camera.stop()
                            pi_cam_active = False
                            print("📹 Voltando para USB REDRAGON")
                        except:
                            pass
                    
                    # Capturar USB
                    if self.usb_camera and self.usb_camera.isOpened():
                        ret, frame = self.usb_camera.read()
                        
                        if not ret or frame is None:
                            frame = None
                
                # Salvar frame
                if frame is not None:
                    with self.lock:
                        self.frame = frame
                    
                    # FPS counter
                    frame_count += 1
                    if frame_count % 30 == 0:
                        now = time.time()
                        fps = 30 / (now - last_fps_time)
                        print(f"📊 {self.active_camera.upper()}: {fps:.1f} FPS | {frame_count} frames")
                        last_fps_time = now
                
                time.sleep(0.033)  # ~30 FPS
            
            except Exception as e:
                print(f"❌ Erro no loop: {e}")
                time.sleep(1.0)
        
        # Cleanup ao sair
        if pi_cam_active and self.pi_camera:
            try:
                self.pi_camera.stop()
            except:
                pass
    
    def _auto_switch_loop(self):
        """Loop que verifica timeout do braço"""
        while self.running:
            try:
                # Se está em modo Pi Camera
                if self.active_camera == "picam":
                    # Verificar timeout
                    idle_time = time.time() - self.last_arm_move_time
                    
                    if idle_time >= self.arm_idle_timeout:
                        # Voltar para USB
                        print(f"⏰ Braço parado por {idle_time:.1f}s → USB")
                        self.active_camera = "usb"
                
                time.sleep(0.5)
            
            except Exception as e:
                print(f"❌ Erro auto-switch: {e}")
                time.sleep(1.0)
    
    def switch_to_arm_camera(self):
        """Troca para Pi Camera (braço movendo)"""
        if self.pi_camera and self.active_camera != "picam":
            print("🔄 Trocando para Pi Camera (braço ativo)")
            self.active_camera = "picam"
        
        # Atualizar timestamp
        self.last_arm_move_time = time.time()
    
    def switch_to_navigation(self):
        """Troca para USB (navegação)"""
        if self.usb_camera and self.active_camera != "usb":
            print("🔄 Trocando para USB REDRAGON (navegação)")
            self.active_camera = "usb"
    
    def get_frame(self):
        """Retorna último frame"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def get_status(self):
        """Status do sistema"""
        return {
            "active": self.active_camera.upper(),
            "usb_available": self.usb_camera is not None,
            "picam_available": self.pi_camera is not None
        }
    
    def stop(self):
        """Para sistema"""
        print("⏹️ Parando sistema de câmeras...")
        self.running = False
        
        time.sleep(1.0)
        
        if self.pi_camera:
            try:
                self.pi_camera.stop()
                self.pi_camera.close()
            except:
                pass
        
        if self.usb_camera:
            try:
                self.usb_camera.release()
            except:
                pass
        
        print("✅ Câmeras paradas")


# ==========================================
# CONTROLADOR DO ROBÔ
# ==========================================

class RobotController:
    """Controlador completo: Motor + Braço"""
    
    def __init__(self, camera_system):
        self.camera_system = camera_system
        self.motor = None
        self.arm = None
        self.speed = 1500
        
        # Motor
        if MOTOR_OK:
            try:
                self.motor = Ordinary_Car()
                print("✅ Motor inicializado")
            except Exception as e:
                print(f"❌ Motor falhou: {e}")
        
        # Braço
        if ARM_OK:
            try:
                self.arm = ArmController(enable_gripper=False, min_delay=0.15)
                print("✅ Braço inicializado (modo cabeça)")
            except Exception as e:
                print(f"❌ Braço falhou: {e}")
    
    def drive(self, vx=0.0, vy=0.0, vz=0.0):
        """
        Movimento do carro
        
        ✅ CORRIGIDO: Esquerda/Direita invertidos
        """
        if not self.motor:
            return {"status": "error", "error": "Motor não disponível"}
        
        # Trocar para câmera de navegação
        self.camera_system.switch_to_navigation()
        
        # Converter para PWM
        max_pwm = self.speed
        
        # Cinemática mecanum
        fl = int((vx + vy + vz) * max_pwm)
        bl = int((vx - vy + vz) * max_pwm)
        fr = int((vx - vy - vz) * max_pwm)
        br = int((vx + vy - vz) * max_pwm)
        
        # INVERTER TUDO (motores invertidos fisicamente)
        fl, bl, fr, br = -fl, -bl, -fr, -br
        
        # INVERTER ESQUERDA/DIREITA
        # Trocar FL↔FR e BL↔BR
        fl, fr = fr, fl
        bl, br = br, bl
        
        # Aplicar
        try:
            self.motor.set_motor_model(fl, bl, fr, br)
            return {
                "status": "ok",
                "motors": [fl, bl, fr, br],
                "vx": vx, "vy": vy, "vz": vz
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def move_head(self, yaw=None, pitch=None):
        """
        Move cabeça (braço)
        
        Automaticamente troca para Pi Camera
        """
        if not self.arm:
            return {"status": "error", "error": "Braço não disponível"}
        
        # Trocar para câmera do braço
        self.camera_system.switch_to_arm_camera()
        
        results = []
        
        # Yaw (base - servo 0)
        if yaw is not None:
            try:
                ok = self.arm.move_smooth(0, yaw, step=2, step_delay=0.02)
                results.append({"servo": "yaw", "angle": yaw, "success": ok})
            except Exception as e:
                results.append({"servo": "yaw", "error": str(e)})
        
        # Pitch (ombro - servo 1)
        if pitch is not None:
            try:
                ok = self.arm.move_smooth(1, pitch, step=2, step_delay=0.02)
                results.append({"servo": "pitch", "angle": pitch, "success": ok})
            except Exception as e:
                results.append({"servo": "pitch", "error": str(e)})
        
        return {
            "status": "ok",
            "results": results,
            "camera": "picam"
        }
    
    def stop(self):
        """Para tudo"""
        if self.motor:
            try:
                self.motor.set_motor_model(0, 0, 0, 0)
            except:
                pass
        
        return {"status": "ok"}
    
    def cleanup(self):
        """Cleanup"""
        self.stop()
        
        if self.motor:
            try:
                self.motor.close()
            except:
                pass
        
        if self.arm:
            try:
                self.arm.cleanup()
            except:
                pass


# ==========================================
# INSTÂNCIAS GLOBAIS
# ==========================================

camera_system = DualCameraSystem()
robot = RobotController(camera_system)

# ==========================================
# ROTAS FLASK
# ==========================================

@app.route('/')
def index():
    return render_template('control.html')

@app.route('/status')
def status():
    cam_status = camera_system.get_status()
    
    return jsonify({
        'camera_active': cam_status['active'],
        'camera_usb': cam_status['usb_available'],
        'camera_picam': cam_status['picam_available'],
        'motor': 'OK' if robot.motor else 'Não disponível',
        'arm': 'OK' if robot.arm else 'Não disponível',
        'time': time.time()
    })

def generate_video():
    """Gerador MJPEG"""
    while True:
        frame = camera_system.get_frame()
        
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Aguardando camera...", (150, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Badge mostrando câmera ativa
        cam_text = camera_system.active_camera.upper()
        color = (0, 255, 0) if cam_text == "USB" else (255, 100, 255)
        
        cv2.rectangle(frame, (10, 10), (150, 50), (0, 0, 0), -1)
        cv2.putText(frame, cam_text, (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
        
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.033)

@app.route('/video_feed')
def video_feed():
    return Response(
        generate_video(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# ==========================================
# WEBSOCKET
# ==========================================

@socketio.on('connect')
def handle_connect():
    print("🔗 Cliente conectado")
    
    cam_status = camera_system.get_status()
    
    emit('welcome', {
        'message': 'Conectado ao EVA Robot',
        'camera': cam_status['active'],
        'motor': 'OK' if robot.motor else 'Não disponível',
        'arm': 'OK' if robot.arm else 'Não disponível'
    })

@socketio.on('disconnect')
def handle_disconnect():
    print("🔌 Cliente desconectado")
    robot.stop()

@socketio.on('command')
def handle_command(data):
    cmd = data.get('cmd')
    params = data.get('params', {})
    
    print(f"📨 CMD: {cmd} {params}")
    
    if cmd == 'drive':
        result = robot.drive(
            vx=params.get('vx', 0),
            vy=params.get('vy', 0),
            vz=params.get('vz', 0)
        )
    
    elif cmd == 'head':
        result = robot.move_head(
            yaw=params.get('yaw'),
            pitch=params.get('pitch')
        )
    
    elif cmd == 'stop':
        result = robot.stop()
    
    else:
        result = {"status": "error", "error": f"Comando desconhecido: {cmd}"}
    
    # Incluir status da câmera
    result['camera'] = camera_system.active_camera
    
    emit('response', result)

# ==========================================
# TEMPLATE HTML
# ==========================================

TEMPLATE_DIR = Path(__file__).parent / 'templates'
TEMPLATE_DIR.mkdir(exist_ok=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>EVA Robot Control - Dual Camera</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            color: white;
        }
        
        .header {
            background: rgba(0,0,0,0.3);
            padding: 15px;
            text-align: center;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }
        
        .header h1 {
            font-size: 28px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .status {
            font-size: 14px;
            margin-top: 5px;
            opacity: 0.8;
        }
        
        .container {
            flex: 1;
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
        }
        
        .video-panel {
            background: rgba(0,0,0,0.4);
            border-radius: 12px;
            padding: 15px;
            display: flex;
            flex-direction: column;
        }
        
        .video-panel h2 {
            margin-bottom: 15px;
            font-size: 20px;
        }
        
        #camera-feed {
            width: 100%;
            border-radius: 8px;
            background: #000;
            aspect-ratio: 4/3;
            object-fit: contain;
        }
        
        .control-panel {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        
        .control-section {
            background: rgba(0,0,0,0.4);
            border-radius: 12px;
            padding: 20px;
        }
        
        .control-section h3 {
            margin-bottom: 15px;
            font-size: 18px;
            border-bottom: 2px solid rgba(255,255,255,0.2);
            padding-bottom: 8px;
        }
        
        .btn-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 15px;
        }
        
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: none;
            border-radius: 8px;
            padding: 15px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            user-select: none;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.3);
        }
        
        .btn:active {
            transform: translateY(0);
            background: linear-gradient(135deg, #564ba2 0%, #667eea 100%);
        }
        
        .btn-stop {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            grid-column: span 3;
            font-size: 18px;
            padding: 20px;
        }
        
        .head-sliders {
            margin-top: 15px;
        }
        
        .slider-group {
            margin-bottom: 15px;
        }
        
        .slider-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
        }
        
        .slider-group input {
            width: 100%;
            height: 8px;
            border-radius: 4px;
            background: rgba(255,255,255,0.2);
        }
        
        .slider-value {
            text-align: center;
            margin-top: 5px;
            font-size: 18px;
            font-weight: 700;
        }
        
        .speed-control {
            margin-top: 15px;
        }
        
        .speed-control label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
        }
        
        .speed-control input {
            width: 100%;
            height: 8px;
            border-radius: 4px;
            background: rgba(255,255,255,0.2);
        }
        
        .speed-value {
            text-align: center;
            margin-top: 8px;
            font-size: 24px;
            font-weight: 700;
        }
        
        .info-panel {
            background: rgba(0,0,0,0.4);
            border-radius: 12px;
            padding: 15px;
            font-size: 14px;
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        .info-row:last-child { border-bottom: none; }
        
        .connected { color: #4ade80; }
        .disconnected { color: #f87171; }
        
        @media (max-width: 968px) {
            .container { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 EVA Robot - Dual Camera System</h1>
        <div class="status">
            Status: <span id="connection-status" class="disconnected">Desconectado</span> | 
            Câmera: <span id="camera-active">-</span>
        </div>
    </div>
    
    <div class="container">
        <div class="video-panel">
            <h2>📹 Camera Feed (auto-switch)</h2>
            <img id="camera-feed" src="/video_feed" alt="Camera Feed">
        </div>
        
        <div class="control-panel">
            <!-- Movimento -->
            <div class="control-section">
                <h3>🚗 Movimento (USB Camera)</h3>
                
                <div class="btn-grid">
                    <div></div>
                    <button class="btn" id="btn-forward">↑<br>Frente</button>
                    <div></div>
                    
                    <button class="btn" id="btn-left">←<br>Esquerda</button>
                    <button class="btn btn-stop" id="btn-stop">⏹<br>PARAR</button>
                    <button class="btn" id="btn-right">→<br>Direita</button>
                    
                    <div></div>
                    <button class="btn" id="btn-backward">↓<br>Ré</button>
                    <div></div>
                </div>
                
                <div class="speed-control">
                    <label>⚡ Velocidade</label>
                    <input type="range" id="speed-slider" min="500" max="3000" value="1500" step="100">
                    <div class="speed-value"><span id="speed-value">1500</span> PWM</div>
                </div>
            </div>
            
            <!-- Cabeça -->
            <div class="control-section">
                <h3>🦾 Cabeça (Pi Camera)</h3>
                
                <div class="head-sliders">
                    <div class="slider-group">
                        <label>Yaw (Base)</label>
                        <input type="range" id="head-yaw" min="0" max="180" value="90">
                        <div class="slider-value"><span id="yaw-value">90</span>°</div>
                    </div>
                    
                    <div class="slider-group">
                        <label>Pitch (Ombro)</label>
                        <input type="range" id="head-pitch" min="0" max="180" value="90">
                        <div class="slider-value"><span id="pitch-value">90</span>°</div>
                    </div>
                </div>
            </div>
            
            <!-- Info -->
            <div class="info-panel">
                <div class="info-row">
                    <span>Câmera Ativa:</span>
                    <span id="info-camera">-</span>
                </div>
                <div class="info-row">
                    <span>Motor:</span>
                    <span id="info-motor">-</span>
                </div>
                <div class="info-row">
                    <span>Braço:</span>
                    <span id="info-arm">-</span>
                </div>
                <div class="info-row">
                    <span>Último comando:</span>
                    <span id="info-last-cmd">-</span>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        let speed = 1500;
        
        socket.on('connect', () => {
            console.log('✅ Conectado');
            document.getElementById('connection-status').textContent = 'Conectado';
            document.getElementById('connection-status').className = 'connected';
        });
        
        socket.on('disconnect', () => {
            console.log('❌ Desconectado');
            document.getElementById('connection-status').textContent = 'Desconectado';
            document.getElementById('connection-status').className = 'disconnected';
        });
        
        socket.on('welcome', (data) => {
            console.log('Welcome:', data);
            document.getElementById('info-motor').textContent = data.motor;
            document.getElementById('info-arm').textContent = data.arm;
            document.getElementById('camera-active').textContent = data.camera;
        });
        
        socket.on('response', (data) => {
            console.log('Response:', data);
            if (data.camera) {
                document.getElementById('camera-active').textContent = data.camera.toUpperCase();
                document.getElementById('info-camera').textContent = data.camera.toUpperCase();
            }
        });
        
        function sendCommand(cmd, params = {}) {
            socket.emit('command', { cmd, params });
            document.getElementById('info-last-cmd').textContent = cmd;
        }
        
        function drive(vx = 0, vy = 0, vz = 0) {
            const factor = speed / 1500;
            sendCommand('drive', {
                vx: vx * factor,
                vy: vy * factor,
                vz: vz * factor
            });
        }
        
        function stop() {
            sendCommand('stop');
        }
        
        function moveHead(yaw, pitch) {
            sendCommand('head', { yaw, pitch });
        }
        
        // Botões de movimento
        const btns = [
            ['btn-forward', () => drive(1, 0, 0)],
            ['btn-backward', () => drive(-1, 0, 0)],
            ['btn-left', () => drive(0, 0, 1)],
            ['btn-right', () => drive(0, 0, -1)]
        ];
        
        btns.forEach(([id, fn]) => {
            const btn = document.getElementById(id);
            btn.addEventListener('mousedown', fn);
            btn.addEventListener('touchstart', fn);
            btn.addEventListener('mouseup', stop);
            btn.addEventListener('touchend', stop);
            btn.addEventListener('mouseleave', stop);
        });
        
        document.getElementById('btn-stop').addEventListener('click', stop);
        
        // Slider de velocidade
        const speedSlider = document.getElementById('speed-slider');
        const speedValue = document.getElementById('speed-value');
        
        speedSlider.addEventListener('input', (e) => {
            speed = parseInt(e.target.value);
            speedValue.textContent = speed;
        });
        
        // Sliders de cabeça
        const yawSlider = document.getElementById('head-yaw');
        const pitchSlider = document.getElementById('head-pitch');
        const yawValue = document.getElementById('yaw-value');
        const pitchValue = document.getElementById('pitch-value');
        
        yawSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            yawValue.textContent = val;
            moveHead(val, parseInt(pitchSlider.value));
        });
        
        pitchSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            pitchValue.textContent = val;
            moveHead(parseInt(yawSlider.value), val);
        });
        
        // Teclado
        let keyPressed = {};
        
        document.addEventListener('keydown', (e) => {
            if (keyPressed[e.key]) return;
            keyPressed[e.key] = true;
            
            switch(e.key.toLowerCase()) {
                case 'w': drive(1, 0, 0); break;
                case 's': drive(-1, 0, 0); break;
                case 'a': drive(0, 0, 1); break;
                case 'd': drive(0, 0, -1); break;
                case ' ': stop(); e.preventDefault(); break;
            }
        });
        
        document.addEventListener('keyup', (e) => {
            keyPressed[e.key] = false;
            if (['w', 's', 'a', 'd'].includes(e.key.toLowerCase())) {
                stop();
            }
        });
        
        // Status periódico
        setInterval(() => {
            fetch('/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('info-camera').textContent = data.camera_active;
                    document.getElementById('camera-active').textContent = data.camera_active;
                    document.getElementById('info-motor').textContent = data.motor;
                    document.getElementById('info-arm').textContent = data.arm;
                })
                .catch(() => {});
        }, 2000);
    </script>
</body>
</html>
"""

(TEMPLATE_DIR / 'control.html').write_text(HTML_TEMPLATE, encoding='utf-8')

# ==========================================
# MAIN
# ==========================================

def main():
    print("\n" + "="*60)
    print("🤖 EVA FLASK SERVER - DUAL CAMERA SYSTEM")
    print("="*60)
    print("\nSistema de Câmeras:")
    print("  📹 USB REDRAGON → Navegação")
    print("  📷 Pi Camera → Braço/Cabeça")
    print("  🔄 Troca automática inteligente")
    print("\nRecursos:")
    print(f"  🚗 Motor: {'OK' if robot.motor else 'Não disponível'}")
    print(f"  🦾 Braço: {'OK' if robot.arm else 'Não disponível'}")
    print("\n" + "="*60)
    
    # Iniciar câmeras
    if not camera_system.start():
        print("⚠️ Sistema de câmeras não iniciou completamente")
    
    # Iniciar servidor
    try:
        print("\n🚀 Servidor iniciando...")
        print("   Porta: 5000")
        print("\n📱 Acesse:")
        print("   http://<IP_DO_RASPBERRY>:5000")
        print("\n💡 Controles:")
        print("   • Movimento: WASD ou botões (USB Camera)")
        print("   • Cabeça: Sliders Yaw/Pitch (Pi Camera)")
        print("   • Auto-switch: 3s parado → volta USB")
        print("\n" + "="*60 + "\n")
        
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Ctrl+C detectado")
    
    finally:
        print("\n🔧 Encerrando...")
        camera_system.stop()
        robot.cleanup()
        print("✅ Servidor encerrado\n")


if __name__ == '__main__':
    main()