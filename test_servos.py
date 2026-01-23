#!/usr/bin/env python3
"""
Teste de Servos - Freenove Smart Car
Move todos os servos para 90 graus para teste e calibração
"""

import sys
import time
from pathlib import Path

# Adicionar pasta ao path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from hardware.servo import Servo
    SERVO_AVAILABLE = True
except ImportError as e:
    print(f"❌ Erro ao importar servo.py: {e}")
    SERVO_AVAILABLE = False
    sys.exit(1)


class ServoTester:
    """Classe para testar servos"""
    
    def __init__(self):
        """Inicializa o testador de servos"""
        print("\n" + "="*60)
        print("🔧 TESTADOR DE SERVOS - Freenove Smart Car")
        print("="*60)
        
        if not SERVO_AVAILABLE:
            print("❌ Módulo servo não disponível")
            return
        
        try:
            self.servo = Servo()
            print("✓ Servos inicializados")
            print("✓ Todos os servos foram movidos para posição inicial (1500µs)")
        except Exception as e:
            print(f"❌ Erro ao inicializar servos: {e}")
            self.servo = None
    
    def test_single_servo(self, channel: str, angle: int = 90):
        """Testa um servo individual"""
        if not self.servo:
            print("❌ Servos não inicializados")
            return False
        
        try:
            print(f"\n🔄 Testando Servo {channel}...")
            print(f"   Movendo para {angle}°")
            
            self.servo.set_servo_pwm(channel, angle)
            time.sleep(0.5)
            
            print(f"✓ Servo {channel} movido para {angle}°")
            return True
            
        except Exception as e:
            print(f"❌ Erro no servo {channel}: {e}")
            return False
    
    def test_all_servos(self, angle: int = 90):
        """Testa todos os servos sequencialmente"""
        print("\n" + "="*60)
        print(f"🔄 TESTANDO TODOS OS SERVOS - Ângulo: {angle}°")
        print("="*60)
        
        channels = ['0', '1', '2', '3', '4', '5', '6', '7']
        results = {}
        
        for channel in channels:
            results[channel] = self.test_single_servo(channel, angle)
            time.sleep(0.3)
        
        # Resumo
        print("\n" + "="*60)
        print("📊 RESUMO DO TESTE")
        print("="*60)
        
        success_count = sum(1 for v in results.values() if v)
        
        for channel, success in results.items():
            status = "✓ OK" if success else "❌ FALHA"
            print(f"Servo {channel}: {status}")
        
        print(f"\nTotal: {success_count}/{len(channels)} servos OK")
        print("="*60)
        
        return results
    
    def sweep_test(self, channel: str, start: int = 0, end: int = 180, step: int = 30):
        """Teste de varredura (sweep) em um servo"""
        print(f"\n🔄 TESTE DE VARREDURA - Servo {channel}")
        print(f"   Range: {start}° → {end}° (passo: {step}°)")
        
        if not self.servo:
            print("❌ Servos não inicializados")
            return
        
        try:
            # Ida
            print("\n   Ida:")
            for angle in range(start, end + 1, step):
                print(f"     → {angle}°", end=" ", flush=True)
                self.servo.set_servo_pwm(channel, angle)
                time.sleep(0.5)
            
            print("\n\n   Volta:")
            # Volta
            for angle in range(end, start - 1, -step):
                print(f"     ← {angle}°", end=" ", flush=True)
                self.servo.set_servo_pwm(channel, angle)
                time.sleep(0.5)
            
            # Voltar para 90°
            print("\n\n   Retornando para 90°...")
            self.servo.set_servo_pwm(channel, 90)
            print("✓ Teste de varredura concluído")
            
        except Exception as e:
            print(f"\n❌ Erro no teste de varredura: {e}")
    
    def interactive_menu(self):
        """Menu interativo para testes"""
        while True:
            print("\n" + "="*60)
            print("MENU DE TESTES")
            print("="*60)
            print("1 - Testar todos os servos (90°)")
            print("2 - Testar servo individual")
            print("3 - Teste de varredura (sweep)")
            print("4 - Mover todos para ângulo específico")
            print("5 - Resetar todos (90°)")
            print("6 - Informações dos servos")
            print("0 - Sair")
            print("="*60)
            
            choice = input("\nEscolha uma opção: ").strip()
            
            if choice == '1':
                self.test_all_servos(90)
            
            elif choice == '2':
                channel = input("Digite o canal do servo (0-7): ").strip()
                if channel in ['0', '1', '2', '3', '4', '5', '6', '7']:
                    try:
                        angle = int(input("Digite o ângulo (0-180): ").strip())
                        if 0 <= angle <= 180:
                            self.test_single_servo(channel, angle)
                        else:
                            print("❌ Ângulo deve estar entre 0 e 180")
                    except ValueError:
                        print("❌ Ângulo inválido")
                else:
                    print("❌ Canal inválido")
            
            elif choice == '3':
                channel = input("Digite o canal do servo (0-7): ").strip()
                if channel in ['0', '1', '2', '3', '4', '5', '6', '7']:
                    self.sweep_test(channel)
                else:
                    print("❌ Canal inválido")
            
            elif choice == '4':
                try:
                    angle = int(input("Digite o ângulo (0-180): ").strip())
                    if 0 <= angle <= 180:
                        self.test_all_servos(angle)
                    else:
                        print("❌ Ângulo deve estar entre 0 e 180")
                except ValueError:
                    print("❌ Ângulo inválido")
            
            elif choice == '5':
                print("\n🔄 Resetando todos os servos para 90°...")
                self.test_all_servos(90)
            
            elif choice == '6':
                self.show_servo_info()
            
            elif choice == '0':
                print("\n👋 Encerrando testador de servos...")
                break
            
            else:
                print("❌ Opção inválida")
    
    def show_servo_info(self):
        """Mostra informações sobre os servos"""
        print("\n" + "="*60)
        print("ℹ️  INFORMAÇÕES DOS SERVOS")
        print("="*60)
        print("\nMapeamento de Canais PWM:")
        print("  Servo 0 → Canal PWM 8")
        print("  Servo 1 → Canal PWM 9")
        print("  Servo 2 → Canal PWM 10")
        print("  Servo 3 → Canal PWM 11")
        print("  Servo 4 → Canal PWM 12")
        print("  Servo 5 → Canal PWM 13")
        print("  Servo 6 → Canal PWM 14")
        print("  Servo 7 → Canal PWM 15")
        
        print("\nConfiguração:")
        print(f"  Frequência PWM: {self.servo.pwm_frequency}Hz")
        print(f"  Pulso inicial: {self.servo.initial_pulse}µs")
        
        print("\nFaixa de operação:")
        print("  Ângulo: 0° a 180°")
        print("  Pulso: ~500µs a ~2500µs")
        
        print("\nNota:")
        print("  - O servo 0 tem inversão de direção")
        print("  - Ajuste o parâmetro 'error' se necessário")
        print("="*60)


def main():
    """Função principal"""
    print("\n🤖 Iniciando testador de servos...")
    
    tester = ServoTester()
    
    if not tester.servo:
        print("\n❌ Não foi possível inicializar os servos")
        return
    
    try:
        # Menu interativo
        tester.interactive_menu()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detectado")
    
    finally:
        print("\n✓ Teste finalizado\n")


if __name__ == '__main__':
    main()