#!/usr/bin/env python3
"""
EVA ROBOT - ARM/HEAD CONTROLLER
Controle do braço: 4 servos (0..3)
0=Base(Yaw), 1=Ombro(Pitch), 2=Cotovelo, 3=Cabeça (PiCam mount)
"""

import time
from typing import Dict, Optional, Tuple


class ArmController:
    def __init__(self, servo_controller):
        self.servo = servo_controller

        # Ângulos atuais (somente 0..3)
        self.current_angles: Dict[int, int] = {
            0: 90,  # Base (Yaw)
            1: 90,  # Ombro (Pitch)
            2: 90,  # Cotovelo
            3: 90,  # Cabeça
        }

        # Limites físicos REAIS -- devem ser idênticos a
        # safety.SafetyController.validate_servo_command.physical_limits.
        # As duas cópias existem porque safety.py valida o caminho da EVA
        # e este dict é a última linha de defesa do caminho manual/gamepad
        # (drone_control_mode.py chama arm.set_angle() direto, sem passar
        # por safety nenhuma vez) -- mas o VALOR tem que ser o mesmo dos
        # dois lados. Se recalibrar um, recalibra o outro.
        self.limits: Dict[int, Tuple[int, int]] = {
            0: (0, 90),    # yaw / base -- confirmado, NÃO vai até 180
            1: (40, 110),  # pitch / ombro -- confirmado fisicamente
            2: (90, 180),  # cotovelo
            3: (0, 117),   # cabeça -- baseline conservador; safety.py relaxa
                           # até 180 quando pitch<=50, este clamp não (ver nota)
        }

        self.smooth_step = 2

        print("🦾 ArmController (0..3) inicializado")

    def _limite_canal(self, channel: int) -> Tuple[int, int]:
        """safety.validate_servo_command (regra 2) libera a cabeça até
        180° quando o pitch está <= 50°. Este clamp não sabia disso e
        cortava calado em 117 -- safety APROVAVA 150°, set_angle
        devolvia True, o servidor respondia ok, e do lado da EVA parecia
        que a cabeça tinha ido pra onde ela pediu."""
        lo, hi = self.limits[channel]
        if channel == 3 and self.current_angles.get(1, 90) <= 50:
            hi = 180
        return lo, hi

    def move_to_home(self):
        for ch in (0, 1, 2, 3):
            self.set_angle(ch, 90, smooth=True)
        time.sleep(0.2)

    def set_angle(self, channel: int, angle: int, smooth: bool = False) -> bool:
        if channel not in self.limits:
            print(f"⚠️ Canal inválido: {channel}")
            return False

        lo, hi = self._limite_canal(channel)
        angle = max(lo, min(hi, int(angle)))

        current = self.current_angles.get(channel, 90)
        if abs(angle - current) < 2:
            return True

        if smooth:
            return self._move_smooth(channel, angle)
        return self._move_direct(channel, angle)

    def _move_direct(self, channel: int, angle: int) -> bool:
        try:
            # robot_core.Servo espera channel como string ('0'..)
            self.servo.set_servo_pwm(str(channel), angle)
            self.current_angles[channel] = angle
            return True
        except Exception as e:
            print(f"❌ Erro servo {channel}: {e}")
            return False

    def _move_smooth(self, channel: int, target: int) -> bool:
        cur = self.current_angles.get(channel, 90)
        step = self.smooth_step if target > cur else -self.smooth_step

        while abs(target - cur) > abs(step):
            cur += step
            if not self._move_direct(channel, cur):
                return False
            time.sleep(0.02)

        return self._move_direct(channel, target)

    # Helpers “humanos”
    def look_left(self, degrees: int = 30):
        return self.set_angle(0, 90 - degrees)

    def look_right(self, degrees: int = 30):
        return self.set_angle(0, 90 + degrees)

    def look_up(self, degrees: int = 20):
        return self.set_angle(1, self.current_angles[1] - degrees)

    def look_down(self, degrees: int = 20):
        return self.set_angle(1, self.current_angles[1] + degrees)

    def look_center(self):
        self.set_angle(0, 90)
        self.set_angle(1, 90)

    def get_status(self) -> dict:
        return {
            "angles": dict(self.current_angles),
            "base": self.current_angles[0],
            "ombro": self.current_angles[1],
            "cotovelo": self.current_angles[2],
            "cabeca": self.current_angles[3],
        }
