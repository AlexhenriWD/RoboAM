#!/usr/bin/env python3
"""
EVA ROBOT REMOTE CONTROL SYSTEM
Sistema de controle remoto completo para o robô EVA
Permite controle manual + integração com IA
Baseado no PLANO_DE_CRIACAO_EVA_ROBOT.txt
"""

import asyncio
import json
import time
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import deque
import threading

# Importar componentes do robô
try:
    from robot_core import EvaRobotCore
    ROBOT_AVAILABLE = True
except ImportError:
    print("⚠️  robot_core não disponível - modo simulação")
    ROBOT_AVAILABLE = False


@dataclass
class RobotState:
    """Estado atual do robô"""
    timestamp: float
    
    # Posição
    position: Dict[str, float]  # x, y, z (estimado)
    
    # Sensores
    ultrasonic_cm: Optional[float]
    battery_v: Optional[float]
    
    # Motor
    motor_values: list  # [fl, bl, fr, br]
    is_moving: bool
    
    # Braço/Cabeça
    head_position: Optional[Dict]
    
    # Estado
    is_autonomous: bool
    eva_is_thinking: bool
    last_command: Optional[str]
    
    def to_dict(self):
        d = asdict(self)
        d['timestamp'] = self.timestamp
        return d


class SafetyController:
    """Controlador de segurança - previne acidentes"""
    
    def __init__(self, robot_core):
        self.robot = robot_core
        self.enabled = True
        
        # Limites de segurança
        self.min_distance_cm = 15.0  # Distância mínima para obstáculos
        self.max_tilt_angle = 45  # Ângulo máximo de inclinação
        self.low_battery_v = 6.5  # Tensão mínima da bateria
        
        # Estado
        self.emergency_stop = False
        self.warnings = deque(maxlen=10)
        
        print("✅ Safety Controller ativo")
    
    def check_safe_to_move(self, direction: str) -> tuple[bool, str]:
        """Verifica se é seguro mover na direção especificada"""
        
        if not self.enabled:
            return True, "Safety desabilitado"
        
        if self.emergency_stop:
            return False, "EMERGENCY STOP ativo"
        
        # Ler sensores
        sensors = self.robot.read_sensors()
        
        # Verificar bateria
        if sensors.get('battery_v'):
            if sensors['battery_v'] < self.low_battery_v:
                self.add_warning(f"Bateria baixa: {sensors['battery_v']:.1f}V")
                return False, f"Bateria muito baixa ({sensors['battery_v']:.1f}V)"
        
        # Verificar obstáculos (apenas para frente)
        if direction in ['forward', 'front']:
            distance = sensors.get('ultrasonic_cm')
            
            if distance is not None:
                if distance < self.min_distance_cm:
                    self.add_warning(f"Obstáculo detectado: {distance:.1f}cm")
                    return False, f"Obstáculo muito próximo ({distance:.1f}cm)"
        
        return True, "OK"
    
    def add_warning(self, message: str):
        """Adiciona warning ao log"""
        self.warnings.append({
            'timestamp': time.time(),
            'message': message
        })
        print(f"⚠️  SAFETY: {message}")
    
    def trigger_emergency_stop(self, reason: str):
        """Aciona parada de emergência"""
        self.emergency_stop = True
        self.robot.stop()
        self.add_warning(f"EMERGENCY STOP: {reason}")
        print(f"🚨 PARADA DE EMERGÊNCIA: {reason}")
    
    def reset_emergency(self):
        """Reseta parada de emergência"""
        self.emergency_stop = False
        print("✅ Emergency stop resetado")


