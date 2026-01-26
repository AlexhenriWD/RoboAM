import time
import cv2
import board
import busio
from adafruit_pca9685 import PCA9685

class EVARobotCore:
    def __init__(self):
        self.pca = None
        self.cap = None 
        self.active_camera_index = 0
        self.motor_channels = [0, 1, 2, 3] # Ajuste conforme sua fiação

    def initialize(self):
        try:
            # Inicializa barramento I2C e PCA9685
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca = PCA9685(i2c)
            self.pca.frequency = 50
            
            # Inicializa a câmera UMA VEZ para evitar gargalo
            self.cap = cv2.VideoCapture(self.active_camera_index)
            if not self.cap.isOpened():
                print("⚠️ Aviso: Câmera não detectada, mas continuando sem vídeo.")
            
            return True
        except Exception as e:
            print(f"❌ Erro na inicialização do hardware: {e}")
            return False

    def drive(self, vx=0, vy=0, vz=0):
        """Controla os motores baseado na velocidade"""
        if not self.pca: return
        
        # Lógica de PWM para frente/trás (exemplo simples)
        speed = int(abs(vx) * 0xFFFF)
        for ch in self.motor_channels:
            self.pca.channels[ch].duty_cycle = speed

    def move_servo(self, channel, angle, smooth=True, enable_camera=True):
        """Move os servos do braço ou cabeça"""
        if not self.pca or not (0 <= channel <= 15): return
        # Mapeia 0-180 graus para o ciclo de trabalho do PCA9685
        pulse = int((angle / 180.0 * 2000 + 500) * 65535 / 20000)
        self.pca.channels[channel].duty_cycle = pulse

    def stop(self):
        """Para todos os motores imediatamente"""
        if self.pca:
            for ch in range(16):
                self.pca.channels[ch].duty_cycle = 0

    def get_camera_frame(self):
        """Captura frame da câmera aberta"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    # Métodos necessários para compatibilidade com o servidor
    def read_sensors(self):
        return {"status": "online", "battery": "100%"}

    def get_camera_status(self):
        return {"active_camera": "USB/Default"}

    def force_camera(self, camera_type):
        print(f"🔄 Solicitada troca para: {camera_type}")

    def disable_arm_camera(self):
        print("🦾 Câmera do braço desativada")