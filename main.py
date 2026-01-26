#!/usr/bin/env python3
"""
EVA ROBOT - MAIN BOOT
Ponto de entrada principal do robô
"""

import sys
import time
import signal
from pathlib import Path

# Adicionar pasta ao path
sys.path.insert(0, str(Path(__file__).parent))

# Imports do core
from core.robot_core import (
    PCA9685, Servo, Ordinary_Car, Ultrasonic, ADC
)

# Imports da arquitetura
from core.hardware_config import CONFIG
from core.safety import SafetyController
from state.robot_state import STATE
from network.robot_server import init_server, run_server


# ============================================================================
# ROBOT CONTROLLER UNIFICADO
# ============================================================================

class EVARobotController:
    """
    Controlador unificado do robô EVA
    
    Integra:
    - Hardware (motores, servos, sensores)
    - Estado (STATE manager)
    - Segurança (safety controller)
    - Rede (servidor WebSocket/Flask)
    """
    
    def __init__(self):
        self.motor = None
        self.arm = None
        self.ultrasonic = None
        self.adc = None
        self.servo = None
        
        self.safety = None
        self.server = None
        
        self.monitoring = False
        
        print("\n" + "="*60)
        print("🤖 EVA ROBOT - INICIALIZANDO")
        print("="*60 + "\n")
    
    def initialize(self, enable_arm: bool = True) -> bool:
        """
        Inicializa todos os componentes
        
        Args:
            enable_arm: Habilitar braço/cabeça
        
        Returns:
            True se sucesso
        """
        success = True
        
        # 1. Motor
        try:
            print("🚗 Inicializando motores...")
            self.motor = Ordinary_Car()
            print("   ✅ Motores OK")
        except Exception as e:
            print(f"   ❌ Motores falhou: {e}")
            success = False
        
        # 2. Servos (braço)
        if enable_arm:
            try:
                print("🦾 Inicializando braço...")
                
                # Importar arm_calibration
                try:
                    from arm_calibration import ArmController
                    self.arm = ArmController(enable_gripper=False, min_delay=0.15)
                    print("   ✅ Braço OK")
                except ImportError:
                    print("   ⚠️  arm_calibration.py não encontrado, usando Servo básico")
                    self.servo = Servo()
                    print("   ✅ Servos básicos OK")
            
            except Exception as e:
                print(f"   ❌ Braço falhou: {e}")
        
        # 3. Ultrasonic
        try:
            print("📡 Inicializando ultrasonic...")
            self.ultrasonic = Ultrasonic(
                trigger_pin=CONFIG.pins.ULTRASONIC_TRIGGER,
                echo_pin=CONFIG.pins.ULTRASONIC_ECHO
            )
            print("   ✅ Ultrasonic OK")
        except Exception as e:
            print(f"   ⚠️  Ultrasonic falhou: {e}")
        
        # 4. ADC (bateria)
        try:
            print("🔋 Inicializando ADC...")
            self.adc = ADC()
            print("   ✅ ADC OK")
        except Exception as e:
            print(f"   ⚠️  ADC falhou: {e}")
        
        # 5. Safety
        print("🛡️  Inicializando safety...")
        self.safety = SafetyController(self)
        
        # 6. Validar configuração
        print("\n🔍 Validando configuração...")
        CONFIG.validate()
        
        if success:
            print("\n✅ Inicialização completa!\n")
        else:
            print("\n⚠️  Inicialização com warnings\n")
        
        return success
    
    # ========================================
    # INTERFACE DE HARDWARE
    # ========================================
    
    def stop(self):
        """Para todos os motores"""
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
    
    def set_motor_model(self, fl: int, bl: int, fr: int, br: int):
        """Define PWM dos motores"""
        if self.motor:
            self.motor.set_motor_model(fl, bl, fr, br)
    
    def read_sensors(self) -> dict:
        """Lê todos os sensores"""
        data = {}
        
        # Ultrasonic
        if self.ultrasonic:
            try:
                distance = self.ultrasonic.get_distance()
                data['ultrasonic_cm'] = distance
            except:
                pass
        
        # Bateria
        if self.adc:
            try:
                # Canal 2 = bateria (baseado no robot_core.py)
                voltage = self.adc.read_adc(2)
                
                # Ajustar por PCB version
                if self.adc.pcb_version == 1:
                    voltage *= 3  # v1 tem divisor 1:3
                else:
                    voltage *= 2  # v2 tem divisor 1:2
                
                data['battery_v'] = voltage
            except:
                pass
        
        return data
    
    # ========================================
    # MONITORAMENTO
    # ========================================
    
    def start_monitoring(self):
        """Inicia loop de monitoramento de sensores"""
        import threading
        
        self.monitoring = True
        
        thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        thread.start()
        
        print("📊 Monitoramento de sensores iniciado")
    
    def stop_monitoring(self):
        """Para monitoramento"""
        self.monitoring = False
        print("📊 Monitoramento parado")
    
    def _monitoring_loop(self):
        """Loop de monitoramento (thread separada)"""
        while self.monitoring:
            try:
                # Ler sensores
                sensor_data = self.read_sensors()
                
                # Atualizar estado
                STATE.update_sensors(
                    ultrasonic=sensor_data.get('ultrasonic_cm'),
                    battery=sensor_data.get('battery_v')
                )
                
                # Atualizar safety
                self.safety.update_sensor_data(sensor_data)
                
                # Verificar watchdog
                self.safety.watchdog.check()
                
                time.sleep(CONFIG.sensors.SENSOR_READ_INTERVAL)
            
            except Exception as e:
                print(f"❌ Erro no monitoramento: {e}")
                time.sleep(1.0)
    
    # ========================================
    # CLEANUP
    # ========================================
    
    def cleanup(self):
        """Cleanup de todos os componentes"""
        print("\n🔧 Encerrando robô...")
        
        # Parar monitoramento
        self.stop_monitoring()
        
        # Parar motores
        self.stop()
        
        # Cleanup componentes
        if self.motor:
            try:
                self.motor.close()
            except:
                pass
        
        if self.arm:
            try:
                self.arm.cleanup()
            except:
                pass
        
        if self.ultrasonic:
            try:
                self.ultrasonic.close()
            except:
                pass
        
        if self.adc:
            try:
                self.adc.close_i2c()
            except:
                pass
        
        print("✅ Robô encerrado com segurança\n")


