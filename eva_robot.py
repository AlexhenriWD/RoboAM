#!/usr/bin/env python3
"""
EVA ROBOT - MAIN CONTROLLER (LIMPO E CONSISTENTE)
- Motores (Ordinary_Car)
- Servos 0..3 (base/ombro/cotovelo/cabeça)
- Câmeras (USB via OpenCV + PiCam via Picamera2)
"""

import os
import sys
import time
from enum import Enum
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from robot_core import Servo, Ordinary_Car, Ultrasonic
from camera_manager import CameraManager, CameraType
from arm_controller import ArmController
from robot_state import STATE
from safety import SafetyController
from hardware_config import CONFIG


class RobotMode(Enum):
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"
    IDLE = "idle"


class EVARobot:
    def __init__(self):
        print("🤖 Inicializando EVA Robot...")

        # Hardware
        self.servo = Servo()
        self.motor = Ordinary_Car()
        self.ultrasonic = Ultrasonic()

        # Subsistemas
        self.arm = ArmController(self.servo)
        self.camera_manager = CameraManager(
            picam_id=0,
            usb_id=CONFIG.cameras.USB_DEVICE_ID,
            width=CONFIG.cameras.USB_WIDTH,
            height=CONFIG.cameras.USB_HEIGHT,
            fps=CONFIG.cameras.USB_FPS,
            rotate_picam=True,
            # Se a sua PiCam está “de lado”, deixe assim. Se ficar certo, mude pra False.
            picam_rotation=getattr(__import__("cv2"), "ROTATE_90_CLOCKWISE"),
            flip_usb=False,
        )
        self.safety = SafetyController(self)

        # Estado
        self.mode = RobotMode.IDLE
        self.running = False

        # Inversão de motores (ajuste se necessário)
        self.invert_left = 1
        self.invert_right = 1

        print("✅ EVA Robot inicializado")

    def start(self) -> bool:
        print("🚀 Iniciando EVA Robot...")
        self.running = True

        cam_ok = self.camera_manager.start()
        if not cam_ok:
            print("⚠️ Iniciando sem câmera")

        self.arm.move_to_home()
        STATE.update(mode=self.mode)
        return True

    def stop(self):
        print("🛑 Parando EVA Robot...")
        self.running = False
        try:
            self.motor.set_motor_model(0, 0, 0, 0)
        except Exception:
            pass
        try:
            self.camera_manager.stop()
        except Exception:
            pass

    # ------------------ Motores ------------------
    def _apply_inv(self, fl, bl, fr, br):
        return (
            int(fl * self.invert_left),
            int(bl * self.invert_left),
            int(fr * self.invert_right),
            int(br * self.invert_right),
        )

    def move_forward(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(speed, speed, speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)

    def move_backward(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(-speed, -speed, -speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)

    def turn_left(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(-speed, -speed, speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)

    def turn_right(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(speed, speed, -speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)

    def strafe_left(self, speed=1500):
        # mecanum (ajuste se seu chassi for outro)
        fl, bl, fr, br = self._apply_inv(-speed, speed, speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)

    def strafe_right(self, speed=1500):
        fl, bl, fr, br = self._apply_inv(speed, -speed, -speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)

    def stop_motors(self):
        self.motor.set_motor_model(0, 0, 0, 0)
        STATE.set_motors(0, 0, 0, 0)

    # ------------------ Servos ------------------
    def arm_set_angle(self, channel: int, angle: int, smooth=False):
        ok, reason = self.safety.validate_servo_command(channel, angle)
        if not ok:
            return False

        moved = self.arm.set_angle(channel, angle, smooth=smooth)
        if moved:
            STATE.set_servo(channel, int(angle))
        return moved

    def arm_look_left(self, deg=30): return self.arm.look_left(deg)
    def arm_look_right(self, deg=30): return self.arm.look_right(deg)
    def arm_look_up(self, deg=20): return self.arm.look_up(deg)
    def arm_look_down(self, deg=20): return self.arm.look_down(deg)
    def arm_look_center(self): return self.arm.look_center()

    # ------------------ Câmeras ------------------
    def switch_camera(self, camera_type: Optional[CameraType] = None):
        self.camera_manager.switch_camera(camera_type)
        STATE.update(active_camera=self.camera_manager.get_active_camera_type().value)
        time.sleep(0.1)

    def get_camera_frame_encoded(self, quality=70):
        return self.camera_manager.get_frame_encoded(quality)

    # ------------------ Status ------------------
    def set_mode(self, mode: RobotMode):
        self.mode = mode
        STATE.update(mode=mode.value)

    def get_status(self) -> dict:
        return {
            "mode": self.mode.value,
            "camera": self.camera_manager.get_status(),
            "arm": self.arm.get_status(),
            "safety": self.safety.get_status(),
        }
