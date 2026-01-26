import asyncio
import base64
import json
import cv2
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from websockets.asyncio.server import serve
from eva_robot_system import EVARobotCore

class EVANetworkServer:
    def __init__(self, http_port=8000, ws_port=8765):
        self.http_port = http_port
        self.ws_port = ws_port
        self.robot = EVARobotCore()
        self.clients = set()
        self.running = False
        self.lock = asyncio.Lock() # Protege o hardware de conflitos

    def _start_http_server(self):
        """Inicia o servidor para carregar o arquivo HTML"""
        def run():
            server = HTTPServer(("0.0.0.0", self.http_port), SimpleHTTPRequestHandler)
            print(f"🏠 Servidor Web em http://IP_DO_RASPBERRY:{self.http_port}")
            server.serve_forever()
        threading.Thread(target=run, daemon=True).start()

    async def _process_request(self, path, request):
        """Corrige o erro de 'keep-alive' do navegador (InvalidUpgrade)"""
        headers = request.headers
        if headers.get("Connection") == "keep-alive":
            headers["Connection"] = "Upgrade"
        return None

    async def start(self):
        print("🚀 Iniciando sistema EVA...")
        if not self.robot.initialize():
            print("❌ Falha crítica no hardware. Verifique os cabos.")
            return

        self.running = True
        self._start_http_server()
        
        # Inicia a transmissão de vídeo em segundo plano
        asyncio.create_task(self._camera_loop())
        
        # Inicia o servidor WebSocket com a correção de headers
        async with serve(
            self._handler, 
            "0.0.0.0", 
            self.ws_port,
            process_request=self._process_request
        ):
            print(f"📡 WebSocket ativo na porta {self.ws_port}")
            await asyncio.Future() # Mantém o servidor rodando

    async def _handler(self, websocket):
        self.clients.add(websocket)
        print(f"✅ Novo cliente conectado. Total: {len(self.clients)}")
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                cmd = msg.get("cmd")
                p = msg.get("params", {})

                async with self.lock:
                    if cmd == "drive":
                        # vx > 0: frente, vx < 0: trás, vz: curvas
                        self.robot.drive(p.get("vx", 0), 0, p.get("vz", 0))
                    elif cmd == "stop":
                        self.robot.stop()
                    elif cmd == "servo":
                        self.robot.move_servo(p.get("channel"), p.get("angle"))
        except Exception as e:
            print(f"⚠️ Erro no cliente: {e}")
        finally:
            self.clients.discard(websocket)

    async def _camera_loop(self):
        while self.running:
            if self.clients:
                async with self.lock:
                    frame = self.robot.get_camera_frame()
                
                if frame is not None:
                    # Comprime a imagem para não pesar na rede
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 45])
                    b64 = base64.b64encode(buf).decode()
                    payload = json.dumps({"type": "camera_frame", "data": b64})
                    
                    # Envia para todos os clientes conectados
                    for ws in list(self.clients):
                        try:
                            await ws.send(payload)
                        except:
                            pass
            await asyncio.sleep(0.05) # ~20 FPS

if __name__ == "__main__":
    server = EVANetworkServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n🛑 Desligando...")