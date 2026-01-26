import sys
import time
import cv2
from pathlib import Path

# Adiciona a pasta hardware ao caminho de busca do Python
sys.path.insert(0, str(Path(__file__).parent / 'hardware'))

try:
    from motor import Ordinary_Car
    from servo import Servo
    from ultrasonic import Ultrasonic
    HARDWARE_OK = True
except ImportError:
    HARDWARE_OK = False
    print("⚠️  Arquivos da pasta 'hardware' não encontrados!")

class EVARobotCore:
    def __init__(self):
        self.car = None
        self.servos = None
        self.cap = None
        self.current_camera_id = 0 

    def initialize(self):
        if not HARDWARE_OK: return False
        try:
            self.car = Ordinary_Car()
            self.servos = Servo()
            # Abre a câmera UMA VEZ para não travar o sistema
            self.cap = cv2.VideoCapture(self.current_camera_id)
            return True
        except Exception as e:
            print(f"Erro hardware: {e}")
            return False

    def drive(self, vx=0, vy=0, vz=0):
        """Lógica para o kit Freenove 4WD"""
        if not self.car: return
        if vx > 0: self.car.forward()
        elif vx < 0: self.car.backward()
        elif vz > 0: self.car.left()
        elif vz < 0: self.car.right()
        else: self.car.stop()

    def stop(self):
        if self.car: self.car.stop()

    def move_servo(self, channel, angle):
        if self.servos:
            # No Freenove o canal é string ('0', '1', etc)
            self.servos.setServoPwm(str(channel), int(angle))

    def get_camera_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret: return frame
        return None

    # Métodos de compatibilidade para o servidor não dar erro
    def read_sensors(self): return {"status": "ok"}
    def get_camera_status(self): return {"active_camera": "default"}
    def force_camera(self, cam): pass
    def disable_arm_camera(self): pass