class ActuatorServer:
    """
    Servidor de atuadores do robô
    Implementa a API descrita no plano
    """
    
    def __init__(self, robot_core):
        self.robot = robot_core
        self.safety = SafetyController(robot_core)
        
        # Estado
        self.state = RobotState(
            timestamp=time.time(),
            position={'x': 0, 'y': 0, 'z': 0},
            ultrasonic_cm=None,
            battery_v=None,
            motor_values=[0, 0, 0, 0],
            is_moving=False,
            head_position=None,
            is_autonomous=False,
            eva_is_thinking=False,
            last_command=None
        )
        
        # Callbacks
        self.on_state_change: Optional[Callable] = None
        
        # Watchdog
        self.last_heartbeat = time.time()
        self.heartbeat_timeout = 5.0
        self.watchdog_active = True
        
        # Thread de monitoramento
        self.monitoring = False
        self.monitor_thread = None
        
        print("✅ Actuator Server inicializado")
    
    def start_monitoring(self):
        """Inicia thread de monitoramento"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitor_thread.start()
        print("✅ Monitoramento iniciado")
    
    def stop_monitoring(self):
        """Para thread de monitoramento"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        print("🔇 Monitoramento parado")
    
    def _monitoring_loop(self):
        """Loop de monitoramento (roda em thread separada)"""
        while self.monitoring:
            try:
                # Atualizar estado
                self._update_state()
                
                # Watchdog
                if self.watchdog_active:
                    elapsed = time.time() - self.last_heartbeat
                    if elapsed > self.heartbeat_timeout:
                        self.safety.trigger_emergency_stop(
                            f"Watchdog timeout ({elapsed:.1f}s)"
                        )
                        self.stop()
                
                # Notificar mudanças
                if self.on_state_change:
                    try:
                        self.on_state_change(self.state)
                    except Exception as e:
                        print(f"⚠️  Erro em callback: {e}")
                
                time.sleep(0.1)  # 10 Hz
                
            except Exception as e:
                print(f"❌ Erro no monitoring loop: {e}")
                time.sleep(1.0)
    
    def _update_state(self):
        """Atualiza estado do robô"""
        sensors = self.robot.read_sensors()
        
        self.state.timestamp = time.time()
        self.state.ultrasonic_cm = sensors.get('ultrasonic_cm')
        self.state.battery_v = sensors.get('battery_v')
        self.state.head_position = sensors.get('arm_position')
        self.state.is_moving = any(v != 0 for v in self.state.motor_values)
    
    # ==========================================
    # API ENDPOINTS (conforme plano)
    # ==========================================
    
    def get_state(self) -> Dict:
        """GET /state - Retorna estado completo"""
        return self.state.to_dict()
    
    def drive(
        self, 
        vx: float = 0.0, 
        vy: float = 0.0, 
        vz: float = 0.0,
        duration: Optional[float] = None
    ) -> Dict:
        """
        POST /drive - Controla movimento do carro
        
        Args:
            vx: Velocidade forward/backward (-1.0 a 1.0)
            vy: Velocidade strafe left/right (-1.0 a 1.0) - mecanum wheels
            vz: Rotação (-1.0 a 1.0)
            duration: Duração do movimento (segundos), None = contínuo
        
        Returns:
            Status da operação
        """
        
        # Normalizar valores
        vx = max(-1.0, min(1.0, float(vx)))
        vy = max(-1.0, min(1.0, float(vy)))
        vz = max(-1.0, min(1.0, float(vz)))
        
        # Converter para PWM (escala -4095 a 4095)
        max_pwm = 4095
        
        # Cinemática inversa para rodas mecanum
        # FL, BL, FR, BR
        fl = int((vx + vy + vz) * max_pwm)
        bl = int((vx - vy + vz) * max_pwm)
        fr = int((vx - vy - vz) * max_pwm)
        br = int((vx + vy - vz) * max_pwm)
        
        # Verificar segurança
        direction = 'forward' if vx > 0 else 'backward' if vx < 0 else 'none'
        safe, msg = self.safety.check_safe_to_move(direction)
        
        if not safe:
            return {
                'status': 'blocked',
                'reason': msg,
                'vx': 0, 'vy': 0, 'vz': 0
            }
        
        # Aplicar movimento
        self.robot.move(fl, bl, fr, br)
        self.state.motor_values = [fl, bl, fr, br]
        self.state.last_command = f"drive(vx={vx:.2f}, vy={vy:.2f}, vz={vz:.2f})"
        
        # Heartbeat
        self.last_heartbeat = time.time()
        
        # Movimento temporário
        if duration:
            def stop_after():
                time.sleep(duration)
                self.stop()
            
            threading.Thread(target=stop_after, daemon=True).start()
        
        return {
            'status': 'ok',
            'vx': vx, 'vy': vy, 'vz': vz,
            'motor_values': [fl, bl, fr, br],
            'duration': duration
        }
    
    def move_head(
        self,
        yaw: Optional[int] = None,
        pitch: Optional[int] = None,
        smooth: bool = True
    ) -> Dict:
        """
        POST /head - Move cabeça (braço robótico)
        
        Args:
            yaw: Rotação base (0-180)
            pitch: Inclinação ombro (0-180)
            smooth: Movimento suave
        """
        
        if not self.robot.arm:
            return {'status': 'error', 'error': 'Braço não disponível'}
        
        results = []
        
        # Mover yaw (servo 0 - base)
        if yaw is not None:
            if smooth:
                ok = self.robot.arm.move_smooth(0, yaw, step=2, step_delay=0.02)
                results.append({'servo': 'yaw', 'success': ok, 'angle': yaw})
            else:
                r = self.robot.arm.move_servo(0, yaw, force=True)
                results.append(r)
        
        # Mover pitch (servo 1 - ombro)
        if pitch is not None:
            if smooth:
                ok = self.robot.arm.move_smooth(1, pitch, step=2, step_delay=0.02)
                results.append({'servo': 'pitch', 'success': ok, 'angle': pitch})
            else:
                r = self.robot.arm.move_servo(1, pitch, force=True)
                results.append(r)
        
        self.state.last_command = f"move_head(yaw={yaw}, pitch={pitch}, smooth={smooth})"
        
        return {
            'status': 'ok',
            'results': results,
            'current_position': self.robot.arm.get_current_position()
        }
    
    def behavior(self, action: str) -> Dict:
        """
        POST /behavior - Executa comportamento pré-definido
        
        Actions:
            - look_forward
            - look_down
            - scan
            - wave
            - home
        """
        
        if not self.robot.arm:
            return {'status': 'error', 'error': 'Braço não disponível'}
        
        behaviors = {
            'look_forward': lambda: self.robot.arm.look_forward(smooth=True),
            'look_down': lambda: self.robot.arm.look_down(smooth=True),
            'scan': lambda: self.robot.arm.scan_left_right(times=2),
            'wave': lambda: self.robot.arm.wave_gesture(),
            'home': lambda: self.robot.arm.home_position(force=True)
        }
        
        if action not in behaviors:
            return {
                'status': 'error',
                'error': f'Behavior "{action}" não existe',
                'available': list(behaviors.keys())
            }
        
        try:
            success = behaviors[action]()
            self.state.last_command = f"behavior({action})"
            
            return {
                'status': 'ok',
                'behavior': action,
                'success': success
            }
        
        except Exception as e:
            return {
                'status': 'error',
                'behavior': action,
                'error': str(e)
            }
    
    def stop(self) -> Dict:
        """POST /stop - Parada de emergência"""
        self.robot.stop()
        self.state.motor_values = [0, 0, 0, 0]
        self.state.last_command = "stop"
        
        return {'status': 'ok', 'message': 'Robot stopped'}
    
    def heartbeat(self) -> Dict:
        """POST /heartbeat - Mantém watchdog ativo"""
        self.last_heartbeat = time.time()
        return {
            'status': 'ok',
            'timestamp': self.last_heartbeat
        }


