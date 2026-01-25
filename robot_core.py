#!/usr/bin/env python3
"""
EVA ROBOT CORE SYSTEM
Sistema central do robô EVA - Controle e testes modulares
Versão: 1.0 - Testes Iniciais (Câmeras + Movimento Manual)
"""

import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Adicionar pasta hardware ao path
HARDWARE_PATH = Path(__file__).parent / 'hardware'
sys.path.insert(0, str(HARDWARE_PATH))

# Importar módulos de hardware (com fallback)
try:
    from motor import Ordinary_Car
    MOTOR_OK = True
except ImportError as e:
    print(f"⚠️  Motor não disponível: {e}")
    MOTOR_OK = False

try:
    from ultrasonic import Ultrasonic
    ULTRASONIC_OK = True
except ImportError:
    print("⚠️  Ultrasonic não disponível")
    ULTRASONIC_OK = False

try:
    from adc import ADC
    ADC_OK = True
except ImportError:
    print("⚠️  ADC não disponível")
    ADC_OK = False

try:
    from buzzer import Buzzer
    BUZZER_OK = True
except ImportError:
    print("⚠️  Buzzer não disponível")
    BUZZER_OK = False

# Importar arm_calibration (braço)
try:
    from arm_calibration import ArmController
    ARM_OK = True
except ImportError:
    print("⚠️  Braço robótico não disponível")
    ARM_OK = False

# Câmeras
try:
    import cv2
    OPENCV_OK = True
except ImportError:
    print("⚠️  OpenCV não disponível - câmeras desabilitadas")
    OPENCV_OK = False

try:
    from picamera2 import Picamera2
    PICAM_OK = True
except ImportError:
    print("⚠️  Picamera2 não disponível")
    PICAM_OK = False


