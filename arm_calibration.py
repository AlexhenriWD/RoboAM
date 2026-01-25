#!/usr/bin/env python3
"""
ArmController (EVA Head) - Controlador do braço como "cabeça"
✅ Remove travas falsas ("já está na posição") via force=True
✅ Movimento suave incremental (move_smooth)
✅ Suporte opcional para desabilitar garra (camera head)
✅ Sequências com modo smooth
"""

import time
from typing import Dict, Optional, Tuple, List
from servo import Servo


class ArmController:
    """Controlador seguro do braço robótico (adaptado para cabeça/câmera)."""

    def __init__(
        self,
        enable_gripper: bool = False,   # ✅ por padrão: garra desativada (virar cabeça)
        min_delay: float = 0.15,        # menor que 0.3 para responsividade (ajuste se aquecer)
        tolerance_deg: int = 2
    ):
        self.servo = Servo()
        self.enable_gripper = enable_gripper
        self.min_delay = float(min_delay)
        self.tolerance_deg = int(tolerance_deg)

        # ====== LIMITES (AJUSTE AQUI) ======
        # Você falou que ombro/cotovelo agora podem ir até 180.
        # Mantive min seguros, mas soltei max pra 180 conforme seu plano.
        self.servos: Dict[int, Dict] = {
            0: {  # Base (Yaw)
                "name": "Base",
                "min": 0,
                "max": 180,
                "home": 90,
                "current": 90,
                "last_sent": None,
            },
            1: {  # Ombro (Pitch / altura)
                "name": "Ombro",
                "min": 0,
                "max": 180,
                "home": 90,
                "current": 90,
                "last_sent": None,
            },
            2: {  # Cotovelo
                "name": "Cotovelo",
                "min": 0,
                "max": 180,
                "home": 90,
                "current": 90,
                "last_sent": None,
            },
            3: {  # Cabeça/Câmera extra (se existir fisicamente)
                "name": "Cabeça",
                "min": 0,
                "max": 180,
                "home": 90,
                "current": 90,
                "last_sent": None,
            },
        }

        # Garra (canal 4) opcional
        if self.enable_gripper:
            self.servos[4] = {
                "name": "Garra",
                "min": 40,
                "max": 100,
                "home": 70,
                "current": 70,
                "last_sent": None,
            }

        self.last_move_time = {ch: 0.0 for ch in self.servos.keys()}

        # Inicializar em home (sem spam)
        self.home_position(silent=True, force=True)

    # -------------------------
    # Utilitários
    # -------------------------

    def _clamp(self, channel: int, angle: int) -> int:
        s = self.servos[channel]
        return max(s["min"], min(s["max"], int(angle)))

    def _wait_min_delay(self, channel: int):
        elapsed = time.time() - self.last_move_time.get(channel, 0.0)
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)

    def _validate_move(self, channel: int, angle: int, force: bool) -> Tuple[bool, str, int]:
        """Valida se o movimento é seguro. Retorna (ok, msg, clamped_angle)."""
        if channel not in self.servos:
            return False, f"Canal {channel} inválido", angle

        angle = self._clamp(channel, angle)
        servo = self.servos[channel]

        # ✅ NÃO travar por 'já está na posição' quando force=True
        if not force:
            if abs(servo["current"] - angle) < self.tolerance_deg:
                return False, f"{servo['name']}: já está na posição {angle}°", angle

        return True, "OK", angle

    # -------------------------
    # Movimento básico
    # -------------------------

    def move_servo(
        self,
        channel: int,
        angle: int,
        delay: Optional[float] = None,
        *,
        force: bool = False,
        update_virtual: bool = True
    ) -> Dict:
        """
        Move um servo.
        - force=True: reenvia mesmo se 'current' estiver igual (corrige 'travado logicamente')
        - update_virtual=False: útil se você quiser testar sem assumir que mexeu
        """
        ok, msg, angle = self._validate_move(channel, angle, force=force)
        if not ok:
            return {
                "success": False,
                "channel": channel,
                "error": msg,
                "current_angle": self.servos[channel]["current"],
                "target_angle": angle
            }

        try:
            self._wait_min_delay(channel)

            self.servo.set_servo_pwm(str(channel), int(angle))
            self.last_move_time[channel] = time.time()
            self.servos[channel]["last_sent"] = int(angle)

            if update_virtual:
                self.servos[channel]["current"] = int(angle)

            if delay and delay > 0:
                time.sleep(delay)

            return {
                "success": True,
                "channel": channel,
                "angle": int(angle),
                "servo_name": self.servos[channel]["name"],
            }

        except Exception as e:
            return {
                "success": False,
                "channel": channel,
                "error": str(e),
                "target_angle": int(angle)
            }

    def move_smooth(
        self,
        channel: int,
        target: int,
        *,
        step: int = 2,
        step_delay: float = 0.03,
        force: bool = True
    ) -> bool:
        """
        Movimento suave incremental até o alvo.
        Ideal para "ângulo de captura" e transições naturais.
        """
        if channel not in self.servos:
            print(f"  ✗ Canal {channel} inválido")
            return False

        target = self._clamp(channel, target)
        current = int(self.servos[channel]["current"])

        if current == target and not force:
            return True

        direction = 1 if target > current else -1
        step = max(1, int(step))

        angle = current
        while angle != target:
            next_angle = angle + direction * step
            if (direction == 1 and next_angle > target) or (direction == -1 and next_angle < target):
                next_angle = target

            r = self.move_servo(channel, next_angle, delay=None, force=force)
            if not r["success"]:
                print(f"  ✗ Erro: {r.get('error')}")
                return False

            time.sleep(step_delay)
            angle = next_angle

        return True

    # -------------------------
    # Posições e comportamentos
    # -------------------------

    def get_current_position(self) -> Dict:
        return {
            ch: {
                "name": info["name"],
                "angle": info["current"],
                "min": info["min"],
                "max": info["max"],
                "last_sent": info.get("last_sent"),
            }
            for ch, info in self.servos.items()
        }

    def home_position(self, silent: bool = False, force: bool = False) -> bool:
        if not silent:
            print("\n🏠 Indo para HOME...")

        ok = True
        for ch in sorted(self.servos.keys()):
            home = int(self.servos[ch]["home"])
            r = self.move_servo(ch, home, delay=0.2, force=force)
            if not silent:
                if r["success"]:
                    print(f"  ✓ {r['servo_name']}: {home}°")
                else:
                    print(f"  ✗ {r.get('error')}")
                    ok = False

        if not silent and ok:
            print("✓ HOME concluído!\n")
        return ok

    def look_forward(self, smooth: bool = True) -> bool:
        """Cabeça olhando para frente."""
        print("👉 Olhando para frente...")

        # Ajuste fino conforme sua mecânica real:
        targets = [
            (0, 90),   # yaw
            (1, 110),  # pitch/ombro
            (2, 90),   # cotovelo
            (3, 90),   # cabeça/câmera
        ]
        return self._execute_sequence(targets, smooth=smooth)

    def look_down(self, smooth: bool = True) -> bool:
        """Pose para 'captura' / olhar mais para baixo (ângulo de captura)."""
        print("🔎 Ajustando ângulo de captura...")
        targets = [
            (1, 140),
            (2, 120),
        ]
        return self._execute_sequence(targets, smooth=smooth)

    def scan_left_right(self, times: int = 2, amplitude: int = 25) -> bool:
        """Varredura simples: yaw esquerda/direita."""
        print("👀 Varredura...")
        base = int(self.servos[0]["current"])
        left = self._clamp(0, base - abs(amplitude))
        right = self._clamp(0, base + abs(amplitude))

        for _ in range(max(1, int(times))):
            if not self.move_smooth(0, left, step=3, step_delay=0.02):
                return False
            if not self.move_smooth(0, right, step=3, step_delay=0.02):
                return False

        return self.move_smooth(0, base, step=3, step_delay=0.02)

    def wave_gesture(self) -> bool:
        """
        Aceno sem garra: usa yaw (servo 0) como 'cumprimento'.
        """
        print("👋 Acenando... (sem garra, sem crimes mecânicos)")
        base = int(self.servos[0]["current"])

        # Preparar pose "social"
        self._execute_sequence([(1, 115), (2, 90)], smooth=True)

        for _ in range(3):
            if not self.move_smooth(0, self._clamp(0, base - 18), step=3, step_delay=0.02):
                return False
            if not self.move_smooth(0, self._clamp(0, base + 18), step=3, step_delay=0.02):
                return False

        self.move_smooth(0, base, step=3, step_delay=0.02)
        print("✓ Aceno concluído!")
        return True

    # -------------------------
    # Execução de sequências
    # -------------------------

    def _execute_sequence(
        self,
        moves: List[tuple],
        *,
        delay: float = 0.12,
        smooth: bool = False
    ) -> bool:
        for ch, angle in moves:
            if smooth:
                ok = self.move_smooth(ch, angle, step=2, step_delay=0.02, force=True)
                if not ok:
                    return False
            else:
                r = self.move_servo(ch, angle, delay=delay, force=True)
                if not r["success"]:
                    print(f"  ✗ Erro: {r.get('error')}")
                    return False

        print("✓ Sequência concluída!")
        return True

    def cleanup(self):
        print("\n🔧 Finalizando braço...")
        # tenta ir pra home só se estiver bem longe (evita ficar “brigando”)
        for ch, info in self.servos.items():
            if abs(int(info["current"]) - int(info["home"])) > 5:
                self.move_servo(ch, int(info["home"]), delay=0.1, force=True)
        print("✓ Braço finalizado com segurança\n")


if __name__ == "__main__":
    arm = ArmController(enable_gripper=False)

    try:
        print("\n" + "=" * 60)
        print("🦾 TESTE DO CONTROLADOR (EVA HEAD)")
        print("=" * 60)

        while True:
            print("\nCOMANDOS:")
            print("  1 - HOME")
            print("  2 - Look Forward")
            print("  3 - Look Down (captura)")
            print("  4 - Scan")
            print("  5 - Wave")
            print("  0 - Sair")

            op = input("Escolha: ").strip()

            if op == "1":
                arm.home_position()
            elif op == "2":
                arm.look_forward(smooth=True)
            elif op == "3":
                arm.look_down(smooth=True)
            elif op == "4":
                arm.scan_left_right(times=2)
            elif op == "5":
                arm.wave_gesture()
            elif op == "0":
                break
            else:
                print("Opção inválida.")

    except KeyboardInterrupt:
        pass
    finally:
        arm.cleanup()
