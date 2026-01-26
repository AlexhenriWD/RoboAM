#!/usr/bin/env python3
"""
EVA FLASK SERVER - Sistema Simples e Funcional
✅ CORRIGIDO: Câmeras detectadas e funcionando!

SUAS CÂMERAS:
  • Pi Camera (ov5647) - Picamera2
  • USB REDRAGON - cv2.VideoCapture(1)

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

# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'eva-robot-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ==========================================
# SISTEMA DE CÂMERA - CORRIGIDO
# ==========================================

class CameraSystem:
    """Sistema dual de câmeras - CORRIGIDO"""
    
    def __init__(self, prefer_picam=True):
        """
        Args:
            prefer_picam: True = preferir Pi Camera, False = preferir USB
        """
        self.camera = None
        self.camera_type = None
        self.running = False
        self.frame = None
        self.lock = threading.Lock()
        
        print("\n📷 Inicializando sistema de câmeras...")
        
        if prefer_picam and PICAM_OK:
            self._init_picamera()
        else:
            self._init_usb_camera()
        
        # Se primeira opção falhou, tentar alternativa
        if not self.camera:
            if prefer_picam:
                self._init_usb_camera()
            else:
                self._init_picamera()
    
    def _init_picamera(self):
        """Inicializa Pi Camera"""
        try:
            print("  🔧 Tentando Pi Camera...")
            
            picam = Picamera2()
            
            # Usar câmera 0 (ov5647)
            config = picam.create_preview_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            
            picam.configure(config)
            picam.start()
            
            # Aguardar estabilização
            time.sleep(1.0)
            
            # Testar captura
            test_frame = picam.capture_array()
            
            if test_frame is not None and test_frame.size > 0:
                self.camera = picam
                self.camera_type = "Pi Camera (ov5647)"
                print(f"  ✅ Pi Camera OK - {test_frame.shape}")
            else:
                picam.stop()
                picam.close()
                print("  ❌ Pi Camera não capturou")
        
        except Exception as e:
            print(f"  ❌ Pi Camera falhou: {e}")
    
    def _init_usb_camera(self):
        """Inicializa USB Webcam REDRAGON"""
        try:
            print("  🔧 Tentando USB Webcam (REDRAGON)...")
            
            # /dev/video1 = REDRAGON (confirmado pelo diagnóstico)
            cap = cv2.VideoCapture(1)
            
            if not cap.isOpened():
                print("  ❌ USB não abriu")
                return
            
            # Configurar
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            
            # Testar captura
            ret, test_frame = cap.read()
            
            if ret and test_frame is not None:
                self.camera = cap
                self.camera_type = "USB REDRAGON (/dev/video1)"
                print(f"  ✅ USB Webcam OK - {test_frame.shape}")
            else:
                cap.release()
                print("  ❌ USB não capturou")
        
        except Exception as e:
            print(f"  ❌ USB Webcam falhou: {e}")
    
    def start(self):
        """Inicia thread de captura"""
        if not self.camera:
            print("❌ Nenhuma câmera disponível")
            return False
        
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        print(f"✅ Streaming iniciado: {self.camera_type}")
        return True
    
    def _capture_loop(self):
        """Loop de captura contínua"""
        print("📹 Loop de captura rodando...")
        
        frame_count = 0
        last_fps_time = time.time()
        
        while self.running:
            try:
                # Capturar frame
                if isinstance(self.camera, Picamera2):
                    # Pi Camera - captura RGB
                    frame = self.camera.capture_array()
                    
                    # Converter RGB -> BGR para OpenCV
                    if frame is not None and len(frame.shape) == 3:
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                else:
                    # USB Webcam - já retorna BGR
                    ret, frame = self.camera.read()
                    
                    if not ret or frame is None:
                        print("⚠️ Frame vazio da webcam")
                        time.sleep(0.1)
                        continue
                
                # Salvar frame
                with self.lock:
                    self.frame = frame
                
                # FPS counter (a cada 30 frames)
                frame_count += 1
                if frame_count % 30 == 0:
                    now = time.time()
                    fps = 30 / (now - last_fps_time)
                    print(f"📊 FPS: {fps:.1f} | Frames: {frame_count}")
                    last_fps_time = now
                
                time.sleep(0.033)  # ~30 FPS
            
            except Exception as e:
                print(f"❌ Erro no loop: {e}")
                time.sleep(1.0)
    
    def get_frame(self):
        """Retorna último frame (thread-safe)"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def stop(self):
        """Para captura"""
        print("⏹️ Parando câmera...")
        self.running = False
        
        time.sleep(0.5)  # Aguardar thread finalizar
        
        if isinstance(self.camera, Picamera2):
            try:
                self.camera.stop()
                self.camera.close()
            except:
                pass
        elif self.camera:
            try:
                self.camera.release()
            except:
                pass
        
        print("✅ Câmera parada")