class EvaRobotCore:
    """
    🤖 Núcleo central do robô EVA
    Gerencia hardware e fornece interface unificada
    """
    
    def __init__(self):
        """Inicializa o sistema"""
        self.running = False
        
        # Hardware
        self.motor = None
        self.ultrasonic = None
        self.adc = None
        self.buzzer = None
        self.arm = None
        
        # Câmeras
        self.picam = None  # Raspberry Pi Camera
        self.webcam = None  # USB Webcam
        self.picam_active = False
        self.webcam_active = False
        
        # Estado
        self.sensor_data = {}
        self.last_motor_cmd = [0, 0, 0, 0]
        
        print("\n" + "="*60)
        print("🤖 EVA ROBOT CORE SYSTEM v1.0")
        print("="*60)
        print("\n📋 Verificando disponibilidade de hardware...\n")
        
        self._show_hardware_status()
    
    def _show_hardware_status(self):
        """Mostra status do hardware disponível"""
        status = {
            "Motor (Rodas)": MOTOR_OK,
            "Ultrasonic (Sonar)": ULTRASONIC_OK,
            "ADC (Bateria)": ADC_OK,
            "Buzzer": BUZZER_OK,
            "Braço Robótico": ARM_OK,
            "OpenCV": OPENCV_OK,
            "PiCamera2": PICAM_OK
        }
        
        for name, ok in status.items():
            symbol = "✅" if ok else "❌"
            print(f"  {symbol} {name}")
        
        print("\n" + "="*60 + "\n")
    
    def initialize(self, enable_arm: bool = True, enable_cameras: bool = True):
        """
        Inicializa o hardware do robô
        
        Args:
            enable_arm: Habilitar braço robótico
            enable_cameras: Habilitar câmeras
        """
        print("🔧 Inicializando hardware...\n")
        
        # Motor (essencial)
        if MOTOR_OK:
            try:
                self.motor = Ordinary_Car()
                print("✅ Motor inicializado")
            except Exception as e:
                print(f"❌ Erro no motor: {e}")
                return False
        else:
            print("❌ Motor não disponível - impossível continuar")
            return False
        
        # Ultrasonic
        if ULTRASONIC_OK:
            try:
                self.ultrasonic = Ultrasonic()
                print("✅ Ultrasonic inicializado")
            except Exception as e:
                print(f"⚠️  Ultrasonic falhou: {e}")
        
        # ADC (Bateria)
        if ADC_OK:
            try:
                self.adc = ADC()
                print("✅ ADC inicializado")
            except Exception as e:
                print(f"⚠️  ADC falhou: {e}")
        
        # Buzzer
        if BUZZER_OK:
            try:
                self.buzzer = Buzzer()
                # 3 beeps de inicialização
                for _ in range(3):
                    self.buzzer.set_state(True)
                    time.sleep(0.1)
                    self.buzzer.set_state(False)
                    time.sleep(0.1)
                print("✅ Buzzer inicializado (beep!)")
            except Exception as e:
                print(f"⚠️  Buzzer falhou: {e}")
        
        # Braço robótico
        if enable_arm and ARM_OK:
            try:
                self.arm = ArmController(enable_gripper=False, min_delay=0.15)
                print("✅ Braço robótico inicializado (modo cabeça)")
            except Exception as e:
                print(f"⚠️  Braço falhou: {e}")
        
        # Câmeras
        if enable_cameras:
            self._init_cameras()
        
        self.running = True
        print("\n✅ Hardware inicializado com sucesso!\n")
        return True
    
    def _init_cameras(self):
        """Inicializa as câmeras disponíveis"""
        print("\n📷 Inicializando câmeras...")
        
        # Raspberry Pi Camera
        if PICAM_OK:
            try:
                self.picam = Picamera2()
                config = self.picam.create_preview_configuration(
                    main={"size": (1280, 720)}
                )
                self.picam.configure(config)
                print("  ✅ Raspberry Pi Camera detectada (1280x720)")
            except Exception as e:
                print(f"  ⚠️  Pi Camera falhou: {e}")
                self.picam = None
        
        # USB Webcam
        if OPENCV_OK:
            try:
                self.webcam = cv2.VideoCapture(0)
                if self.webcam.isOpened():
                    self.webcam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    self.webcam.set(cv2.CAP_PROP_FPS, 30)
                    print("  ✅ USB Webcam detectada (1280x720)")
                else:
                    self.webcam = None
                    print("  ⚠️  Nenhuma USB Webcam detectada")
            except Exception as e:
                print(f"  ⚠️  Webcam falhou: {e}")
                self.webcam = None
    
    def read_sensors(self) -> Dict[str, Any]:
        """
        Lê todos os sensores disponíveis
        
        Returns:
            Dicionário com dados dos sensores
        """
        data = {
            'timestamp': time.time(),
            'ultrasonic_cm': None,
            'battery_v': None,
            'arm_position': None
        }
        
        # Ultrasonic
        if self.ultrasonic:
            try:
                distance = self.ultrasonic.get_distance()
                data['ultrasonic_cm'] = round(distance, 2) if distance else None
            except:
                pass
        
        # Bateria
        if self.adc:
            try:
                voltage = self.adc.read_adc(2)
                multiplier = 3 if self.adc.pcb_version == 1 else 2
                data['battery_v'] = round(voltage * multiplier, 2)
            except:
                pass
        
        # Posição do braço
        if self.arm:
            try:
                data['arm_position'] = self.arm.get_current_position()
            except:
                pass
        
        self.sensor_data = data
        return data
    
    def get_picam_frame(self):
        """Captura frame da Pi Camera"""
        if not self.picam:
            return None
        
        try:
            if not self.picam_active:
                self.picam.start()
                self.picam_active = True
                time.sleep(0.5)  # Aguardar estabilização
            
            frame = self.picam.capture_array()
            return frame
        except Exception as e:
            print(f"Erro ao capturar Pi Camera: {e}")
            return None
    
    def get_webcam_frame(self):
        """Captura frame da Webcam USB"""
        if not self.webcam or not self.webcam.isOpened():
            return None
        
        try:
            ret, frame = self.webcam.read()
            return frame if ret else None
        except Exception as e:
            print(f"Erro ao capturar Webcam: {e}")
            return None
    
    def save_test_images(self):
        """Salva imagens de teste das duas câmeras"""
        print("\n📸 Capturando imagens de teste...\n")
        
        # Pi Camera
        if self.picam:
            frame = self.get_picam_frame()
            if frame is not None and OPENCV_OK:
                filename = f"test_picam_{int(time.time())}.jpg"
                cv2.imwrite(filename, frame)
                print(f"  ✅ Pi Camera: {filename}")
        
        # Webcam
        if self.webcam:
            frame = self.get_webcam_frame()
            if frame is not None:
                filename = f"test_webcam_{int(time.time())}.jpg"
                cv2.imwrite(filename, frame)
                print(f"  ✅ Webcam: {filename}")
        
        print()
    
    def move(self, fl: int, bl: int, fr: int, br: int):
        """
        Move o carro (valores PWM -4095 a 4095)
        
        Args:
            fl: Front Left
            bl: Back Left
            fr: Front Right
            br: Back Right
        """
        if not self.motor:
            print("❌ Motor não disponível")
            return
        
        try:
            self.motor.set_motor_model(fl, bl, fr, br)
            self.last_motor_cmd = [fl, bl, fr, br]
        except Exception as e:
            print(f"❌ Erro ao mover: {e}")
    
    def stop(self):
        """Para todos os motores"""
        self.move(0, 0, 0, 0)
    
    def forward(self, speed: int = 1000):
        """Move para frente (INVERTIDO conforme seu código)"""
        self.move(-speed, -speed, -speed, -speed)
    
    def backward(self, speed: int = 1000):
        """Move para trás (INVERTIDO conforme seu código)"""
        self.move(speed, speed, speed, speed)
    
    def turn_left(self, speed: int = 1000):
        """Vira à esquerda"""
        self.move(speed, speed, -speed, -speed)
    
    def turn_right(self, speed: int = 1000):
        """Vira à direita"""
        self.move(-speed, -speed, speed, speed)
    
    def cleanup(self):
        """Desliga tudo com segurança"""
        print("\n🛑 Encerrando EVA Robot Core...\n")
        
        self.running = False
        
        # Parar motor
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
            self.motor.close()
            print("  ✅ Motor desligado")
        
        # Fechar câmeras
        if self.picam and self.picam_active:
            self.picam.stop()
            self.picam.close()
            print("  ✅ Pi Camera fechada")
        
        if self.webcam and self.webcam.isOpened():
            self.webcam.release()
            print("  ✅ Webcam fechada")
        
        # Fechar sensores
        if self.ultrasonic:
            self.ultrasonic.close()
            print("  ✅ Ultrasonic fechado")
        
        if self.adc:
            self.adc.close_i2c()
            print("  ✅ ADC fechado")
        
        # Braço
        if self.arm:
            self.arm.cleanup()
            print("  ✅ Braço finalizado")
        
        # Beep final
        if self.buzzer:
            self.buzzer.set_state(True)
            time.sleep(0.3)
            self.buzzer.set_state(False)
            self.buzzer.close()
            print("  ✅ Buzzer desligado")
        
        print("\n✅ Sistema encerrado com segurança!\n")


