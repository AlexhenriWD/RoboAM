#!/usr/bin/env python3
"""
EVA ROBOT SYSTEM - Sistema Principal Consolidado
Drone de Análise com Dual Camera System

CONCEITO:
- USB Webcam: Navegação (movimento do carro)
- Pi Camera: Análise (quando braço/cabeça ativo)
- Troca automática inteligente
- Controle completo: Base, Ombro, Cotovelo, Cabeça

ARQUITETURA:
- eva_robot_system.py (este arquivo) - Sistema principal
- eva_network_server.py - Servidor WebSocket
- eva_web_interface.html - Interface web
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
import threading
import numpy as np

# Hardware imports
sys.path.insert(0, str(Path(__file__).parent / 'hardware'))

try:
    from motor import Ordinary_Car
    MOTOR_OK = True
except:
    MOTOR_OK = False
    print("⚠️ Motor não disponível")

try:
    from ultrasonic import Ultrasonic
    ULTRASONIC_OK = True
except:
    ULTRASONIC_OK = False
    print("⚠️ Ultrasonic não disponível")

try:
    from adc import ADC
    ADC_OK = True
except:
    ADC_OK = False
    print("⚠️ ADC não disponível")

try:
    from buzzer import Buzzer
    BUZZER_OK = True
except:
    BUZZER_OK = False
    print("⚠️ Buzzer não disponível")

# Câmeras
try:
    import cv2
    OPENCV_OK = True
except:
    OPENCV_OK = False
    print("⚠️ OpenCV não disponível")

try:
    from picamera2 import Picamera2
    PICAM_OK = True
except:
    PICAM_OK = False
    print("⚠️ Picamera2 não disponível")


# ==========================================
# CONTROLADOR DE SERVOS (BRAÇO/CABEÇA)
# ==========================================

class ServoController:
    """
    Controlador completo de servos
    Suporta: Base, Ombro, Cotovelo, Cabeça
    """
    
    def __init__(self):
        try:
            from servo import Servo
            self.servo = Servo()
        except:
            self.servo = None
            print("⚠️ Servos não disponíveis")
            return
        
        # Configuração dos servos
        self.servos = {
            0: {"name": "Base (Yaw)", "min": 0, "max": 180, "home": 90, "current": 90},
            1: {"name": "Ombro (Pitch)", "min": 0, "max": 180, "home": 90, "current": 90},
            2: {"name": "Cotovelo", "min": 0, "max": 180, "home": 90, "current": 90},
            3: {"name": "Cabeça", "min": 0, "max": 180, "home": 90, "current": 90},
        }
        
        self.min_delay = 0.02
        self.last_move_time = {ch: 0.0 for ch in self.servos.keys()}
        
        # Inicializar em home
        self.home_position()
        print("✅ Servos inicializados")
    
    def _clamp(self, channel: int, angle: int) -> int:
        """Limita ângulo aos valores permitidos"""
        s = self.servos[channel]
        return max(s["min"], min(s["max"], int(angle)))
    
    def _wait_min_delay(self, channel: int):
        """Aguarda delay mínimo entre movimentos"""
        elapsed = time.time() - self.last_move_time.get(channel, 0.0)
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
    
    def move_servo(self, channel: int, angle: int, smooth: bool = True) -> bool:
        """
        Move um servo
        
        Args:
            channel: 0=Base, 1=Ombro, 2=Cotovelo, 3=Cabeça
            angle: Ângulo (0-180)
            smooth: Movimento suave incremental
        """
        if not self.servo or channel not in self.servos:
            return False
        
        angle = self._clamp(channel, angle)
        
        try:
            if smooth:
                # Movimento suave
                current = int(self.servos[channel]["current"])
                step = 2
                direction = 1 if angle > current else -1
                
                pos = current
                while pos != angle:
                    next_pos = pos + direction * step
                    if (direction == 1 and next_pos > angle) or (direction == -1 and next_pos < angle):
                        next_pos = angle
                    
                    self._wait_min_delay(channel)
                    self.servo.set_servo_pwm(str(channel), int(next_pos))
                    self.last_move_time[channel] = time.time()
                    
                    pos = next_pos
                    time.sleep(0.02)
            else:
                # Movimento direto
                self._wait_min_delay(channel)
                self.servo.set_servo_pwm(str(channel), int(angle))
                self.last_move_time[channel] = time.time()
            
            self.servos[channel]["current"] = int(angle)
            return True
            
        except Exception as e:
            print(f"❌ Erro ao mover servo {channel}: {e}")
            return False
    
    def home_position(self):
        """Retorna todos servos para posição home"""
        for ch, info in self.servos.items():
            self.move_servo(ch, info["home"], smooth=False)
        print("🏠 Servos em home position")
    
    def get_position(self) -> Dict:
        """Retorna posição atual de todos servos"""
        return {
            ch: {
                "name": info["name"],
                "angle": info["current"],
                "min": info["min"],
                "max": info["max"]
            }
            for ch, info in self.servos.items()
        }


# ==========================================
# SISTEMA DUAL DE CÂMERAS
# ==========================================

class DualCameraSystem:
    """
    Sistema inteligente com 2 câmeras:
    
    📹 USB Webcam → Navegação (movimento do carro)
    📷 Pi Camera → Análise (braço/cabeça ativo)
    
    ROTAÇÃO: Pi Camera rotacionada 90° (problema físico)
    """
    
    def __init__(self):
        self.usb_camera = None
        self.pi_camera = None
        
        self.active_camera = "usb"  # Padrão: navegação
        self.arm_mode_active = False
        
        self.running = False
        self.frame = None
        self.lock = threading.Lock()
        
        # Auto-switch
        self.last_arm_move_time = 0.0
        self.arm_idle_timeout = 3.0  # 3s sem braço → volta USB
        
        print("\n📷 Inicializando sistema dual de câmeras...")
        self._init_cameras()
    
    def _init_cameras(self):
        """Inicializa ambas as câmeras"""
        
        # 1. USB Webcam (navegação)
        if OPENCV_OK:
            try:
                print("  🔧 Inicializando USB Webcam...")
                cap = cv2.VideoCapture(1)  # /dev/video1 = REDRAGON
                
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 15)
                    
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None:
                        self.usb_camera = cap
                        print("  ✅ USB Webcam OK (navegação)")
                    else:
                        cap.release()
                        print("  ❌ USB não captura")
                else:
                    print("  ❌ USB não abre")
            except Exception as e:
                print(f"  ❌ USB falhou: {e}")
        
        # 2. Pi Camera (análise) - NÃO inicia ainda
        if PICAM_OK:
            try:
                print("  🔧 Configurando Pi Camera...")
                self.pi_camera = Picamera2()
                config = self.pi_camera.create_preview_configuration(
                    main={"size": (640, 480), "format": "RGB888"}
                )
                self.pi_camera.configure(config)
                print("  ✅ Pi Camera configurada (ov5647)")
            except Exception as e:
                print(f"  ❌ Pi Camera falhou: {e}")
                self.pi_camera = None
    
    def start(self):
        """Inicia sistema de streaming"""
        if not self.usb_camera and not self.pi_camera:
            print("❌ Nenhuma câmera disponível")
            return False
        
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._auto_switch_loop, daemon=True).start()
        
        print(f"✅ Sistema dual iniciado (ativa: {self.active_camera.upper()})")
        return True
    
    def _capture_loop(self):
        """Loop de captura da câmera ativa"""
        pi_cam_active = False
        
        while self.running:
            try:
                frame = None
                
                # Decidir qual câmera usar
                if self.active_camera == "picam" and self.pi_camera:
                    # Pi Camera
                    if not pi_cam_active:
                        try:
                            self.pi_camera.start()
                            time.sleep(1.0)
                            pi_cam_active = True
                            print("📷 Pi Camera ATIVADA")
                        except Exception as e:
                            print(f"❌ Erro ao iniciar Pi Camera: {e}")
                            self.active_camera = "usb"
                            continue
                    
                    # Capturar
                    try:
                        frame = self.pi_camera.capture_array()
                        if frame is not None and len(frame.shape) == 3:
                            # RGB → BGR
                            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                            # ROTACIONAR 90° (problema físico)
                            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                    except Exception as e:
                        print(f"⚠️ Erro captura Pi Camera: {e}")
                
                else:
                    # USB Camera
                    if pi_cam_active:
                        try:
                            self.pi_camera.stop()
                            pi_cam_active = False
                            print("📹 Voltando para USB Webcam")
                        except:
                            pass
                    
                    # Capturar USB
                    if self.usb_camera and self.usb_camera.isOpened():
                        ret, frame = self.usb_camera.read()
                        if not ret or frame is None:
                            frame = None
                
                # Salvar frame
                if frame is not None:
                    with self.lock:
                        self.frame = frame
                
                time.sleep(0.033)  # ~30 FPS
                
            except Exception as e:
                print(f"❌ Erro no loop: {e}")
                time.sleep(1.0)
        
        # Cleanup
        if pi_cam_active and self.pi_camera:
            try:
                self.pi_camera.stop()
            except:
                pass
    
    def _auto_switch_loop(self):
        """Loop que verifica timeout do braço"""
        while self.running:
            try:
                # Se está em modo Pi Camera e braço não está ativo
                if self.active_camera == "picam" and not self.arm_mode_active:
                    idle_time = time.time() - self.last_arm_move_time
                    
                    if idle_time >= self.arm_idle_timeout:
                        print(f"⏰ Braço parado por {idle_time:.1f}s → USB")
                        self.active_camera = "usb"
                
                time.sleep(0.5)
            except Exception as e:
                print(f"❌ Erro auto-switch: {e}")
                time.sleep(1.0)
    
    def enable_arm_mode(self):
        """Ativa modo braço (usa Pi Camera)"""
        if self.pi_camera and self.active_camera != "picam":
            print("🔄 Ativando modo ANÁLISE (Pi Camera)")
            self.active_camera = "picam"
        
        self.arm_mode_active = True
        self.last_arm_move_time = time.time()
    
    def disable_arm_mode(self):
        """Desativa modo braço (volta USB)"""
        self.arm_mode_active = False
        self.last_arm_move_time = time.time()
        print("🔄 Modo análise desativado")
    
    def force_usb(self):
        """Força uso de USB Webcam"""
        if self.usb_camera:
            self.arm_mode_active = False
            self.active_camera = "usb"
            print("📹 Forçado para USB Webcam")
    
    def force_picam(self):
        """Força uso de Pi Camera"""
        if self.pi_camera:
            self.arm_mode_active = True
            self.active_camera = "picam"
            print("📷 Forçado para Pi Camera")
    
    def get_frame(self):
        """Retorna último frame capturado"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def get_status(self) -> Dict:
        """Status do sistema de câmeras"""
        return {
            "active_camera": self.active_camera.upper(),
            "arm_mode": self.arm_mode_active,
            "usb_available": self.usb_camera is not None,
            "picam_available": self.pi_camera is not None
        }
    
    def stop(self):
        """Para sistema"""
        print("⏹️ Parando sistema de câmeras...")
        self.running = False
        time.sleep(1.0)
        
        if self.pi_camera:
            try:
                self.pi_camera.stop()
                self.pi_camera.close()
            except:
                pass
        
        if self.usb_camera:
            try:
                self.usb_camera.release()
            except:
                pass
        
        print("✅ Câmeras paradas")