class RemoteController:
    """
    Controlador remoto - interface de alto nível
    Permite controle manual via comandos simples
    """
    
    def __init__(self, actuator_server: ActuatorServer):
        self.server = actuator_server
        self.speed = 0.5  # Velocidade padrão (0-1)
        self.turn_speed = 0.4
        
        print("✅ Remote Controller inicializado")
    
    # Comandos de movimento simplificados
    
    def forward(self, speed: Optional[float] = None):
        """Move para frente"""
        s = speed or self.speed
        return self.server.drive(vx=s, vy=0, vz=0)
    
    def backward(self, speed: Optional[float] = None):
        """Move para trás"""
        s = speed or self.speed
        return self.server.drive(vx=-s, vy=0, vz=0)
    
    def strafe_left(self, speed: Optional[float] = None):
        """Move para esquerda (lateral - mecanum)"""
        s = speed or self.speed
        return self.server.drive(vx=0, vy=-s, vz=0)
    
    def strafe_right(self, speed: Optional[float] = None):
        """Move para direita (lateral - mecanum)"""
        s = speed or self.speed
        return self.server.drive(vx=0, vy=s, vz=0)
    
    def turn_left(self, speed: Optional[float] = None):
        """Vira à esquerda"""
        s = speed or self.turn_speed
        return self.server.drive(vx=0, vy=0, vz=-s)
    
    def turn_right(self, speed: Optional[float] = None):
        """Vira à direita"""
        s = speed or self.turn_speed
        return self.server.drive(vx=0, vy=0, vz=s)
    
    def stop(self):
        """Para completamente"""
        return self.server.stop()
    
    # Comandos de cabeça
    
    def look_at(self, yaw: int, pitch: int, smooth: bool = True):
        """Olha para posição específica"""
        return self.server.move_head(yaw=yaw, pitch=pitch, smooth=smooth)
    
    def look_forward(self):
        """Olha para frente"""
        return self.server.behavior('look_forward')
    
    def scan_area(self):
        """Varre área"""
        return self.server.behavior('scan')
    
    def wave(self):
        """Acena"""
        return self.server.behavior('wave')
    
    # Controle de velocidade
    
    def set_speed(self, speed: float):
        """Define velocidade padrão (0-1)"""
        self.speed = max(0.0, min(1.0, speed))
        print(f"🎯 Velocidade: {self.speed:.0%}")


