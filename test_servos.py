#!/usr/bin/env python3
from servo import Servo
import time

class RoboticArmCalibration:
    def __init__(self):
        self.servo = Servo()
        
        # Limites seguros (ajuste após testes!)
        self.limits = {
            0: {'name': 'Base', 'min': 10, 'max': 170},
            1: {'name': 'Ombro', 'min': 20, 'max': 160},
            2: {'name': 'Cotovelo', 'min': 30, 'max': 150},
            3: {'name': 'Garra', 'min': 40, 'max': 140}
        }
    
    def safe_move(self, channel, angle, delay=0.3):
        """Move servo com verificação de limites"""
        limits = self.limits[channel]
        
        if angle < limits['min'] or angle > limits['max']:
            print(f"⚠️  Ângulo {angle}° fora dos limites seguros para {limits['name']}")
            return False
        
        self.servo.set_servo_pwm(str(channel), angle)
        time.sleep(delay)
        return True
    
    def home_position(self):
        """Posição inicial segura"""
        print("🏠 Movendo para posição inicial...")
        for channel in range(4):
            self.safe_move(channel, 90, delay=0.5)
        print("✓ Posição inicial alcançada!")
    
    def test_servo(self, channel):
        """Testa um servo específico"""
        limits = self.limits[channel]
        print(f"\n🔧 Testando {limits['name']} (Canal {channel})")
        
        # Centro -> Min -> Centro -> Max -> Centro
        sequence = [90, limits['min'], 90, limits['max'], 90]
        
        for angle in sequence:
            print(f"  Movendo para {angle}°...")
            self.safe_move(channel, angle, delay=0.8)
        
        print(f"✓ {limits['name']} testado!")
    
    def test_all(self):
        """Testa todos os servos sequencialmente"""
        self.home_position()
        time.sleep(1)
        
        for channel in range(4):
            self.test_servo(channel)
            time.sleep(1)
        
        self.home_position()
        print("\n✓ Todos os servos testados!")

if __name__ == '__main__':
    arm = RoboticArmCalibration()
    
    try:
        print("=" * 50)
        print("🤖 Calibração do Braço Robótico MG90S")
        print("=" * 50)
        
        arm.test_all()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Teste interrompido!")
        arm.home_position()