#!/usr/bin/env python3
"""
Servidor Web para controle do Freenove Smart Car com IA
Versão melhorada com integração Groq AI
"""

from flask import Flask, render_template_string, Response, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
import json
import sys
from pathlib import Path

# Adicionar pasta hardware ao path
sys.path.insert(0, str(Path(__file__).parent / 'hardware'))

# Importar módulos do hardware
try:
    from hardware.motor import Ordinary_Car
    from hardware.servo import Servo
    from hardware.ultrasonic import Ultrasonic
    from hardware.infrared import Infrared
    from hardware.adc import ADC
    from hardware.buzzer import Buzzer
    HARDWARE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Erro ao importar hardware: {e}")
    HARDWARE_AVAILABLE = False

# Tentar importar opencv (opcional para câmera)
try:
    import cv2
    CAMERA_AVAILABLE = True
except ImportError:
    print("⚠️ OpenCV não disponível. Câmera desabilitada.")
    CAMERA_AVAILABLE = False

# Tentar importar LED (opcional)
try:
    from led import Led
    LED_AVAILABLE = True
except ImportError:
    print("⚠️ LED não disponível")
    LED_AVAILABLE = False
    class Led:
        def __init__(self):
            self.is_support_led_function = False
        def colorBlink(self, *args, **kwargs):
            pass
        def rainbowCycle(self, *args, **kwargs):
            pass
        def rainbowbreathing(self, *args, **kwargs):
            pass
        def following(self, *args, **kwargs):
            pass
        def ledIndex(self, *args, **kwargs):
            pass

# Importar cliente IA
try:
    from ai.groq_client import GroqVisionClient
    AI_AVAILABLE = True
