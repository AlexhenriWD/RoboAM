#!/usr/bin/env python3
"""
EVA ROBOT - CAMERA MANAGER (OpenCV ONLY)
Pi Camera e USB Webcam via V4L2
"""

import cv2
import time
import threading
from enum import Enum
from typing import Optional
import numpy as np


class CameraType(Enum):
    USB = "usb"
    PICAM = "picam"


class CameraManager:
    def __init__(
        self,
        picam_id: int = 0,
        usb_id: int = 1,
        width: int = 640,
        height: int = 480,
        fps: int = 15
    ):
        self.picam_id = picam_id
        self.usb_id = usb_id

        self.width = width
        self.height = height
        self.fps = fps

        self.active_camera_type = CameraType.USB
        self.cap: Optional[cv2.VideoCapture] = None

        self.frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()

        self.running = False
        self.thread: Optional[threading.Thread] = None

        print("📷 CameraManager (OpenCV) inicializado")

    # ==========================================================
    # START / STOP
    # ==========================================================

    def start(self) -> bool:
        print("🚀 Iniciando CameraManager...")
        self.running = True

        if not self._open_camera(self.usb_id):
            print("⚠️  USB Camera não disponível, tentando Pi Camera")
            if not self._open_camera(self.picam_id):
                print("❌ Nenhuma câmera disponível")
                return False
            self.active_camera_type = CameraType.PICAM
        else:
            self.active_camera_type = CameraType.USB

        self.thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )
        self.thread.start()

        print(f"✅ Streaming iniciado ({self.active_camera_type.value})")
        return True

    def stop(self):
        print("🛑 Parando CameraManager...")
        self.running = False

        if self.thread:
            self.thread.join(timeout=2)

        if self.cap:
            self.cap.release()
            self.cap = None

        print("✅ CameraManager finalizado")

    # ==========================================================
    # CAMERA CONTROL
    # ==========================================================

    def switch_camera(self, camera_type: Optional[CameraType] = None):
        if camera_type is None:
            camera_type = (
                CameraType.PICAM
                if self.active_camera_type == CameraType.USB
                else CameraType.USB
            )

        if camera_type == self.active_camera_type:
            return

        cam_id = self.picam_id if camera_type == CameraType.PICAM else self.usb_id

        print(f"🔁 Alternando câmera para {camera_type.value.upper()}")

        # Fecha câmera atual
        if self.cap:
            self.cap.release()
            self.cap = None
            time.sleep(0.2)

        if not self._open_camera(cam_id):
            print(f"❌ Falha ao abrir {camera_type.value}")
            return

        self.active_camera_type = camera_type

    def _open_camera(self, device_id: int) -> bool:
        cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)

        if not cap.isOpened():
            return False

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.cap = cap
        return True

    # ==========================================================
    # CAPTURE LOOP
    # ==========================================================

    def _capture_loop(self):
        frame_interval = 1.0 / self.fps

        while self.running:
            if not self.cap:
                time.sleep(0.1)
                continue

            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.frame_lock:
                    self.frame = frame

            time.sleep(frame_interval)

    # ==========================================================
    # FRAME ACCESS
    # ==========================================================

    def get_frame(self) -> Optional[np.ndarray]:
        with self.frame_lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def get_frame_encoded(self, quality: int = 70) -> Optional[bytes]:
        frame = self.get_frame()
        if frame is None:
            return None

        # Overlay simples
        label = self.active_camera_type.value.upper()
        cv2.putText(
            frame,
            label,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        _, buffer = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality]
        )

        return buffer.tobytes()

    # ==========================================================
    # STATUS
    # ==========================================================

    def get_active_camera_type(self) -> CameraType:
        return self.active_camera_type

    def get_status(self) -> dict:
        return {
            "active_camera": self.active_camera_type.value,
            "running": self.running,
            "resolution": f"{self.width}x{self.height}",
            "fps": self.fps
        }


if __name__ == "__main__":
    cam = CameraManager()
    cam.start()

    print("SPACE = switch | Q = quit")

    while True:
        frame = cam.get_frame()
        if frame is not None:
            cv2.imshow("Camera Test", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            cam.switch_camera()

    cam.stop()
    cv2.destroyAllWindows()
