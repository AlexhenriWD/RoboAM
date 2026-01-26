import asyncio
import base64
import json
import cv2
from websockets.asyncio.server import serve
from eva_robot_system import EVARobotCore

class EVANetworkServer:
    def __init__(self):
        self.robot = EVARobotCore()
        self.clients = set()
        self.lock = asyncio.Lock() # 🔒 Garante que um comando não atropele o outro

    async def start(self):
        if not self.robot.initialize():
            print("❌ Falha no hardware")
            return

        # Inicia a câmera em segundo plano
        asyncio.create_task(self._camera_loop())
        
        async with serve(self._handler, "0.0.0.0", 8765):
            print("🚀 Servidor Rodando em ws://IP_DO_RASPBERRY:8765")
            await asyncio.Future()

    async def _handler(self, websocket):
        self.clients.add(websocket)
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                # Dá prioridade total ao movimento
                async with self.lock:
                    if msg['cmd'] == "drive":
                        p = msg['params']
                        self.robot.drive(p.get('vx',0), 0, p.get('vz',0))
                    elif msg['cmd'] == "stop":
                        self.robot.stop()
        finally:
            self.clients.discard(websocket)

    async def _camera_loop(self):
        while True:
            if self.clients:
                async with self.lock: # Espera o motor liberar o processador
                    frame = self.robot.get_camera_frame()
                
                if frame is not None:
                    # Reduz a qualidade para 40% para a transmissão ser instantânea
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 40])
                    b64 = base64.b64encode(buf).decode()
                    data = json.dumps({"type":"camera_frame", "data": b64})
                    for ws in list(self.clients):
                        try: await ws.send(data)
                        except: pass
            await asyncio.sleep(0.05) # 20 FPS

if __name__ == "__main__":
    asyncio.run(EVANetworkServer().start())