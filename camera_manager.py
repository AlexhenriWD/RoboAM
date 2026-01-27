#!/usr/bin/env python3
"""
EVA ROBOT - CAMERA MANAGER (OpenCV ONLY, THREAD-SAFE)
Pi Camera e USB Webcam via V4L2, com switch atômico e sem travar stream.
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
        fps: int = 15,
        rotate_picam_ccw: bool = False,
    ):
        self.picam_id = picam_id
        self.usb_id = usb_id

        self.width = width
        self.height = height
        self.fps = max(5, int(fps))

        self.rotate_picam_ccw = rotate_picam_ccw

        self.active_camera_type = CameraType.USB
        self.cap: Optional[cv2.VideoCapture] = None

        self.frame: Optional[np.ndarray] = None
        self.last_good_frame: Optional[np.ndarray] = None

        self.frame_lock = threading.Lock()
        self.cap_lock = threading.Lock()

        self.running = False
        self.switching = False
        self.thread: Optional[threading.Thread] = None

        print("📷 CameraManager (OpenCV, thread-safe) inicializado")

    # ==========================================================
    # START / STOP
    # ==========================================================

    def start(self) -> bool:
        print("🚀 Iniciando CameraManager...")
        self.running = True

        # Tenta USB primeiro, senão PiCam
        if self._open_camera(self.usb_id):
            self.active_camera_type = CameraType.USB
        elif self._open_camera(self.picam_id):
            self.active_camera_type = CameraType.PICAM
        else:
            print("❌ Nenhuma câmera disponível")
            return False

        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print(f"✅ Streaming iniciado ({self.active_camera_type.value})")
        return True

    def stop(self):
        print("🛑 Parando CameraManager...")
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

        with self.cap_lock:
            if self.cap:
                self.cap.release()
                self.cap = None

        print("✅ CameraManager finalizado")

    # ==========================================================
    # SWITCH CAMERA (ATÔMICO)
    # ==========================================================

    def switch_camera(self, camera_type: Optional[CameraType] = None):
        if camera_type is None:
            camera_type = CameraType.PICAM if self.active_camera_type == CameraType.USB else CameraType.USB

        if camera_type == self.active_camera_type:
            return

        target_id = self.picam_id if camera_type == CameraType.PICAM else self.usb_id

        print(f"🔁 Alternando câmera para {camera_type.value.upper()}")

        self.switching = True
        try:
            with self.cap_lock:
                # Fecha atual
                if self.cap:
                    self.cap.release()
                    self.cap = None

                # Pequena pausa para o driver respirar
                time.sleep(0.25)

                # Abre nova
                if not self._open_camera(target_id):
                    print(f"❌ Falha ao abrir {camera_type.value.upper()} (device {target_id})")
                    # tenta reabrir a anterior como fallback
                    fallback_id = self.usb_id if self.active_camera_type == CameraType.USB else self.picam_id
                    self._open_camera(fallback_id)
                    return

                self.active_camera_type = camera_type

        finally:
            # deixa o loop voltar a capturar
            self.switching = False

    def _open_camera(self, device_id: int) -> bool:
        cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
        if not cap.isOpened():
            return False

        # Configurações seguras
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Alguns drivers adoram travar com auto-exposure; mas não vou forçar aqui.

        self.cap = cap
        return True

    # ==========================================================
    # CAPTURE LOOP
    # ==========================================================

    def _capture_loop(self):
        frame_interval = 1.0 / self.fps

        while self.running:
            if self.switching:
                time.sleep(0.01)
                continue

            with self.cap_lock:
                cap = self.cap

            if cap is None:
                time.sleep(0.05)
                continue

            ok, frame = cap.read()
            if ok and frame is not None:
                # Rotação opcional da PiCam
                if self.active_camera_type == CameraType.PICAM and self.rotate_picam_ccw:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                with self.frame_lock:
                    self.frame = frame
                    self.last_good_frame = frame
            else:
                # Se falhou, não zera frame: mantém last_good_frame para o stream não “sumir”
                time.sleep(0.01)

            time.sleep(frame_interval)

    # ==========================================================
    # FRAME ACCESS
    # ==========================================================

    def get_frame(self) -> Optional[np.ndarray]:
        with self.frame_lock:
            if self.frame is not None:
                return self.frame.copy()
            if self.last_good_frame is not None:
                return self.last_good_frame.copy()
            return None

    def get_frame_encoded(self, quality: int = 70) -> Optional[bytes]:
        frame = self.get_frame()
        if frame is None:
            return None

        label = self.active_camera_type.value.upper()
        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if not ok:
            return None
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
            "fps": self.fps,
            "resolution": f"{self.width}x{self.height}",
            "switching": self.switching,
        }
