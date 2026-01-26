#!/usr/bin/env python3
"""
EVA FLASK SERVER - Sistema Simples e Funcional
Servidor web + WebSocket para controle do robô

FEATURES:
✅ Flask web server (interface HTML)
✅ WebSocket para controle em tempo real
✅ Camera streaming (Pi Camera OU USB Webcam)
✅ Controle de movimento (teclado/botões)
✅ Auto-detecção de câmeras
✅ Debug detalhado

RODE NO RASPBERRY PI:
    python3 eva_flask_server.py

ACESSE DO PC:
    http://192.168.1.100:5000
"""

from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO, emit
import cv2
import time
import threading
import json
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

# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'eva-robot-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==========================================
# SISTEMA DE CÂMERA (AUTO-DETECT)
# ==========================================

class CameraSystem:
    """Sistema de câmera com auto-detecção"""
    
    def __init__(self):
        self.camera = None
        self.camera_type = None
        self.running = False
        self.frame = None
        self.lock = threading.Lock()
        
        print("\n📷 Detectando câmeras...")
        self._detect_camera()
    
    def _detect_camera(self):
        """Detecta câmera disponível (Pi Camera ou USB)"""
        
        # TENTAR 1: USB Webcam (mais confiável)
        for idx in [0, 1, 2]:
            try:
                print(f"  Testando /dev/video{idx}...")
                cap = cv2.VideoCapture(idx)
                
                if cap.isOpened():
                    ret, test_frame = cap.read()
                    
                    if ret and test_frame is not None:
                        print(f"  ✅ USB Webcam encontrada em /dev/video{idx}")
                        
                        # Configurar
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        cap.set(cv2.CAP_PROP_FPS, 15)
                        
                        self.camera = cap
                        self.camera_type = f"USB Webcam (/dev/video{idx})"
                        return
                    else:
                        cap.release()
                else:
                    cap.release()
            
            except Exception as e:
                print(f"    Erro em video{idx}: {e}")
        
        # TENTAR 2: Pi Camera (se USB falhou)
        if PICAM_OK:
            try:
                print("  Testando Pi Camera...")
                
                picam = Picamera2()
                
                # Configuração simplificada
                config = picam.create_preview_configuration(
                    main={"size": (640, 480), "format": "RGB888"}
                )
                
                picam.configure(config)
                picam.start()
                
                # Aguardar estabilização
                time.sleep(1.0)
                
                # Testar captura
                test_frame = picam.capture_array()
                
                if test_frame is not None:
                    print("  ✅ Pi Camera funcionando")
                    self.camera = picam
                    self.camera_type = "Raspberry Pi Camera"
                    return
                else:
                    picam.stop()
                    picam.close()
            
            except Exception as e:
                print(f"    Pi Camera falhou: {e}")
        
        print("  ❌ Nenhuma câmera detectada!")
        self.camera_type = "Sem câmera"
    
    def start(self):
        """Inicia captura"""
        if not self.camera:
            print("❌ Sem câmera para iniciar")
            return False
        
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        print(f"✅ Camera iniciada: {self.camera_type}")
        return True
    
    def _capture_loop(self):
        """Loop de captura"""
        print("📹 Loop de captura iniciado")
        
        while self.running:
            try:
                # Capturar frame
                if isinstance(self.camera, Picamera2):
                    # Pi Camera
                    frame = self.camera.capture_array()
                    
                    # Converter RGB para BGR (OpenCV)
                    if frame is not None and len(frame.shape) == 3:
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                else:
                    # USB Webcam
                    ret, frame = self.camera.read()
                    
                    if not ret or frame is None:
                        print("⚠️ Falha ao capturar frame da webcam")
                        time.sleep(0.1)
                        continue
                
                # Salvar frame
                with self.lock:
                    self.frame = frame
                
                time.sleep(0.033)  # ~30 FPS
            
            except Exception as e:
                print(f"❌ Erro no loop de captura: {e}")
                time.sleep(1.0)
    
    def get_frame(self):
        """Retorna último frame capturado"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def stop(self):
        """Para captura"""
        self.running = False
        
        if isinstance(self.camera, Picamera2):
            self.camera.stop()
            self.camera.close()
        elif self.camera:
            self.camera.release()
        
        print("📴 Camera parada")


# ==========================================
# SISTEMA DE CONTROLE DO ROBÔ
# ==========================================

class RobotController:
    """Controlador do robô"""
    
    def __init__(self):
        self.motor = None
        self.speed = 1500  # PWM padrão
        
        if MOTOR_OK:
            try:
                self.motor = Ordinary_Car()
                print("✅ Motor inicializado")
            except Exception as e:
                print(f"❌ Erro ao inicializar motor: {e}")
    
    def drive(self, vx=0.0, vy=0.0, vz=0.0):
        """
        Controla movimento
        
        Args:
            vx: forward/backward (-1.0 a 1.0)
            vy: strafe left/right (-1.0 a 1.0)
            vz: rotação (-1.0 a 1.0)
        """
        if not self.motor:
            return {"status": "error", "error": "Motor não disponível"}
        
        # Converter para PWM
        max_pwm = self.speed
        
        # Cinemática mecanum
        fl = int((vx + vy + vz) * max_pwm)
        bl = int((vx - vy + vz) * max_pwm)
        fr = int((vx - vy - vz) * max_pwm)
        br = int((vx + vy - vz) * max_pwm)
        
        # Aplicar
        self.motor.set_motor_model(fl, bl, fr, br)
        
        return {
            "status": "ok",
            "motors": [fl, bl, fr, br]
        }
    
    def stop(self):
        """Para motores"""
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
        
        return {"status": "ok"}
    
    def cleanup(self):
        """Cleanup"""
        self.stop()
        
        if self.motor:
            self.motor.close()


# ==========================================
# INSTÂNCIAS GLOBAIS
# ==========================================

camera_system = CameraSystem()
robot = RobotController()

# ==========================================
# ROTAS FLASK
# ==========================================

@app.route('/')
def index():
    """Página principal"""
    return render_template('control.html')

@app.route('/status')
def status():
    """Status do sistema"""
    return jsonify({
        'camera': camera_system.camera_type,
        'motor': 'OK' if robot.motor else 'Não disponível',
        'time': time.time()
    })

def generate_video():
    """Gerador de frames para streaming"""
    while True:
        frame = camera_system.get_frame()
        
        if frame is None:
            # Frame vazio se sem câmera
            frame = create_placeholder_frame()
        
        # Codificar JPEG
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.033)  # ~30 FPS

def create_placeholder_frame():
    """Cria frame placeholder quando sem câmera"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    text = "Sem Camera"
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    text_size = cv2.getTextSize(text, font, 1, 2)[0]
    text_x = (640 - text_size[0]) // 2
    text_y = (480 + text_size[1]) // 2
    
    cv2.putText(frame, text, (text_x, text_y), font, 1, (255, 255, 255), 2)
    
    return frame

