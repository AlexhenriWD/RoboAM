#!/usr/bin/env python3
"""
Sistema Principal do Freenove Smart Car com IA e Braço Robótico
Versão Otimizada - Focado em Ultrasonic + Câmera + Braço
"""

import sys
import time
import json
import threading
from pathlib import Path
from typing import Dict, Optional
import requests

# Importar hardware
sys.path.insert(0, str(Path(__file__).parent / 'hardware'))
from hardware.motor import Ordinary_Car
from hardware.ultrasonic import Ultrasonic
from hardware.adc import ADC
from hardware.buzzer import Buzzer
from arm_controller import ArmController

# Tentar importar câmera
try:
    import cv2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    print("⚠️  OpenCV não disponível - modo sem visão")


class AICarSystem:
    """Sistema principal do carro inteligente"""
    
    def __init__(self, config_path: str = 'config.json'):
        """Inicializa o sistema completo"""
        
        # Configuração
        self.config = self._load_config(config_path)
        
        # Estado
        self.running = False
        self.ai_enabled = False
        self.camera_enabled = False
        self.arm_enabled = False
        
        # Hardware
        self.motor = None
        self.ultrasonic = None
        self.adc = None
        self.buzzer = None
        self.camera = None
        self.arm = None
        
        # Threads
        self.sensor_thread = None
        self.ai_thread = None
        
        # Dados
        self.current_frame = None
        self.sensor_data = {
            'ultrasonic': 0,
            'battery': 0,
            'arm_position': {}
        }
        self.last_decision = None
        
        # Estatísticas
        self.stats = {
            'decisions_made': 0,
            'errors': 0,
            'objects_detected': 0,
            'arm_actions': 0,
            'start_time': time.time()
        }
        
        # URL da IA externa (LM Studio, Ollama, etc)
        self.external_ai_url = self.config.get('external_ai_url', None)
        
        self.initialize()
    
    def _load_config(self, path: str) -> Dict:
        """Carrega configuração"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Config não encontrada: {path}")
            return {
                'ai_mode': 'sensor_only',
                'decision_interval': 2.0,
                'max_speed': 50,
                'safety_distance': 30,
                'camera_enabled': True,
                'arm_enabled': True,
                'detection_distance': 50,
                'external_ai_url': None
            }
    
    def initialize(self):
        """Inicializa todos os componentes"""
        print("\n" + "="*60)
        print("🤖 Iniciando Freenove AI Car System v2.0")
        print("="*60)
        
        try:
            # Motor
            self.motor = Ordinary_Car()
            print("✓ Motor inicializado")
            
            # Ultrasonic
            self.ultrasonic = Ultrasonic()
            print("✓ Ultrasonic inicializado")
            
            # ADC (bateria)
            self.adc = ADC()
            print("✓ ADC inicializado")
            
            # Buzzer
            self.buzzer = Buzzer()
            print("✓ Buzzer inicializado")
            
            # Beep de inicialização
            for _ in range(3):
                self.buzzer.set_state(True)
                time.sleep(0.1)
                self.buzzer.set_state(False)
                time.sleep(0.1)
            
            # Câmera (opcional)
            if CAMERA_AVAILABLE and self.config.get('camera_enabled'):
                try:
                    self.camera = cv2.VideoCapture(0)
                    if self.camera.isOpened():
                        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                        self.camera.set(cv2.CAP_PROP_FPS, 30)
                        self.camera_enabled = True
                        print("✓ Câmera inicializada (1280x720)")
                    else:
                        self.camera = None
                except:
                    self.camera = None
            
            # Braço robótico (opcional)
            if self.config.get('arm_enabled'):
                try:
                    self.arm = ArmController()
                    self.arm_enabled = True
                    print("✓ Braço robótico inicializado")
                except Exception as e:
                    print(f"⚠️  Braço não disponível: {e}")
                    self.arm_enabled = False
            
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
                distance = round(self.ultrasonic.get_distance() or 0, 2)
                self.sensor_data['ultrasonic'] = distance
                self.sensor_data['battery'] = round(
                    self.adc.read_adc(2) * (3 if self.adc.pcb_version == 1 else 2), 2
                )
                
                # Posição do braço
                if self.arm:
                    self.sensor_data['arm_position'] = self.arm.get_current_position()
                
                # Capturar frame
                if self.camera and self.camera.isOpened():
                    ret, frame = self.camera.read()
                    if ret:
                        self.current_frame = frame
                
                # Detecção de proximidade -> ativar câmera e braço
                if distance < self.config.get('detection_distance', 50) and distance > 0:
                    if not self.camera_enabled and self.camera:
                        print(f"\n📷 Objeto detectado a {distance}cm - Ativando câmera")
                        self.camera_enabled = True
                        self.stats['objects_detected'] += 1
                        
                        # Beep de detecção
                        self.buzzer.set_state(True)
                        time.sleep(0.05)
                        self.buzzer.set_state(False)
                        
                        # Posição de atenção do braço
                        if self.arm:
                            self.arm.point_forward()
                            self.stats['arm_actions'] += 1
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Erro no loop de sensores: {e}")
                time.sleep(0.5)
    
    def send_to_external_ai(self, prompt: str, context: Dict) -> Optional[Dict]:
        """Envia comando para IA externa (LM Studio, Ollama, etc)"""
        if not self.external_ai_url:
            return None
        
        try:
            # Preparar payload
            payload = {
                'model': 'local-model',  # Ajustar conforme necessário
                'messages': [
                    {
                        'role': 'system',
                        'content': f"""Você é uma IA que controla um carro robótico com braço mecânico.
                        
