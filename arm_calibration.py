#!/usr/bin/env python3
"""
Programa de Calibração do Braço Robótico
Testes seguros com delays adequados para proteção dos servos

Configuração dos Servos:
- Servo 0: Base (Rotação) - OK em qualquer ângulo
- Servo 1: Ombro (Elevação) - Evitar ângulos < 60°
- Servo 2: Cotovelo - Evitar ângulos < 60°
- Servo 4: Garra - 0° (abrir) até 180° (fechar)

Uso:
  python3 arm_calibration.py
"""

import requests
import time
import sys

class ArmCalibration:
    """Sistema de calibração do braço robótico"""
    
    def __init__(self, server_url: str = "http://192.168.100.30:5001"):
        self.server_url = server_url.rstrip('/')
        self.connected = False
        
        # Configuração SEGURA dos servos baseada nos testes
        self.servos = {
            0: {
                'name': 'Base (Rotação)',
                'safe_min': 0,
                'safe_max': 180,
                'home': 90,
                'test_angles': [0, 45, 90, 135, 180]
            },
            1: {
                'name': 'Ombro (Elevação)',
                'safe_min': 60,  # Ângulos pequenos não funcionam bem
                'safe_max': 180,
                'home': 90,
                'test_angles': [60, 75, 90, 120, 150, 180]
            },
            2: {
                'name': 'Cotovelo',
                'safe_min': 60,  # Ângulos pequenos não funcionam bem
                'safe_max': 180,
                'home': 90,
                'test_angles': [60, 75, 90, 120, 150, 180]
            },
            4: {
                'name': 'Garra',
                'safe_min': 0,   # 0 = abrir
                'safe_max': 180, # 180 = fechar
                'home': 90,
                'test_angles': [0, 45, 90, 135, 180]
            }
        }
        
        # Delay de segurança entre movimentos (5 segundos)
        self.safety_delay = 5.0
    
    def check_connection(self) -> bool:
        """Verifica conexão com o servidor"""
        try:
            response = requests.get(f"{self.server_url}/status", timeout=2)
            if response.status_code == 200:
                self.connected = True
                return True
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Erro de conexão: {e}")
            self.connected = False
            return False
    
    def move_servo(self, channel: int, angle: int, delay: float = None) -> bool:
        """Move um servo e aguarda o delay de segurança"""
        if not self.connected:
            print("❌ Não conectado ao servidor")
            return False
        
        if channel not in self.servos:
            print(f"❌ Canal inválido: {channel}")
            return False
        
        servo_info = self.servos[channel]
        
        # Validar se está na zona segura
        if angle < servo_info['safe_min'] or angle > servo_info['safe_max']:
            print(f"⚠️  PERIGO: Ângulo {angle}° fora da zona segura!")
            print(f"   {servo_info['name']}: {servo_info['safe_min']}° - {servo_info['safe_max']}°")
            return False
        
        try:
            response = requests.post(
                f"{self.server_url}/servo/move",
                json={'channel': channel, 'angle': angle},
                timeout=2
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print(f"✓ {servo_info['name']} → {angle}°")
                    
                    # Aguardar delay de segurança
                    wait_time = delay if delay is not None else self.safety_delay
                    if wait_time > 0:
                        print(f"  ⏳ Aguardando {wait_time}s (proteção do servo)...")
                        time.sleep(wait_time)
                    
                    return True
            
            print(f"❌ Falha ao mover servo: {response.text}")
            return False
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Erro na requisição: {e}")
            return False
    
    def home_position(self):
        """Retorna todos os servos para posição home (90°)"""
        print("\n🏠 Retornando para posição HOME...")
        print("=" * 60)
        
        for channel in sorted(self.servos.keys()):
            servo_info = self.servos[channel]
            print(f"\n{servo_info['name']}:")
            self.move_servo(channel, servo_info['home'], delay=3.0)
        
        print("\n✓ Todos os servos em posição HOME!")
    
    def test_individual_servo(self, channel: int):
        """Testa um servo com sequência de ângulos seguros"""
        if channel not in self.servos:
            print(f"❌ Canal inválido: {channel}")
            return
        
        servo_info = self.servos[channel]
        
        print("\n" + "=" * 60)
        print(f"🔧 TESTE: {servo_info['name']} (Canal {channel})")
        print("=" * 60)
        print(f"Zona segura: {servo_info['safe_min']}° - {servo_info['safe_max']}°")
        print(f"Sequência de teste: {servo_info['test_angles']}")
        print(f"Delay entre movimentos: {self.safety_delay}s")
        
        confirm = input("\n▶ Iniciar teste? (s/N): ").strip().lower()
        if confirm != 's':
            print("❌ Teste cancelado")
            return
        
        print("\n🚀 Iniciando teste...\n")
        
        # Primeiro ir para home
        print("1. Indo para posição inicial (HOME)...")
        if not self.move_servo(channel, servo_info['home']):
            print("❌ Erro ao ir para HOME - teste interrompido")
            return
        
        # Testar cada ângulo
        for i, angle in enumerate(servo_info['test_angles'], 2):
            print(f"\n{i}. Testando {angle}°...")
            if not self.move_servo(channel, angle):
                print("❌ Teste interrompido")
                return
        
        # Retornar para home
        print(f"\n{len(servo_info['test_angles']) + 2}. Retornando para HOME...")
        self.move_servo(channel, servo_info['home'])
        
        print(f"\n✓ {servo_info['name']} testado com sucesso!")
    
    def test_range_exploration(self, channel: int):
        """Explora a faixa de ângulos seguros em incrementos"""
        if channel not in self.servos:
            print(f"❌ Canal inválido: {channel}")
            return
        
        servo_info = self.servos[channel]
        
        print("\n" + "=" * 60)
        print(f"🔍 EXPLORAÇÃO DE RANGE: {servo_info['name']}")
        print("=" * 60)
        print(f"Zona segura: {servo_info['safe_min']}° - {servo_info['safe_max']}°")
        
        # Escolher incremento
        print("\nIncrementos disponíveis:")
        print("  1 - 15° (rápido - 9 posições)")
        print("  2 - 10° (médio - 13 posições)")
        print("  3 - 5° (detalhado - 25 posições)")
        
        choice = input("\nEscolha o incremento (1-3): ").strip()
        
        increments = {'1': 15, '2': 10, '3': 5}
        increment = increments.get(choice, 15)
        
        # Gerar sequência
        angles = list(range(servo_info['safe_min'], 
                           servo_info['safe_max'] + 1, 
                           increment))
        if servo_info['safe_max'] not in angles:
            angles.append(servo_info['safe_max'])
        
        print(f"\nSequência: {angles}")
        print(f"Total de posições: {len(angles)}")
        print(f"Tempo estimado: {len(angles) * self.safety_delay / 60:.1f} minutos")
        
        confirm = input("\n▶ Iniciar exploração? (s/N): ").strip().lower()
        if confirm != 's':
            print("❌ Exploração cancelada")
            return
        
        print("\n🚀 Iniciando exploração...\n")
        
        for i, angle in enumerate(angles, 1):
            print(f"[{i}/{len(angles)}] Testando {angle}°...")
            if not self.move_servo(channel, angle):
                print("❌ Exploração interrompida")
                return
        
        print(f"\n✓ Exploração concluída!")
    
    def garra_test(self):
        """Teste específico da garra (abrir/fechar)"""
        print("\n" + "=" * 60)
        print("🤏 TESTE DA GARRA")
        print("=" * 60)
        print("0° = Totalmente aberta")
        print("180° = Totalmente fechada")
        
        confirm = input("\n▶ Iniciar teste da garra? (s/N): ").strip().lower()
        if confirm != 's':
            print("❌ Teste cancelado")
            return
        
        print("\n🚀 Testando garra...\n")
        
        # Sequência: home → abrir → fechar → meio → home
        sequence = [
            (90, "Posição neutra"),
            (0, "Totalmente ABERTA"),
            (180, "Totalmente FECHADA"),
            (90, "Meio termo"),
            (45, "Levemente aberta"),
            (135, "Levemente fechada"),
            (90, "Retorno ao neutro")
        ]
        
        for angle, description in sequence:
            print(f"→ {description} ({angle}°)")
            if not self.move_servo(4, angle):
                print("❌ Teste interrompido")
                return
        
        print("\n✓ Teste da garra concluído!")
    
    def manual_control(self):
        """Controle manual dos servos"""
        print("\n" + "=" * 60)
        print("🎮 CONTROLE MANUAL")
        print("=" * 60)
        
        while True:
            print("\nServos disponíveis:")
            for ch, info in self.servos.items():
                print(f"  {ch} - {info['name']} ({info['safe_min']}° - {info['safe_max']}°)")
            
            print("\n  H - Home position")
            print("  Q - Sair")
            
            choice = input("\nEscolha (canal/H/Q): ").strip().upper()
            
            if choice == 'Q':
                break
            elif choice == 'H':
                self.home_position()
                continue
            
            try:
                channel = int(choice)
                if channel not in self.servos:
                    print("❌ Canal inválido")
                    continue
                
                servo_info = self.servos[channel]
                angle = int(input(f"Ângulo ({servo_info['safe_min']}-{servo_info['safe_max']}): "))
                
                self.move_servo(channel, angle)
                
            except ValueError:
                print("❌ Entrada inválida")
    
    def menu(self):
        """Menu principal"""
        print("\n" + "=" * 60)
        print("🦾 CALIBRAÇÃO DO BRAÇO ROBÓTICO")
        print("=" * 60)
        print(f"Servidor: {self.server_url}")
        
        # Verificar conexão
        print("\n🔌 Verificando conexão...")
        if not self.check_connection():
            print("❌ Não foi possível conectar ao servidor")
            print(f"   Verifique se o servidor está rodando em {self.server_url}")
            return
        
        print("✓ Conectado ao servidor!")
        
        while True:
            print("\n" + "=" * 60)
            print("MENU PRINCIPAL")
            print("=" * 60)
            print("1 - Home position (todos → 90°)")
            print("2 - Testar servo individual")
            print("3 - Explorar range de um servo")
            print("4 - Teste da garra (abrir/fechar)")
            print("5 - Controle manual")
            print("6 - Info dos servos")
            print("0 - Sair")
            print("=" * 60)
            
            choice = input("\nEscolha: ").strip()
            
            if choice == '1':
                self.home_position()
            
            elif choice == '2':
                print("\nServos disponíveis:")
                for ch, info in self.servos.items():
                    print(f"  {ch} - {info['name']}")
                
                try:
                    channel = int(input("\nCanal (0/1/2/4): ").strip())
                    self.test_individual_servo(channel)
                except ValueError:
                    print("❌ Entrada inválida")
            
            elif choice == '3':
                print("\nServos disponíveis:")
                for ch, info in self.servos.items():
                    print(f"  {ch} - {info['name']}")
                
                try:
                    channel = int(input("\nCanal (0/1/2/4): ").strip())
                    self.test_range_exploration(channel)
                except ValueError:
                    print("❌ Entrada inválida")
            
            elif choice == '4':
                self.garra_test()
            
            elif choice == '5':
                self.manual_control()
            
            elif choice == '6':
                self.show_info()
            
            elif choice == '0':
                print("\n👋 Encerrando...")
                self.home_position()
                break
            
            else:
                print("❌ Opção inválida")
    
    def show_info(self):
        """Mostra informações dos servos"""
        print("\n" + "=" * 60)
        print("ℹ️  INFORMAÇÕES DOS SERVOS")
        print("=" * 60)
        
        for channel in sorted(self.servos.keys()):
            info = self.servos[channel]
            print(f"\n📍 Servo {channel}: {info['name']}")
            print(f"   Zona segura: {info['safe_min']}° - {info['safe_max']}°")
            print(f"   Home: {info['home']}°")
            print(f"   Ângulos de teste: {info['test_angles']}")
        
        print(f"\n⏱️  Delay de segurança: {self.safety_delay}s entre movimentos")
        print("\n⚠️  ATENÇÃO:")
        print("   - Ombro e Cotovelo: ângulos < 60° não funcionam bem")
        print("   - Garra: 0° (abrir) até 180° (fechar)")
        print("=" * 60)


def main():
    """Função principal"""
    default_url = "http://192.168.100.30:5001"
    
    print("\n🦾 Sistema de Calibração do Braço Robótico")
    print("=" * 60)
    
    server_url = input(f"URL do servidor [{default_url}]: ").strip()
    if not server_url:
        server_url = default_url
    
    arm = ArmCalibration(server_url)
    
    try:
        arm.menu()
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detectado")
        arm.home_position()
    finally:
        print("\n✓ Programa encerrado\n")


if __name__ == '__main__':
    main()