except ImportError:
    print("⚠️ Groq AI não disponível")
    AI_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'freenove-secret-key-2026'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class RobotController:
    def __init__(self):
        """Inicializa todos os componentes do robô"""
        self.running = False
        self.camera = None
        self.motor = None
        self.servo = None
        self.ultrasonic = None
        self.infrared = None
        self.adc = None
        self.buzzer = None
        self.led = None
        self.groq_client = None
        
        self.led_available = LED_AVAILABLE
        self.camera_available = CAMERA_AVAILABLE
        self.ai_available = AI_AVAILABLE
        
        # Estados
        self.car_mode = 'manual'  # manual, ultrasonic, infrared, light, ai, ai_vision
        self.led_mode = 'off'
        self.camera_active = False
        self.ai_enabled = False
        
        # Threads
        self.sensor_thread = None
        self.led_thread = None
        self.auto_mode_thread = None
        self.ai_thread = None
        
        # Dados
        self.current_frame = None
        self.sensor_data = {}
        self.last_ai_decision = None
        self.ai_stats = {
            'decisions': 0,
            'errors': 0,
            'last_decision_time': 0
        }
        
        self.initialize_hardware()
    
    def initialize_hardware(self):
        """Inicializa o hardware do robô"""
        if not HARDWARE_AVAILABLE:
            print("❌ Hardware não disponível - modo simulação")
            return
        
        try:
            print("Inicializando hardware...")
            self.motor = Ordinary_Car()
            print("✓ Motor inicializado")
            
            self.servo = Servo()
            print("✓ Servo inicializado")
            
            self.ultrasonic = Ultrasonic()
            print("✓ Ultrasonic inicializado")
            
            self.infrared = Infrared()
            print("✓ Infrared inicializado")
            
            self.adc = ADC()
            print("✓ ADC inicializado")
            
            self.buzzer = Buzzer()
            print("✓ Buzzer inicializado")
            
            # Inicializar LED se disponível
            if self.led_available:
                try:
                    self.led = Led()
                    print("✓ LED inicializado")
                except Exception as e:
                    print(f"✗ LED falhou: {e}")
                    self.led_available = False
                    self.led = Led()
            else:
                self.led = Led()
                print("○ LED não disponível (modo mock)")
            
            # Inicializar webcam USB se OpenCV disponível
            if self.camera_available:
                try:
                    self.camera = cv2.VideoCapture(0)
                    if self.camera.isOpened():
                        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        self.camera.set(cv2.CAP_PROP_FPS, 30)
                        print("✓ Câmera inicializada")
                    else:
                        print("○ Câmera não detectada")
                        self.camera = None
                        self.camera_available = False
                except Exception as e:
                    print(f"✗ Câmera falhou: {e}")
                    self.camera = None
                    self.camera_available = False
            
            # Inicializar Groq AI
            if self.ai_available:
                try:
                    config_path = Path(__file__).parent / 'config.json'
                    if config_path.exists():
                        with open(config_path) as f:
                            config = json.load(f)
                            api_key = config.get('groq_api_key')
                            if api_key:
                                self.groq_client = GroqVisionClient(api_key)
                                print("✓ Groq AI inicializada")
                            else:
                                print("⚠️ GROQ_API_KEY não configurada")
                                self.ai_available = False
                    else:
                        print("⚠️ config.json não encontrado")
                        self.ai_available = False
                except Exception as e:
                    print(f"✗ Groq AI falhou: {e}")
                    self.ai_available = False
            
            self.running = True
            print("\n✓ Hardware inicializado com sucesso!")
            
            # Iniciar threads de monitoramento
            self.start_monitoring_threads()
            
        except Exception as e:
            print(f"✗ Erro ao inicializar hardware: {e}")
            self.cleanup()
            raise
    
    def start_monitoring_threads(self):
        """Inicia threads de monitoramento de sensores"""
        self.sensor_thread = threading.Thread(target=self.sensor_monitor_loop, daemon=True)
        self.sensor_thread.start()
        
        if self.led_available:
            self.led_thread = threading.Thread(target=self.led_loop, daemon=True)
            self.led_thread.start()
        
        self.auto_mode_thread = threading.Thread(target=self.auto_mode_loop, daemon=True)
        self.auto_mode_thread.start()
    
    def sensor_monitor_loop(self):
        """Loop de monitoramento contínuo dos sensores"""
        while self.running:
            try:
                # Ler sensores
                data = {
                    'ultrasonic': round(self.ultrasonic.get_distance() or 0, 2),
                    'infrared': [
                        self.infrared.read_one_infrared(1),
                        self.infrared.read_one_infrared(2),
                        self.infrared.read_one_infrared(3)
                    ],
                    'light_left': round(self.adc.read_adc(0), 2),
                    'light_right': round(self.adc.read_adc(1), 2),
                    'battery': round(self.adc.read_adc(2) * (3 if self.adc.pcb_version == 1 else 2), 2),
                    'mode': self.car_mode,
                    'led_available': self.led_available,
                    'camera_available': self.camera_available,
                    'ai_available': self.ai_available,
                    'ai_enabled': self.ai_enabled
                }
                
                # Adicionar dados da IA se disponível
                if self.ai_enabled and self.last_ai_decision:
                    data['ai_decision'] = self.last_ai_decision
                    data['ai_stats'] = self.ai_stats
                
                self.sensor_data = data
                
                # Capturar frame da câmera
                if self.camera and self.camera.isOpened():
                    ret, frame = self.camera.read()
                    if ret:
                        self.current_frame = frame
                
                # Enviar dados via SocketIO
                socketio.emit('sensor_data', data)
                
                time.sleep(0.2)
            except Exception as e:
                print(f"Erro no loop de sensores: {e}")
                time.sleep(0.5)
    
    def led_loop(self):
        """Loop de controle dos LEDs"""
        while self.running and self.led_available:
            try:
                if self.led_mode == 'rainbow':
                    self.led.rainbowCycle(20)
                elif self.led_mode == 'breathing':
                    self.led.rainbowbreathing(10)
                elif self.led_mode == 'following':
                    self.led.following(50)
                elif self.led_mode == 'blink':
                    self.led.colorBlink(1, 300)
                elif self.led_mode == 'off':
                    self.led.colorBlink(0)
                    time.sleep(0.1)
                else:
                    time.sleep(0.05)
            except Exception as e:
                print(f"Erro no loop de LED: {e}")
                time.sleep(0.5)
    
    def auto_mode_loop(self):
        """Loop para modos automáticos"""
        while self.running:
            try:
                if self.car_mode == 'ultrasonic':
                    self.ultrasonic_mode()
                elif self.car_mode == 'infrared':
                    self.infrared_mode()
                elif self.car_mode == 'light':
                    self.light_mode()
                elif self.car_mode in ['ai', 'ai_vision']:
                    self.ai_mode()
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"Erro no modo automático: {e}")
                time.sleep(0.5)
    
    def ai_mode(self):
        """Modo de navegação com IA"""
        if not self.ai_enabled or not self.groq_client:
            time.sleep(0.5)
            return
        
        try:
            # Decidir se usa visão ou só sensores
            use_vision = (self.car_mode == 'ai_vision' and 
                         self.current_frame is not None)
            
            # Fazer requisição à IA
            if use_vision:
                result = self.groq_client.analyze_scene(
                    self.current_frame,
                    self.sensor_data
                )
            else:
                result = self.groq_client.simple_decision(self.sensor_data)
            
            if result['success']:
                decision = result['decision']
                self.last_ai_decision = decision
                self.ai_stats['decisions'] += 1
                self.ai_stats['last_decision_time'] = time.time()
                
                # Executar decisão
                self._execute_ai_decision(decision)
                
                # Log
                print(f"🤖 IA: {decision.get('recommended_action')} - {decision.get('reason')}")
            else:
                self.ai_stats['errors'] += 1
                print(f"⚠️ Erro IA: {result.get('error')}")
                # Parar em caso de erro
                self.motor.set_motor_model(0, 0, 0, 0)
            
            time.sleep(1.5)  # Intervalo entre decisões
            
        except Exception as e:
            print(f"Erro no modo IA: {e}")
            self.ai_stats['errors'] += 1
            self.motor.set_motor_model(0, 0, 0, 0)
            time.sleep(1)
    
    def _execute_ai_decision(self, decision):
        """Executa decisão da IA"""
        action = decision.get('recommended_action', 'stop')
        speed_percent = decision.get('speed', 50)
        
        # Limitar velocidade (máx 60%)
        speed_percent = min(speed_percent, 60)
        speed = int((speed_percent / 100.0) * 2000)
        
        if action == 'forward':
            self.motor.set_motor_model(speed, speed, speed, speed)
        elif action == 'backward':
            self.motor.set_motor_model(-speed, -speed, -speed, -speed)
        elif action == 'left':
            self.motor.set_motor_model(-speed, -speed, speed, speed)
        elif action == 'right':
            self.motor.set_motor_model(speed, speed, -speed, -speed)
        else:
            self.motor.set_motor_model(0, 0, 0, 0)
    
    def ultrasonic_mode(self):
        """Modo de navegação por ultrassom"""
        servo_angle = 90
        servo_dir = 1
        distances = [30, 30, 30]
        
        self.servo.set_servo_pwm('0', servo_angle)
        time.sleep(0.2)
        
        if servo_angle == 30:
            distances[0] = self.ultrasonic.get_distance() or 30
        elif servo_angle == 90:
            distances[1] = self.ultrasonic.get_distance() or 30
        elif servo_angle == 150:
            distances[2] = self.ultrasonic.get_distance() or 30
        
        # Lógica de navegação
        if (distances[0] < 30 and distances[1] < 30 and distances[2] < 30) or distances[1] < 30:
            self.motor.set_motor_model(-1450, -1450, -1450, -1450)
            time.sleep(0.1)
            if distances[0] < distances[2]:
                self.motor.set_motor_model(1450, 1450, -1450, -1450)
            else:
                self.motor.set_motor_model(-1450, -1450, 1450, 1450)
        elif distances[0] < 20:
            self.motor.set_motor_model(2000, 2000, -500, -500)
        elif distances[2] < 20:
            self.motor.set_motor_model(-500, -500, 2000, 2000)
        else:
            self.motor.set_motor_model(600, 600, 600, 600)
    
    def infrared_mode(self):
        """Modo de seguir linha"""
        ir_value = self.infrared.read_all_infrared()
        
        if ir_value == 2:
            self.motor.set_motor_model(800, 800, 800, 800)
        elif ir_value == 4:
            self.motor.set_motor_model(-1500, -1500, 2500, 2500)
        elif ir_value == 6:
            self.motor.set_motor_model(-2000, -2000, 4000, 4000)
        elif ir_value == 1:
            self.motor.set_motor_model(2500, 2500, -1500, -1500)
        elif ir_value == 3:
            self.motor.set_motor_model(4000, 4000, -2000, -2000)
        elif ir_value == 7:
            self.motor.set_motor_model(0, 0, 0, 0)
        
        time.sleep(0.2)
    
    def light_mode(self):
        """Modo de seguir luz"""
        L = self.adc.read_adc(0)
        R = self.adc.read_adc(1)
        
        if L < 2.99 and R < 2.99:
            self.motor.set_motor_model(600, 600, 600, 600)
        elif abs(L - R) < 0.15:
            self.motor.set_motor_model(0, 0, 0, 0)
        elif L > 3 or R > 3:
            if L > R:
                self.motor.set_motor_model(-1200, -1200, 1400, 1400)
            else:
                self.motor.set_motor_model(1400, 1400, -1200, -1200)
        
        time.sleep(0.2)
    
    def get_camera_frame(self):
        """Captura frame da webcam"""
        if self.camera_available and self.camera and self.camera.isOpened():
            ret, frame = self.camera.read()
            if ret:
                frame = cv2.resize(frame, (640, 480))
                return frame
        return None
    
    def cleanup(self):
        """Limpa recursos"""
        print("\nLimpando recursos...")
        self.running = False
        self.ai_enabled = False
        
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
            self.motor.close()
            print("✓ Motor desligado")
        
        if self.camera_available and self.camera and self.camera.isOpened():
            self.camera.release()
            print("✓ Câmera liberada")
        
        if self.ultrasonic:
            self.ultrasonic.close()
            print("✓ Ultrasonic fechado")
        
        if self.infrared:
            self.infrared.close()
            print("✓ Infrared fechado")
        
        if self.adc:
            self.adc.close_i2c()
            print("✓ ADC fechado")
        
        if self.buzzer:
            self.buzzer.close()
            print("✓ Buzzer fechado")
        
        if self.led and self.led_available:
            self.led.colorBlink(0)
            print("✓ LED desligado")