# ============================================================================
# SISTEMA DE CÂMERAS (MOCK - adaptar eva_camera_system.py)
# ============================================================================

class CameraSystem:
    """Sistema de câmeras (placeholder)"""
    
    def __init__(self):
        self.active_camera = "webcam"
        self.frame = None
    
    def start(self) -> bool:
        print("📷 Sistema de câmeras iniciado (placeholder)")
        return True
    
    def switch_to_navigation(self):
        self.active_camera = "webcam"
    
    def switch_to_arm_camera(self):
        self.active_camera = "picam"
    
    def get_frame(self):
        return self.frame
    
    def cleanup(self):
        pass


# ============================================================================
# MAIN
# ============================================================================

def signal_handler(sig, frame):
    """Handler para Ctrl+C"""
    print("\n\n⚠️  Interrupção detectada (Ctrl+C)")
    sys.exit(0)


def main():
    """Função principal"""
    
    # Handler para Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Inicializar robô
    robot = EVARobotController()
    
    if not robot.initialize(enable_arm=True):
        print("❌ Falha na inicialização")
        return 1
    
    # Inicializar câmeras
    camera = CameraSystem()
    camera.start()
    
    # Iniciar monitoramento
    robot.start_monitoring()
    
    # Inicializar servidor de rede
    server = init_server(robot, camera, robot.safety)
    
    # Menu
    print("="*60)
    print("MODO DE OPERAÇÃO")
    print("="*60)
    print("\n1 - Servidor Web (Controle Remoto)")
    print("2 - Teste Manual (Terminal)")
    print("3 - Sair")
    print()
    
    choice = input("Escolha: ").strip()
    exit_code = 0
    
    try:
        if choice == '1':
            # Modo servidor
            run_server(host='0.0.0.0', port=5000)
        
        elif choice == '2':
            # Modo teste manual
            print("\n🎮 Modo teste manual")
            print("Comandos: w=frente, s=ré, a=esq, d=dir, x=parar, q=sair\n")
            
            import sys
            import tty
            import termios
            
            # Modo raw do terminal
            old_settings = termios.tcgetattr(sys.stdin)
            
            try:
                tty.setraw(sys.stdin.fileno())
                
                while True:
                    char = sys.stdin.read(1)
                    
                    if char == 'q':
                        break
                    elif char == 'w':
                        robot.set_motor_model(1500, 1500, 1500, 1500)
                        print("\r⬆️  Frente    ", end='', flush=True)
                    elif char == 's':
                        robot.set_motor_model(-1500, -1500, -1500, -1500)
                        print("\r⬇️  Ré       ", end='', flush=True)
                    elif char == 'a':
                        robot.set_motor_model(-1500, -1500, 1500, 1500)
                        print("\r⬅️  Esquerda ", end='', flush=True)
                    elif char == 'd':
                        robot.set_motor_model(1500, 1500, -1500, -1500)
                        print("\r➡️  Direita  ", end='', flush=True)
                    elif char == 'x':
                        robot.stop()
                        print("\r⏹️  Parado   ", end='', flush=True)
            
            finally:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                print("\n")
        
        else:
            print("👋 Saindo...")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido")
    
    finally:
        # Cleanup
        camera.cleanup()
        robot.cleanup()
        print("✅ Programa encerrado\n")
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())