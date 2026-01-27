#!/usr/bin/env python3
"""
EVA ROBOT - ARM/HEAD CONTROLLER
Controle do braço robótico usado como cabeça/pescoço
"""

import time
import threading
from typing import Dict, Optional, Tuple
from enum import Enum


class ServoJoint(Enum):
    """Juntas do braço/cabeça"""
    YAW = 0      # Base - rotação horizontal (pan)
    PITCH = 1    # Ombro - inclinação vertical (tilt)
    ELBOW = 2    # Cotovelo - movimento adicional
    HEAD = 3     # Cabeça extra
    GRIPPER = 4  # Garra (opcional)


class ArmController:
    """Controlador do braço robótico"""
    
    def __init__(self, servo_controller):
        """
        Inicializa o controlador do braço
        
        Args:
            servo_controller: Instância do Servo() do robot_core
        """
        self.servo = servo_controller
        
        # Posições atuais
        self.current_angles: Dict[int, int] = {
            0: 90,  # Yaw
            1: 90,  # Pitch
            2: 90,  # Elbow
            3: 90,  # Head
            4: 70,  # Gripper
        }
        
        # Limites de segurança
        self.limits: Dict[int, Tuple[int, int]] = {
            0: (0, 180),    # Yaw
            1: (0, 180),    # Pitch
            2: (0, 180),    # Elbow
            3: (0, 180),    # Head
            4: (40, 100),   # Gripper
        }
        
        # Velocidades (graus por comando)
        self.step_size = 5  # Movimento discreto
        self.smooth_step = 2  # Movimento suave
        
        # Estado
        self.is_moving = False
        self.last_move_time = 0
        self.move_delay = 0.05  # Delay entre movimentos
        
        print("🦾 ArmController inicializado")
    
    def move_to_home(self):
        """Move para posição HOME (90° em todos os servos)"""
        print("🏠 Movendo para HOME...")
        
        for channel in [0, 1, 2, 3]:
            self.set_angle(channel, 90, smooth=True)
        
        time.sleep(0.5)
        print("✅ Posição HOME alcançada")
    
    def set_angle(self, channel: int, angle: int, smooth: bool = False) -> bool:
        """
        Define ângulo de um servo
        
        Args:
            channel: Canal do servo (0-4)
            angle: Ângulo desejado (0-180)
            smooth: Se True, move suavemente
        
        Returns:
            True se movimento foi executado
        """
        # Validar canal
        if channel not in self.limits:
            print(f"⚠️  Canal inválido: {channel}")
            return False
        
        # Aplicar limites
        min_angle, max_angle = self.limits[channel]
        angle = max(min_angle, min(max_angle, angle))
        
        # Verificar se já está na posição
        current = self.current_angles[channel]
        if abs(angle - current) < 2:
            return True
        
        # Movimento suave
        if smooth:
            return self._move_smooth(channel, angle)
        else:
            return self._move_direct(channel, angle)
    
    def _move_direct(self, channel: int, angle: int) -> bool:
        """Movimento direto para o ângulo"""
        try:
            self.servo.set_servo_pwm(str(channel), angle)
            self.current_angles[channel] = angle
            self.last_move_time = time.time()
            return True
        except Exception as e:
            print(f"❌ Erro ao mover servo {channel}: {e}")
            return False
    
    def _move_smooth(self, channel: int, target_angle: int) -> bool:
        """Movimento suave até o ângulo"""
        current = self.current_angles[channel]
        step = self.smooth_step if target_angle > current else -self.smooth_step
        
        while abs(target_angle - current) > abs(step):
            current += step
            
            try:
                self.servo.set_servo_pwm(str(channel), current)
                self.current_angles[channel] = current
                time.sleep(0.03)
            except Exception as e:
                print(f"❌ Erro no movimento suave: {e}")
                return False
        
        # Movimento final
        return self._move_direct(channel, target_angle)
    
    def move_relative(self, channel: int, delta: int) -> bool:
        """
        Move servo de forma relativa
        
        Args:
            channel: Canal do servo
            delta: Variação em graus (positivo ou negativo)
        """
        current = self.current_angles[channel]
        new_angle = current + delta
        return self.set_angle(channel, new_angle)
    
    # ========================================================================
    # MOVIMENTOS DE CABEÇA (YAW + PITCH)
    # ========================================================================
    
    def look_left(self, degrees: int = 45):
        """Olhar para esquerda"""
        return self.set_angle(ServoJoint.YAW.value, 90 - degrees)
    
    def look_right(self, degrees: int = 45):
        """Olhar para direita"""
        return self.set_angle(ServoJoint.YAW.value, 90 + degrees)
    
    def look_up(self, degrees: int = 30):
        """Olhar para cima"""
        current_pitch = self.current_angles[ServoJoint.PITCH.value]
        return self.set_angle(ServoJoint.PITCH.value, current_pitch - degrees)
    
    def look_down(self, degrees: int = 30):
        """Olhar para baixo"""
        current_pitch = self.current_angles[ServoJoint.PITCH.value]
        return self.set_angle(ServoJoint.PITCH.value, current_pitch + degrees)
    
    def look_center(self):
        """Centralizar cabeça"""
        self.set_angle(ServoJoint.YAW.value, 90)
        self.set_angle(ServoJoint.PITCH.value, 90)
    
    def pan(self, angle: int):
        """
        Pan horizontal (yaw)
        
        Args:
            angle: -90 (esquerda) até +90 (direita)
        """
        absolute_angle = 90 + angle
        return self.set_angle(ServoJoint.YAW.value, absolute_angle)
    
    def tilt(self, angle: int):
        """
        Tilt vertical (pitch)
        
        Args:
            angle: -45 (cima) até +45 (baixo)
        """
        absolute_angle = 90 + angle
        return self.set_angle(ServoJoint.PITCH.value, absolute_angle)
    
    # ========================================================================
    # POSES PRÉ-DEFINIDAS
    # ========================================================================
    
    def pose_home(self):
        """Pose HOME - neutro"""
        self.set_angle(0, 90)
        self.set_angle(1, 90)
        self.set_angle(2, 90)
        self.set_angle(3, 90)
    
    def pose_look_forward(self):
        """Pose olhando para frente"""
        self.set_angle(0, 90)   # Yaw centro
        self.set_angle(1, 110)  # Pitch ligeiramente para baixo
        self.set_angle(2, 90)   # Elbow neutro
    
    def pose_look_down(self):
        """Pose olhando para baixo (ver o chão)"""
        self.set_angle(0, 90)   # Yaw centro
        self.set_angle(1, 140)  # Pitch bem para baixo
        self.set_angle(2, 120)  # Elbow auxiliar
    
    def pose_scan_left(self):
        """Pose scan esquerda"""
        self.set_angle(0, 45)   # Yaw esquerda
        self.set_angle(1, 110)  # Pitch ligeiramente para baixo
    
    def pose_scan_right(self):
        """Pose scan direita"""
        self.set_angle(0, 135)  # Yaw direita
        self.set_angle(1, 110)  # Pitch ligeiramente para baixo
    
    # ========================================================================
    # CONTROLE DE GARRA
    # ========================================================================
    
    def gripper_open(self):
        """Abrir garra"""
        return self.set_angle(ServoJoint.GRIPPER.value, 100)
    
    def gripper_close(self):
        """Fechar garra"""
        return self.set_angle(ServoJoint.GRIPPER.value, 40)
    
    def gripper_half(self):
        """Garra meio aberta"""
        return self.set_angle(ServoJoint.GRIPPER.value, 70)
    
    # ========================================================================
    # MOVIMENTOS COMPOSTOS
    # ========================================================================
    
    def scan_area(self, steps: int = 5):
        """
        Faz scan da área (pan da esquerda para direita)
        
        Args:
            steps: Número de passos no scan
        """
        print("🔍 Iniciando scan...")
        
        angles = [int(45 + (90 * i / (steps - 1))) for i in range(steps)]
        
        for angle in angles:
            self.set_angle(ServoJoint.YAW.value, angle, smooth=True)
            time.sleep(0.5)
        
        # Voltar ao centro
        self.look_center()
        print("✅ Scan concluído")
    
    def nod_yes(self, times: int = 3):
        """Movimento de 'sim' com a cabeça"""
        for _ in range(times):
            self.look_down(15)
            time.sleep(0.3)
            self.look_up(15)
            time.sleep(0.3)
        self.look_center()
    
    def shake_no(self, times: int = 3):
        """Movimento de 'não' com a cabeça"""
        for _ in range(times):
            self.look_left(30)
            time.sleep(0.3)
            self.look_right(30)
            time.sleep(0.3)
        self.look_center()
    
    # ========================================================================
    # INFORMAÇÕES
    # ========================================================================
    
    def get_current_angles(self) -> Dict[int, int]:
        """Retorna ângulos atuais de todos os servos"""
        return self.current_angles.copy()
    
    def get_angle(self, channel: int) -> Optional[int]:
        """Retorna ângulo atual de um servo"""
        return self.current_angles.get(channel)
    
    def get_status(self) -> dict:
        """Retorna status do braço"""
        return {
            'angles': self.current_angles.copy(),
            'is_moving': self.is_moving,
            'yaw': self.current_angles[0],
            'pitch': self.current_angles[1],
            'elbow': self.current_angles[2],
            'head': self.current_angles[3],
            'gripper': self.current_angles[4],
        }
    
    def print_status(self):
        """Imprime status atual"""
        print("\n" + "="*50)
        print("🦾 ARM STATUS")
        print("="*50)
        print(f"Yaw (Pan):     {self.current_angles[0]:3d}°")
        print(f"Pitch (Tilt):  {self.current_angles[1]:3d}°")
        print(f"Elbow:         {self.current_angles[2]:3d}°")
        print(f"Head:          {self.current_angles[3]:3d}°")
        print(f"Gripper:       {self.current_angles[4]:3d}°")
        print("="*50 + "\n")


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🦾 TESTE: ARM CONTROLLER")
    print("="*60 + "\n")
    
    try:
        # Mock do servo para teste sem hardware
        class MockServo:
            def set_servo_pwm(self, channel, angle):
                print(f"   → Servo {channel}: {angle}°")
        
        servo = MockServo()
        arm = ArmController(servo)
        
        # Teste de movimentos
        print("\n1️⃣  Testando pose HOME...")
        arm.pose_home()
        time.sleep(1)
        
        print("\n2️⃣  Testando look left...")
        arm.look_left(45)
        time.sleep(1)
        
        print("\n3️⃣  Testando look right...")
        arm.look_right(45)
        time.sleep(1)
        
        print("\n4️⃣  Testando look down...")
        arm.pose_look_down()
        time.sleep(1)
        
        print("\n5️⃣  Testando scan...")
        arm.scan_area(steps=5)
        
        print("\n6️⃣  Testando nod yes...")
        arm.nod_yes(times=2)
        
        print("\n7️⃣  Status final:")
        arm.print_status()
        
        print("✅ Teste concluído!")
    
    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        import traceback
        traceback.print_exc()