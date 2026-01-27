#!/usr/bin/env python3
"""
EVA ROBOT - TCP SERVER
Servidor para controle remoto e streaming de vídeo
"""

import sys
import time
import struct
import threading
from typing import Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# Importar servidor TCP original
from server import Server

# EVA Robot
from eva_robot import EVARobot, RobotMode
from camera_manager import CameraType


class CommandParser:
    """Parser de comandos recebidos do cliente"""
    
    # Comandos de movimento
    CMD_FORWARD = "CMD_FORWARD"
    CMD_BACKWARD = "CMD_BACKWARD"
    CMD_LEFT = "CMD_LEFT"
    CMD_RIGHT = "CMD_RIGHT"
    CMD_STOP = "CMD_STOP"
    CMD_STRAFE_LEFT = "CMD_STRAFE_LEFT"
    CMD_STRAFE_RIGHT = "CMD_STRAFE_RIGHT"
    
    # Comandos de câmera
    CMD_CAMERA_SWITCH = "CMD_CAMERA_SWITCH"
    CMD_CAMERA_USB = "CMD_CAMERA_USB"
    CMD_CAMERA_PI = "CMD_CAMERA_PI"
    
    # Comandos do braço
    CMD_ARM_LEFT = "CMD_ARM_LEFT"
    CMD_ARM_RIGHT = "CMD_ARM_RIGHT"
    CMD_ARM_UP = "CMD_ARM_UP"
    CMD_ARM_DOWN = "CMD_ARM_DOWN"
    CMD_ARM_CENTER = "CMD_ARM_CENTER"
    CMD_ARM_SERVO = "CMD_ARM_SERVO"  # Format: CMD_ARM_SERVO,channel,angle
    
    # Comandos de modo
    CMD_MODE_MANUAL = "CMD_MODE_MANUAL"
    CMD_MODE_AUTO = "CMD_MODE_AUTO"
    
    # Comandos de status
    CMD_STATUS = "CMD_STATUS"
    CMD_PING = "CMD_PING"
    
    @staticmethod
    def parse(command: str) -> tuple:
        """
        Parse comando recebido
        
        Returns:
            (cmd, args) - comando e argumentos
        """
        parts = command.strip().split(',')
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        return cmd, args