Capacidades do carro:
- Mover: forward, backward, left, right, stop
- Velocidade: 0-100%

Capacidades do braço:
- Base: rotação 0-180°
- Ombro: elevação 75-175°
- Cotovelo: flexão 70-145°
- Garra: abertura 40° (aberta) - 100° (fechada)

Posições pré-definidas:
- home: posição inicial
- point_forward: apontar para frente
- grab: posição para pegar objetos
- rest: posição de descanso
- wave: acenar

Responda APENAS com JSON válido:
{{
    "car_action": "forward|backward|left|right|stop",
    "car_speed": 0-100,
    "arm_action": "home|point_forward|grab|rest|wave|custom",
    "arm_positions": {{"base": 90, "shoulder": 90, "elbow": 90, "gripper": 70}},
    "reason": "explicação da ação"
}}"""
                    },
                    {
                        'role': 'user',
                        'content': f"{prompt}\n\nContexto:\n{json.dumps(context, indent=2)}"
                    }
                ],
                'temperature': 0.7,
                'max_tokens': 500
            }
            
            # Enviar requisição
            response = requests.post(
                f"{self.external_ai_url}/v1/chat/completions",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # Tentar parsear JSON
                try:
                    decision = json.loads(content)
                    return {
                        'success': True,
                        'decision': decision
                    }
                except json.JSONDecodeError:
                    return {
                        'success': False,
                        'error': 'Resposta da IA não é JSON válido'
                    }
            else:
                return {
                    'success': False,
                    'error': f'Erro HTTP {response.status_code}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def execute_ai_command(self, command: Dict):
        """Executa comando da IA"""
        try:
            # Ação do carro
            car_action = command.get('car_action', 'stop')
            car_speed = min(command.get('car_speed', 0), self.config.get('max_speed', 50))
            
            speed = int((car_speed / 100.0) * 2000)
            
            # Executar movimento (INVERTIDO forward/backward)
            if car_action == 'forward':
                self.motor.set_motor_model(-speed, -speed, -speed, -speed)
            elif car_action == 'backward':
                self.motor.set_motor_model(speed, speed, speed, speed)
            elif car_action == 'left':
                self.motor.set_motor_model(speed, speed, -speed, -speed)
            elif car_action == 'right':
                self.motor.set_motor_model(-speed, -speed, speed, speed)
            else:
                self.motor.set_motor_model(0, 0, 0, 0)
            
            # Ação do braço
            if self.arm:
                arm_action = command.get('arm_action', 'home')
                
                if arm_action == 'home':
                    self.arm.home_position()
                elif arm_action == 'point_forward':
                    self.arm.point_forward()
                elif arm_action == 'grab':
                    self.arm.grab_position()
                elif arm_action == 'rest':
                    self.arm.rest_position()
                elif arm_action == 'wave':
                    self.arm.wave_gesture()
                elif arm_action == 'custom':
                    # Posições customizadas
                    positions = command.get('arm_positions', {})
                    if 'base' in positions:
                        self.arm.move_servo(0, positions['base'])
                    if 'shoulder' in positions:
                        self.arm.move_servo(1, positions['shoulder'])
                    if 'elbow' in positions:
                        self.arm.move_servo(2, positions['elbow'])
                    if 'gripper' in positions:
                        self.arm.move_servo(4, positions['gripper'])
                
                self.stats['arm_actions'] += 1
            
            self.stats['decisions_made'] += 1
            print(f"\n✓ Comando executado: {command.get('reason', 'N/A')}")
            
        except Exception as e:
            print(f"✗ Erro ao executar comando: {e}")
            self.stats['errors'] += 1
    
    def autonomous_mode(self):
        """Modo autônomo com IA externa"""
        print("\n🤖 MODO AUTÔNOMO ATIVADO")
        print("Pressione Ctrl+C para parar\n")
        
        self.ai_enabled = True
        interval = self.config.get('decision_interval', 2.0)
        
        try:
            while self.ai_enabled and self.running:
                # Preparar contexto
                context = {
                    'ultrasonic_distance': self.sensor_data['ultrasonic'],
                    'battery': self.sensor_data['battery'],
                    'arm_position': self.sensor_data['arm_position'],
                    'camera_active': self.camera_enabled
                }
                
                # Decisão baseada em proximidade
                distance = self.sensor_data['ultrasonic']
                
                if distance < 20 and distance > 0:
                    prompt = "Objeto muito próximo! O que fazer?"
                elif distance < 40 and distance > 0:
                    prompt = "Objeto detectado próximo. Investigar?"
                else:
                    prompt = "Caminho livre. Continue explorando."
                
                # Consultar IA externa
                result = self.send_to_external_ai(prompt, context)
                
                if result and result.get('success'):
                    self.execute_ai_command(result['decision'])
                else:
                    # Fallback: comportamento básico
                    if distance < 20:
                        self.motor.set_motor_model(1000, 1000, 1000, 1000)  # Ré
                    elif distance < 40:
                        self.motor.set_motor_model(0, 0, 0, 0)  # Parar
                    else:
                        self.motor.set_motor_model(-800, -800, -800, -800)  # Frente
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n⏸️  Modo autônomo interrompido")
        finally:
            self.ai_enabled = False
            self.motor.set_motor_model(0, 0, 0, 0)
    
    def manual_control(self):
        """Controle manual interativo"""
        print("\n🎮 CONTROLE MANUAL")
        print("="*60)
        
        while True:
            print("\nComandos:")
            print("  w - Frente    s - Ré      a - Esquerda  d - Direita")
            print("  x - Parar")
            print("  1-7 - Posições do braço")
            print("  g - Abrir garra    h - Fechar garra")
            print("  q - Sair")
            
            cmd = input("\n> ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == 'w':
                self.motor.set_motor_model(-1000, -1000, -1000, -1000)
            elif cmd == 's':
                self.motor.set_motor_model(1000, 1000, 1000, 1000)
            elif cmd == 'a':
                self.motor.set_motor_model(1000, 1000, -1000, -1000)
            elif cmd == 'd':
                self.motor.set_motor_model(-1000, -1000, 1000, 1000)
            elif cmd == 'x':
                self.motor.set_motor_model(0, 0, 0, 0)
            elif cmd == '1' and self.arm:
                self.arm.home_position()
            elif cmd == '2' and self.arm:
                self.arm.point_forward()
            elif cmd == '3' and self.arm:
                self.arm.grab_position()
            elif cmd == '4' and self.arm:
                self.arm.rest_position()
            elif cmd == '5' and self.arm:
                self.arm.wave_gesture()
            elif cmd == 'g' and self.arm:
                self.arm.open_gripper()
            elif cmd == 'h' and self.arm:
                self.arm.close_gripper()
            else:
                print("✗ Comando inválido")
    
    def print_status(self):
        """Imprime status do sistema"""
        uptime = time.time() - self.stats['start_time']
        
        print("\n" + "="*60)
        print("📊 STATUS DO SISTEMA")
        print("="*60)
        print(f"⏱️  Tempo online: {uptime:.1f}s")
        print(f"🧠 Decisões tomadas: {self.stats['decisions_made']}")
        print(f"🤖 Ações do braço: {self.stats['arm_actions']}")
        print(f"👁️  Objetos detectados: {self.stats['objects_detected']}")
        print(f"❌ Erros: {self.stats['errors']}")
        
        print(f"\n📡 SENSORES:")
        print(f"  Ultrassom: {self.sensor_data['ultrasonic']} cm")
        print(f"  Bateria: {self.sensor_data['battery']}V")
        
        if self.arm:
            print(f"\n🦾 BRAÇO:")
            for ch, info in self.sensor_data['arm_position'].items():
                print(f"  {info['name']}: {info['angle']}°")
        
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
        
        if self.adc:
            self.adc.close_i2c()
        
        if self.arm:
            self.arm.cleanup()
        
        if self.buzzer:
            self.buzzer.set_state(True)
            time.sleep(0.3)
            self.buzzer.set_state(False)
            self.buzzer.close()
        
        print("✓ Sistema encerrado\n")


def main():
    """Função principal"""
    print("\n🚗 Freenove AI Car System v2.0")
    print("Sistema Inteligente com Braço Robótico\n")
    
    car = AICarSystem()
    
    try:
        while True:
            print("\n" + "="*60)
            print("MENU PRINCIPAL:")
            print("  1 - Modo Autônomo (IA)")
            print("  2 - Controle Manual")
            print("  3 - Ver Status")
            print("  4 - Testar Braço")
            print("  5 - Configurações")
            print("  0 - Sair")
            print("="*60)
            
            choice = input("\nEscolha: ").strip()
            
            if choice == '1':
                if car.external_ai_url:
                    car.autonomous_mode()
                else:
                    print("✗ Configure external_ai_url no config.json")
            elif choice == '2':
                car.manual_control()
            elif choice == '3':
                car.print_status()
            elif choice == '4':
                if car.arm:
                    car.arm.wave_gesture()
                else:
                    print("✗ Braço não disponível")
            elif choice == '5':
                print(f"\nConfiguração atual:")
                print(f"  IA Externa: {car.external_ai_url or 'Não configurada'}")
                print(f"  Câmera: {'Ativa' if car.camera_enabled else 'Inativa'}")
                print(f"  Braço: {'Ativo' if car.arm_enabled else 'Inativo'}")
            elif choice == '0':
                break
            else:
                print("✗ Opção inválida")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detectado")
    
    finally:
        car.cleanup()


if __name__ == '__main__':
    main()