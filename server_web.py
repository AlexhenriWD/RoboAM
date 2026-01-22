#!/usr/bin/env python3
"""
Servidor Web para controle do Freenove Smart Car com IA
Versão otimizada - removido LED e Servo, corrigido controle motor
"""

from flask import Flask, render_template, Response, jsonify, request
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
        self.ultrasonic = None
        self.infrared = None
        self.adc = None
        self.buzzer = None
        self.groq_client = None
        
        self.camera_available = CAMERA_AVAILABLE
        self.ai_available = AI_AVAILABLE
        
        # Estados
        self.car_mode = 'manual'  # manual, ultrasonic, infrared, light, ai, ai_vision
        self.camera_active = False
        self.ai_enabled = False
        
        # Threads
        self.sensor_thread = None
        self.auto_mode_thread = None
        
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
            
            self.ultrasonic = Ultrasonic()
            print("✓ Ultrasonic inicializado")
            
            self.infrared = Infrared()
            print("✓ Infrared inicializado")
            
            self.adc = ADC()
            print("✓ ADC inicializado")
            
            self.buzzer = Buzzer()
            print("✓ Buzzer inicializado")
            
            # Beep de inicialização (3 beeps curtos)
            for _ in range(3):
                self.buzzer.set_state(True)
                time.sleep(0.1)
                self.buzzer.set_state(False)
                time.sleep(0.1)
            print("✓ Beep de inicialização concluído")
            
            # Inicializar webcam USB se OpenCV disponível
            if self.camera_available:
                try:
                    self.camera = cv2.VideoCapture(0)
                    if self.camera.isOpened():
                        # Resolução maior para melhor qualidade
                        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        self.camera.set(cv2.CAP_PROP_FPS, 30)
                        # Ajustes de qualidade
                        self.camera.set(cv2.CAP_PROP_BRIGHTNESS, 128)
                        self.camera.set(cv2.CAP_PROP_CONTRAST, 128)
                        self.camera.set(cv2.CAP_PROP_SATURATION, 128)
                        print("✓ Câmera inicializada (1280x720)")
                    else:
                        print("◯ Câmera não detectada")
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
                                rate_limit = config.get('rate_limit', 8)
                                self.groq_client = GroqVisionClient(api_key, rate_limit=rate_limit)
                                print(f"✓ Groq AI inicializada (limite: {rate_limit} req/min)")
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
            use_vision = (self.car_mode == 'ai_vision' and 
                         self.current_frame is not None)
            
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
                
                self._execute_ai_decision(decision)
                
                print(f"🤖 IA: {decision.get('recommended_action')} - {decision.get('reason')}")
            else:
                self.ai_stats['errors'] += 1
                print(f"⚠️ Erro IA: {result.get('error')}")
                self.motor.set_motor_model(0, 0, 0, 0)
            
            time.sleep(1.5)
            
        except Exception as e:
            print(f"Erro no modo IA: {e}")
            self.ai_stats['errors'] += 1
            self.motor.set_motor_model(0, 0, 0, 0)
            time.sleep(1)
    
    def _execute_ai_decision(self, decision):
        """Executa decisão da IA - INVERTIDO FRENTE/TRÁS"""
        action = decision.get('recommended_action', 'stop')
        speed_percent = decision.get('speed', 50)
        
        speed_percent = min(speed_percent, 60)
        speed = int((speed_percent / 100.0) * 2000)
        
        # INVERTIDO forward/backward
        if action == 'forward':
            self.motor.set_motor_model(-speed, -speed, -speed, -speed)
        elif action == 'backward':
            self.motor.set_motor_model(speed, speed, speed, speed)
        elif action == 'left':
            self.motor.set_motor_model(speed, speed, -speed, -speed)
        elif action == 'right':
            self.motor.set_motor_model(-speed, -speed, speed, speed)
        else:
            self.motor.set_motor_model(0, 0, 0, 0)
    
    def ultrasonic_mode(self):
        """Modo de navegação por ultrassom - INVERTIDO FRENTE/TRÁS"""
        distance = self.ultrasonic.get_distance() or 100
        
        if distance < 20:
            # INVERTIDO: backward (ré)
            self.motor.set_motor_model(1450, 1450, 1450, 1450)
            time.sleep(0.3)
            self.motor.set_motor_model(1450, 1450, -1450, -1450)
            time.sleep(0.3)
        elif distance < 40:
            # INVERTIDO: forward lento
            self.motor.set_motor_model(-400, -400, -400, -400)
        else:
            # INVERTIDO: forward normal
            self.motor.set_motor_model(-800, -800, -800, -800)
        
        time.sleep(0.1)
    
    def infrared_mode(self):
        """Modo de seguir linha"""
        ir_value = self.infrared.read_all_infrared()
        
        if ir_value == 2:
            self.motor.set_motor_model(-800, -800, -800, -800)
        elif ir_value == 4:
            self.motor.set_motor_model(2500, 2500, -1500, -1500)
        elif ir_value == 6:
            self.motor.set_motor_model(4000, 4000, -2000, -2000)
        elif ir_value == 1:
            self.motor.set_motor_model(-1500, -1500, 2500, 2500)
        elif ir_value == 3:
            self.motor.set_motor_model(-2000, -2000, 4000, 4000)
        elif ir_value == 7:
            self.motor.set_motor_model(0, 0, 0, 0)
        
        time.sleep(0.2)
    
    def light_mode(self):
        """Modo de seguir luz - INVERTIDO FRENTE/TRÁS"""
        L = self.adc.read_adc(0)
        R = self.adc.read_adc(1)
        
        if L < 2.99 and R < 2.99:
            # INVERTIDO: forward
            self.motor.set_motor_model(-600, -600, -600, -600)
        elif abs(L - R) < 0.15:
            self.motor.set_motor_model(0, 0, 0, 0)
        elif L > 3 or R > 3:
            if L > R:
                self.motor.set_motor_model(1400, 1400, -1200, -1200)
            else:
                self.motor.set_motor_model(-1200, -1200, 1400, 1400)
        
        time.sleep(0.2)
    
    def get_camera_frame(self):
        """Captura frame da webcam"""
        if self.camera_available and self.camera and self.camera.isOpened():
            ret, frame = self.camera.read()
            if ret:
                frame = cv2.resize(frame, (800, 600))
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
            self.buzzer.set_state(True)
            time.sleep(0.2)
            self.buzzer.set_state(False)
            self.buzzer.close()
            print("✓ Buzzer desligado")

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
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Stream de vídeo"""
    def generate():
        while True:
            if robot and robot.camera_active and robot.camera_available:
                frame = robot.get_camera_frame()
                if frame is not None:
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.03)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@socketio.on('connect')
def handle_connect():
    """Cliente conectado"""
    print('Cliente conectado')
    emit('status', {
        'message': 'Conectado ao robô',
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

@socketio.on('car_mode')
def handle_car_mode(data):
    """Modo do carro"""
    if robot:
        try:
            mode = data.get('mode', 'manual')
            
            if mode in ['ai', 'ai_vision'] and not robot.ai_available:
                emit('status', {'message': 'IA não disponível. Configure GROQ_API_KEY'})
                return
            
            if robot.car_mode in ['ai', 'ai_vision']:
                robot.ai_enabled = False
            
            robot.car_mode = mode
            
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