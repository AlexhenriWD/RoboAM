#!/usr/bin/env python3
"""
EVA ROBOT - MAIN CONTROLLER (VERSÃO CORRIGIDA)
Sistema principal que integra: motores, câmeras, braço, sensores

CORREÇÕES:
- Direção dos motores invertida corrigida
- Suporte a 4 servos completo
- Pi Camera corrigida
- Ultrasonic sempre ativo
"""

import sys
import time
import threading
from typing import Optional, Dict, Union
from enum import Enum
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importar do robot_core original
try:
    from robot_core import Servo, Ordinary_Car, Ultrasonic, ADC
    HARDWARE_AVAILABLE = True
except Exception as e:
    print("⚠️  robot_core não encontrado. Usando modo simulação.")
    print("ERRO REAL:", e)
    
    # Criar classes dummy para type checking
    class Servo:
        pass
    class Ordinary_Car:
        pass
    class Ultrasonic:
        pass
    class ADC:
        pcb_version = 1
    HARDWARE_AVAILABLE = False

# Módulos locais
from camera_manager import CameraManager, CameraType
from arm_controller import ArmController
from camera_manager import CameraManager, CameraType
from robot_state import STATE, RobotMode
from arm_controller import ArmController
from robot_core import Servo, Ordinary_Car, Ultrasonic
from safety import SafetyController
import time


class RobotMode(Enum):
    """Modos de operação do robô"""
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"
    FOLLOW = "follow"
    PATROL = "patrol"
    IDLE = "idle"

