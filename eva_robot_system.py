import time
import cv2
import numpy as np

# Importa as bibliotecas específicas do seu kit Freenove
try:
    from motor import Ordinary_Car
    from servo import Servo
    from ultrasonic import Ultrasonic
    from adc import ADC
    # Adicione outros se necessário (buzzer, led, etc)
    HARDWARE_OK = True
except ImportError as e:
    print(f"⚠️ Erro ao importar bibliotecas Freenove: {e}")
    HARDWARE_OK = False

class EVARobotCore:
    def __init__(self):
        self.car = None
        self.servo = None
        self.ultrasonic = None
        self.cap = None
        self.active_camera_index = 0

    def initialize(self):
        if not HARDWARE_OK:
            print("❌ Hardware não encontrado. Verifique se os arquivos .py do kit estão na pasta.")
            return False
        
        try:
            self.car = Ordinary_Car()
            self.servo = Servo()
            self.ultrasonic = Ultrasonic()
            
            # Abre a câmera UMA VEZ para não travar o sistema
            self.cap = cv2.VideoCapture(self.active_camera_index)
            return True
        except Exception as e:
            print(f"❌ Erro ao iniciar componentes: {e}")
            return False

    def drive(self, vx=0, vy=0, vz=0):
        """Usa a lógica da classe Ordinary_Car do seu kit"""
        if not self.car: return
        
        # O kit Freenove geralmente usa valores de -1500 a 1500 ou 0 a 100
        # Adaptando para a lógica do Ordinary_Car:
        if vx > 0:
            self.car.forward()
        elif vx < 0:
            self.car.backward()
        elif vz > 0:
            self.car.left()
        elif vz < 0:
            self.car.right()
        else:
            self.car.stop()

    def move_servo(self, channel, angle, smooth=True, enable_camera=True):
        """Usa a função setServoPwm do seu kit (conforme página 141 do manual)"""
        if self.servo:
            # O canal no Freenove costuma ser string '0', '1', etc.
            self.servo.setServoPwm(str(channel), int(angle))

    def stop(self):
        if self.car:
            self.car.stop()

    def get_camera_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    def read_sensors(self):
        """Lê os sensores reais do kit"""
        dist = 0
        if self.ultrasonic:
            try: dist = self.ultrasonic.get_distance()
            except: pass
        return {"ultrasonic_cm": dist, "status": "online"}

    def get_camera_status(self):
        return {"active_camera": "Freenove Cam"}

    def force_camera(self, camera_type): pass
    def disable_arm_camera(self): pass