@app.route('/video_feed')
def video_feed():
    """Stream de vídeo"""
    return Response(
        generate_video(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# ==========================================
# WEBSOCKET EVENTS
# ==========================================

@socketio.on('connect')
def handle_connect():
    """Cliente conectou"""
    print("🔗 Cliente conectado")
    
    emit('welcome', {
        'message': 'Conectado ao EVA Robot',
        'camera': camera_system.camera_type,
        'motor': 'OK' if robot.motor else 'Não disponível'
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectou"""
    print("🔌 Cliente desconectado")
    robot.stop()

@socketio.on('command')
def handle_command(data):
    """Recebe comando do cliente"""
    cmd = data.get('cmd')
    params = data.get('params', {})
    
    print(f"📨 Comando: {cmd} {params}")
    
    if cmd == 'drive':
        result = robot.drive(
            vx=params.get('vx', 0),
            vy=params.get('vy', 0),
            vz=params.get('vz', 0)
        )
    
    elif cmd == 'stop':
        result = robot.stop()
    
    else:
        result = {"status": "error", "error": f"Comando desconhecido: {cmd}"}
    
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
    <title>EVA Robot Control</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
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
        }
        
        .btn-stop {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            grid-column: span 3;
            font-size: 18px;
            padding: 20px;
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
            outline: none;
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
        
        .info-row:last-child {
            border-bottom: none;
        }
        
        .connected {
            color: #4ade80;
        }
        
        .disconnected {
            color: #f87171;
        }
        
        @media (max-width: 968px) {
            .container {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 EVA Robot Control</h1>
        <div class="status">
            Status: <span id="connection-status" class="disconnected">Desconectado</span>
        </div>
    </div>
    
    <div class="container">
        <!-- Painel de Vídeo -->
        <div class="video-panel">
            <h2>📹 Camera Feed</h2>
            <img id="camera-feed" src="/video_feed" alt="Camera Feed">
        </div>
        
        <!-- Painel de Controles -->
        <div class="control-panel">
            <!-- Movimento -->
            <div class="control-section">
                <h3>🎮 Movimento</h3>
                
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
                
                <!-- Velocidade -->
                <div class="speed-control">
                    <label>⚡ Velocidade</label>
                    <input type="range" id="speed-slider" min="500" max="3000" value="1500" step="100">
                    <div class="speed-value"><span id="speed-value">1500</span> PWM</div>
                </div>
            </div>
            
            <!-- Info -->
            <div class="info-panel">
                <div class="info-row">
                    <span>Câmera:</span>
                    <span id="info-camera">-</span>
                </div>
                <div class="info-row">
                    <span>Motor:</span>
                    <span id="info-motor">-</span>
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
        // WebSocket
        const socket = io();
        
        let speed = 1500;
        
        // Conexão
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
            document.getElementById('info-camera').textContent = data.camera;
            document.getElementById('info-motor').textContent = data.motor;
        });
        
        socket.on('response', (data) => {
            console.log('Response:', data);
        });
        
        // Funções de controle
        function sendCommand(cmd, params = {}) {
            socket.emit('command', { cmd, params });
            document.getElementById('info-last-cmd').textContent = cmd;
        }
        
        function drive(vx = 0, vy = 0, vz = 0) {
            // Normalizar pela velocidade
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
        
        // Botões
        document.getElementById('btn-forward').addEventListener('mousedown', () => drive(1, 0, 0));
        document.getElementById('btn-forward').addEventListener('mouseup', stop);
        document.getElementById('btn-forward').addEventListener('mouseleave', stop);
        
        document.getElementById('btn-backward').addEventListener('mousedown', () => drive(-1, 0, 0));
        document.getElementById('btn-backward').addEventListener('mouseup', stop);
        document.getElementById('btn-backward').addEventListener('mouseleave', stop);
        
        document.getElementById('btn-left').addEventListener('mousedown', () => drive(0, 0, 1));
        document.getElementById('btn-left').addEventListener('mouseup', stop);
        document.getElementById('btn-left').addEventListener('mouseleave', stop);
        
        document.getElementById('btn-right').addEventListener('mousedown', () => drive(0, 0, -1));
        document.getElementById('btn-right').addEventListener('mouseup', stop);
        document.getElementById('btn-right').addEventListener('mouseleave', stop);
        
        document.getElementById('btn-stop').addEventListener('click', stop);
        
        // Slider de velocidade
        const speedSlider = document.getElementById('speed-slider');
        const speedValue = document.getElementById('speed-value');
        
        speedSlider.addEventListener('input', (e) => {
            speed = parseInt(e.target.value);
            speedValue.textContent = speed;
        });
        
        // Teclado (WASD)
        let keyPressed = {};
        
        document.addEventListener('keydown', (e) => {
            if (keyPressed[e.key]) return;
            keyPressed[e.key] = true;
            
            switch(e.key.toLowerCase()) {
                case 'w': drive(1, 0, 0); break;
                case 's': drive(-1, 0, 0); break;
                case 'a': drive(0, 0, 1); break;
                case 'd': drive(0, 0, -1); break;
                case ' ': stop(); break;
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
                    document.getElementById('info-camera').textContent = data.camera;
                    document.getElementById('info-motor').textContent = data.motor;
                })
                .catch(err => console.error('Status error:', err));
        }, 5000);
    </script>
</body>
</html>
"""

# Salvar template
(TEMPLATE_DIR / 'control.html').write_text(HTML_TEMPLATE, encoding='utf-8')

# ==========================================
# MAIN
# ==========================================

def main():
    print("\n" + "="*60)
    print("🤖 EVA FLASK SERVER")
    print("="*60)
    print("\nRecursos:")
    print(f"  📷 Câmera: {camera_system.camera_type}")
    print(f"  🚗 Motor: {'OK' if robot.motor else 'Não disponível'}")
    print("\n" + "="*60)
    
    # Iniciar câmera
    if camera_system.camera:
        camera_system.start()
    
    # Iniciar servidor
    try:
        print("\n🚀 Servidor iniciando...")
        print("   Porta: 5000")
        print("\n📱 Acesse de outro dispositivo:")
        print("   http://<IP_DO_RASPBERRY>:5000")
        print("\n" + "="*60 + "\n")
        
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Ctrl+C detectado")
    
    finally:
        print("\n🔧 Encerrando...")
        camera_system.stop()
        robot.cleanup()
        print("✅ Servidor encerrado\n")


if __name__ == '__main__':
    main()