class EVARobot:
    def __init__(self):
        print("🤖 Inicializando EVA Robot...")

        # ==========================
        # HARDWARE
        # ==========================
        self.servo = Servo()
        self.motor = Ordinary_Car()
        self.ultrasonic = Ultrasonic()

        # ==========================
        # SUBSISTEMAS
        # ==========================
        self.arm = ArmController(self.servo)
        self.camera_manager = CameraManager(
            picam_id=0,
            usb_id=1,
            width=640,
            height=480,
            fps=15
        )
        self.safety = SafetyController(self)

        # ==========================
        # ESTADO
        # ==========================
        self.mode = RobotMode.IDLE
        self.running = False

        self.invert_left = 1   # troque para -1 se lado esquerdo estiver invertido
        self.invert_right = 1  # troque para -1 se lado direito estiver invertido


        print("✅ EVA Robot inicializado")

    # ==================================================
    # START / STOP
    # ==================================================

    def start(self) -> bool:
        print("🚀 Iniciando EVA Robot...")
        self.running = True

        if not self.camera_manager.start():
            print("⚠️  Sistema iniciado sem câmera")

        self.arm.move_to_home()
        STATE.update(mode=RobotMode.IDLE)

        return True

    def stop(self):
        print("🛑 Parando EVA Robot...")
        self.running = False

        self.motor.set_motor_model(0, 0, 0, 0)
        self.camera_manager.stop()

    # ==================================================
    # MOVIMENTO
    # ==================================================

    def _apply_inv(self, fl, bl, fr, br):
        fl *= self.invert_left
        bl *= self.invert_left
        fr *= self.invert_right
        br *= self.invert_right
        return fl, bl, fr, br

    def move_forward(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(speed, speed, speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)

    def move_backward(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(-speed, -speed, -speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)

    def turn_left(self, speed=1500):
        # esquerda pra trás, direita pra frente
        fl, bl, fr, br = self._apply_inv(-speed, -speed, speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)

    def turn_right(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(speed, speed, -speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)

    def set_motor_inversion(self, invert_left: bool, invert_right: bool):
        self.invert_left = -1 if invert_left else 1
        self.invert_right = -1 if invert_right else 1
        print(f"🔧 Inversão motores: left={invert_left} right={invert_right}")

    def stop_motors(self):
        self.motor.set_motor_model(0, 0, 0, 0)
        STATE.set_motors(0, 0, 0, 0)

    # ==================================================
    # BRAÇO / CABEÇA
    # ==================================================

    def arm_set_angle(self, channel: int, angle: int, smooth=False):
        ok, reason = self.safety.validate_servo_command(channel, angle)
        if not ok:
            print(f"❌ Servo bloqueado: {reason}")
            return False

        result = self.arm.set_angle(channel, angle, smooth)
        if result:
            STATE.set_servo(channel, angle)
        return result

    def arm_look_left(self, deg=30):
        return self.arm.look_left(deg)

    def arm_look_right(self, deg=30):
        return self.arm.look_right(deg)

    def arm_look_up(self, deg=20):
        return self.arm.look_up(deg)

    def arm_look_down(self, deg=20):
        return self.arm.look_down(deg)

    def arm_look_center(self):
        return self.arm.look_center()

    # ==================================================
    # CÂMERA
    # ==================================================

    def switch_camera(self, camera_type: CameraType = None):
        self.camera_manager.switch_camera(camera_type)
        STATE.update(active_camera=self.camera_manager.get_active_camera_type().value)

    def get_camera_frame_encoded(self, quality=70):
        return self.camera_manager.get_frame_encoded(quality)

    # ==================================================
    # ESTADO / STATUS
    # ==================================================

    def set_mode(self, mode: RobotMode):
        self.mode = mode
        STATE.update(mode=mode)

    def get_status(self) -> dict:
        return {
            "mode": self.mode.value,
            "camera": self.camera_manager.get_status(),
            "arm": self.arm.get_status(),
            "safety": self.safety.get_status()
        }

    def print_status(self):
        print("\n🤖 EVA ROBOT STATUS")
        print(self.get_status())

    
    # ========================================================================
    # FINALIZAÇÃO
    # ========================================================================
    
    def stop(self):
        """Para todos os sistemas"""
        print("\n🛑 Parando EVA Robot...")
        
        self.is_running = False
        self.stop_event.set()
        
        # Parar motores
        self.stop_motors()
        
        # Parar câmeras
        if self.camera_manager is not None:
            self.camera_manager.stop()
        
        # Aguardar thread
        if self.monitor_thread is not None:
            self.monitor_thread.join(timeout=2.0)
        
        # Liberar hardware
        if self.motor is not None:
            self.motor.close()
        if self.ultrasonic is not None:
            self.ultrasonic.close()
        if self.adc is not None:
            self.adc.close_i2c()
        
        print("✅ EVA Robot finalizado")
    
    def __del__(self):
        """Destrutor"""
        try:
            self.stop()
        except:
            pass


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 TESTE: EVA ROBOT (VERSÃO CORRIGIDA)")
    print("="*60 + "\n")
    
    robot = EVARobot()
    
    try:
        if not robot.start():
            print("⚠️  Robô iniciado em modo limitado")
        
        # Status inicial
        robot.print_status()
        
        print("\n💡 Comandos disponíveis:")
        print("   w - Frente")
        print("   s - Trás")
        print("   a - Esquerda")
        print("   d - Direita")
        print("   q - Strafe Esquerda")
        print("   e - Strafe Direita")
        print("   x - Parar")
        print("   c - Trocar câmera")
        print("   i - Inverter motores")
        print("   u - Status ultrasonic")
        print("   0-3 - Testar servo (0=Yaw, 1=Pitch, 2=Elbow, 3=Head)")
        print("   h - Home (centralizar braço)")
        print("   ? - Status")
        print("   Ctrl+C - Sair\n")
        
        # Loop de comandos
        import sys
        import select
        import tty
        import termios
        
        # Configurar terminal para leitura sem buffer
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            
            while True:
                # Verificar se há entrada
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1).lower()
                    
                    if key == 'w':
                        print("⬆️  Frente")
                        robot.move_forward(1500)
                    elif key == 's':
                        print("⬇️  Trás")
                        robot.move_backward(1500)
                    elif key == 'a':
                        print("⬅️  Esquerda")
                        robot.turn_left(1500)
                    elif key == 'd':
                        print("➡️  Direita")
                        robot.turn_right(1500)
                    elif key == 'q':
                        print("↖️  Strafe Esquerda")
                        robot.strafe_left(1500)
                    elif key == 'e':
                        print("↗️  Strafe Direita")
                        robot.strafe_right(1500)
                    elif key == 'x':
                        print("🛑 Parar")
                        robot.stop_motors()
                    elif key == 'c':
                        print("📷 Trocar câmera")
                        robot.switch_camera()
                    elif key == 'i':
                        # Inverter motores
                        robot.invert_left *= -1
                        robot.invert_right *= -1
                        print(f"🔧 Inversão: L={robot.invert_left == -1}, R={robot.invert_right == -1}")
                    elif key == 'u':
                        robot.read_sensors_now()
                        print(f"📏 Distância: {robot.get_distance():.1f} cm")
                    elif key in ['0', '1', '2', '3']:
                        channel = int(key)
                        print(f"🦾 Testando servo {channel}...")
                        robot.arm_set_angle(channel, 60)
                        time.sleep(1)
                        robot.arm_set_angle(channel, 120)
                        time.sleep(1)
                        robot.arm_set_angle(channel, 90)
                    elif key == 'h':
                        print("🏠 Home (centralizando)")
                        robot.arm_look_center()
                    elif key == '?':
                        robot.print_status()
                    
                time.sleep(0.05)
        
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário")
    
    finally:
        robot.stop()
        print("\n✅ Teste finalizado")