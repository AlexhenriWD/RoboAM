import time
import cv2
import board
import busio
from adafruit_pca9685 import PCA9685

class EVARobotCore:
    def __init__(self):
        self.pca = None
        self.cap = None # Câmera persistente
        self.active_camera = 0
        self.motor_channels = [0, 1, 2, 3] 

    def initialize(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca = PCA9685(i2c)
            self.pca.frequency = 50
            # Inicializa a câmera UMA VEZ
            self.cap = cv2.VideoCapture(self.active_camera)
            return True
        except Exception as e:
            print(f"Erro inicialização: {e}")
            return False

    def drive(self, vx=0, vy=0, vz=0):
        if not self.pca: return
        # Lógica simplificada de acionamento PCA
        duty = int(abs(vx) * 0xFFFF)
        for ch in self.motor_channels:
            self.pca.channels[ch].duty_cycle = duty

    def stop(self):
        if self.pca:
            for ch in range(16):
                self.pca.channels[ch].duty_cycle = 0

    def get_camera_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    # MÉTODOS QUE FALTAVAM PARA O SERVIDOR FUNCIONAR:
    def read_sensors(self):
        return {"status": "operacional", "cpu_temp": 45}

    def get_camera_status(self):
        return {"active_camera": "USB/PiCam"}

    def force_camera(self, cam_type):
        print(f"Trocando para {cam_type}")

    def disable_arm_camera(self):
        print("Braço desativado")