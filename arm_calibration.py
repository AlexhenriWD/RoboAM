#!/usr/bin/env python3
"""
Controlador do Braço Robótico com Garra
Sistema otimizado com limites seguros e proteção contra sobrecarga
"""

import time
from typing import Dict, Optional
from servo import Servo


class ArmController:
    """Controlador seguro do braço robótico"""
    
    def __init__(self):
        self.servo = Servo()
        
        # Configuração SEGURA baseada nos testes
        self.servos = {
            0: {  # Base (Rotação)
                'name': 'Base',
                'min': 0,
                'max': 180,
                'home': 90,
                'current': 90
            },
            1: {  # Ombro (Elevação)
                'name': 'Ombro',
                'min': 75,
                'max': 175,
                'home': 90,
                'current': 90
            },
            2: {  # Cotovelo
                'name': 'Cotovelo',
                'min': 70,
                'max': 145,
                'home': 90,
                'current': 90
            },
            4: {  # Garra
                'name': 'Garra',
                'min': 40,   # Aberta
                'max': 100,  # Fechada
                'home': 70,  # Meio-aberta
                'current': 70
            }
        }
        
        # Delay mínimo entre movimentos (proteção)
        self.min_delay = 0.3
        self.last_move_time = {ch: 0 for ch in self.servos.keys()}
        
        # Inicializar em posição home
        self.home_position(silent=True)
    
    def _validate_move(self, channel: int, angle: int) -> tuple[bool, str]:
        """Valida se o movimento é seguro"""
        if channel not in self.servos:
            return False, f"Canal {channel} inválido"
        
        servo = self.servos[channel]
        
        # Verificar limites
        if angle < servo['min'] or angle > servo['max']:
            return False, f"{servo['name']}: ângulo fora dos limites ({servo['min']}° - {servo['max']}°)"
        
        # Verificar se já está na posição (evita sobrecarga)
        if abs(servo['current'] - angle) < 2:  # Tolerância de 2 graus
            return False, f"{servo['name']}: já está na posição {angle}°"
        
        # Verificar delay mínimo
        elapsed = time.time() - self.last_move_time[channel]
        if elapsed < self.min_delay:
            wait_time = self.min_delay - elapsed
            time.sleep(wait_time)
        
        return True, "OK"
    
    def move_servo(self, channel: int, angle: int, delay: float = None) -> Dict:
        """Move um servo com validação e proteção"""
        # Validar movimento
        valid, message = self._validate_move(channel, angle)
        if not valid:
            return {
                'success': False,
                'channel': channel,
                'error': message,
                'current_angle': self.servos[channel]['current']
            }
        
        try:
            # Executar movimento
            self.servo.set_servo_pwm(str(channel), angle)
            self.servos[channel]['current'] = angle
            self.last_move_time[channel] = time.time()
            
            # Aguardar delay se especificado
            if delay and delay > 0:
                time.sleep(delay)
            
            return {
                'success': True,
                'channel': channel,
                'angle': angle,
                'servo_name': self.servos[channel]['name']
            }
            
        except Exception as e:
            return {
                'success': False,
                'channel': channel,
                'error': str(e)
            }
    
    def get_current_position(self) -> Dict:
        """Retorna posição atual de todos os servos"""
        return {
            ch: {
                'name': info['name'],
                'angle': info['current'],
                'min': info['min'],
                'max': info['max']
            }
            for ch, info in self.servos.items()
        }
    
    def home_position(self, silent: bool = False) -> bool:
        """Retorna todos os servos para posição home"""
        if not silent:
            print("\n🏠 Retornando para posição HOME...")
        
        success = True
        for channel in sorted(self.servos.keys()):
            home_angle = self.servos[channel]['home']
            result = self.move_servo(channel, home_angle, delay=0.4)
            
            if not silent:
                if result['success']:
                    print(f"  ✓ {result['servo_name']}: {home_angle}°")
                else:
                    print(f"  ✗ {result.get('error')}")
                    success = False
        
        if not silent and success:
            print("✓ Posição HOME concluída!\n")
        
        return success
    
    def open_gripper(self) -> Dict:
        """Abre a garra completamente"""
        return self.move_servo(4, self.servos[4]['min'], delay=0.5)
    
    def close_gripper(self) -> Dict:
        """Fecha a garra completamente"""
        return self.move_servo(4, self.servos[4]['max'], delay=0.5)
    
    def set_gripper(self, percentage: int) -> Dict:
        """
        Define abertura da garra por porcentagem
        0% = totalmente aberta, 100% = totalmente fechada
        """
        if percentage < 0 or percentage > 100:
            return {'success': False, 'error': 'Porcentagem deve ser 0-100'}
        
        servo_min = self.servos[4]['min']
        servo_max = self.servos[4]['max']
        angle = int(servo_min + (servo_max - servo_min) * (percentage / 100.0))
        
        return self.move_servo(4, angle, delay=0.3)
    
    def point_forward(self) -> bool:
        """Posição de apontar para frente"""
        print("👉 Apontando para frente...")
        moves = [
            (0, 90),   # Base centro
            (1, 120),  # Ombro elevado
            (2, 90),   # Cotovelo reto
            (4, 40)    # Garra aberta
        ]
        return self._execute_sequence(moves)
    
    def grab_position(self) -> bool:
        """Posição para pegar objetos"""
        print("🤲 Posição de captura...")
        moves = [
            (0, 90),   # Base centro
            (1, 140),  # Ombro baixo
            (2, 110),  # Cotovelo flexionado
            (4, 40)    # Garra aberta
        ]
        return self._execute_sequence(moves)
    
    def rest_position(self) -> bool:
        """Posição de descanso (compacta)"""
        print("😴 Posição de descanso...")
        moves = [
            (4, 100),  # Fechar garra primeiro
            (2, 70),   # Recolher cotovelo
            (1, 75),   # Baixar ombro
            (0, 90)    # Base centro
        ]
        return self._execute_sequence(moves)
    
    def wave_gesture(self) -> bool:
        """Acena (movimento de cumprimento)"""
        print("👋 Acenando...")
        base_pos = self.servos[0]['current']
        
        # Preparar para acenar
        self.move_servo(1, 120, delay=0.4)
        self.move_servo(2, 90, delay=0.4)
        self.move_servo(4, 40, delay=0.4)
        
        # Movimento de aceno
        for _ in range(3):
            self.move_servo(0, base_pos - 20, delay=0.3)
            self.move_servo(0, base_pos + 20, delay=0.3)
        
        # Retornar
        self.move_servo(0, base_pos, delay=0.3)
        print("✓ Aceno concluído!")
        return True
    
    def _execute_sequence(self, moves: list, delay: float = 0.4) -> bool:
        """Executa uma sequência de movimentos"""
        for channel, angle in moves:
            result = self.move_servo(channel, angle, delay=delay)
            if not result['success']:
                print(f"  ✗ Erro: {result.get('error')}")
                return False
        print("✓ Sequência concluída!")
        return True
    
    def cleanup(self):
        """Finaliza de forma segura"""
        print("\n🔧 Finalizando braço robótico...")
        # Apenas retorna para home se não estiver já lá
        for channel, info in self.servos.items():
            if abs(info['current'] - info['home']) > 5:
                self.move_servo(channel, info['home'], delay=0.3)
        print("✓ Braço finalizado com segurança\n")


