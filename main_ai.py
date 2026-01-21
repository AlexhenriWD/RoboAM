#!/usr/bin/env python3
"""
Sistema Principal do Freenove Smart Car com IA (Groq)
Modo autônomo com visão computacional e tomada de decisões
"""

import sys
import time
import json
import threading
from pathlib import Path
from typing import Dict, Optional

# Importar hardware
sys.path.insert(0, str(Path(__file__).parent / 'hardware'))
from hardware.motor import Ordinary_Car
from hardware.servo import Servo
from hardware.ultrasonic import Ultrasonic
from hardware.infrared import Infrared
from hardware.adc import ADC
from hardware.buzzer import Buzzer

# Importar IA
from ai.groq_client import GroqVisionClient

try:
    import cv2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    print("⚠️  OpenCV não disponível - modo sem visão")

try:
    from led import Led
    LED_AVAILABLE = True
except ImportError:
    LED_AVAILABLE = False
    print("⚠️  LED não disponível")


class AICarController:
    """Controlador principal do carro com IA"""
    
    def __init__(self, config_path: str = 'config.json'):
        """Inicializa o sistema"""
        
        # Carregar configuração
        self.config = self._load_config(config_path)
        
        # Estado
        self.running = False
        self.ai_enabled = False
        self.vision_enabled = False
        
        # Hardware
        self.motor = None
        self.servo = None
        self.ultrasonic = None
        self.infrared = None
        self.adc = None
        self.buzzer = None
        self.led = None
        self.camera = None
        
        # IA
        self.groq_client = None
        
        # Threads
        self.ai_thread = None
        self.sensor_thread = None
        
        # Dados
        self.current_frame = None
        self.sensor_data = {
            'ultrasonic': 0,
            'infrared': [0, 0, 0],
            'light_left': 0,
            'light_right': 0,
            'battery': 0
        }
        self.last_decision = None
        
        # Estatísticas
        self.stats = {
            'decisions_made': 0,
            'errors': 0,
            'distance_traveled': 0,
            'start_time': time.time()
        }
        
        self.initialize()
    
    def _load_config(self, path: str) -> Dict:
        """Carrega configuração do arquivo JSON"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Config não encontrada: {path}, usando padrões")
            return {
                'groq_api_key': '',
                'ai_mode': 'sensor_only',  # sensor_only, vision, hybrid
                'decision_interval': 1.0,
                'max_speed': 60,
                'safety_distance': 30,
                'camera_enabled': True
            }
    
    def initialize(self):
        """Inicializa todos os componentes"""
        print("\n" + "="*60)
        print("🤖 Iniciando Freenove AI Car")
        print("="*60)
        
        try:
            # Hardware básico
            self.motor = Ordinary_Car()
            print("✓ Motor inicializado")
            
            self.servo = Servo()
            print("✓ Servo inicializado")
            
            self.ultrasonic = Ultrasonic()
            print("✓ Ultrasonic inicializado")
            
            self.infrared = Infrared()
            print("✓ Infrared inicializado")
            
            self.adc = ADC()
            print("✓ ADC inicializado")
            
            self.buzzer = Buzzer()
            print("✓ Buzzer inicializado")
            
            # LED (opcional)
            if LED_AVAILABLE:
                self.led = Led()
                print("✓ LED inicializado")
            
            # Câmera (opcional)
            if CAMERA_AVAILABLE and self.config.get('camera_enabled'):
                try:
                    self.camera = cv2.VideoCapture(0)
                    if self.camera.isOpened():
                        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        print("✓ Câmera inicializada")
                    else:
                        self.camera = None
                except:
                    self.camera = None
            
            # Cliente Groq
            api_key = self.config.get('groq_api_key')
            if api_key:
                try:
                    self.groq_client = GroqVisionClient(api_key)
                    print("✓ Groq AI inicializada")
                except Exception as e:
                    print(f"✗ Erro ao inicializar Groq: {e}")
            else:
                print("⚠️  GROQ_API_KEY não configurada - IA desabilitada")
            
            self.running = True
            print("\n✓ Sistema inicializado com sucesso!")
            print("="*60 + "\n")
            
            # Iniciar threads
            self._start_threads()
            
        except Exception as e:
            print(f"\n✗ Erro na inicialização: {e}")
            self.cleanup()
            raise
    
    def _start_threads(self):
        """Inicia threads de monitoramento"""
        self.sensor_thread = threading.Thread(target=self._sensor_loop, daemon=True)
        self.sensor_thread.start()
        print("✓ Thread de sensores iniciada")
    
    def _sensor_loop(self):
        """Loop de atualização de sensores"""
        while self.running:
            try:
                # Ler sensores
                self.sensor_data['ultrasonic'] = round(self.ultrasonic.get_distance() or 0, 2)
                self.sensor_data['infrared'] = [
                    self.infrared.read_one_infrared(1),
                    self.infrared.read_one_infrared(2),
                    self.infrared.read_one_infrared(3)
                ]
                self.sensor_data['light_left'] = round(self.adc.read_adc(0), 2)
                self.sensor_data['light_right'] = round(self.adc.read_adc(1), 2)
                self.sensor_data['battery'] = round(
                    self.adc.read_adc(2) * (3 if self.adc.pcb_version == 1 else 2), 2
                )
                
                # Capturar frame se câmera disponível
                if self.camera and self.camera.isOpened():
                    ret, frame = self.camera.read()
                    if ret:
                        self.current_frame = frame
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Erro no loop de sensores: {e}")
                time.sleep(0.5)
    
    def enable_ai(self, vision: bool = False):
        """Ativa modo IA"""
        if not self.groq_client:
            print("❌ Groq client não inicializado")
            return False
        
        self.ai_enabled = True
        self.vision_enabled = vision and self.camera is not None
        
        mode = "visão" if self.vision_enabled else "sensores"
        print(f"\n🤖 IA ATIVADA - Modo: {mode}")
        
        if self.led and LED_AVAILABLE:
            self.led.colorBlink(3)  # Indicar que IA está ativa
        
        # Iniciar thread de IA
        if self.ai_thread is None or not self.ai_thread.is_alive():
            self.ai_thread = threading.Thread(target=self._ai_loop, daemon=True)
            self.ai_thread.start()
        
        return True
    
    def disable_ai(self):
        """Desativa modo IA"""
        self.ai_enabled = False
        self.motor.set_motor_model(0, 0, 0, 0)
        print("\n⏸️  IA DESATIVADA")
        
        if self.led and LED_AVAILABLE:
            self.led.colorBlink(0)
    
    def _ai_loop(self):
        """Loop principal de decisões da IA"""
        interval = self.config.get('decision_interval', 1.0)
        
        while self.running:
            if not self.ai_enabled:
                time.sleep(0.5)
                continue
            
            try:
                # Fazer decisão
                if self.vision_enabled and self.current_frame is not None:
                    result = self.groq_client.analyze_scene(
                        self.current_frame,
                        self.sensor_data
                    )
                else:
                    result = self.groq_client.simple_decision(self.sensor_data)
                
                if result['success']:
                    decision = result['decision']
                    self.last_decision = decision
                    self._execute_decision(decision)
                    self.stats['decisions_made'] += 1
                    
                    # Log
                    print(f"\n🎯 Decisão #{self.stats['decisions_made']}")
                    print(f"   Ação: {decision.get('recommended_action', 'N/A')}")
                    print(f"   Velocidade: {decision.get('speed', 0)}%")
                    print(f"   Razão: {decision.get('reason', 'N/A')}")
                    print(f"   Segurança: {decision.get('safety_level', 'N/A')}")
                else:
                    print(f"⚠️  Erro na IA: {result.get('error')}")
                    self.stats['errors'] += 1
                
                time.sleep(interval)
                
            except Exception as e:
                print(f"❌ Erro no loop de IA: {e}")
                self.stats['errors'] += 1
                self.motor.set_motor_model(0, 0, 0, 0)
                time.sleep(1)
    
    def _execute_decision(self, decision: Dict):
        """Executa decisão da IA no hardware"""
        action = decision.get('recommended_action', 'stop')
        speed_percent = decision.get('speed', 0)
        max_speed = self.config.get('max_speed', 60)
        
        # Calcular velocidade real (0-2000)
        speed = int((speed_percent / 100.0) * max_speed * 33.33)  # 2000 = 100%
        
        # Executar movimento
        if action == 'forward':
            self.motor.set_motor_model(speed, speed, speed, speed)
        elif action == 'backward':
            self.motor.set_motor_model(-speed, -speed, -speed, -speed)
        elif action == 'left':
            self.motor.set_motor_model(-speed, -speed, speed, speed)
        elif action == 'right':
            self.motor.set_motor_model(speed, speed, -speed, -speed)
        else:  # stop
            self.motor.set_motor_model(0, 0, 0, 0)
    
    def print_status(self):
        """Imprime status do sistema"""
        uptime = time.time() - self.stats['start_time']
        
        print("\n" + "="*60)
        print("📊 STATUS DO SISTEMA")
        print("="*60)
        print(f"Tempo online: {uptime:.1f}s")
        print(f"Decisões tomadas: {self.stats['decisions_made']}")
        print(f"Erros: {self.stats['errors']}")
        print(f"\n📡 SENSORES:")
        print(f"  Ultrassom: {self.sensor_data['ultrasonic']} cm")
        print(f"  Infrared: {self.sensor_data['infrared']}")
        print(f"  Luz: L={self.sensor_data['light_left']}V, R={self.sensor_data['light_right']}V")
        print(f"  Bateria: {self.sensor_data['battery']}V")
        
        if self.last_decision:
            print(f"\n🤖 ÚLTIMA DECISÃO:")
            print(f"  {json.dumps(self.last_decision, indent=2, ensure_ascii=False)}")
        
        print("="*60 + "\n")
    
    def cleanup(self):
        """Limpa recursos"""
        print("\n🛑 Encerrando sistema...")
        self.running = False
        self.ai_enabled = False
        
        if self.motor:
            self.motor.set_motor_model(0, 0, 0, 0)
            self.motor.close()
        
        if self.camera and self.camera.isOpened():
            self.camera.release()
        
        if self.ultrasonic:
            self.ultrasonic.close()
        
        if self.infrared:
            self.infrared.close()
        
        if self.adc:
            self.adc.close_i2c()
        
        if self.buzzer:
            self.buzzer.close()
        
        if self.led and LED_AVAILABLE:
            self.led.colorBlink(0)
        
        print("✓ Sistema encerrado\n")


def main():
    """Função principal"""
    print("\n🚗 Freenove AI Car - Sistema Autônomo")
    
    car = AICarController()
    
    try:
        # Menu interativo
        while True:
            print("\n" + "="*60)
            print("COMANDOS:")
            print("  1 - Ativar IA (somente sensores)")
            print("  2 - Ativar IA (com visão)")
            print("  3 - Desativar IA")
            print("  4 - Ver status")
            print("  5 - Sair")
            print("="*60)
            
            choice = input("\nEscolha: ").strip()
            
            if choice == '1':
                car.enable_ai(vision=False)
            elif choice == '2':
                if not CAMERA_AVAILABLE:
                    print("❌ Câmera não disponível")
                else:
                    car.enable_ai(vision=True)
            elif choice == '3':
                car.disable_ai()
            elif choice == '4':
                car.print_status()
            elif choice == '5':
                break
            else:
                print("❌ Opção inválida")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detectado")
    
    finally:
        car.cleanup()


if __name__ == '__main__':
    main()