# Instância global do controlador
robot = None

def init_robot():
    """Inicializa o robô"""
    global robot
    if robot is None:
        robot = RobotController()
    return robot

# Rotas Flask
@app.route('/')
def index():
    """Página principal"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Freenove AI Car</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff; 
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { 
            color: #00ff88; 
            text-align: center;
            margin-bottom: 20px;
            text-shadow: 0 0 20px rgba(0,255,136,0.5);
            font-size: 2em;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card { 
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            padding: 20px; 
            border-radius: 15px; 
            border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        .card h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            border-bottom: 2px solid rgba(0,212,255,0.3);
            padding-bottom: 10px;
        }
        .sensor-value {
            font-size: 24px;
            font-weight: bold;
            color: #00ff88;
            margin: 10px 0;
        }
        .controls {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        button { 
            padding: 15px 20px; 
            font-size: 16px; 
            cursor: pointer; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            transition: all 0.3s;
            font-weight: bold;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102,126,234,0.4);
        }
        button:active { transform: translateY(0); }
        button.active {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        button.ai-mode {
            background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }
        input[type="range"] {
            -webkit-appearance: none;
            appearance: none;
            width: 100%;
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 5px;
            outline: none;
        }
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            background: #667eea;
            border-radius: 50%;
            cursor: pointer;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #00ff88;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .info { color: #00d4ff; }
        .warning { color: #ffd700; }
        .ai-decision {
            background: rgba(250,112,154,0.1);
            padding: 15px;
            border-radius: 10px;
            margin-top: 10px;
            border-left: 3px solid #fa709a;
        }
        .ai-decision p {
            margin: 5px 0;
            font-size: 14px;
        }
        #video {
            width: 100%;
            border-radius: 10px;
            border: 2px solid rgba(255,255,255,0.1);
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 5px;
            font-size: 12px;
            font-weight: bold;
            margin-left: 10px;
        }
        .badge.success { background: #00ff88; color: #000; }
        .badge.danger { background: #ff4757; color: #fff; }
        .badge.warning { background: #ffd700; color: #000; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Freenove AI Car <span id="ai-badge"></span></h1>
        
        <div class="grid">
            <div class="card">
                <h3><span class="status-indicator"></span>Status do Sistema</h3>
                <p id="connection-status" class="info">Conectando...</p>
                <p>Bateria: <span id="battery" class="sensor-value">--</span>V</p>
                <p>Modo: <span id="mode" class="sensor-value">--</span></p>
                <p id="ai-status" style="margin-top: 10px;"></p>
            </div>
            
            <div class="card">
                <h3>📡 Sensores</h3>
                <p>Ultrassom: <span id="ultrasonic" class="sensor-value">--</span>cm</p>
                <p>Luz Esq: <span id="light-left" class="sensor-value">--</span>V</p>
                <p>Luz Dir: <span id="light-right" class="sensor-value">--</span>V</p>
                <p>Infrared: <span id="infrared" class="sensor-value">--</span></p>
            </div>
            
            <div class="card">
                <h3>🎮 Modos de Controle</h3>
                <div class="controls">
                    <button onclick="setMode('manual')" id="btn-manual">🎮 Manual</button>
                    <button onclick="setMode('ultrasonic')" id="btn-ultrasonic">📡 Ultrassom</button>
                    <button onclick="setMode('infrared')" id="btn-infrared">🛤️ Linha</button>
                    <button onclick="setMode('light')" id="btn-light">💡 Luz</button>
                    <button onclick="setMode('ai')" id="btn-ai" class="ai-mode">🤖 IA Sensores</button>
                    <button onclick="setMode('ai_vision')" id="btn-ai_vision" class="ai-mode">👁️ IA Visão</button>
                </div>
            </div>
            
            <div class="card">
                <h3>💡 LEDs</h3>
                <div class="controls">
                    <button onclick="setLed('off')" id="btn-led-off">Desligar</button>
                    <button onclick="setLed('rainbow')" id="btn-led-rainbow">Arco-íris</button>
                    <button onclick="setLed('breathing')" id="btn-led-breathing">Respiração</button>
                    <button onclick="setLed('blink')" id="btn-led-blink">Piscar</button>
                </div>
            </div>
        </div>
        
        <div class="card" id="ai-decision-card" style="display:none;">
            <h3>🧠 Última Decisão da IA</h3>
            <div class="ai-decision" id="ai-decision-content">
                <p><strong>Ação:</strong> <span id="ai-action">--</span></p>
                <p><strong>Velocidade:</strong> <span id="ai-speed">--</span>%</p>
                <p><strong>Razão:</strong> <span id="ai-reason">--</span></p>
                <p><strong>Segurança:</strong> <span id="ai-safety">--</span></p>
                <p style="margin-top: 10px; font-size: 12px; opacity: 0.7;">
                    Decisões: <span id="ai-decisions">0</span> | Erros: <span id="ai-errors">0</span>
                </p>
            </div>
        </div>
        
        <div class="card">
            <h3>🕹️ Controle Manual</h3>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; max-width: 300px; margin: 0 auto;">
                <div></div>
                <button onmousedown="move('forward')" onmouseup="stop()" ontouchstart="move('forward')" ontouchend="stop()">⬆️<br>Frente</button>
                <div></div>
                
                <button onmousedown="move('left')" onmouseup="stop()" ontouchstart="move('left')" ontouchend="stop()">⬅️<br>Esq</button>
                <button onclick="stop()" style="background: #dc3545;">⏹️<br>Parar</button>
                <button onmousedown="move('right')" onmouseup="stop()" ontouchstart="move('right')" ontouchend="stop()">➡️<br>Dir</button>
                
                <div></div>
                <button onmousedown="move('backward')" onmouseup="stop()" ontouchstart="move('backward')" ontouchend="stop()">⬇️<br>Trás</button>
                <div></div>
            </div>
            <div style="margin-top: 15px;">
                <label>Velocidade: <span id="speed-value">50</span>%</label>
                <input type="range" id="speed" min="0" max="100" value="50" oninput="updateSpeed(this.value)">
            </div>
        </div>
        
        <div class="card">
            <h3>📹 Câmera</h3>
            <button onclick="toggleCamera()" id="btn-camera">Ativar Câmera</button>
            <div style="margin-top: 15px;">
                <img id="video" src="" style="display:none;">
            </div>
        </div>
    </div>
    
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        let cameraActive = false;
        let currentMode = 'manual';
        let currentLed = 'off';
        let speedMultiplier = 0.5;
        let aiAvailable = false;
        
        socket.on('connect', () => {
            document.getElementById('connection-status').innerHTML = '✓ Conectado ao robô!';
            document.getElementById('connection-status').className = 'info';
        });
        
        socket.on('disconnect', () => {
            document.getElementById('connection-status').innerHTML = '✗ Desconectado';
            document.getElementById('connection-status').className = 'warning';
        });
        
        socket.on('sensor_data', (data) => {
            // Sensores
            document.getElementById('battery').textContent = data.battery || '--';
            document.getElementById('ultrasonic').textContent = data.ultrasonic || '--';
            document.getElementById('light-left').textContent = data.light_left?.toFixed(2) || '--';
            document.getElementById('light-right').textContent = data.light_right?.toFixed(2) || '--';
            document.getElementById('infrared').textContent = data.infrared?.join(', ') || '--';
            document.getElementById('mode').textContent = data.mode || '--';
            
            // Status da IA
            aiAvailable = data.ai_available || false;
            updateAIBadge(data.ai_enabled, aiAvailable);
            
            // Atualizar botões ativos
            document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
            const modeBtn = document.getElementById('btn-' + data.mode);
            if (modeBtn) modeBtn.classList.add('active');
            
            // Decisão da IA
            if (data.ai_decision) {
                showAIDecision(data.ai_decision, data.ai_stats);
            } else if (data.mode !== 'ai' && data.mode !== 'ai_vision') {
                document.getElementById('ai-decision-card').style.display = 'none';
            }
        });
        
        function updateAIBadge(enabled, available) {
            const badge = document.getElementById('ai-badge');
            const status = document.getElementById('ai-status');
            
            if (!available) {
                badge.innerHTML = '<span class="badge danger">IA Indisponível</span>';
                status.innerHTML = '⚠️ Configure GROQ_API_KEY no config.json';
                status.className = 'warning';
            } else if (enabled) {
                badge.innerHTML = '<span class="badge success">IA ATIVA</span>';
                status.innerHTML = '🤖 IA em operação';
                status.className = 'info';
            } else {
                badge.innerHTML = '<span class="badge warning">IA Pronta</span>';
                status.innerHTML = 'ℹ️ Selecione um modo de IA para ativar';
                status.className = 'info';
            }
        }
        
        function showAIDecision(decision, stats) {
            document.getElementById('ai-decision-card').style.display = 'block';
            document.getElementById('ai-action').textContent = decision.recommended_action || '--';
            document.getElementById('ai-speed').textContent = decision.speed || '--';
            document.getElementById('ai-reason').textContent = decision.reason || '--';
            document.getElementById('ai-safety').textContent = decision.safety_level || '--';
            
            if (stats) {
                document.getElementById('ai-decisions').textContent = stats.decisions || 0;
                document.getElementById('ai-errors').textContent = stats.errors || 0;
            }
        }
        
        socket.on('status', (data) => {
            console.log(data.message);
        });
        
        function setMode(mode) {
            socket.emit('car_mode', { mode: mode });
            currentMode = mode;
        }
        
        function updateSpeed(value) {
            speedMultiplier = value / 100;
            document.getElementById('speed-value').textContent = value;
        }
        
        function move(direction) {
            if (currentMode !== 'manual') return;
            
            const baseSpeed = 2000;
            const speed = Math.round(baseSpeed * speedMultiplier);
            
            let fl = 0, bl = 0, fr = 0, br = 0;
            
            switch(direction) {
                case 'forward':
                    fl = bl = fr = br = speed;
                    break;
                case 'backward':
                    fl = bl = fr = br = -speed;
                    break;
                case 'left':
                    fl = bl = -speed;
                    fr = br = speed;
                    break;
                case 'right':
                    fl = bl = speed;
                    fr = br = -speed;
                    break;
            }
            
            socket.emit('motor_control', { fl, bl, fr, br });
        }
        
        function stop() {
            socket.emit('motor_control', { fl: 0, bl: 0, fr: 0, br: 0 });
        }
        
        function setLed(mode) {
            socket.emit('led_mode', { mode: mode });
            currentLed = mode;
            document.querySelectorAll('[id^="btn-led-"]').forEach(b => b.classList.remove('active'));
            document.getElementById('btn-led-' + mode).classList.add('active');
        }
        
        function toggleCamera() {
            cameraActive = !cameraActive;
            socket.emit('camera_toggle', { active: cameraActive });
            const video = document.getElementById('video');
            const btn = document.getElementById('btn-camera');
            
            if (cameraActive) {
                video.src = '/video_feed';
                video.style.display = 'block';
                btn.textContent = 'Desativar Câmera';
                btn.classList.add('active');
            } else {
                video.src = '';
                video.style.display = 'none';
                btn.textContent = 'Ativar Câmera';
                btn.classList.remove('active');
            }
        }
        
        // Atalhos de teclado
        document.addEventListener('keydown', (e) => {
            if (currentMode !== 'manual') return;
            
            switch(e.key) {
                case 'ArrowUp':
                case 'w':
                    move('forward');
                    break;
                case 'ArrowDown':
                case 's':
                    move('backward');
                    break;
                case 'ArrowLeft':
                case 'a':
                    move('left');
                    break;
                case 'ArrowRight':
                case 'd':
                    move('right');
                    break;
                case ' ':
                    stop();
                    e.preventDefault();
                    break;
            }
        });
        
        document.addEventListener('keyup', (e) => {
            if (currentMode !== 'manual') return;
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'a', 's', 'd'].includes(e.key)) {
                stop();
            }
        });
        
        // Marcar modo manual como ativo ao carregar
        document.getElementById('btn-manual').classList.add('active');
        document.getElementById('btn-led-off').classList.add('active');
    </script>
</body>
</html>
    """
    return render_template_string(html)