class EVAServer:
    """Servidor principal do robô EVA"""
    
    def __init__(self):
        """Inicializa o servidor"""
        print("\n" + "="*60)
        print("🌐 EVA SERVER - Inicializando...")
        print("="*60 + "\n")
        
        # Servidor TCP
        self.server = Server()
        
        # Robô
        self.robot: Optional[EVARobot] = None
        
        # Estado
        self.is_running = False
        self.video_streaming = False
        
        # Threads
        self.command_thread: Optional[threading.Thread] = None
        self.video_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Parser
        self.parser = CommandParser()
        
        print("✅ EVAServer inicializado")
    
    def start(self, command_port: int = 5000, video_port: int = 8000) -> bool:
        """
        Inicia o servidor
        
        Args:
            command_port: Porta para comandos
            video_port: Porta para streaming de vídeo
        """
        print(f"\n🚀 Iniciando servidor nas portas {command_port} e {video_port}...\n")
        
        # Iniciar robô
        self.robot = EVARobot()
        if not self.robot.start():
            print("⚠️  Robô iniciado em modo limitado")
        
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
            print(f"   Porta comandos: {command_port}")
            print(f"   Porta vídeo: {video_port}")
        except Exception as e:
            print(f"❌ Erro ao iniciar servidor TCP: {e}")
            return False
        
        # Iniciar threads
        self.is_running = True
        self.stop_event.clear()
        
        self.command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self.command_thread.start()
        
        self.video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self.video_thread.start()
        
        print("\n" + "="*60)
        print("✅ Servidor iniciado com sucesso!")
        print("="*60 + "\n")
        
        return True
    
    def _command_loop(self):
        """Loop de processamento de comandos"""
        while not self.stop_event.is_set() and self.is_running:
            try:
                if not self.server.is_video_server_connected():
                    time.sleep(0.1)
                    continue

                # 🔒 se câmera está trocando, NÃO streama
                if self.robot.camera_manager.switching:
                    time.sleep(0.02)
                    continue

                frame_data = self.robot.get_camera_frame_encoded(quality=70)

                # 🚫 NUNCA envie frame inválido
                if frame_data is None or len(frame_data) < 100:
                    time.sleep(0.02)
                    continue

                length = len(frame_data)
                packet = struct.pack('<L', length) + frame_data

                try:
                    self.server.send_data_to_video_client(packet)
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    print(f"📴 Cliente de vídeo caiu: {e}")
                    time.sleep(0.2)
                    continue

                time.sleep(1 / 15)

            except Exception as e:
                print(f"⚠️ Erro no streaming de vídeo: {e}")
                time.sleep(0.1)

    
    def _process_command(self, command: str) -> str:
        """
        Processa um comando recebido
        
        Returns:
            Resposta para enviar ao cliente
        """
        cmd, args = self.parser.parse(command)
        
        try:
            # Comandos de movimento
            if cmd == self.parser.CMD_FORWARD:
                speed = int(args[0]) if args else 1500
                self.robot.move_forward(speed)
                return "OK:FORWARD"
            
            elif cmd == self.parser.CMD_BACKWARD:
                speed = int(args[0]) if args else 1500
                self.robot.move_backward(speed)
                return "OK:BACKWARD"
            
            elif cmd == self.parser.CMD_LEFT:
                speed = int(args[0]) if args else 1500
                self.robot.turn_left(speed)
                return "OK:LEFT"
            
            elif cmd == self.parser.CMD_RIGHT:
                speed = int(args[0]) if args else 1500
                self.robot.turn_right(speed)
                return "OK:RIGHT"
            
            elif cmd == self.parser.CMD_STRAFE_LEFT:
                speed = int(args[0]) if args else 1500
                self.robot.strafe_left(speed)
                return "OK:STRAFE_LEFT"
            
            elif cmd == self.parser.CMD_STRAFE_RIGHT:
                speed = int(args[0]) if args else 1500
                self.robot.strafe_right(speed)
                return "OK:STRAFE_RIGHT"
            
            elif cmd == self.parser.CMD_STOP:
                self.robot.stop_motors()
                return "OK:STOP"
            
            # Comandos de câmera
            elif cmd == self.parser.CMD_CAMERA_SWITCH:
                self.robot.switch_camera()
                camera_type = self.robot.camera_manager.get_active_camera_type()
                return f"OK:CAMERA:{camera_type.value.upper()}"
            
            elif cmd == self.parser.CMD_CAMERA_USB:
                self.robot.switch_camera(CameraType.USB)
                return "OK:CAMERA:USB"
            
            elif cmd == self.parser.CMD_CAMERA_PI:
                self.robot.switch_camera(CameraType.PICAM)
                return "OK:CAMERA:PI"
            
            # Comandos do braço
            elif cmd == self.parser.CMD_ARM_LEFT:
                degrees = int(args[0]) if args else 30
                self.robot.arm_look_left(degrees)
                return "OK:ARM_LEFT"
            
            elif cmd == self.parser.CMD_ARM_RIGHT:
                degrees = int(args[0]) if args else 30
                self.robot.arm_look_right(degrees)
                return "OK:ARM_RIGHT"
            
            elif cmd == self.parser.CMD_ARM_UP:
                degrees = int(args[0]) if args else 20
                self.robot.arm_look_up(degrees)
                return "OK:ARM_UP"
            
            elif cmd == self.parser.CMD_ARM_DOWN:
                degrees = int(args[0]) if args else 20
                self.robot.arm_look_down(degrees)
                return "OK:ARM_DOWN"
            
            elif cmd == self.parser.CMD_ARM_CENTER:
                self.robot.arm_look_center()
                return "OK:ARM_CENTER"
            
            elif cmd == self.parser.CMD_ARM_SERVO:
                if len(args) >= 2:
                    channel = int(args[0])
                    angle = int(args[1])
                    smooth = args[2].lower() == 'true' if len(args) > 2 else False
                    self.robot.arm_set_angle(channel, angle, smooth)
                    return f"OK:ARM_SERVO:{channel}:{angle}"
                return "ERROR:INVALID_ARGS"
            
            # Comandos de modo
            elif cmd == self.parser.CMD_MODE_MANUAL:
                self.robot.set_mode(RobotMode.MANUAL)
                return "OK:MODE:MANUAL"
            
            elif cmd == self.parser.CMD_MODE_AUTO:
                self.robot.set_mode(RobotMode.AUTONOMOUS)
                return "OK:MODE:AUTO"
            
            # Comandos de status
            elif cmd == self.parser.CMD_STATUS:
                status = self.robot.get_status()
                return f"OK:STATUS:{status}"
            
            elif cmd == self.parser.CMD_PING:
                return "OK:PONG"
            
            else:
                return f"ERROR:UNKNOWN_COMMAND:{cmd}"
        
        except Exception as e:
            return f"ERROR:{str(e)}"
    
    def _video_loop(self):
        """Loop de streaming de vídeo"""
        while not self.stop_event.is_set() and self.is_running:
            try:
                # Obter frame
                frame_data = self.robot.get_camera_frame_encoded(quality=70)
                
                if frame_data is not None:
                    # Enviar frame no formato: [length:4bytes][jpeg_data]
                    length = len(frame_data)
                    packet = struct.pack('<L', length) + frame_data
                    
                    self.server.send_data_to_video_client(packet)
                
                time.sleep(0.033)  # ~30 FPS
                
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                # Client fechou / caiu. Não mata o servidor inteiro.
                print(f"📴 Cliente de vídeo caiu: {e}")
                time.sleep(0.2)
                continue
                
            except Exception as e:
                print(f"⚠️  Erro no streaming de vídeo: {e}")
                time.sleep(0.1)
    
    def get_status(self) -> dict:
        """Retorna status do servidor"""
        return {
            'is_running': self.is_running,
            'ip_address': self.server.ip_address,
            'command_clients': self.server.get_command_server_client_ips(),
            'video_clients': self.server.get_video_server_client_ips(),
            'robot_status': self.robot.get_status() if self.robot else None
        }
    
    def print_status(self):
        """Imprime status do servidor"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("🌐 EVA SERVER STATUS")
        print("="*60)
        print(f"Running:        {status['is_running']}")
        print(f"IP:             {status['ip_address']}")
        print(f"Cmd Clients:    {len(status['command_clients'])}")
        print(f"Video Clients:  {len(status['video_clients'])}")
        print("="*60 + "\n")
        
        if self.robot is not None:
            self.robot.print_status()
    
    def stop(self):
        """Para o servidor"""
        print("\n🛑 Parando servidor...")
        
        self.is_running = False
        self.stop_event.set()
        
        # Aguardar threads
        if self.command_thread is not None:
            self.command_thread.join(timeout=2.0)
        if self.video_thread is not None:
            self.video_thread.join(timeout=2.0)
        
        # Parar servidor TCP
        self.server.stop_tcp_servers()
        
        # Parar robô
        if self.robot is not None:
            self.robot.stop()
        
        print("✅ Servidor finalizado")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Função principal"""
    print("\n" + "="*60)
    print("🤖 EVA ROBOT SERVER")
    print("="*60 + "\n")
    
    server = EVAServer()
    
    try:
        if not server.start(command_port=5000, video_port=8000):
            print("❌ Falha ao iniciar servidor")
            return 1
        
        print("\n💡 Comandos disponíveis:")
        print("   's' - Mostrar status")
        print("   'q' - Sair")
        print("\n")
        
        # Loop principal
        while True:
            cmd = input().strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == 's':
                server.print_status()
            else:
                print("Comando inválido. Use 's' (status) ou 'q' (sair)")
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário")
    
    finally:
        server.stop()
        print("\n✅ Programa finalizado")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())