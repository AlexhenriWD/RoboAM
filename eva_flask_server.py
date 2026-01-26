#!/usr/bin/env python3
"""
EVA FLASK SERVER - Sistema Completo
✅ Dual camera com rotação da Pi Camera
✅ Controle completo do braço (5 servos)
✅ Seletor manual de câmera (USB/Pi/Auto)

RODE NO RASPBERRY PI:
    python3 eva_flask_server.py
"""

from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit
import cv2
import time
import threading
import numpy as np
from pathlib import Path
import sys

# Hardware
HARDWARE_PATH = Path(__file__).parent / 'hardware'
sys.path.insert(0, str(HARDWARE_PATH))

try:
    from motor import Ordinary_Car
    MOTOR_OK = True
except:
    MOTOR_OK = False

try:
    from picamera2 import Picamera2
    PICAM_OK = True
except:
    PICAM_OK = False

try:
    from arm_calibration import ArmController
    ARM_OK = True
except:
    ARM_OK = False

# ==========================================
# FLASK
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'eva-robot-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==========================================
# SISTEMA DUAL DE CÂMERAS
# ==========================================

class DualCameraSystem:
    """
    Sistema dual inteligente
    
    Modos:
    - AUTO: Troca automática (navegação → USB, braço → Pi)
    - USB: Força USB sempre
    - PICAM: Força Pi Camera sempre
    """
    
    def __init__(self):
        self.usb_camera = None
        self.pi_camera = None
        
        # Modos: "auto", "usb", "picam"
        self.mode = "auto"
        self.active_camera = "usb"
        
        self.running = False
        self.frame = None
        self.lock = threading.Lock()
        
        # Auto-switch
        self.last_arm_move_time = 0.0
        self.arm_idle_timeout = 3.0
        
        # Rotação da Pi Camera (90° = lateral direita)
        self.picam_rotation = 90  # 0, 90, 180, 270
        
        print("\n📷 Inicializando câmeras...")
        self._init_cameras()
    
    def _init_cameras(self):
        """Inicializa ambas"""
        
        # USB REDRAGON
        try:
            print("  🔧 USB REDRAGON...")
            cap = cv2.VideoCapture(1)
            
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 15)
                
                ret, test = cap.read()
                if ret and test is not None:
                    self.usb_camera = cap
                    print("  ✅ USB OK")
                else:
                    cap.release()
        except Exception as e:
            print(f"  ❌ USB: {e}")
        
        # Pi Camera
        if PICAM_OK:
            try:
                print("  🔧 Pi Camera...")
                self.pi_camera = Picamera2()
                
                config = self.pi_camera.create_preview_configuration(
                    main={"size": (640, 480), "format": "RGB888"}
                )
                
                self.pi_camera.configure(config)
                print("  ✅ Pi Camera OK")
            except Exception as e:
                print(f"  ❌ Pi Camera: {e}")
                self.pi_camera = None
    
    def start(self):
        """Inicia sistema"""
        if not self.usb_camera and not self.pi_camera:
            print("❌ Nenhuma câmera")
            return False
        
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._auto_switch_loop, daemon=True).start()
        
        print(f"✅ Sistema iniciado (modo: {self.mode.upper()})")
        return True
    
    def _capture_loop(self):
        """Loop de captura"""
        pi_cam_active = False
        
        while self.running:
            try:
                frame = None
                
                # Decidir câmera (respeitar modo manual)
                if self.mode == "usb":
                    target = "usb"
                elif self.mode == "picam":
                    target = "picam"
                else:
                    target = self.active_camera  # Auto
                
                # Pi Camera
                if target == "picam" and self.pi_camera:
                    if not pi_cam_active:
                        try:
                            self.pi_camera.start()
                            time.sleep(1.0)
                            pi_cam_active = True
                            print("📷 Pi Camera ATIVADA")
                        except Exception as e:
                            print(f"❌ Erro Pi Camera: {e}")
                            target = "usb"
                    
                    if pi_cam_active:
                        try:
                            frame = self.pi_camera.capture_array()
                            
                            if frame is not None and len(frame.shape) == 3:
                                # RGB → BGR
                                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                                
                                # ROTACIONAR (corrigir orientação física)
                                if self.picam_rotation == 90:
                                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                                elif self.picam_rotation == 180:
                                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                                elif self.picam_rotation == 270:
                                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                        except Exception as e:
                            print(f"⚠️ Erro captura Pi: {e}")
                
                # USB Camera
                else:
                    if pi_cam_active:
                        try:
                            self.pi_camera.stop()
                            pi_cam_active = False
                            print("📹 Voltando USB")
                        except:
                            pass
                    
                    if self.usb_camera and self.usb_camera.isOpened():
                        ret, frame = self.usb_camera.read()
                        if not ret:
                            frame = None
                
                # Salvar frame
                if frame is not None:
                    with self.lock:
                        self.frame = frame
                
                time.sleep(0.033)
            
            except Exception as e:
                print(f"❌ Loop erro: {e}")
                time.sleep(1.0)
        
        # Cleanup
        if pi_cam_active and self.pi_camera:
            try:
                self.pi_camera.stop()
            except:
                pass
    
    def _auto_switch_loop(self):
        """Auto-switch (só funciona em modo AUTO)"""
        while self.running:
            try:
                if self.mode == "auto":
                    if self.active_camera == "picam":
                        idle = time.time() - self.last_arm_move_time
                        
                        if idle >= self.arm_idle_timeout:
                            print(f"⏰ Braço parado {idle:.1f}s → USB")
                            self.active_camera = "usb"
                
                time.sleep(0.5)
            except:
                time.sleep(1.0)
    
    def set_mode(self, mode):
        """Define modo: auto/usb/picam"""
        if mode in ["auto", "usb", "picam"]:
            self.mode = mode
            print(f"🎥 Modo: {mode.upper()}")
            return True
        return False
    
    def switch_to_arm_camera(self):
        """Ativa Pi Camera (se auto)"""
        if self.mode == "auto":
            if self.active_camera != "picam":
                print("🔄 → Pi Camera (braço)")
                self.active_camera = "picam"
        
        self.last_arm_move_time = time.time()
    
    def switch_to_navigation(self):
        """Ativa USB (se auto)"""
        if self.mode == "auto":
            if self.active_camera != "usb":
                print("🔄 → USB (navegação)")
                self.active_camera = "usb"
    
    def get_frame(self):
        """Retorna frame"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def get_status(self):
        """Status"""
        # Câmera atual (respeitando modo)
        if self.mode == "usb":
            current = "USB (forçado)"
        elif self.mode == "picam":
            current = "PICAM (forçado)"
        else:
            current = self.active_camera.upper() + " (auto)"
        
        return {
            "mode": self.mode,
            "active": current,
            "usb_available": self.usb_camera is not None,
            "picam_available": self.pi_camera is not None
        }
    
    def stop(self):
        """Para tudo"""
        print("⏹️ Parando câmeras...")
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


# ==========================================
# CONTROLADOR COMPLETO
# ==========================================

class RobotController:
    """Motor + Braço completo (5 servos)"""
    
    def __init__(self, camera_system):
        self.camera_system = camera_system
        self.motor = None
        self.arm = None
        self.speed = 1500
        
        # Posições atuais do braço
        self.arm_positions = {
            0: 90,  # Base
            1: 90,  # Ombro
            2: 90,  # Cotovelo
            3: 90,  # Pulso
            4: 90   # Garra
        }
        
        # Motor
        if MOTOR_OK:
            try:
                self.motor = Ordinary_Car()
                print("✅ Motor OK")
            except Exception as e:
                print(f"❌ Motor: {e}")
        
        # Braço
        if ARM_OK:
            try:
                self.arm = ArmController(enable_gripper=True, min_delay=0.15)
                print("✅ Braço OK (5 servos)")
            except Exception as e:
                print(f"❌ Braço: {e}")
    
    def drive(self, vx=0.0, vy=0.0, vz=0.0):
        """Movimento (CORRIGIDO)"""
        if not self.motor:
            return {"status": "error", "error": "Motor não disponível"}
        
        self.camera_system.switch_to_navigation()
        
        max_pwm = self.speed
        
        # Mecanum
        fl = int((vx + vy + vz) * max_pwm)
        bl = int((vx - vy + vz) * max_pwm)
        fr = int((vx - vy - vz) * max_pwm)
        br = int((vx + vy - vz) * max_pwm)
        
        # Inverter tudo
        fl, bl, fr, br = -fl, -bl, -fr, -br
        
        # Trocar esquerda/direita
        fl, fr = fr, fl
        bl, br = br, bl
        
        try:
            self.motor.set_motor_model(fl, bl, fr, br)
            return {"status": "ok", "motors": [fl, bl, fr, br]}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def move_servo(self, servo_id, angle):
        """
        Move servo individual
        
        Args:
            servo_id: 0=Base, 1=Ombro, 2=Cotovelo, 3=Pulso, 4=Garra
            angle: 0-180
        """
        if not self.arm:
            return {"status": "error", "error": "Braço não disponível"}
        
        # Ativar Pi Camera
        self.camera_system.switch_to_arm_camera()
        
        try:
            # Movimento suave
            ok = self.arm.move_smooth(servo_id, angle, step=2, step_delay=0.02)
            
            if ok:
                self.arm_positions[servo_id] = angle
                
                return {
                    "status": "ok",
                    "servo": servo_id,
                    "angle": angle,
                    "positions": self.arm_positions.copy()
                }
            else:
                return {"status": "error", "error": "Movimento falhou"}
        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def stop(self):
        """Para motores"""
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
# INSTÂNCIAS
# ==========================================

camera_system = DualCameraSystem()
robot = RobotController(camera_system)

# ==========================================
# ROTAS
# ==========================================

@app.route('/')
def index():
    return render_template('control.html')

@app.route('/status')
def status():
    cam = camera_system.get_status()
    
    return jsonify({
        'camera_mode': cam['mode'],
        'camera_active': cam['active'],
        'camera_usb': cam['usb_available'],
        'camera_picam': cam['picam_available'],
        'motor': 'OK' if robot.motor else 'Não disponível',
        'arm': 'OK' if robot.arm else 'Não disponível',
        'arm_positions': robot.arm_positions,
        'time': time.time()
    })

@app.route('/camera/mode/<mode>')
def set_camera_mode(mode):
    """Troca modo de câmera"""
    if camera_system.set_mode(mode):
        return jsonify({"status": "ok", "mode": mode})
    else:
        return jsonify({"status": "error", "error": "Modo inválido"})

def generate_video():
    """Gerador MJPEG"""
    while True:
        frame = camera_system.get_frame()
        
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Aguardando...", (200, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Badge
        mode = camera_system.mode.upper()
        active = "USB" if "USB" in camera_system.get_status()['active'] else "PICAM"
        
        if mode == "AUTO":
            text = f"{active} (auto)"
            color = (0, 255, 0) if active == "USB" else (255, 100, 255)
        else:
            text = f"{active} (manual)"
            color = (255, 200, 0)
        
        cv2.rectangle(frame, (10, 10), (200, 50), (0, 0, 0), -1)
        cv2.putText(frame, text, (20, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.033)

@app.route('/video_feed')
def video_feed():
    return Response(generate_video(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

# ==========================================
# WEBSOCKET
# ==========================================

@socketio.on('connect')
def handle_connect():
    print("🔗 Cliente conectado")
    
    cam = camera_system.get_status()
    
    emit('welcome', {
        'message': 'EVA Robot conectado',
        'camera_mode': cam['mode'],
        'camera_active': cam['active'],
        'motor': 'OK' if robot.motor else 'Não',
        'arm': 'OK' if robot.arm else 'Não',
        'arm_positions': robot.arm_positions
    })

@socketio.on('disconnect')
def handle_disconnect():
    print("🔌 Desconectado")
    robot.stop()

@socketio.on('command')
def handle_command(data):
    cmd = data.get('cmd')
    params = data.get('params', {})
    
    print(f"📨 {cmd} {params}")
    
    if cmd == 'drive':
        result = robot.drive(
            vx=params.get('vx', 0),
            vy=params.get('vy', 0),
            vz=params.get('vz', 0)
        )
    
    elif cmd == 'servo':
        result = robot.move_servo(
            servo_id=params.get('servo'),
            angle=params.get('angle')
        )
    
    elif cmd == 'camera_mode':
        mode = params.get('mode', 'auto')
        if camera_system.set_mode(mode):
            result = {"status": "ok", "mode": mode}
        else:
            result = {"status": "error", "error": "Modo inválido"}
    
    elif cmd == 'stop':
        result = robot.stop()
    
    else:
        result = {"status": "error", "error": f"Comando desconhecido: {cmd}"}
    
    emit('response', result)

# ==========================================
# HTML TEMPLATE
# ==========================================

TEMPLATE_DIR = Path(__file__).parent / 'templates'
TEMPLATE_DIR.mkdir(exist_ok=True)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>EVA Robot - Full Control</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            color: white;
            padding: 20px;
        }
        
        .header {
            background: rgba(0,0,0,0.3);
            padding: 15px;
            border-radius: 12px;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        
        .status-bar {
            display: flex;
            gap: 20px;
            justify-content: center;
            flex-wrap: wrap;
            font-size: 14px;
        }
        
        .status-item {
            background: rgba(0,0,0,0.2);
            padding: 5px 15px;
            border-radius: 20px;
        }
        
        .container {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            max-width: 1600px;
            margin: 0 auto;
        }
        
        .panel {
            background: rgba(0,0,0,0.4);
            border-radius: 12px;
            padding: 20px;
        }
        
        .panel h2 {
            font-size: 20px;
            margin-bottom: 15px;
            border-bottom: 2px solid rgba(255,255,255,0.2);
            padding-bottom: 10px;
        }
        
        #camera-feed {
            width: 100%;
            border-radius: 8px;
            background: #000;
        }
        
        .controls {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        
        .btn-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
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
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.3);
        }
        
        .btn:active {
            transform: translateY(0);
        }
        
        .btn-stop {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            grid-column: span 3;
            padding: 20px;
            font-size: 18px;
        }
        
        .slider-group {
            margin-bottom: 15px;
        }
        
        .slider-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            font-size: 14px;
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
            font-size: 20px;
            font-weight: 700;
        }
        
        .camera-selector {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .camera-btn {
            flex: 1;
            padding: 10px;
            background: rgba(255,255,255,0.1);
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 8px;
            color: white;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }
        
        .camera-btn.active {
            background: rgba(100,200,100,0.3);
            border-color: #4ade80;
        }
        
        .connected { color: #4ade80; }
        .disconnected { color: #f87171; }
        
        @media (max-width: 968px) {
            .container { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 EVA Robot - Full Control</h1>
        <div class="status-bar">
            <div class="status-item">
                Status: <span id="conn-status" class="disconnected">Offline</span>
            </div>
            <div class="status-item">
                Câmera: <span id="cam-active">-</span>
            </div>
            <div class="status-item">
                Motor: <span id="motor-status">-</span>
            </div>
            <div class="status-item">
                Braço: <span id="arm-status">-</span>
            </div>
        </div>
    </div>
    
    <div class="container">
        <!-- Vídeo -->
        <div class="panel">
            <h2>📹 Video Feed</h2>
            
            <div class="camera-selector">
                <button class="camera-btn active" id="cam-auto" onclick="setCameraMode('auto')">
                    🔄 Auto
                </button>
                <button class="camera-btn" id="cam-usb" onclick="setCameraMode('usb')">
                    📹 USB
                </button>
                <button class="camera-btn" id="cam-picam" onclick="setCameraMode('picam')">
                    📷 Pi Cam
                </button>
            </div>
            
            <img id="camera-feed" src="/video_feed">
        </div>
        
        <!-- Controles -->
        <div class="controls">
            <!-- Movimento -->
            <div class="panel">
                <h2>🚗 Movimento</h2>
                
                <div class="btn-grid">
                    <div></div>
                    <button class="btn" id="btn-fwd">↑<br>Frente</button>
                    <div></div>
                    
                    <button class="btn" id="btn-left">←<br>Esq</button>
                    <button class="btn btn-stop" id="btn-stop">⏹<br>STOP</button>
                    <button class="btn" id="btn-right">→<br>Dir</button>
                    
                    <div></div>
                    <button class="btn" id="btn-back">↓<br>Ré</button>
                    <div></div>
                </div>
                
                <div class="slider-group" style="margin-top:15px;">
                    <label>⚡ Velocidade</label>
                    <input type="range" id="speed" min="500" max="3000" value="1500" step="100">
                    <div class="slider-value"><span id="speed-val">1500</span> PWM</div>
                </div>
            </div>
            
            <!-- Braço -->
            <div class="panel">
                <h2>🦾 Braço (5 Servos)</h2>
                
                <div class="slider-group">
                    <label>0️⃣ Base (Rotação)</label>
                    <input type="range" class="servo" data-servo="0" min="0" max="180" value="90">
                    <div class="slider-value"><span id="servo-0">90</span>°</div>
                </div>
                
                <div class="slider-group">
                    <label>1️⃣ Ombro</label>
                    <input type="range" class="servo" data-servo="1" min="0" max="180" value="90">
                    <div class="slider-value"><span id="servo-1">90</span>°</div>
                </div>
                
                <div class="slider-group">
                    <label>2️⃣ Cotovelo</label>
                    <input type="range" class="servo" data-servo="2" min="0" max="180" value="90">
                    <div class="slider-value"><span id="servo-2">90</span>°</div>
                </div>
                
                <div class="slider-group">
                    <label>3️⃣ Pulso</label>
                    <input type="range" class="servo" data-servo="3" min="0" max="180" value="90">
                    <div class="slider-value"><span id="servo-3">90</span>°</div>
                </div>
                
                <div class="slider-group">
                    <label>4️⃣ Garra</label>
                    <input type="range" class="servo" data-servo="4" min="0" max="180" value="90">
                    <div class="slider-value"><span id="servo-4">90</span>°</div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        let speed = 1500;
        let cameraMode = 'auto';
        
        // Conexão
        socket.on('connect', () => {
            document.getElementById('conn-status').textContent = 'Online';
            document.getElementById('conn-status').className = 'connected';
        });
        
        socket.on('disconnect', () => {
            document.getElementById('conn-status').textContent = 'Offline';
            document.getElementById('conn-status').className = 'disconnected';
        });
        
        socket.on('welcome', (data) => {
            document.getElementById('cam-active').textContent = data.camera_active;
            document.getElementById('motor-status').textContent = data.motor;
            document.getElementById('arm-status').textContent = data.arm;
            
            // Atualizar sliders
            if (data.arm_positions) {
                for (let i = 0; i < 5; i++) {
                    const slider = document.querySelector(`[data-servo="${i}"]`);
                    const value = document.getElementById(`servo-${i}`);
                    if (slider && data.arm_positions[i]) {
                        slider.value = data.arm_positions[i];
                                                value.textContent = data.arm_positions[i];
                    }
                }
            }
        });

        socket.on('response', (data) => {
            console.log('Response:', data);
            if (data.camera) {
                document.getElementById('cam-active').textContent = data.camera;
            }
        });

        function sendCommand(cmd, params = {}) {
            socket.emit('command', { cmd, params });
        }

        // ===== MOVIMENTO =====
        function drive(vx, vy, vz) {
            sendCommand('drive', { vx, vy, vz });
        }

        function stop() {
            sendCommand('stop');
        }

        document.getElementById('btn-fwd').onmousedown = () => drive(1,0,0);
        document.getElementById('btn-back').onmousedown = () => drive(-1,0,0);
        document.getElementById('btn-left').onmousedown = () => drive(0,0,1);
        document.getElementById('btn-right').onmousedown = () => drive(0,0,-1);
        document.getElementById('btn-stop').onclick = stop;

        document.querySelectorAll('.btn').forEach(btn => {
            btn.onmouseup = stop;
            btn.onmouseleave = stop;
        });

        // ===== VELOCIDADE =====
        const speedSlider = document.getElementById('speed');
        const speedVal = document.getElementById('speed-val');

        speedSlider.addEventListener('input', (e) => {
            speed = parseInt(e.target.value);
            speedVal.textContent = speed;
        });

        // ===== SERVOS =====
        document.querySelectorAll('.servo').forEach(slider => {
            slider.addEventListener('input', (e) => {
                const servo = parseInt(e.target.dataset.servo);
                const angle = parseInt(e.target.value);
                document.getElementById(`servo-${servo}`).textContent = angle;

                sendCommand('servo', { servo, angle });
            });
        });

        // ===== CÂMERA =====
        function setCameraMode(mode) {
            sendCommand('camera_mode', { mode });
            document.querySelectorAll('.camera-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(`cam-${mode}`).classList.add('active');
        }

        // ===== TECLADO =====
        let keys = {};
        document.addEventListener('keydown', (e) => {
            if (keys[e.key]) return;
            keys[e.key] = true;

            switch(e.key.toLowerCase()) {
                case 'w': drive(1,0,0); break;
                case 's': drive(-1,0,0); break;
                case 'a': drive(0,0,1); break;
                case 'd': drive(0,0,-1); break;
                case ' ': stop(); break;
            }
        });

        document.addEventListener('keyup', (e) => {
            keys[e.key] = false;
            stop();
        });
    </script>
</body>
</html>
"""
def main():
    camera_system.start()
    socketio.run(app, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    main()