@app.route('/video_feed')
def video_feed():
    """Stream de vídeo"""
    def generate():
        while True:
            if robot and robot.camera_active and robot.camera_available:
                frame = robot.get_camera_frame()
                if frame is not None:
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.03)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# SocketIO eventos
@socketio.on('connect')
def handle_connect():
    """Cliente conectado"""
    print('Cliente conectado')
    emit('status', {
        'message': 'Conectado ao robô',
        'led_available': robot.led_available if robot else False,
        'camera_available': robot.camera_available if robot else False,
        'ai_available': robot.ai_available if robot else False
    })

@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectado"""
    print('Cliente desconectado')
    if robot:
        robot.motor.set_motor_model(0, 0, 0, 0)

@socketio.on('motor_control')
def handle_motor(data):
    """Controle do motor"""
    if robot and robot.car_mode == 'manual':
        try:
            fl = int(data.get('fl', 0))
            bl = int(data.get('bl', 0))
            fr = int(data.get('fr', 0))
            br = int(data.get('br', 0))
            robot.motor.set_motor_model(fl, bl, fr, br)
        except Exception as e:
            print(f"Erro no controle do motor: {e}")

@socketio.on('led_mode')
def handle_led_mode(data):
    """Modo de LED"""
    if robot:
        if not robot.led_available:
            emit('status', {'message': 'LED não disponível neste sistema'})
            return
        try:
            mode = data.get('mode', 'off')
            robot.led_mode = mode
            emit('status', {'message': f'Modo LED: {mode}'})
        except Exception as e:
            print(f"Erro no modo LED: {e}")

@socketio.on('car_mode')
def handle_car_mode(data):
    """Modo do carro"""
    if robot:
        try:
            mode = data.get('mode', 'manual')
            
            # Verificar se modo IA está disponível
            if mode in ['ai', 'ai_vision'] and not robot.ai_available:
                emit('status', {'message': 'IA não disponível. Configure GROQ_API_KEY'})
                return
            
            # Desabilitar IA se estava ativo
            if robot.car_mode in ['ai', 'ai_vision']:
                robot.ai_enabled = False
            
            # Mudar modo
            robot.car_mode = mode
            
            # Ativar IA se necessário
            if mode in ['ai', 'ai_vision']:
                robot.ai_enabled = True
                emit('status', {'message': f'🤖 Modo IA ativado: {mode}'})
            else:
                robot.motor.set_motor_model(0, 0, 0, 0)
                emit('status', {'message': f'Modo: {mode}'})
                
        except Exception as e:
            print(f"Erro no modo do carro: {e}")

@socketio.on('camera_toggle')
def handle_camera(data):
    """Toggle da câmera"""
    if robot:
        if not robot.camera_available:
            emit('status', {'message': 'Câmera não disponível'})
            return
        try:
            robot.camera_active = bool(data.get('active', False))
            emit('status', {'message': f'Câmera: {"Ativa" if robot.camera_active else "Inativa"}'})
        except Exception as e:
            print(f"Erro no toggle da câmera: {e}")

if __name__ == '__main__':
    try:
        print("=" * 60)
        print("🚗 Iniciando servidor web do Freenove AI Car...")
        print("=" * 60)
        init_robot()
        
        # Obter IP
        import socket
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        
        print("\n" + "=" * 60)
        print("✓ Robô inicializado!")
        print(f"✓ Acesse: http://{ip}:5000")
        print(f"✓ IA disponível: {'Sim' if robot.ai_available else 'Não'}")
        print("=" * 60 + "\n")
        
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n\nEncerrando servidor...")
    finally:
        if robot:
            robot.cleanup()
        print("\n✓ Servidor encerrado com sucesso!")