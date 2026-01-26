#!/usr/bin/env python3
"""
EVA NETWORK SERVER - CAMERA REAL + CONTROLE ESTÁVEL
Compatível com robot_core.py (Picamera2 ou Webcam USB)
"""

import asyncio
import json
import base64
import signal
import traceback
from datetime import datetime

import websockets
from websockets.asyncio.server import serve

from eva_remote_control import ActuatorServer, EVAIntegration
from robot_core import EvaRobotCore
from robot_protocol import parse_command, now_s, clamp, as_float, as_int

# Camera imports
try:
    from picamera2 import Picamera2
    PICAM_OK = True
except:
    PICAM_OK = False

try:
    import cv2
    OPENCV_OK = True
except:
    OPENCV_OK = False


class CameraSystem:
    def __init__(self):
        self.picam = None
        self.webcam = None

        if PICAM_OK:
            try:
                self.picam = Picamera2()
                config = self.picam.create_preview_configuration(
                    main={"size": (640, 480)}
                )
                self.picam.configure(config)
                self.picam.start()
                print("✅ Pi Camera ativa")
            except Exception as e:
                print(f"⚠️ PiCam falhou: {e}")
                self.picam = None

        if self.picam is None and OPENCV_OK:
            try:
                self.webcam = cv2.VideoCapture(1)
                if self.webcam.isOpened():
                    print("✅ Webcam USB (/dev/video1) ativa")
                else:
                    self.webcam = None
            except Exception as e:
                print(f"⚠️ Webcam falhou: {e}")
                self.webcam = None

    def get_frame(self):
        if self.picam:
            return self.picam.capture_array()
        if self.webcam:
            ok, frame = self.webcam.read()
            return frame if ok else None
        return None

    def cleanup(self):
        if self.picam:
            self.picam.stop()
            self.picam.close()
        if self.webcam:
            self.webcam.release()


class RobotServer:
    def __init__(self):
        self.robot = EvaRobotCore()
        self.robot.initialize(enable_arm=True, enable_cameras=True)

        self.actuator = ActuatorServer(self.robot)
        self.actuator.start_monitoring()

        self.eva = EVAIntegration(self.actuator)
        self.eva.enable_autonomous()

        self.camera = CameraSystem()
        self.clients = set()
        self.running = True

    async def start(self):
        async with serve(self.handle_client, "0.0.0.0", 8765,
                         ping_interval=20, ping_timeout=30):
            print("🚀 Servidor rodando na porta 8765")
            await asyncio.Future()

    async def handle_client(self, ws):
        print("📡 Cliente conectado")
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({
                "type": "welcome",
                "time": datetime.now().isoformat()
            }))

            async for raw in ws:
                await self.process_message(ws, raw)
        except:
            pass
        finally:
            self.clients.remove(ws)
            print("📡 Cliente saiu")

    async def process_message(self, ws, raw):
        msg = json.loads(raw)
        env = parse_command(msg)

        if env.cmd == "drive":
            vx = clamp(as_float(env.params.get("vx", 0)), -1, 1)
            vy = clamp(as_float(env.params.get("vy", 0)), -1, 1)
            vz = clamp(as_float(env.params.get("vz", 0)), -1, 1)
            self.actuator.drive(vx, vy, vz)

        elif env.cmd == "stop":
            self.actuator.stop()

        elif env.cmd == "estop":
            self.actuator.stop()

        elif env.cmd == "head":
            yaw = env.params.get("yaw")
            pitch = env.params.get("pitch")
            self.actuator.move_head(yaw=yaw, pitch=pitch)

    async def camera_loop(self):
        while self.running:
            frame = self.camera.get_frame()
            if frame is not None and self.clients:
                _, buf = cv2.imencode(".jpg", frame)
                b64 = base64.b64encode(buf).decode()
                msg = json.dumps({
                    "type": "camera_frame",
                    "data": b64
                })
                dead = set()
                for ws in self.clients:
                    try:
                        await ws.send(msg)
                    except:
                        dead.add(ws)
                self.clients -= dead
            await asyncio.sleep(0.15)  # ~6 FPS


async def main():
    server = RobotServer()
    loop = asyncio.get_running_loop()
    loop.create_task(server.camera_loop())
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
