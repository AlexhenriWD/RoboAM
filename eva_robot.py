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


class RobotMode(Enum):
    """Modos de operação do robô"""
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"
    FOLLOW = "follow"
    PATROL = "patrol"
    IDLE = "idle"


class EVARobot:
    """Controlador principal do robô EVA (VERSÃO CORRIGIDA)"""
    
    def __init__(self):
        """Inicializa o robô EVA"""
        print("\n" + "="*60)
        print("🤖 EVA ROBOT - Inicializando (VERSÃO CORRIGIDA)...")
        print("="*60 + "\n")
        
        # Hardware
        self.servo: Optional[Servo] = None
        self.motor: Optional[Ordinary_Car] = None
        self.ultrasonic: Optional[Ultrasonic] = None
        self.adc: Optional[ADC] = None
        
        # Sistemas
        self.camera_manager: Optional[CameraManager] = None
        self.arm_controller: Optional[ArmController] = None
        
        # Estado
        self.mode = RobotMode.IDLE
        self.is_running = False
        self.safety_stop = False
        
        # Sensores
        self.distance = 999.0
        self.battery_voltage = 0.0
        self.last_sensor_read = 0
        
        # Thread de monitoramento
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # NOVO: Inversão de motores (ajustável)
        self.invert_left = -1   # -1 para inverter, 1 para normal
        self.invert_right = -1  # -1 para inverter, 1 para normal
        
        print("✅ EVARobot inicializado")
    
    def start(self) -> bool:
        """Inicia todos os sistemas do robô"""
        print("\n🚀 Iniciando sistemas...\n")
        
        success = True
        
        # 1. Hardware básico
        if not self._init_hardware():
            print("⚠️  Hardware não inicializado (modo simulação)")
            success = False
        
        # 2. Câmeras (CORRIGIDO: Pi Camera primeiro, depois USB)
        self.camera_manager = CameraManager(
            usb_device_id=1,      # USB webcam no /dev/video1
            picam_device_id=0     # Pi Camera no /dev/video0
        )
        if not self.camera_manager.start():
            print("❌ Falha ao iniciar câmeras")
            success = False
        else:
            # Definir Pi Camera como padrão
            self.camera_manager.switch_camera(CameraType.PICAM)
            print("📷 Pi Camera definida como padrão")
        
        # 3. Braço/Cabeça (CORRIGIDO: Suporte a 4 servos)
        if self.servo is not None:
            self.arm_controller = ArmController(self.servo)
            self.arm_controller.pose_home()
            print("🦾 Braço inicializado com 4 servos (0-3)")
        else:
            print("⚠️  Braço/cabeça não disponível (servo ausente)")
        
        # 4. Thread de monitoramento
        self.is_running = True
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        print("\n" + "="*60)
        if success:
            print("✅ Todos os sistemas iniciados com sucesso!")
        else:
            print("⚠️  Alguns sistemas não foram iniciados")
        print("="*60 + "\n")
        
        return success
    
    def _init_hardware(self) -> bool:
        """Inicializa hardware básico (motores, sensores)"""
        if not HARDWARE_AVAILABLE:
            print("⚠️  Hardware libraries não disponíveis (modo simulação)")
            return False
        
        try:
            # Servos
            self.servo = Servo()
            print("✅ Servos inicializados (canais 0-7 disponíveis)")
            
            # Motores
            self.motor = Ordinary_Car()
            print("✅ Motores inicializados")
            
            # Ultrasônico (SEMPRE ATIVO)
            self.ultrasonic = Ultrasonic()
            print("✅ Sensor ultrasônico inicializado (ATIVO)")
            
            # ADC (bateria, sensores)
            self.adc = ADC()
            print("✅ ADC inicializado")
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao inicializar hardware: {e}")
            return False
    
    def _monitor_loop(self):
        """Loop de monitoramento contínuo"""
        while not self.stop_event.is_set() and self.is_running:
            try:
                # Leitura de sensores a cada 100ms
                if time.time() - self.last_sensor_read >= 0.1:
                    self._read_sensors()
                    self.last_sensor_read = time.time()
                
                # Verificar segurança
                self._check_safety()
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"⚠️  Erro no monitor: {e}")
                time.sleep(0.1)
    
    def _read_sensors(self):
        """Lê todos os sensores"""
        # Distância ultrasônica
        if self.ultrasonic is not None:
            try:
                dist = self.ultrasonic.get_distance()
                if dist is not None:
                    self.distance = dist
            except Exception as e:
                # Silencioso - não logar erros frequentes
                pass
        
        # Tensão da bateria
        if self.adc is not None:
            try:
                voltage_raw = self.adc.read_adc(2)
                # Converter para voltagem real
                multiplier = 3 if self.adc.pcb_version == 1 else 2
                self.battery_voltage = voltage_raw * multiplier
            except:
                pass
    
    def _check_safety(self):
        """Verifica condições de segurança"""
        # Parada de emergência por obstáculo
        if self.distance < 10.0 and not self.safety_stop:
            print("🛑 SAFETY STOP: Obstáculo detectado!")
            self.stop_motors()
            self.safety_stop = True
        elif self.distance > 15.0 and self.safety_stop:
            # Liberar safety stop quando obstáculo se afasta
            self.safety_stop = False
        
        # Bateria baixa
        if self.battery_voltage > 0 and self.battery_voltage < 6.5:
            print(f"⚠️  Bateria baixa: {self.battery_voltage:.1f}V")
    
    # ========================================================================
    # CONTROLE DE MOVIMENTO (CORRIGIDO)
    # ========================================================================
    
    def move_forward(self, speed: int = 1500):
        """Move para frente (CORRIGIDO)"""
        if self.motor is not None and not self.safety_stop:
            # CORRIGIDO: Inverte os motores conforme necessário
            left_speed = speed * self.invert_left
            right_speed = speed * self.invert_right
            self.motor.set_motor_model(left_speed, left_speed, right_speed, right_speed)
    
    def move_backward(self, speed: int = 1500):
        """Move para trás (CORRIGIDO)"""
        if self.motor is not None:
            # CORRIGIDO: Inverte os motores conforme necessário
            left_speed = -speed * self.invert_left
            right_speed = -speed * self.invert_right
            self.motor.set_motor_model(left_speed, left_speed, right_speed, right_speed)
    
    def turn_left(self, speed: int = 1500):
        """Gira para esquerda (CORRIGIDO)"""
        if self.motor is not None and not self.safety_stop:
            # CORRIGIDO: Lado esquerdo para trás, direito para frente
            left_speed = -speed * self.invert_left
            right_speed = speed * self.invert_right
            self.motor.set_motor_model(left_speed, left_speed, right_speed, right_speed)
    
    def turn_right(self, speed: int = 1500):
        """Gira para direita (CORRIGIDO)"""
        if self.motor is not None and not self.safety_stop:
            # CORRIGIDO: Lado esquerdo para frente, direito para trás
            left_speed = speed * self.invert_left
            right_speed = -speed * self.invert_right
            self.motor.set_motor_model(left_speed, left_speed, right_speed, right_speed)
    
    def strafe_left(self, speed: int = 1500):
        """Desloca lateralmente para esquerda (Mecanum) (CORRIGIDO)"""
        if self.motor is not None and not self.safety_stop:
            # Padrão Mecanum: FL=back, BL=forward, FR=forward, BR=back
            fl = -speed * self.invert_left
            bl = speed * self.invert_left
            fr = speed * self.invert_right
            br = -speed * self.invert_right
            self.motor.set_motor_model(fl, bl, fr, br)
    
    def strafe_right(self, speed: int = 1500):
        """Desloca lateralmente para direita (Mecanum) (CORRIGIDO)"""
        if self.motor is not None and not self.safety_stop:
            # Padrão Mecanum: FL=forward, BL=back, FR=back, BR=forward
            fl = speed * self.invert_left
            bl = -speed * self.invert_left
            fr = -speed * self.invert_right
            br = speed * self.invert_right
            self.motor.set_motor_model(fl, bl, fr, br)
    
    def stop_motors(self):
        """Para todos os motores"""
        if self.motor is not None:
            self.motor.set_motor_model(0, 0, 0, 0)
        self.safety_stop = False
    
    def set_motor_model(self, fl: int, bl: int, fr: int, br: int):
        """
        Controle direto dos 4 motores (CORRIGIDO)
        
        Args:
            fl: Front Left
            bl: Back Left
            fr: Front Right
            br: Back Right
        """
        if self.motor is not None and not self.safety_stop:
            # Aplica inversões configuradas
            fl_adj = fl * self.invert_left
            bl_adj = bl * self.invert_left
            fr_adj = fr * self.invert_right
            br_adj = br * self.invert_right
            self.motor.set_motor_model(fl_adj, bl_adj, fr_adj, br_adj)
    
    def set_motor_inversion(self, invert_left: bool = True, invert_right: bool = True):
        """
        Configura inversão de motores
        
        Args:
            invert_left: Inverte motores esquerdos (True = invertido)
            invert_right: Inverte motores direitos (True = invertido)
        """
        self.invert_left = -1 if invert_left else 1
        self.invert_right = -1 if invert_right else 1
        print(f"🔧 Inversão de motores: Left={invert_left}, Right={invert_right}")
    
    # ========================================================================
    # CONTROLE DE CÂMERA (CORRIGIDO)
    # ========================================================================
    
    def switch_camera(self, camera_type: Optional[CameraType] = None):
        """Alterna entre câmeras (CORRIGIDO)"""
        if self.camera_manager is not None:
            self.camera_manager.switch_camera(camera_type)
            active = self.camera_manager.get_active_camera_type()
            print(f"📷 Câmera ativa: {active.value.upper()}")
    
    def get_camera_frame(self):
        """Retorna frame atual da câmera"""
        if self.camera_manager is not None:
            return self.camera_manager.get_frame()
        return None
    
    def get_camera_frame_encoded(self, quality: int = 70):
        """Retorna frame atual como JPEG"""
        if self.camera_manager is not None:
            return self.camera_manager.get_frame_encoded(quality)
        return None
    
    def get_active_camera_type(self) -> str:
        """Retorna tipo de câmera ativa"""
        if self.camera_manager is not None:
            cam_type = self.camera_manager.get_active_camera_type()
            return cam_type.value
        return "none"
    
    # ========================================================================
    # CONTROLE DO BRAÇO/CABEÇA (CORRIGIDO: 4 SERVOS)
    # ========================================================================
    
    def arm_look_left(self, degrees: int = 45):
        """Braço olha para esquerda"""
        if self.arm_controller is not None:
            return self.arm_controller.look_left(degrees)
    
    def arm_look_right(self, degrees: int = 45):
        """Braço olha para direita"""
        if self.arm_controller is not None:
            return self.arm_controller.look_right(degrees)
    
    def arm_look_up(self, degrees: int = 30):
        """Braço olha para cima"""
        if self.arm_controller is not None:
            return self.arm_controller.look_up(degrees)
    
    def arm_look_down(self, degrees: int = 30):
        """Braço olha para baixo"""
        if self.arm_controller is not None:
            return self.arm_controller.look_down(degrees)
    
    def arm_look_center(self):
        """Centraliza braço"""
        if self.arm_controller is not None:
            self.arm_controller.look_center()
    
    def arm_set_angle(self, channel: int, angle: int, smooth: bool = False):
        """
        Define ângulo de um servo do braço (CORRIGIDO: Suporta 0-3)
        
        Args:
            channel: Canal do servo (0=Yaw, 1=Pitch, 2=Elbow, 3=Head)
            angle: Ângulo desejado (0-180)
            smooth: Movimento suave
        """
        if self.arm_controller is not None:
            if channel not in [0, 1, 2, 3]:
                print(f"⚠️  Canal inválido: {channel}. Use 0-3.")
                return False
            return self.arm_controller.set_angle(channel, angle, smooth)
        return False
    
    def arm_get_angles(self) -> Dict[int, int]:
        """Retorna ângulos de todos os servos (0-3)"""
        if self.arm_controller is not None:
            return self.arm_controller.get_current_angles()
        return {}
    
    # ========================================================================
    # SENSORES (ULTRASONIC SEMPRE ATIVO)
    # ========================================================================
    
    def get_distance(self) -> float:
        """Retorna distância do ultrasonic em cm"""
        return self.distance
    
    def get_battery_voltage(self) -> float:
        """Retorna voltagem da bateria"""
        return self.battery_voltage
    
    def read_sensors_now(self):
        """Força leitura imediata dos sensores"""
        self._read_sensors()
    
    # ========================================================================
    # MODOS DE OPERAÇÃO
    # ========================================================================
    
    def set_mode(self, mode: RobotMode):
        """Define modo de operação"""
        print(f"🔄 Modo alterado: {self.mode.value} → {mode.value}")
        self.mode = mode
    
    def get_mode(self) -> RobotMode:
        """Retorna modo atual"""
        return self.mode
    
    # ========================================================================
    # STATUS E INFORMAÇÕES
    # ========================================================================
    
    def get_status(self) -> Dict:
        """Retorna status completo do robô"""
        status = {
            'mode': self.mode.value,
            'is_running': self.is_running,
            'safety_stop': self.safety_stop,
            'distance': round(self.distance, 1),
            'battery_voltage': round(self.battery_voltage, 2),
            'motor_inversion': {
                'left': self.invert_left == -1,
                'right': self.invert_right == -1
            }
        }
        
        # Status da câmera
        if self.camera_manager is not None:
            cam_status = self.camera_manager.get_status()
            status['camera'] = {
                'active': cam_status['active_camera'],
                'usb_available': cam_status['usb_available'],
                'picam_available': cam_status['picam_available'],
                'fps': cam_status['fps']
            }
        
        # Status do braço (4 servos)
        if self.arm_controller is not None:
            arm_status = self.arm_controller.get_status()
            status['arm'] = {
                'yaw': arm_status['yaw'],
                'pitch': arm_status['pitch'],
                'elbow': arm_status['elbow'],
                'head': arm_status['head']
            }
        
        return status
    
    def print_status(self):
        """Imprime status do robô"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("🤖 EVA ROBOT STATUS (VERSÃO CORRIGIDA)")
        print("="*60)
        print(f"Modo:           {status['mode']}")
        print(f"Running:        {status['is_running']}")
        print(f"Safety Stop:    {status['safety_stop']}")
        print(f"Distância:      {status['distance']:.1f} cm")
        print(f"Bateria:        {status['battery_voltage']:.2f} V")
        
        inv = status.get('motor_inversion', {})
        print(f"\nInversão Motores:")
        print(f"   Esquerda:    {inv.get('left', False)}")
        print(f"   Direita:     {inv.get('right', False)}")
        
        if 'camera' in status:
            cam = status['camera']
            print(f"\n📷 Câmera:      {cam['active'].upper()}")
            print(f"   USB:         {'✅' if cam['usb_available'] else '❌'}")
            print(f"   Pi Camera:   {'✅' if cam['picam_available'] else '❌'}")
            print(f"   FPS:         {cam['fps']}")
        
        if 'arm' in status:
            arm = status['arm']
            print(f"\n🦾 Braço (4 servos):")
            print(f"   Yaw:         {arm['yaw']}°")
            print(f"   Pitch:       {arm['pitch']}°")
            print(f"   Elbow:       {arm['elbow']}°")
            print(f"   Head:        {arm['head']}°")
        
        print("="*60 + "\n")
    
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