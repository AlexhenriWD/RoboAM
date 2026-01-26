import asyncio
import base64
import json
import cv2
import threading
from pathlib import Path
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
        self.lock = asyncio.Lock() # 🔒 Trava de segurança para hardware

    async def start(self):
        print("🚀 Iniciando Servidor EVA...")
        if not self.robot.initialize():
            print("❌ Falha crítica no hardware.")
            return

        self.running = True
        self._start_http_server()
        
        # Inicia loops de estado e câmera
        asyncio.create_task(self._broadcast_state_loop())
        asyncio.create_task(self._broadcast_camera_loop())

        async with serve(self._handle_client, "0.0.0.0", self.ws_port):
            print(f"🌐 Interface Web: http://localhost:{self.http_port}")
            await asyncio.Future()

    def _start_http_server(self):
        def run():
            server = HTTPServer(("0.0.0.0", self.http_port), SimpleHTTPRequestHandler)
            server.serve_forever()
        threading.Thread(target=run, daemon=True).start()

    async def _handle_client(self, websocket):
        self.clients.add(websocket)
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                cmd = msg.get("cmd")
                p = msg.get("params", {})
                
                # Usa a trava para priorizar comandos de movimento
                async with self.lock:
                    loop = asyncio.get_running_loop()
                    if cmd == "drive":
                        await loop.run_in_executor(None, self.robot.drive, p.get("vx",0), 0, p.get("vz",0))
                    elif cmd == "servo":
                        await loop.run_in_executor(None, self.robot.move_servo, p["channel"], p["angle"])
                    elif cmd == "stop":
                        await loop.run_in_executor(None, self.robot.stop)
        finally:
            self.clients.discard(websocket)

    async def _broadcast_camera_loop(self):
        while self.running:
            if self.clients:
                async with self.lock: # Evita conflito com motores
                    frame = self.robot.get_camera_frame()
                
                if frame is not None:
                    # Comprime mais a imagem para fluidez (qualidade 50)
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    if ok:
                        b64 = base64.b64encode(buf).decode()
                        payload = json.dumps({"type": "camera_frame", "data": b64})
                        for ws in list(self.clients):
                            try: await ws.send(payload)
                            except: pass
            await asyncio.sleep(0.05) # ~20 FPS

    async def _broadcast_state_loop(self):
        while self.running:
            if self.clients:
                data = self.robot.read_sensors()
                payload = json.dumps({"type": "state", "data": data})
                for ws in list(self.clients):
                    try: await ws.send(payload)
                    except: pass
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    asyncio.run(EVANetworkServer().start())