class EVAIntegration:
    """
    Integração com a IA EVA
    Permite que a EVA controle o robô remotamente
    """
    
    def __init__(self, actuator_server: ActuatorServer):
        self.server = actuator_server
        self.eva_active = False
        self.autonomous_mode = False
        
        # Registro de ações
        self.action_log = deque(maxlen=100)
        
        print("✅ EVA Integration pronta")
    
    def enable_autonomous(self):
        """Habilita modo autônomo (EVA controla)"""
        self.autonomous_mode = True
        self.server.state.is_autonomous = True
        print("🤖 Modo autônomo ATIVADO")
    
    def disable_autonomous(self):
        """Desabilita modo autônomo (controle manual)"""
        self.autonomous_mode = False
        self.server.state.is_autonomous = False
        self.server.stop()
        print("👤 Modo manual ATIVADO")
    
    def execute_eva_command(self, command: Dict) -> Dict:
        """
        Executa comando vindo da EVA
        
        Formato do comando:
        {
            "action": "drive" | "head" | "behavior" | "stop",
            "params": {...}
        }
        """
        
        if not self.autonomous_mode:
            return {
                'status': 'blocked',
                'reason': 'Modo autônomo desativado'
            }
        
        action = command.get('action')
        params = command.get('params', {})
        
        # Log
        self.action_log.append({
            'timestamp': time.time(),
            'command': command
        })
        
        # Executar
        if action == 'drive':
            result = self.server.drive(**params)
        
        elif action == 'head':
            result = self.server.move_head(**params)
        
        elif action == 'behavior':
            result = self.server.behavior(params.get('action'))
        
        elif action == 'stop':
            result = self.server.stop()
        
        else:
            result = {
                'status': 'error',
                'error': f'Ação desconhecida: {action}'
            }
        
        return result


# ==========================================
# INTERFACE DE LINHA DE COMANDO
# ==========================================