if __name__ == '__main__':
    """Teste do controlador"""
    arm = ArmController()
    
    try:
        print("\n" + "="*60)
        print("🦾 TESTE DO CONTROLADOR DO BRAÇO")
        print("="*60)
        
        # Menu interativo
        while True:
            print("\n" + "="*60)
            print("COMANDOS:")
            print("  1 - Posição HOME")
            print("  2 - Abrir garra")
            print("  3 - Fechar garra")
            print("  4 - Apontar para frente")
            print("  5 - Posição de captura")
            print("  6 - Posição de descanso")
            print("  7 - Acenar")
            print("  8 - Mover servo manual")
            print("  9 - Ver posição atual")
            print("  0 - Sair")
            print("="*60)
            
            choice = input("\nEscolha: ").strip()
            
            if choice == '1':
                arm.home_position()
            elif choice == '2':
                result = arm.open_gripper()
                print(f"{'✓' if result['success'] else '✗'} Garra aberta")
            elif choice == '3':
                result = arm.close_gripper()
                print(f"{'✓' if result['success'] else '✗'} Garra fechada")
            elif choice == '4':
                arm.point_forward()
            elif choice == '5':
                arm.grab_position()
            elif choice == '6':
                arm.rest_position()
            elif choice == '7':
                arm.wave_gesture()
            elif choice == '8':
                print("\nServos disponíveis:")
                for ch, info in arm.servos.items():
                    print(f"  {ch} - {info['name']} ({info['min']}° - {info['max']}°)")
                try:
                    ch = int(input("Canal: "))
                    angle = int(input("Ângulo: "))
                    result = arm.move_servo(ch, angle)
                    print(f"{'✓' if result['success'] else '✗'} {result.get('error', 'Movimento realizado')}")
                except ValueError:
                    print("✗ Entrada inválida")
            elif choice == '9':
                pos = arm.get_current_position()
                print("\n📍 POSIÇÃO ATUAL:")
                for ch, info in pos.items():
                    print(f"  {info['name']}: {info['angle']}° ({info['min']}° - {info['max']}°)")
            elif choice == '0':
                break
            else:
                print("✗ Opção inválida")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detectado")
    
    finally:
        arm.cleanup()
        print("✓ Programa encerrado\n")