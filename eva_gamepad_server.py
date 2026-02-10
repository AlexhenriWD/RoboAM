#!/usr/bin/env python3
"""
EVA ROBOT - GAMEPAD SERVER
Servidor com controle via gamepad + streaming TCP

FEATURES:
✅ Controle via gamepad (PS4/PS5/Xbox)
✅ Modo Drone FPV
✅ Streaming de vídeo TCP (porta 8000)
✅ Telemetria TCP (porta 5000)
✅ Cliente pode ser PC ou celular
"""

import sys
import os
import time
import json
import struct
import threading
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# EVA Robot
from eva_robot import EVARobot, RobotMode
from camera_manager import CameraType

# Servidor TCP
from server import Server

# Gamepad
from gamepad_controller import GamepadController
from drone_control_mode import DroneControlMode, DroneControlConfig


class EVAGamepadServer:
    """
    Servidor EVA com controle via gamepad
    
    Dual mode:
    1. Gamepad direto → Drone FPV control
    2. Cliente remoto → Recebe telemetria, envia comandos opcionais
    """
    
    def __init__(self):
        print("\n" + "="*60)
        print("🎮 EVA GAMEPAD SERVER - Inicializando...")
        print("="*60 + "\n")
        
        # Robô
        self.robot: Optional[EVARobot] = None
        
        # Gamepad
        self.gamepad: Optional[GamepadController] = None
        self.drone_mode: Optional[DroneControlMode] = None
        
        # Servidor TCP
        self.server = Server()
        
        # Estado
        self.running = False
        self.stop_event = threading.Event()
        
        # Threads
        self.video_thread: Optional[threading.Thread] = None
        self.telemetry_thread: Optional[threading.Thread] = None
        self.monitor_thread: Optional[threading.Thread] = None
        
        print("✅ EVAGamepadServer inicializado")
    
    # ========================================
    # START / STOP
    # ========================================
    
    def start(
        self,
        command_port: int = 5000,
        video_port: int = 8000,
        enable_gamepad: bool = True
    ) -> bool:
        """
        Inicia servidor
        
        Args:
            command_port: Porta para comandos/telemetria
            video_port: Porta para streaming de vídeo
            enable_gamepad: Habilitar controle via gamepad
        """
        print(f"\n🚀 Iniciando servidor...")
        print(f"   Comando/Telemetria: {command_port}")
        print(f"   Vídeo: {video_port}")
        print(f"   Gamepad: {'Sim' if enable_gamepad else 'Não'}\n")
        
        # Iniciar robô
        self.robot = EVARobot()
        if not self.robot.start():
            print("⚠️  Robô iniciado em modo limitado")
        
        # Iniciar gamepad (se habilitado)
        if enable_gamepad:
            try:
                self.gamepad = GamepadController(
                    device_path="/dev/input/event5",
                    deadzone=0.02,      # ✅ Reduzido de 0.15 para 0.05
                    smoothing=0.0,      # ✅ Desabilitado para resposta mais rápida
                    auto_detect=True
                )
                
                if self.gamepad.start():
                    # Criar modo drone
                    config = DroneControlConfig(
                        drive_sensitivity=1.0,
                        head_pan_sensitivity=1.0,
                        head_tilt_sensitivity=0.8
                    )
                    
                    self.drone_mode = DroneControlMode(
                        self.robot,
                        self.gamepad,
                        config
                    )
                    
                    # Ativar
                    self.drone_mode.enable()
                    
                    print("✅ Gamepad conectado e modo drone ativo")
                else:
                    print("⚠️  Gamepad não detectado (continuando sem)")
                    self.gamepad = None
            
            except Exception as e:
                print(f"⚠️  Erro ao iniciar gamepad: {e}")
                self.gamepad = None
        
        # Iniciar servidor TCP
        try:
            self.server.start_tcp_servers(
                command_port=command_port,
                video_port=video_port,
                max_clients=1,
                listen_count=1
            )
            print(f"✅ Servidor TCP iniciado")
            print(f"   IP: {self.server.ip_address}")
        except Exception as e:
            print(f"❌ Erro ao iniciar servidor TCP: {e}")
            return False
        
        # Iniciar threads
        self.running = True
        self.stop_event.clear()
        
        self.video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self.video_thread.start()
        
        self.telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self.telemetry_thread.start()
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        print("\n" + "="*60)
        print("✅ Servidor iniciado com sucesso!")
        print("="*60 + "\n")
        
        self._print_controls()
        
        return True
    
    def stop(self):
        """Para servidor"""
        print("\n🛑 Parando servidor...")
        
        self.running = False
        self.stop_event.set()
        
        # Aguardar threads
        for thread in [self.video_thread, self.telemetry_thread, self.monitor_thread]:
            if thread:
                thread.join(timeout=2.0)
        
        # Parar gamepad
        if self.drone_mode:
            self.drone_mode.disable()
        
        if self.gamepad:
            self.gamepad.stop()
        
        # Parar servidor TCP
        self.server.stop_tcp_servers()
        
        # Parar robô
        if self.robot:
            self.robot.stop()
        
        print("✅ Servidor finalizado")
    
    # ========================================
    # LOOPS
    # ========================================
    
    def _video_loop(self):
        """Loop de streaming de vídeo"""
        print("📹 Video loop iniciado")
        
        while not self.stop_event.is_set() and self.running:
            try:
                # Verificar se há cliente conectado
                if not self.server.is_video_server_connected():
                    time.sleep(0.1)
                    continue
                
                # Verificar se está trocando câmera
                if self.robot.camera_manager.switching:
                    time.sleep(0.02)
                    continue
                
                # Capturar frame
                frame_data = self.robot.get_camera_frame_encoded(quality=75)
                
                if frame_data is None or len(frame_data) < 100:
                    time.sleep(0.02)
                    continue
                
                # Enviar com header de tamanho
                packet = struct.pack('<L', len(frame_data)) + frame_data
                self.server.send_data_to_video_client(packet)
                
                # 15 FPS
                time.sleep(1 / 15)
            
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Cliente desconectou
                time.sleep(0.2)
            
            except Exception as e:
                print(f"⚠️  Erro no vídeo: {e}")
                time.sleep(0.1)
        
        print("📹 Video loop finalizado")
    
    def _telemetry_loop(self):
        """Loop de envio de telemetria"""
        print("📡 Telemetry loop iniciado")
        
        while not self.stop_event.is_set() and self.running:
            try:
                # Enviar telemetria a cada 200ms (5Hz)
                if self.server.is_command_server_connected():
                    telemetry = self._build_telemetry()
                    
                    # Enviar como JSON
                    data = json.dumps(telemetry) + "\n"
                    self.server.send_data_to_command_client(data)
                
                time.sleep(0.2)
            
            except Exception as e:
                print(f"⚠️  Erro na telemetria: {e}")
                time.sleep(0.5)
        
        print("📡 Telemetry loop finalizado")
    
    def _monitor_loop(self):
        """Loop de monitoramento"""
        print("👁️  Monitor loop iniciado")
        
        last_status_print = 0
        
        while not self.stop_event.is_set() and self.running:
            try:
                # Printar status a cada 10s
                now = time.time()
                if now - last_status_print > 10:
                    self._print_status()
                    last_status_print = now
                
                time.sleep(1)
            
            except Exception as e:
                print(f"⚠️  Erro no monitor: {e}")
                time.sleep(1)
        
        print("👁️  Monitor loop finalizado")
    
    # ========================================
    # TELEMETRIA
    # ========================================
    
    def _build_telemetry(self) -> dict:
        """Constrói pacote de telemetria"""
        # Estado do robô
        robot_state = self.robot.get_status()
        
        # Estado do gamepad
        gamepad_state = None
        if self.gamepad and self.gamepad.is_connected():
            gp = self.gamepad.get_state()
            gamepad_state = {
                'left_stick': {'x': gp.left_x, 'y': gp.left_y},
                'right_stick': {'x': gp.right_x, 'y': gp.right_y},
                'triggers': {'left': gp.left_trigger, 'right': gp.right_trigger},
                'buttons': {
                    'a': gp.button_a,
                    'b': gp.button_b,
                    'x': gp.button_x,
                    'y': gp.button_y
                }
            }
        
        # Estado do drone mode
        drone_state = None
        if self.drone_mode:
            drone_state = self.drone_mode.get_status()
        
        return {
            'type': 'telemetry',
            'timestamp': time.time(),
            'robot': robot_state,
            'gamepad': gamepad_state,
            'drone_mode': drone_state
        }
    
    # ========================================
    # STATUS / INFO
    # ========================================
    
    def _print_controls(self):
        """Imprime controles disponíveis"""
        print("\n" + "="*60)
        print("🎮 CONTROLES")
        print("="*60)
        
        if self.gamepad and self.gamepad.is_connected():
            print("\n🕹️  GAMEPAD (Modo Drone):")
            print("   Left Stick     → Movimento (frente/trás/lateral)")
            print("   Right Stick    → Cabeça (pan/tilt)")
            print("   L1/LB          → Girar esquerda")
            print("   R1/RB          → Girar direita")
            print("   Left Trigger   → Slow mode (precisão)")
            print("   Right Trigger  → Turbo mode")
            print("   A/Cross        → Switch câmera")
            print("   B/Circle       → Emergency stop")
            print("   X/Square       → Home cabeça")
            print("   Y/Triangle     → Center cabeça")
            print("   D-Pad          → Presets (frente/baixo/esq/dir)")
        else:
            print("\n⚠️  Gamepad não conectado")
        
        print("\n⌨️  TECLADO:")
        print("   's' → Status")
        print("   'g' → Toggle gamepad")
        print("   'c' → Switch câmera")
        print("   'h' → Home position")
        print("   'q' → Sair")
        
        print("\n" + "="*60 + "\n")
    
    def _print_status(self):
        """Imprime status do sistema"""
        print("\n" + "="*60)
        print("📊 STATUS DO SISTEMA")
        print("="*60)
        
        # Servidor
        print(f"\n🌐 Servidor:")
        print(f"   IP: {self.server.ip_address}")
        print(f"   Clientes comando: {len(self.server.get_command_server_client_ips())}")
        print(f"   Clientes vídeo: {len(self.server.get_video_server_client_ips())}")
        
        # Gamepad
        if self.gamepad:
            info = self.gamepad.get_info()
            print(f"\n🎮 Gamepad:")
            print(f"   Nome: {info.get('name', 'N/A')}")
            print(f"   Tipo: {info.get('type', 'N/A')}")
            print(f"   Conectado: {'✅' if info.get('connected') else '❌'}")
        
        # Drone mode
        if self.drone_mode:
            status = self.drone_mode.get_status()
            print(f"\n🚁 Drone Mode:")
            print(f"   Ativo: {'✅' if status['enabled'] else '❌'}")
            print(f"   Velocidade: {status['speed_mode']}")
            print(f"   Cabeça: yaw={status['target_head']['yaw']:.0f}° "
                  f"pitch={status['target_head']['pitch']:.0f}°")
            print(f"   Comandos enviados: {status['stats']['commands_sent']}")
        
        # Robô
        print(f"\n🤖 Robô:")
        robot_status = self.robot.get_status()
        print(f"   Modo: {robot_status['mode']}")
        
        # Câmera (safe access)
        cam_info = robot_status.get('camera', {})
        cam_active = cam_info.get('active_camera', 'unknown')
        print(f"   Câmera: {cam_active}")
        
        print("\n" + "="*60 + "\n")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Função principal"""
    print("\n" + "="*60)
    print("🎮 EVA ROBOT GAMEPAD SERVER")
    print("="*60 + "\n")
    
    server = EVAGamepadServer()
    
    try:
        # Iniciar
        if not server.start(
            command_port=5000,
            video_port=8000,
            enable_gamepad=True
        ):
            print("❌ Falha ao iniciar servidor")
            return 1
        
        # Loop principal (comandos de teclado)
        print("💡 Digite 's' para status, 'q' para sair\n")
        
        while True:
            try:
                cmd = input().strip().lower()
                
                if cmd == 'q':
                    break
                
                elif cmd == 's':
                    server._print_status()
                
                elif cmd == 'g':
                    # Toggle gamepad
                    if server.drone_mode:
                        if server.drone_mode.enabled:
                            server.drone_mode.disable()
                            print("⚪ Gamepad desativado")
                        else:
                            server.drone_mode.enable()
                            print("✅ Gamepad ativado")
                
                elif cmd == 'c':
                    # Switch câmera
                    server.robot.switch_camera()
                    print("📷 Câmera alternada")
                
                elif cmd == 'h':
                    # Home
                    server.robot.arm.move_to_home()
                    print("🏠 Home position")
                
                else:
                    print("Comando inválido. Use: s (status), g (gamepad), c (câmera), h (home), q (sair)")
            
            except EOFError:
                break
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido pelo usuário")
    
    finally:
        server.stop()
        print("\n✅ Programa finalizado")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())