# ==========================================
# CONTROLADOR PRINCIPAL DO ROBÔ
# ==========================================

class EVARobotCore:
    """
    🤖 Núcleo principal do robô EVA
    Integra: Motor, Sensores, Braço, Câmeras
    """
    
    def __init__(self):
        # Hardware
        self.motor = None
        self.ultrasonic = None
        self.adc = None
        self.buzzer = None
        self.servos = None
        self.cameras = None
        
        # Estado
        self.running = False
        self.sensor_data = {}
        self.last_motor_cmd = [0, 0, 0, 0]
        
        # Velocidade
        self.speed = 1500  # PWM padrão
        
        print("\n" + "="*60)
        print("🤖 EVA ROBOT CORE SYSTEM")
        print("="*60)
    
    def initialize(self):
        """Inicializa todos os componentes"""
        print("\n🔧 Inicializando hardware...\n")
        
        # Motor (essencial)
        if MOTOR_OK:
            try:
                self.motor = Ordinary_Car()
                print("✅ Motor inicializado")
            except Exception as e:
                print(f"❌ Erro no motor: {e}")
                return False
        else:
            print("❌ Motor não disponível")
            return False
        
        # Sensores
        if ULTRASONIC_OK:
            try:
                self.ultrasonic = Ultrasonic()
                print("✅ Ultrasonic inicializado")
            except Exception as e:
                print(f"⚠️ Ultrasonic falhou: {e}")
        
        if ADC_OK:
            try:
                self.adc = ADC()
                print("✅ ADC inicializado")
            except Exception as e:
                print(f"⚠️ ADC falhou: {e}")
        
        if BUZZER_OK:
            try:
                self.buzzer = Buzzer()
                # Beep de inicialização
                for _ in range(2):
                    self.buzzer.set_state(True)
                    time.sleep(0.1)
                    self.buzzer.set_state(False)
                    time.sleep(0.1)
                print("✅ Buzzer inicializado")
            except Exception as e:
                print(f"⚠️ Buzzer falhou: {e}")
        
        # Servos (braço/cabeça)
        try:
            self.servos = ServoController()
        except Exception as e:
            print(f"⚠️ Servos falharam: {e}")
        
        # Câmeras
        try:
            self.cameras = DualCameraSystem()
            self.cameras.start()
        except Exception as e:
            print(f"⚠️ Câmeras falharam: {e}")
        
        self.running = True
        print("\n✅ Sistema inicializado!\n")
        return True
    
    # ==========================================
    # MOVIMENTO
    # ==========================================
    
    def drive(self, vx: float = 0.0, vy: float = 0.0, vz: float = 0.0):
        """
        Movimento do carro (cinemática mecanum)
        
        Args:
            vx: Forward/backward (-1.0 a 1.0)
            vy: Strafe left/right (-1.0 a 1.0)
            vz: Rotação (-1.0 a 1.0)
        """
        if not self.motor:
            return {"status": "error", "error": "Motor não disponível"}
        
        # Garantir navegação com USB
        if self.cameras:
            self.cameras.force_usb()
        
        # Converter para PWM
        max_pwm = self.speed
        
        # Cinemática mecanum
        fl = int((vx + vy + vz) * max_pwm)
        bl = int((vx - vy + vz) * max_pwm)
        fr = int((vx - vy - vz) * max_pwm)
        br = int((vx + vy - vz) * max_pwm)
        
        # INVERTER TUDO (motores físicos invertidos)
        fl, bl, fr, br = -fl, -bl, -fr, -br
        
        # INVERTER ESQUERDA/DIREITA
        fl, fr = fr, fl
        bl, br = br, bl
        
        try:
            self.motor.set_motor_model(fl, bl, fr, br)
            self.last_motor_cmd = [fl, bl, fr, br]
            
            return {
                "status": "ok",
                "motors": [fl, bl, fr, br],
                "vx": vx, "vy": vy, "vz": vz
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def stop(self):
        """Para o carro"""
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
            self.last_motor_cmd = [0, 0, 0, 0]
    
    # ==========================================
    # BRAÇO/CABEÇA
    # ==========================================
    
    def move_servo(
        self,
        channel: int,
        angle: int,
        smooth: bool = True,
        enable_camera: bool = True
    ):
        """
        Move servo individual
        
        Args:
            channel: 0=Base, 1=Ombro, 2=Cotovelo, 3=Cabeça
            angle: Ângulo (0-180)
            smooth: Movimento suave
            enable_camera: Ativar Pi Camera
        """
        if not self.servos:
            return {"status": "error", "error": "Servos não disponíveis"}
        
        # Ativar modo análise se solicitado
        if enable_camera and self.cameras:
            self.cameras.enable_arm_mode()
        
        success = self.servos.move_servo(channel, angle, smooth)
        
        return {
            "status": "ok" if success else "error",
            "channel": channel,
            "angle": angle,
            "camera": self.cameras.active_camera if self.cameras else None
        }
    
    def disable_arm_camera(self):
        """Desativa modo braço (volta para navegação)"""
        if self.cameras:
            self.cameras.disable_arm_mode()
        
        return {"status": "ok", "camera": "usb"}
    
    def get_servo_positions(self):
        """Retorna posições de todos servos"""
        if self.servos:
            return self.servos.get_position()
        return {}
    
    # ==========================================
    # CÂMERAS
    # ==========================================
    
    def force_camera(self, camera: str):
        """
        Força uso de uma câmera específica
        
        Args:
            camera: "usb" ou "picam"
        """
        if not self.cameras:
            return {"status": "error", "error": "Câmeras não disponíveis"}
        
        if camera == "usb":
            self.cameras.force_usb()
        elif camera == "picam":
            self.cameras.force_picam()
        else:
            return {"status": "error", "error": f"Câmera inválida: {camera}"}
        
        return {
            "status": "ok",
            "active_camera": self.cameras.active_camera
        }
    
    def get_camera_frame(self):
        """Retorna frame da câmera ativa"""
        if self.cameras:
            return self.cameras.get_frame()
        return None
    
    def get_camera_status(self):
        """Status das câmeras"""
        if self.cameras:
            return self.cameras.get_status()
        return {}
    
    # ==========================================
    # SENSORES
    # ==========================================
    
    def read_sensors(self) -> Dict:
        """Lê todos os sensores"""
        data = {
            'timestamp': time.time(),
            'ultrasonic_cm': None,
            'battery_v': None,
            'servo_positions': None,
            'camera_status': None
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
        
        # Servos
        if self.servos:
            data['servo_positions'] = self.get_servo_positions()
        
        # Câmeras
        if self.cameras:
            data['camera_status'] = self.get_camera_status()
        
        self.sensor_data = data
        return data
    
    # ==========================================
    # CLEANUP
    # ==========================================
    
    def cleanup(self):
        """Desliga tudo com segurança"""
        print("\n🛑 Encerrando EVA Robot...\n")
        
        self.running = False
        
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
            self.motor.close()
            print("  ✅ Motor desligado")
        
        if self.cameras:
            self.cameras.stop()
            print("  ✅ Câmeras paradas")
        
        if self.servos:
            self.servos.home_position()
            print("  ✅ Servos em home")
        
        if self.ultrasonic:
            self.ultrasonic.close()
            print("  ✅ Ultrasonic fechado")
        
        if self.adc:
            self.adc.close_i2c()
            print("  ✅ ADC fechado")
        
        if self.buzzer:
            self.buzzer.set_state(True)
            time.sleep(0.2)
            self.buzzer.set_state(False)
            self.buzzer.close()
            print("  ✅ Buzzer desligado")
        
        print("\n✅ Sistema encerrado!\n")


# ==========================================
# TESTE STANDALONE
# ==========================================

def test_system():
    """Menu de testes"""
    robot = EVARobotCore()
    
    if not robot.initialize():
        print("❌ Falha na inicialização")
        return
    
    try:
        while True:
            print("\n" + "="*60)
            print("🎮 EVA ROBOT - MENU DE TESTES")
            print("="*60)
            
            print("\n🚗 MOVIMENTO:")
            print("  w - Frente    s - Ré")
            print("  a - Esquerda  d - Direita")
            print("  x - PARAR")
            
            print("\n🦾 SERVOS:")
            print("  1 - Mover Base")
            print("  2 - Mover Ombro")
            print("  3 - Mover Cotovelo")
            print("  4 - Mover Cabeça")
            print("  h - Home (todos)")
            
            print("\n📷 CÂMERAS:")
            print("  u - Forçar USB Webcam")
            print("  p - Forçar Pi Camera")
            print("  c - Status câmeras")
            
            print("\n📊 SENSORES:")
            print("  i - Ler sensores")
            
            print("\n❌ SAIR:")
            print("  q - Sair")
            
            print("="*60)
            
            cmd = input("\n> ").strip().lower()
            
            # Movimento
            if cmd == 'w':
                robot.drive(vx=0.5)
                time.sleep(0.5)
                robot.stop()
            elif cmd == 's':
                robot.drive(vx=-0.5)
                time.sleep(0.5)
                robot.stop()
            elif cmd == 'a':
                robot.drive(vz=0.5)
                time.sleep(0.5)
                robot.stop()
            elif cmd == 'd':
                robot.drive(vz=-0.5)
                time.sleep(0.5)
                robot.stop()
            elif cmd == 'x':
                robot.stop()
            
            # Servos
            elif cmd == '1':
                angle = int(input("Ângulo Base (0-180): "))
                robot.move_servo(0, angle)
            elif cmd == '2':
                angle = int(input("Ângulo Ombro (0-180): "))
                robot.move_servo(1, angle)
            elif cmd == '3':
                angle = int(input("Ângulo Cotovelo (0-180): "))
                robot.move_servo(2, angle)
            elif cmd == '4':
                angle = int(input("Ângulo Cabeça (0-180): "))
                robot.move_servo(3, angle)
            elif cmd == 'h':
                robot.servos.home_position()
            
            # Câmeras
            elif cmd == 'u':
                robot.force_camera('usb')
            elif cmd == 'p':
                robot.force_camera('picam')
            elif cmd == 'c':
                status = robot.get_camera_status()
                print(f"\n📊 Status: {status}")
            
            # Sensores
            elif cmd == 'i':
                data = robot.read_sensors()
                print(f"\n📊 SENSORES:")
                print(f"  Ultrasonic: {data.get('ultrasonic_cm')} cm")
                print(f"  Bateria: {data.get('battery_v')} V")
                print(f"  Câmera: {data.get('camera_status')}")
            
            # Sair
            elif cmd == 'q':
                break
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Ctrl+C detectado")
    
    finally:
        robot.cleanup()


if __name__ == '__main__':
    test_system()