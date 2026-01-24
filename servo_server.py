#!/usr/bin/env python3
"""
Servidor Flask para controle de servos via web
Execute no Raspberry Pi: python3 servo_server.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import sys
from pathlib import Path
import socket

# Adicionar pasta hardware ao path
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

try:
    from servo import Servo
    SERVO_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Erro ao importar hardware: {e}")
    SERVO_AVAILABLE = False

app = Flask(__name__)
CORS(app)  # Permitir requisições de outros IPs

# Instância global do servo
servo_controller = None

def initialize_servo():
    """Inicializa o controlador de servos"""
    global servo_controller
    if SERVO_AVAILABLE and servo_controller is None:
        try:
            servo_controller = Servo()
            print("✓ Servos inicializados")
            # Mover todos para posição inicial (90°)
            for channel in range(4):
                servo_controller.set_servo_pwm(str(channel), 90)
            return True
        except Exception as e:
            print(f"✗ Erro ao inicializar servos: {e}")
            return False
    return servo_controller is not None

@app.route('/status', methods=['GET'])
def status():
    """Verifica status do servidor"""
    return jsonify({
        'status': 'ok',
        'servo_available': SERVO_AVAILABLE,
        'servo_initialized': servo_controller is not None
    })

@app.route('/servo/move', methods=['POST'])
def move_servo():
    """Move um servo para um ângulo específico"""
    if not servo_controller:
        return jsonify({
            'success': False,
            'error': 'Servos não inicializados'
        }), 500
    
    try:
        data = request.get_json()
        channel = int(data.get('channel', 0))
        angle = int(data.get('angle', 90))
        
        # Validar limites
        if channel < 0 or channel > 7:
            return jsonify({
                'success': False,
                'error': 'Canal inválido (0-7)'
            }), 400
        
        if angle < 0 or angle > 180:
            return jsonify({
                'success': False,
                'error': 'Ângulo inválido (0-180)'
            }), 400
        
        # Mover servo
        servo_controller.set_servo_pwm(str(channel), angle)
        
        print(f"✓ Servo {channel} → {angle}°")
        
        return jsonify({
            'success': True,
            'channel': channel,
            'angle': angle
        })
        
    except Exception as e:
        print(f"✗ Erro ao mover servo: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/servo/stop', methods=['POST'])
def stop_servos():
    """Para todos os servos (retorna para 90°)"""
    if not servo_controller:
        return jsonify({
            'success': False,
            'error': 'Servos não inicializados'
        }), 500
    
    try:
        # Retornar todos para posição neutra
        for channel in range(4):
            servo_controller.set_servo_pwm(str(channel), 90)
        
        print("🛑 Todos os servos retornados para 90°")
        
        return jsonify({
            'success': True,
            'message': 'Todos os servos em posição neutra'
        })
        
    except Exception as e:
        print(f"✗ Erro ao parar servos: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/servo/test', methods=['POST'])
def test_servo():
    """Testa um servo com sequência de movimentos"""
    if not servo_controller:
        return jsonify({
            'success': False,
            'error': 'Servos não inicializados'
        }), 500
    
    try:
        data = request.get_json()
        channel = int(data.get('channel', 0))
        
        if channel < 0 or channel > 7:
            return jsonify({
                'success': False,
                'error': 'Canal inválido (0-7)'
            }), 400
        
        # Sequência de teste
        import time
        sequence = [90, 45, 90, 135, 90]
        
        for angle in sequence:
            servo_controller.set_servo_pwm(str(channel), angle)
            time.sleep(0.5)
        
        print(f"✓ Servo {channel} testado")
        
        return jsonify({
            'success': True,
            'channel': channel,
            'message': 'Teste concluído'
        })
        
    except Exception as e:
        print(f"✗ Erro no teste: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def get_ip_address():
    """Obtém o endereço IP local"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

if __name__ == '__main__':
    print("=" * 60)
    print("🔧 Servidor de Calibração de Servos - Raspberry Pi")
    print("=" * 60)
    
    # Inicializar servos
    if initialize_servo():
        print("✓ Sistema pronto!")
    else:
        print("⚠️ Sistema iniciado, mas servos não disponíveis")
    
    # Obter IP
    ip = get_ip_address()
    
    print("\n" + "=" * 60)
    print("📡 ENDEREÇOS DE ACESSO:")
    print(f"   Local:  http://localhost:5001")
    print(f"   Rede:   http://{ip}:5001")
    print("=" * 60)
    print("\n💡 Configure este endereço no calibrador web!")
    print("   Exemplo: http://" + ip + ":5001")
    print("\n⚠️  Pressione Ctrl+C para encerrar")
    print("=" * 60 + "\n")
    
    try:
        app.run(host='0.0.0.0', port=5001, debug=False)
    except KeyboardInterrupt:
        print("\n\n🛑 Servidor encerrado")
        if servo_controller:
            # Retornar servos para posição neutra
            for channel in range(4):
                servo_controller.set_servo_pwm(str(channel), 90)
            print("✓ Servos retornados para posição neutra")