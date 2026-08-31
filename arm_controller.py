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
            2: (90, 170),  # cotovelo -- 170, não 180: 165/170 foram
                           # verificados fisicamente com a base lateral;
                           # acima disso não há observação nenhuma. E a
                           # combinação cotovelo alto + base de frente
                           # estica o flat CSI (safety, regra do cabo) --
                           # esse limite é condicional e vive lá, não aqui.
            3: (0, 117),   # cabeça -- baseline conservador; safety.py relaxa
                           # até 180 quando pitch<=50, este clamp não (ver nota)
        }

        self.smooth_step = 2

        # Por que o último set_angle() não moveu, quando não moveu.
        # Lido por eva_robot.arm_set_angle e propagado até a EVA: "ok"
        # idêntico pra "movi" e pra "já estava lá" fazia quatro comandos
        # seguidos parecerem bem-sucedidos sem um grau de movimento.
        self.ultimo_motivo = "ok"

        print("🦾 ArmController (0..3) inicializado")

    def move_to_home(self):
        for ch in (0, 1, 2, 3):
            self.set_angle(ch, 90, smooth=True)
        time.sleep(0.2)

    def _limite_canal(self, channel: int) -> Tuple[int, int]:
        """Limite efetivo do canal, já com as exceções condicionais.

        safety.validate_servo_command (regra 2) libera a cabeça até 180°
        quando o pitch está <= 50° -- a interferência mecânica que impõe
        o teto de 117 some quando o braço está baixo. Este clamp não
        sabia disso e cortava calado em 117: safety APROVAVA 150°,
        set_angle devolvia True, o servidor respondia "ok", e do lado da
        EVA parecia que a cabeça tinha ido pra onde ela pediu.

        As duas cópias de limite continuam existindo de propósito (ver
        self.limits acima) -- o que muda é que agora elas concordam."""
        lo, hi = self.limits[channel]
        if channel == 3 and self.current_angles.get(1, 90) <= 50:
            hi = 180
        return lo, hi

    def set_angle(self, channel: int, angle: int, smooth: bool = False) -> bool:
        if channel not in self.limits:
            print(f"⚠️ Canal inválido: {channel}")
            self.ultimo_motivo = "canal inválido"
            return False

        lo, hi = self._limite_canal(channel)
        pedido = int(angle)
        angle = max(lo, min(hi, pedido))
        if angle != pedido:
            self.ultimo_motivo = f"pedido {pedido}° cortado para {angle}° (limite {lo}-{hi})"
        else:
            self.ultimo_motivo = "ok"

        current = self.current_angles.get(channel, 90)
        if abs(angle - current) < 2:
            # True porque não há falha nenhuma -- só não há nada a fazer.
            self.ultimo_motivo = f"já estava em {current}°"
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

    # APAGADOS: look_left/look_right/look_up/look_down.
    #
    # Os quatro mentiam sobre o que faziam, e nenhum estava no caminho da
    # EVA (que passa por safety + eva_robot.arm_set_angle):
    #
    #   look_right(30) calculava 90+30=120, era clampado pelo limite
    #                  (0,90) e não movia UM GRAU. Código morto que
    #                  sugeria um curso que não existe.
    #   look_up/down   invertidos. Confirmado por foto na calibração:
    #                  pitch MAIOR aponta mais alto e mais à frente
    #                  (cotovelo 120 com pitch 110 olha pra frente; com
    #                  pitch 70 olha pra trás e pra baixo). look_up fazia
    #                  current - graus, ou seja, olhava pra baixo.
    #
    # Helper de conveniência com nome mentiroso é armadilha esperando --
    # melhor não existir que existir errado.

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