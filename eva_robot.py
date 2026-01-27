#!/usr/bin/env python3
"""
EVA ROBOT - MAIN CONTROLLER
Sistema principal que integra: motores, câmeras, braço, sensores
"""

import sys
import time
import threading
from typing import Optional, Dict, Union, TYPE_CHECKING
from enum import Enum

# Importar do robot_core original
try:
    from robot_core import Servo, Ordinary_Car, Ultrasonic, ADC
    HARDWARE_AVAILABLE = True
except ImportError:
    print("⚠️  robot_core não encontrado. Usando modo simulação.")
    # Criar classes dummy para type checking
    class Servo:  # type: ignore
        pass
    class Ordinary_Car:  # type: ignore
        pass
    class Ultrasonic:  # type: ignore
        pass
    class ADC:  # type: ignore
        pcb_version = 1
    HARDWARE_AVAILABLE = False

# Módulos locais
from camera_manager import CameraManager, CameraType
from arm_controller import ArmController


class RobotMode(Enum):
    """Modos de operação do robô"""
    MANUAL = "manual"           # Controle manual remoto
    AUTONOMOUS = "autonomous"   # Navegação autônoma
    FOLLOW = "follow"           # Seguir pessoa/objeto
    PATROL = "patrol"           # Patrulha
    IDLE = "idle"              # Ocioso


class EVARobot:
    """Controlador principal do robô EVA"""
    
    def __init__(self):
        """Inicializa o robô EVA"""
        print("\n" + "="*60)
        print("🤖 EVA ROBOT - Inicializando...")
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
        
        print("✅ EVARobot inicializado (hardware não conectado)")
    
    def start(self) -> bool:
        """Inicia todos os sistemas do robô"""
        print("\n🚀 Iniciando sistemas...\n")
        
        success = True
        
        # 1. Hardware básico
        if not self._init_hardware():
            print("⚠️  Hardware não inicializado (modo simulação)")
            success = False
        
        # 2. Câmeras
        self.camera_manager = CameraManager(usb_device_id=1, picam_device_id=0)
        if not self.camera_manager.start():
            print("❌ Falha ao iniciar câmeras")
            success = False
        
        # 3. Braço/Cabeça
        if self.servo is not None:
            self.arm_controller = ArmController(self.servo)
            self.arm_controller.pose_home()
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
            print("✅ Servos inicializados")
            
            # Motores
            self.motor = Ordinary_Car()
            print("✅ Motores inicializados")
            
            # Ultrasônico
            self.ultrasonic = Ultrasonic()
            print("✅ Sensor ultrasônico inicializado")
            
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
                self.distance = self.ultrasonic.get_distance()
            except:
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
        
        # Bateria baixa
        if self.battery_voltage > 0 and self.battery_voltage < 6.5:
            print(f"⚠️  Bateria baixa: {self.battery_voltage:.1f}V")
    
    # ========================================================================
    # CONTROLE DE MOVIMENTO
    # ========================================================================
    
    def move_forward(self, speed: int = 1500):
        """Move para frente"""
        if self.motor is not None and not self.safety_stop:
            self.motor.set_motor_model(speed, speed, speed, speed)
    
    def move_backward(self, speed: int = 1500):
        """Move para trás"""
        if self.motor is not None:
            self.motor.set_motor_model(-speed, -speed, -speed, -speed)
    
    def turn_left(self, speed: int = 1500):
        """Gira para esquerda"""
        if self.motor is not None and not self.safety_stop:
            self.motor.set_motor_model(-speed, -speed, speed, speed)
    
    def turn_right(self, speed: int = 1500):
        """Gira para direita"""
        if self.motor is not None and not self.safety_stop:
            self.motor.set_motor_model(speed, speed, -speed, -speed)
    
    def strafe_left(self, speed: int = 1500):
        """Desloca lateralmente para esquerda (Mecanum)"""
        if self.motor is not None and not self.safety_stop:
            self.motor.set_motor_model(-speed, speed, speed, -speed)
    
    def strafe_right(self, speed: int = 1500):
        """Desloca lateralmente para direita (Mecanum)"""
        if self.motor is not None and not self.safety_stop:
            self.motor.set_motor_model(speed, -speed, -speed, speed)
    
    def stop_motors(self):
        """Para todos os motores"""
        if self.motor is not None:
            self.motor.set_motor_model(0, 0, 0, 0)
        self.safety_stop = False
    
    def set_motor_model(self, fl: int, bl: int, fr: int, br: int):
        """
        Controle direto dos 4 motores
        
        Args:
            fl: Front Left
            bl: Back Left
            fr: Front Right
            br: Back Right
        """
        if self.motor is not None and not self.safety_stop:
            self.motor.set_motor_model(fl, bl, fr, br)
    
    # ========================================================================
    # CONTROLE DE CÂMERA
    # ========================================================================
    
    def switch_camera(self, camera_type: Optional[CameraType] = None):
        """Alterna entre câmeras"""
        if self.camera_manager is not None:
            self.camera_manager.switch_camera(camera_type)
    
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
    
    # ========================================================================
    # CONTROLE DO BRAÇO/CABEÇA
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
        """Define ângulo de um servo do braço"""
        if self.arm_controller is not None:
            return self.arm_controller.set_angle(channel, angle, smooth)
    
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
            'distance': self.distance,
            'battery_voltage': self.battery_voltage,
        }
        
        # Status da câmera
        if self.camera_manager is not None:
            status['camera'] = self.camera_manager.get_status()
        
        # Status do braço
        if self.arm_controller is not None:
            status['arm'] = self.arm_controller.get_status()
        
        return status
    
    def print_status(self):
        """Imprime status do robô"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("🤖 EVA ROBOT STATUS")
        print("="*60)
        print(f"Modo:           {status['mode']}")
        print(f"Running:        {status['is_running']}")
        print(f"Safety Stop:    {status['safety_stop']}")
        print(f"Distância:      {status['distance']:.1f} cm")
        print(f"Bateria:        {status['battery_voltage']:.1f} V")
        
        if 'camera' in status:
            cam = status['camera']
            print(f"\n📷 Câmera:      {cam['active_camera'].upper()}")
            print(f"   FPS:         {cam['fps']}")
        
        if 'arm' in status:
            arm = status['arm']
            print(f"\n🦾 Braço:")
            print(f"   Yaw:         {arm['yaw']}°")
            print(f"   Pitch:       {arm['pitch']}°")
        
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
        self.stop()


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 TESTE: EVA ROBOT")
    print("="*60 + "\n")
    
    robot = EVARobot()
    
    try:
        if not robot.start():
            print("⚠️  Robô iniciado em modo limitado")
        
        # Teste básico
        print("\n💡 Testando funcionalidades básicas...\n")
        
        # Status
        robot.print_status()
        
        # Testar câmera
        if robot.camera_manager is not None:
            print("📷 Testando alternância de câmera...")
            robot.switch_camera()
            time.sleep(2)
            robot.switch_camera()
        
        # Testar braço
        if robot.arm_controller is not None:
            print("\n🦾 Testando movimentos do braço...")
            robot.arm_look_left(30)
            time.sleep(1)
            robot.arm_look_right(30)
            time.sleep(1)
            robot.arm_look_center()
        
        print("\n✅ Teste básico concluído")
        print("Pressione Ctrl+C para sair...\n")
        
        # Loop principal
        while True:
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário")
    
    finally:
        robot.stop()
        print("\n✅ Teste finalizado")