def test_menu():
    """Menu interativo de testes"""
    robot = EvaRobotCore()
    
    # Inicializar
    if not robot.initialize(enable_arm=True, enable_cameras=True):
        print("❌ Falha na inicialização")
        return
    
    try:
        while True:
            print("\n" + "="*60)
            print("🎮 MENU DE TESTES - EVA ROBOT")
            print("="*60)
            print("\n📷 CÂMERAS:")
            print("  1 - Testar Pi Camera")
            print("  2 - Testar Webcam USB")
            print("  3 - Salvar imagens de teste (ambas)")
            
            print("\n🚗 MOVIMENTO:")
            print("  w - Frente      s - Ré")
            print("  a - Esquerda    d - Direita")
            print("  x - PARAR")
            
            print("\n🦾 BRAÇO (CABEÇA):")
            print("  h - Home")
            print("  f - Look Forward")
            print("  v - Wave (acenar)")
            print("  c - Scan (varredura)")
            
            print("\n📊 SENSORES:")
            print("  i - Ler sensores")
            
            print("\n❌ SAIR:")
            print("  q - Sair")
            print("="*60)
            
            cmd = input("\n> ").strip().lower()
            
            # Câmeras
            if cmd == '1':
                frame = robot.get_picam_frame()
                if frame is not None:
                    print("✅ Pi Camera OK - Frame capturado")
                else:
                    print("❌ Pi Camera falhou")
            
            elif cmd == '2':
                frame = robot.get_webcam_frame()
                if frame is not None:
                    print("✅ Webcam OK - Frame capturado")
                else:
                    print("❌ Webcam falhou")
            
            elif cmd == '3':
                robot.save_test_images()
            
            # Movimento
            elif cmd == 'w':
                print("⬆️  Frente...")
                robot.forward(1000)
                time.sleep(0.5)
                robot.stop()
            
            elif cmd == 's':
                print("⬇️  Ré...")
                robot.backward(1000)
                time.sleep(0.5)
                robot.stop()
            
            elif cmd == 'a':
                print("⬅️  Esquerda...")
                robot.turn_left(1000)
                time.sleep(0.5)
                robot.stop()
            
            elif cmd == 'd':
                print("➡️  Direita...")
                robot.turn_right(1000)
                time.sleep(0.5)
                robot.stop()
            
            elif cmd == 'x':
                print("🛑 PARAR")
                robot.stop()
            
            # Braço
            elif cmd == 'h' and robot.arm:
                robot.arm.home_position()
            
            elif cmd == 'f' and robot.arm:
                robot.arm.look_forward(smooth=True)
            
            elif cmd == 'v' and robot.arm:
                robot.arm.wave_gesture()
            
            elif cmd == 'c' and robot.arm:
                robot.arm.scan_left_right(times=2)
            
            # Sensores
            elif cmd == 'i':
                data = robot.read_sensors()
                print("\n📊 DADOS DOS SENSORES:")
                print(f"  🔊 Ultrasonic: {data.get('ultrasonic_cm', 'N/A')} cm")
                print(f"  🔋 Bateria: {data.get('battery_v', 'N/A')} V")
                if data.get('arm_position'):
                    print(f"  🦾 Braço: {len(data['arm_position'])} servos ativos")
            
            # Sair
            elif cmd == 'q':
                break
            
            else:
                print("❌ Comando inválido")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detectado")
    
    finally:
        robot.cleanup()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🤖 EVA ROBOT - Sistema de Testes Iniciais")
    print("="*60)
    print("\nEste módulo testa:")
    print("  ✓ Conexão das duas câmeras (Pi Camera + USB Webcam)")
    print("  ✓ Movimento manual do carro")
    print("  ✓ Leitura de sensores")
    print("  ✓ Controle do braço (cabeça)")
    print("\n" + "="*60 + "\n")
    
    test_menu()