# ==========================================
# SISTEMA DE CONTROLE - CORRIGIDO
# ==========================================

class RobotController:
    """Controlador do robô - invertido conforme seu código"""
    
    def __init__(self):
        self.motor = None
        self.speed = 1500  # PWM padrão
        
        if MOTOR_OK:
            try:
                self.motor = Ordinary_Car()
                print("✅ Motor inicializado")
            except Exception as e:
                print(f"❌ Motor falhou: {e}")
    
    def drive(self, vx=0.0, vy=0.0, vz=0.0):
        """
        Controla movimento (valores -1.0 a 1.0)
        
        IMPORTANTE: Motores INVERTIDOS conforme robot_core.py
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
        
        # INVERTER conforme robot_core.py
        # (seus motores estão invertidos fisicamente)
        fl, bl, fr, br = -fl, -bl, -fr, -br
        
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
    
    def stop(self):
        """Para motores"""
        if self.motor:
            try:
                self.motor.set_motor_model(0, 0, 0, 0)
                return {"status": "ok"}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return {"status": "ok"}
    
    def cleanup(self):
        """Cleanup"""
        self.stop()
        
        if self.motor:
            try:
                self.motor.close()
            except:
                pass


# ==========================================
# INSTÂNCIAS GLOBAIS
# ==========================================

# Preferir Pi Camera (melhor qualidade)
# Altere prefer_picam=False se quiser USB por padrão
camera_system = CameraSystem(prefer_picam=True)
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
        'camera': camera_system.camera_type or 'Sem câmera',
        'motor': 'OK' if robot.motor else 'Não disponível',
        'time': time.time()
    })

def generate_video():
    """Gerador de frames MJPEG"""
    while True:
        frame = camera_system.get_frame()
        
        if frame is None:
            # Placeholder se sem frame
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Aguardando camera...", (150, 240),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Codificar JPEG
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.033)  # ~30 FPS

@app.route('/video_feed')
def video_feed():
    """Stream de vídeo MJPEG"""
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
        'camera': camera_system.camera_type or 'Sem câmera',
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
    
    print(f"📨 CMD: {cmd} {params}")
    
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
# TEMPLATE HTML (salvo automaticamente)
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
        <h1>🤖 EVA Robot Control</h1>
        <div class="status">
            Status: <span id="connection-status" class="disconnected">Desconectado</span>
        </div>
    </div>
    
    <div class="container">
        <div class="video-panel">
            <h2>📹 Camera Feed</h2>
            <img id="camera-feed" src="/video_feed" alt="Camera Feed">
        </div>
        
        <div class="control-panel">
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
                
                <div class="speed-control">
                    <label>⚡ Velocidade</label>
                    <input type="range" id="speed-slider" min="500" max="3000" value="1500" step="100">
                    <div class="speed-value"><span id="speed-value">1500</span> PWM</div>
                </div>
            </div>
            
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
            document.getElementById('info-camera').textContent = data.camera;
            document.getElementById('info-motor').textContent = data.motor;
        });
        
        socket.on('response', (data) => {
            console.log('Response:', data);
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
        
        // Botões
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
        
        // Slider
        const speedSlider = document.getElementById('speed-slider');
        const speedValue = document.getElementById('speed-value');
        
        speedSlider.addEventListener('input', (e) => {
            speed = parseInt(e.target.value);
            speedValue.textContent = speed;
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
                    document.getElementById('info-camera').textContent = data.camera;
                    document.getElementById('info-motor').textContent = data.motor;
                })
                .catch(() => {});
        }, 5000);
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
    print("🤖 EVA FLASK SERVER")
    print("="*60)
    print("\nSuas câmeras detectadas:")
    print("  • Pi Camera (ov5647)")
    print("  • USB REDRAGON (/dev/video1)")
    print("\nRecursos:")
    print(f"  📷 Câmera ativa: {camera_system.camera_type or 'NENHUMA'}")
    print(f"  🚗 Motor: {'OK' if robot.motor else 'Não disponível'}")
    print("\n" + "="*60)
    
    # Iniciar câmera
    if camera_system.camera:
        if not camera_system.start():
            print("⚠️ Falha ao iniciar streaming")
    else:
        print("❌ NENHUMA câmera disponível!")
        print("   O servidor vai rodar mas sem vídeo")
    
    # Iniciar servidor
    try:
        print("\n🚀 Servidor iniciando...")
        print("   Porta: 5000")
        print("\n📱 Acesse de outro dispositivo:")
        print("   http://<IP_DO_RASPBERRY>:5000")
        print("\n   Exemplo: http://192.168.1.100:5000")
        print("\n💡 Controles:")
        print("   • Botões na interface")
        print("   • Teclado: W/A/S/D + ESPAÇO para parar")
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