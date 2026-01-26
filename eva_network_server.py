#!/usr/bin/env python3
import asyncio
import base64
import json
import signal
import traceback
from datetime import datetime
from typing import Set
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import cv2
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from eva_robot_system import EVARobotCore


class EVANetworkServer:
    def __init__(self, http_port=8000, ws_port=8765):
        self.http_port = http_port
        self.ws_port = ws_port
        self.robot = EVARobotCore()
        self.clients: Set = set()
        self.running = False
        self._state_task = None
        self._camera_task = None
        self._http_server = None

    async def start(self):
        print("🚀 Iniciando servidor...")
        if not self.robot.initialize():
            print("❌ Falha ao inicializar robô")
            return

        self.running = True
        self._start_http_server()
        self._state_task = asyncio.create_task(self._broadcast_state_loop())
        self._camera_task = asyncio.create_task(self._broadcast_camera_loop())

        async def process_request(path, request):
            headers = request.headers
            if headers.get("Upgrade", "").lower() != "websocket":
                import http
                html = "<h1>EVA WS Server</h1><p>Use a interface web.</p>"
                return (
                    http.HTTPStatus.OK,
                    [("Content-Type", "text/html; charset=utf-8")],
                    html.encode()
                )
            return None

        async with serve(self._handle_client, "0.0.0.0", self.ws_port, process_request=process_request):
            print(f"🌐 HTTP: http://<IP>:{self.http_port}")
            print(f"🔌 WS: ws://<IP>:{self.ws_port}")
            await asyncio.Future()

    def _start_http_server(self):
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(Path.cwd()), **kwargs)
            def log_message(self, format, *args): pass

        def run():
            self._http_server = HTTPServer(("0.0.0.0", self.http_port), Handler)
            self._http_server.serve_forever()

        threading.Thread(target=run, daemon=True).start()

    async def _handle_client(self, websocket):
        client_id = f"{websocket.remote_address}"
        print(f"📡 Cliente conectado: {client_id}")
        self.clients.add(websocket)

        try:
            await websocket.send(json.dumps({"type": "welcome"}))
            async for raw in websocket:
                await self._process_message(websocket, raw)
        except (ConnectionClosedError, ConnectionClosedOK):
            pass
        finally:
            self.clients.discard(websocket)
            print(f"📡 Cliente saiu: {client_id}")

    async def _process_message(self, websocket, raw):
        msg = json.loads(raw)
        cmd = msg.get("cmd")
        p = msg.get("params", {})

        if cmd == "drive":
            self.robot.drive(p.get("vx",0), p.get("vy",0), p.get("vz",0))
        elif cmd == "servo":
            self.robot.move_servo(p["channel"], p["angle"], p.get("smooth",True), p.get("enable_camera",True))
        elif cmd == "camera":
            if p["action"] == "force":
                self.robot.force_camera(p["camera"])
            elif p["action"] == "disable_arm":
                self.robot.disable_arm_camera()
        elif cmd == "stop":
            self.robot.stop()

    async def _broadcast_state_loop(self):
        while self.running:
            if self.clients:
                data = self.robot.read_sensors()
                payload = json.dumps({"type":"state","data":data})
                for ws in list(self.clients):
                    await ws.send(payload)
            await asyncio.sleep(0.5)

    async def _broadcast_camera_loop(self):
        while self.running:
            if self.clients:
                frame = self.robot.get_camera_frame()
                if frame is not None:
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY,70])
                    if ok:
                        b64 = base64.b64encode(buf).decode()
                        payload = json.dumps({
                            "type":"camera_frame",
                            "data":b64,
                            "camera": self.robot.get_camera_status()["active_camera"]
                        })
                        for ws in list(self.clients):
                            await ws.send(payload)
            await asyncio.sleep(0.07)


async def main():
    server = EVANetworkServer()
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
