#!/usr/bin/env python3
"""
EVA NETWORK SERVER - Servidor WebSocket Consolidado
Servidor único para controle remoto + streaming de câmera

COMANDOS SUPORTADOS:
- drive: Movimento do carro
- servo: Controle individual de servos
- camera: Troca de câmera
- stop: Parada
- sensors: Leitura de sensores
"""

import asyncio
import base64
import json
import signal
import traceback
from datetime import datetime
from typing import Set, Dict, Any

import cv2
import websockets
from websockets.asyncio.server import serve

from eva_robot_system import EVARobotCore


class EVANetworkServer:
    """
    Servidor WebSocket unificado
    Controle + Streaming de câmera em um só servidor
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        
        # Robô
        self.robot = EVARobotCore()
        
        # Clientes conectados
        self.clients: Set = set()
        
        # Estado
        self.running = False
        
        # Tasks
        self._state_task = None
        self._camera_task = None
        
        print(f"✅ WebSocket Server configurado: ws://{host}:{port}")
    
    async def start(self):
        """Inicia o servidor"""
        print("\n🚀 Iniciando servidor WebSocket...")
        print(f"   Host: {self.host}")
        print(f"   Porta: {self.port}\n")
        
        # Inicializar robô
        if not self.robot.initialize():
            print("❌ Falha ao inicializar robô")
            return
        
        self.running = True
        
        # Iniciar tasks de background
        self._state_task = asyncio.create_task(self._broadcast_state_loop())
        self._camera_task = asyncio.create_task(self._broadcast_camera_loop())
        
        try:
            async with serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=15,
                ping_timeout=20,
                max_size=10_000_000  # 10MB para frames
            ):
                print("✅ Servidor rodando!\n")
                await asyncio.Future()
        
        except OSError as e:
            if getattr(e, "errno", None) == 98:
                print(f"\n❌ ERRO: Porta {self.port} já está em uso!")
                print(f"\n💡 Matar processo: sudo fuser -k {self.port}/tcp")
                raise
            raise
    
    async def stop(self):
        """Para o servidor"""
        print("\n🔴 Parando servidor...")
        
        self.running = False
        
        # Cancelar tasks
        for task in [self._state_task, self._camera_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Desconectar clientes
        if self.clients:
            await asyncio.gather(
                *[ws.close() for ws in list(self.clients)],
                return_exceptions=True
            )
        
        # Cleanup robô
        self.robot.cleanup()
        
        print("✅ Servidor parado")
    
    # ==========================================
    # HANDLER DE CLIENTES
    # ==========================================
    
    async def _handle_client(self, websocket):
        """Handler de conexão de cliente"""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        print(f"📡 Cliente conectado: {client_id}")
        
        self.clients.add(websocket)
        
        try:
            # Mensagem de boas-vindas
            welcome = {
                "type": "welcome",
                "message": "Conectado ao EVA Robot",
                "client_id": client_id,
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send(json.dumps(welcome))
            
            # Processar mensagens
            async for raw in websocket:
                try:
                    await self._process_message(websocket, raw)
                except Exception as e:
                    print(f"❌ Erro processando mensagem: {e}")
                    traceback.print_exc()
                    await self._send_error(websocket, str(e))
        
        except websockets.exceptions.ConnectionClosed:
            print(f"📡 Conexão fechada: {client_id}")
        
        except Exception as e:
            print(f"❌ Erro no handler: {e}")
            traceback.print_exc()
        
        finally:
            self.clients.discard(websocket)
            print(f"📡 Cliente desconectado: {client_id}")
    
    async def _process_message(self, websocket, raw_message: str):
        """Processa mensagem do cliente"""
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send_error(websocket, "JSON inválido")
            return
        
        cmd = msg.get("cmd")
        params = msg.get("params", {})
        
        # ==========================================
        # COMANDOS
        # ==========================================
        
        # DRIVE - Movimento do carro
        if cmd == "drive":
            vx = float(params.get("vx", 0.0))
            vy = float(params.get("vy", 0.0))
            vz = float(params.get("vz", 0.0))
            
            result = self.robot.drive(vx=vx, vy=vy, vz=vz)
            await websocket.send(json.dumps({
                "type": "response",
                "cmd": "drive",
                "result": result
            }))
        
        # SERVO - Controle de servo individual
        elif cmd == "servo":
            channel = int(params.get("channel", 0))
            angle = int(params.get("angle", 90))
            smooth = bool(params.get("smooth", True))
            enable_camera = bool(params.get("enable_camera", True))
            
            result = self.robot.move_servo(
                channel=channel,
                angle=angle,
                smooth=smooth,
                enable_camera=enable_camera
            )
            
            await websocket.send(json.dumps({
                "type": "response",
                "cmd": "servo",
                "result": result
            }))
        
        # CAMERA - Controle de câmera
        elif cmd == "camera":
            action = params.get("action")
            
            if action == "force":
                camera = params.get("camera", "usb")
                result = self.robot.force_camera(camera)
            
            elif action == "disable_arm":
                result = self.robot.disable_arm_camera()
            
            elif action == "status":
                result = {
                    "status": "ok",
                    "camera_status": self.robot.get_camera_status()
                }
            
            else:
                result = {"status": "error", "error": f"Ação inválida: {action}"}
            
            await websocket.send(json.dumps({
                "type": "response",
                "cmd": "camera",
                "result": result
            }))
        
        # STOP - Parada
        elif cmd == "stop":
            self.robot.stop()
            await websocket.send(json.dumps({
                "type": "response",
                "cmd": "stop",
                "result": {"status": "ok"}
            }))
        
        # SENSORS - Leitura de sensores
        elif cmd == "sensors":
            data = self.robot.read_sensors()
            await websocket.send(json.dumps({
                "type": "response",
                "cmd": "sensors",
                "result": {"status": "ok", "data": data}
            }))
        
        # Comando desconhecido
        else:
            await self._send_error(websocket, f"Comando desconhecido: {cmd}")
    
    async def _send_error(self, websocket, error_message: str):
        """Envia mensagem de erro"""
        await websocket.send(json.dumps({
            "type": "error",
            "error": error_message
        }))
    
    # ==========================================
    # BROADCAST LOOPS
    # ==========================================
    
    async def _broadcast_state_loop(self):
        """Broadcast periódico do estado do robô"""
        while self.running:
            try:
                if self.clients:
                    # Ler sensores
                    data = self.robot.read_sensors()
                    
                    payload = {
                        "type": "state",
                        "timestamp": datetime.now().isoformat(),
                        "data": data
                    }
                    
                    raw = json.dumps(payload)
                    
                    # Enviar para todos clientes
                    disconnected = set()
                    for ws in list(self.clients):
                        try:
                            await ws.send(raw)
                        except:
                            disconnected.add(ws)
                    
                    self.clients -= disconnected
                
                await asyncio.sleep(0.5)  # 2 Hz
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Erro state loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _broadcast_camera_loop(self):
        """Broadcast de frames de câmera"""
        while self.running:
            try:
                if self.clients:
                    # Capturar frame
                    frame = self.robot.get_camera_frame()
                    
                    if frame is not None:
                        # Comprimir JPEG
                        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        
                        if ok:
                            # Base64
                            b64 = base64.b64encode(buf.tobytes()).decode('ascii')
                            
                            # Status da câmera
                            cam_status = self.robot.get_camera_status()
                            
                            payload = {
                                "type": "camera_frame",
                                "timestamp": datetime.now().isoformat(),
                                "camera": cam_status.get("active_camera", "unknown"),
                                "arm_mode": cam_status.get("arm_mode", False),
                                "data": b64
                            }
                            
                            raw = json.dumps(payload)
                            
                            # Enviar para todos clientes
                            disconnected = set()
                            for ws in list(self.clients):
                                try:
                                    await ws.send(raw)
                                except:
                                    disconnected.add(ws)
                            
                            self.clients -= disconnected
                
                await asyncio.sleep(0.066)  # ~15 FPS
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ Erro camera loop: {e}")
                await asyncio.sleep(1.0)


# ==========================================
# MAIN
# ==========================================

async def main():
    print("\n" + "="*60)
    print("🤖 EVA ROBOT NETWORK SERVER")
    print("="*60)
    
    server = EVANetworkServer(host="0.0.0.0", port=8765)
    
    # Signal handlers
    def signal_handler(sig, frame):
        print("\n\n⚠️ Sinal recebido, encerrando...")
        asyncio.create_task(server.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        print("\n\n⚠️ Ctrl+C detectado")
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        traceback.print_exc()
    finally:
        await server.stop()
        print("\n✅ Encerrado!\n")


if __name__ == "__main__":
    asyncio.run(main())