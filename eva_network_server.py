#!/usr/bin/env python3
"""
EVA NETWORK SERVER - Servidor HTTP + WebSocket Consolidado
Servidor único para interface web + controle remoto + streaming

PORTAS:
- 8000: HTTP (interface web)
- 8765: WebSocket (controle + streaming)

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
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

import cv2
import websockets
from websockets.asyncio.server import serve
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from eva_robot_system import EVARobotCore


class EVAWebSocketServer:
    """
    Servidor WebSocket com suporte a HTTP fallback
    Aceita tanto conexões WebSocket quanto HTTP
    """
    
    def __init__(self, ws_port: int = 8765):
        self.ws_port = ws_port
        
        # Robô
        self.robot = EVARobotCore()
        
        # Clientes conectados
        self.clients: Set = set()
        
        # Estado
        self.running = False
        
        # Tasks
        self._state_task = None
        self._camera_task = None
        
        print(f"✅ Servidor WebSocket configurado na porta {ws_port}")
    
    async def process_request(self, path, request_headers):
        """
        Handler customizado para requisições HTTP
        Redireciona para instruções de uso
        """
        headers = request_headers
        # Se não for uma requisição WebSocket válida
        if headers.get("Upgrade", "").lower() != "websocket":
            import http
            html_content = """<!DOCTYPE html>
<html>
<head>
    <title>EVA Robot - WebSocket Server</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1e3c72;
            color: white;
        }
        .box {
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        code {
            background: rgba(0,0,0,0.3);
            padding: 2px 8px;
            border-radius: 4px;
            font-family: monospace;
        }
        h1 { color: #4ade80; }
        h2 { color: #93c5fd; }
        a {
            color: #60a5fa;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <h1>🤖 EVA Robot - WebSocket Server</h1>
    
    <div class="box">
        <h2>✅ Servidor Ativo</h2>
        <p>Este é o servidor WebSocket do EVA Robot.</p>
        <p>Porta WebSocket: <code>8765</code></p>
    </div>
    
    <div class="box">
        <h2>📱 Como Conectar</h2>
        <p>Baixe a interface de controle:</p>
        <p><a href="/eva_control_standalone.html" download>📥 Download eva_control_standalone.html</a></p>
        <p>Ou crie uma conexão WebSocket para:</p>
        <p><code>ws://192.168.100.30:8765</code></p>
    </div>
    
    <div class="box">
        <h2>💻 Exemplo JavaScript</h2>
        <pre><code>const ws = new WebSocket('ws://192.168.100.30:8765');

ws.onopen = () => {
    console.log('Conectado!');
    
    // Mover para frente
    ws.send(JSON.stringify({
        cmd: 'drive',
        params: { vx: 0.5 }
    }));
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    console.log('Mensagem:', msg);
};</code></pre>
    </div>
    
    <div class="box">
        <h2>📚 Documentação</h2>
        <p>Comandos disponíveis:</p>
        <ul>
            <li><code>drive</code> - Controle de movimento</li>
            <li><code>servo</code> - Controle de servos</li>
            <li><code>camera</code> - Controle de câmeras</li>
            <li><code>stop</code> - Parada de emergência</li>
            <li><code>sensors</code> - Leitura de sensores</li>
        </ul>
    </div>
</body>
</html>"""
            return (
                http.HTTPStatus.OK,
                [("Content-Type", "text/html; charset=utf-8")],
                html_content.encode("utf-8")
            )
        
        # Requisição WebSocket válida - permitir
        return None


class EVANetworkServer:
    """
    Servidor HTTP + WebSocket unificado
    HTTP: Interface web (porta 8000)
    WebSocket: Controle + Streaming (porta 8765)
    """
    
    def __init__(self, http_port: int = 8000, ws_port: int = 8765):
        self.http_port = http_port
        self.ws_port = ws_port
        
        # Robô
        self.robot = EVARobotCore()
        
        # Clientes conectados
        self.clients: Set = set()
        
        # Estado
        self.running = False
        
        # Tasks
        self._state_task = None
        self._camera_task = None
        self._http_server = None
        
        print(f"✅ Servidor configurado:")
        print(f"   HTTP: http://0.0.0.0:{http_port}")
        print(f"   WebSocket: ws://0.0.0.0:{ws_port}")
    
    async def start(self):
        """Inicia os servidores HTTP e WebSocket"""
        print("\n🚀 Iniciando servidores...")
        print(f"   HTTP: porta {self.http_port}")
        print(f"   WebSocket: porta {self.ws_port}\n")
        
        # Inicializar robô
        if not self.robot.initialize():
            print("❌ Falha ao inicializar robô")
            return
        
        self.running = True
        
        # Iniciar servidor HTTP em thread separada
        self._start_http_server()
        
        # Iniciar tasks de background
        self._state_task = asyncio.create_task(self._broadcast_state_loop())
        self._camera_task = asyncio.create_task(self._broadcast_camera_loop())
        
        try:
            # Importar http para o handler
            import http
            
            async def process_request(path, request):
                headers = request.headers

                if headers.get("Upgrade", "").lower() != "websocket":
                    import http
                    html_content = """<!DOCTYPE html>
            <html>
            <head>
                <title>EVA Robot - WebSocket Server</title>
            </head>
            <body>
                <h1>🤖 EVA Robot - WebSocket Server</h1>
                <p>Servidor ativo.</p>
            </body>
            </html>"""
                    return (
                        http.HTTPStatus.OK,
                        [("Content-Type", "text/html; charset=utf-8")],
                        html_content.encode("utf-8")
                    )

                return None

            
            async with serve(
                self._handle_client,
                "0.0.0.0",
                self.ws_port,
                process_request=process_request,
                ping_interval=15,
                ping_timeout=20,
                max_size=10_000_000
            ):
                print("✅ Servidores rodando!\n")
                print(f"📱 Interface: http://<IP_DO_RASPBERRY>:{self.http_port}/eva_control_standalone.html")
                print(f"🔌 WebSocket: ws://<IP_DO_RASPBERRY>:{self.ws_port}\n")
                await asyncio.Future()
        
        except OSError as e:
            if getattr(e, "errno", None) == 98:
                print(f"\n❌ ERRO: Porta {self.ws_port} já está em uso!")
                print(f"\n💡 Matar processo: sudo fuser -k {self.ws_port}/tcp")
                raise
            raise
    
    def _start_http_server(self):
        """Inicia servidor HTTP para servir a interface web"""
        
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(Path.cwd()), **kwargs)
            
            def log_message(self, format, *args):
                # Silenciar logs HTTP
                pass
        
        def run_server():
            try:
                self._http_server = HTTPServer(("0.0.0.0", self.http_port), Handler)
                print(f"✅ Servidor HTTP iniciado na porta {self.http_port}")
                self._http_server.serve_forever()
            except Exception as e:
                print(f"❌ Erro no servidor HTTP: {e}")
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
    
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
        """Handler de conexão de cliente WebSocket"""
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
        
        except ConnectionClosedOK:
            print(f"📡 Cliente desconectado normalmente: {client_id}")
        
        except ConnectionClosedError as e:
            print(f"📡 Cliente desconectado com erro: {client_id} - {e}")
        
        except Exception as e:
            print(f"❌ Erro no handler: {e}")
            traceback.print_exc()
        
        finally:
            self.clients.discard(websocket)
            print(f"📡 Cliente removido: {client_id} (total: {len(self.clients)})")
    
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
    
    server = EVANetworkServer(http_port=8000, ws_port=8765)
    
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