class InteractiveCLI:
    """Interface de linha de comando para controle manual"""
    
    def __init__(self, controller: RemoteController):
        self.controller = controller
        self.running = False
        
        # Mapeamento de teclas
        self.keymap = {
            'w': ('forward', 'Frente'),
            's': ('backward', 'Ré'),
            'a': ('turn_left', 'Girar esquerda'),
            'd': ('turn_right', 'Girar direita'),
            'q': ('strafe_left', 'Lateral esquerda'),
            'e': ('strafe_right', 'Lateral direita'),
            'x': ('stop', 'PARAR'),
            ' ': ('stop', 'PARAR'),
            
            # Cabeça
            'i': ('look_forward', 'Olhar frente'),
            'k': ('scan_area', 'Varrer área'),
            'l': ('wave', 'Acenar'),
            
            # Velocidade
            '1': ('speed_20', '20% velocidade'),
            '2': ('speed_40', '40% velocidade'),
            '3': ('speed_60', '60% velocidade'),
            '4': ('speed_80', '80% velocidade'),
            '5': ('speed_100', '100% velocidade'),
        }
    
    def print_help(self):
        """Mostra ajuda"""
        print("\n" + "="*60)
        print("🎮 CONTROLE REMOTO EVA ROBOT")
        print("="*60)
        print("\n📍 MOVIMENTO:")
        print("  W - Frente      S - Ré")
        print("  A - Girar ←     D - Girar →")
        print("  Q - Lateral ←   E - Lateral →")
        print("  X / ESPAÇO - PARAR")
        
        print("\n🦾 CABEÇA:")
        print("  I - Olhar frente")
        print("  K - Varrer área")
        print("  L - Acenar")
        
        print("\n⚡ VELOCIDADE:")
        print("  1 - 20%    2 - 40%    3 - 60%    4 - 80%    5 - 100%")
        
        print("\n⚙️  OUTROS:")
        print("  H - Mostrar esta ajuda")
        print("  Q - Sair")
        print("="*60 + "\n")
    
    def process_key(self, key: str):
        """Processa tecla pressionada"""
        key = key.lower().strip()
        
        if key == 'h':
            self.print_help()
            return True
        
        if key in ['quit', 'exit']:
            return False
        
        if key not in self.keymap:
            print(f"⚠️  Tecla desconhecida: {key}")
            return True
        
        action, description = self.keymap[key]
        
        # Velocidades
        if action.startswith('speed_'):
            speed = int(action.split('_')[1]) / 100
            self.controller.set_speed(speed)
            return True
        
        # Executar ação
        try:
            method = getattr(self.controller, action)
            result = method()
            
            if result.get('status') == 'ok':
                print(f"✅ {description}")
            else:
                print(f"❌ {description}: {result.get('reason', 'erro')}")
        
        except Exception as e:
            print(f"❌ Erro: {e}")
        
        return True
    
    def run(self):
        """Loop principal"""
        self.running = True
        self.print_help()
        
        print("🎮 Controle ativo! Digite comandos:")
        print("   (use 'h' para ajuda, 'quit' para sair)\n")
        
        try:
            while self.running:
                cmd = input("> ").strip()
                
                if not cmd:
                    continue
                
                if not self.process_key(cmd):
                    break
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Ctrl+C detectado")
        
        finally:
            self.controller.stop()
            print("\n✅ Controle encerrado\n")


# ==========================================
# MAIN - PONTO DE ENTRADA
# ==========================================

def main():
    """Função principal"""
    
    print("\n" + "="*60)
    print("🤖 EVA ROBOT - SISTEMA DE CONTROLE REMOTO")
    print("="*60)
    print("\nBaseado no PLANO_DE_CRIACAO_EVA_ROBOT.txt")
    print("Arquitetura: Cérebro (EVA/PC) ← → Corpo (Robô/RPi)")
    print("="*60 + "\n")
    
    # Inicializar robô
    if not ROBOT_AVAILABLE:
        print("❌ Sistema de robô não disponível")
        print("   Execute no Raspberry Pi com hardware conectado")
        return
    
    print("🔧 Inicializando hardware...\n")
    robot = EvaRobotCore()
    
    if not robot.initialize(enable_arm=True, enable_cameras=False):
        print("❌ Falha na inicialização do hardware")
        return
    
    # Criar servidor de atuadores
    actuator_server = ActuatorServer(robot)
    actuator_server.start_monitoring()
    
    # Criar controlador remoto
    remote = RemoteController(actuator_server)
    
    # Criar integração EVA
    eva_integration = EVAIntegration(actuator_server)
    
    # Menu
    print("\n" + "="*60)
    print("MODO DE OPERAÇÃO")
    print("="*60)
    print("\n1 - Controle Manual (CLI)")
    print("2 - Modo Autônomo (EVA controla)")
    print("3 - Sair")
    print()
    
    choice = input("Escolha: ").strip()
    
    try:
        if choice == '1':
            # Modo manual
            cli = InteractiveCLI(remote)
            cli.run()
        
        elif choice == '2':
            # Modo autônomo
            print("\n🤖 Modo autônomo ativado")
            print("   EVA pode controlar o robô via API")
            print("   Pressione Ctrl+C para sair\n")
            
            eva_integration.enable_autonomous()
            
            # Loop de exemplo
            while True:
                state = actuator_server.get_state()
                print(f"\r⏱️  Bateria: {state.get('battery_v', 'N/A')}V | "
                      f"Distância: {state.get('ultrasonic_cm', 'N/A')}cm | "
                      f"Último cmd: {state.get('last_command', 'none')}", end='')
                time.sleep(1)
        
        else:
            print("👋 Saindo...")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido")
    
    finally:
        # Cleanup
        print("\n\n🔧 Encerrando sistema...")
        actuator_server.stop_monitoring()
        robot.cleanup()
        print("✅ Sistema encerrado com segurança\n")


if __name__ == '__main__':
    main()