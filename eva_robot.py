#!/usr/bin/env python3
"""
EVA ROBOT - MAIN CONTROLLER (LIMPO E CONSISTENTE)
- Motores (Ordinary_Car)
- Servos 0..3 (base/ombro/cotovelo/cabeça)
- Câmeras (USB via OpenCV + PiCam via Picamera2)

MUDANÇAS NESTA VERSÃO (integração com a EVA):
- Todos os métodos que movem o robô (linear e drive_vector) agora
  passam por SafetyController.validate_drive_command() ANTES de tocar
  no motor. Antes, só arm_set_angle validava -- movimento linear ia
  direto pro motor sem checar obstáculo/bateria/emergency_stop. Isso
  era um buraco de segurança real: tolerável com humano no gamepad
  reagindo em tempo real, não tolerável com a EVA decidindo sozinha.
- Novo método drive_vector(vx, vy, vz, speed_scale): movimento contínuo
  estilo drone (mesma fórmula mecanum de drone_control_mode.py), pensado
  pra ser o alvo principal de comandos vindos da EVA via
  eva_command_server.py. AINDA NÃO TESTADO EM BANCADA -- a fórmula usa
  _apply_inv() pra manter consistência com os outros métodos desta
  classe, mas drone_control_mode.py monta o mecanum sem passar por
  _apply_inv (calibrou sinal na mão, empiricamente). Antes de confiar
  nisso, testar com o robô de rodas fora do chão, exatamente como você
  já faz com o resto (ver "Empirical validation over theoretical fixes").
- Watchdog agora é ativamente checado (thread própria, iniciada em
  start()). Antes, safety.py criava o Watchdog mas nada chamava
  watchdog.check() periodicamente em nenhum runtime real (só existia em
  safety.py --main-- e no main.py legado, que usa outra estrutura de
  pastas e não é o caminho ativo hoje) -- ou seja, o watchdog nunca
  disparava de verdade em produção.
- NOVO GAP ENCONTRADO E FECHADO: nada no caminho ativo (este arquivo,
  eva_gamepad_server.py, eva_server.py) chamava safety.update_sensor_data()
  com leitura real de sensor. safety.validate_drive_command() lê
  self.last_sensor_data.get('ultrasonic_cm')/'battery_v' -- com
  last_sensor_data sempre vazio ({}), os dois `if ... is not None` da
  validação nunca entravam, e a checagem de obstáculo/bateria SEMPRE
  devolvia "OK" independente da distância real ou da bateria real. Ou
  seja: a validação que acabei de ligar em todo movimento existia, mas
  era inerte -- não tinha dado pra checar. Agora existe uma thread de
  sensores (_sensor_loop, iniciada junto com o watchdog em start()) que
  lê ultrassônico sempre, e bateria via ADC quando ele estiver disponível
  (self.adc é None com aviso no console se ADC() falhar ao inicializar --
  mesma filosofia de degradação graciosa do resto do projeto). Fórmula de
  bateria idêntica à já usada em car.py (`read_adc(2) * divisor do PCB`),
  não inventei conta nova.
- estop()/reset_estop()/heartbeat(): atalhos finos sobre safety.py, pra
  quem fala com o robô de fora (eva_command_server.py) não precisar
  saber que safety existe como atributo interno.
"""

import os
import sys
import threading
import time
from enum import Enum
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from robot_core import Servo, Ordinary_Car, Ultrasonic, ADC
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

        # ADC (bateria) -- opcional, mesma filosofia de degradação
        # graciosa do resto do projeto (câmera, TTS, etc). Sem ele, o
        # sensor loop simplesmente nunca alimenta 'battery_v', e a
        # checagem de bateria em safety.py fica sempre "sem leitura" em
        # vez de "OK" falso -- ver docstring do módulo.
        self.adc: Optional[ADC] = None
        try:
            self.adc = ADC()
        except Exception as e:
            print(f"⚠️ ADC (bateria) não disponível: {e} -- "
                  f"checagem de bateria não vai ter leitura real")

        # Subsistemas
        self.arm = ArmController(self.servo)
        self.camera_manager = CameraManager(
            picam_id=0,
            usb_id=CONFIG.cameras.USB_DEVICE_ID,
            width=CONFIG.cameras.USB_WIDTH,
            height=CONFIG.cameras.USB_HEIGHT,
            fps=CONFIG.cameras.USB_FPS,
            rotate_picam=True,
            # Se a sua PiCam está "de lado", deixe assim. Se ficar certo, mude pra False.
            picam_rotation=getattr(__import__("cv2"), "ROTATE_90_CLOCKWISE"),
            flip_usb=False,
        )
        self.safety = SafetyController(self)

        # Estado
        self.mode = RobotMode.IDLE
        self.running = False
        self._watchdog_thread: Optional[threading.Thread] = None
        self._sensor_thread: Optional[threading.Thread] = None
        # Ver heartbeat()/_watchdog_loop -- watchdog só passa a exigir
        # heartbeat regular DEPOIS que o primeiro chegou de verdade.
        self._recebeu_primeiro_heartbeat = False

        # Inversão de motores (ajuste se necessário)
        self.invert_left = -1
        self.invert_right = -1

        print("✅ EVA Robot inicializado")

    def start(self) -> bool:
        print("🚀 Iniciando EVA Robot...")
        self.running = True

        cam_ok = self.camera_manager.start()
        if not cam_ok:
            print("⚠️ Iniciando sem câmera")

        self.arm.move_to_home()
        STATE.update(mode=self.mode)

        # Watchdog ativo -- sem isso, o Watchdog criado dentro de
        # SafetyController nunca era checado em nenhum runtime real, e
        # portanto nunca disparava emergency stop por abandono/conexão
        # morta. Ver docstring do módulo.
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="eva-robot-watchdog"
        )
        self._watchdog_thread.start()

        # Ver docstring do módulo -- sem isso, validate_drive_command
        # nunca tinha leitura real pra checar.
        self._sensor_thread = threading.Thread(
            target=self._sensor_loop, daemon=True, name="eva-robot-sensors"
        )
        self._sensor_thread.start()

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
        if self.adc is not None:
            try:
                self.adc.close_i2c()
            except Exception:
                pass

    def _watchdog_loop(self):
        """Checa o watchdog a cada 0.5s -- bem abaixo de
        CONFIG.safety.WATCHDOG_TIMEOUT (5s padrão), pra não perder a
        janela. Roda enquanto self.running for True; para sozinho junto
        com stop().

        SÓ CHECA DE VERDADE DEPOIS DO PRIMEIRO HEARTBEAT (achado em uso
        real): Watchdog.__init__ (safety.py) já marca last_heartbeat no
        instante da criação, e nada alimenta o watchdog até um cliente
        de verdade conectar e mandar comando/heartbeat -- que só
        acontece depois que o servidor já está de pé e alguém chamou uma
        ferramenta de robô pela primeira vez (ver robot_tools.py,
        _iniciar_thread_robo). Sem essa checagem, todo start()
        disparava emergency stop sozinho ~5s depois de subir, mesmo com
        tudo funcionando, só porque ninguém tinha conectado ainda --
        "ninguém conectou ainda" e "perdeu conexão no meio do
        movimento" são situações diferentes; só a segunda é o que o
        watchdog existe pra proteger contra."""
        while self.running:
            try:
                if self._recebeu_primeiro_heartbeat:
                    self.safety.watchdog.check()
            except Exception as e:
                print(f"⚠️ erro no watchdog loop: {e}")
            time.sleep(0.5)

    def _sensor_loop(self):
        """Lê ultrassônico sempre, e bateria via ADC quando disponível,
        alimentando safety.update_sensor_data() -- é isso que dá dado
        real pra validate_drive_command() checar. Frequência de
        CONFIG.sensors.SENSOR_READ_INTERVAL (0.1s/10Hz por padrão).
        Erro de leitura pontual (sensor solto, I2C ocupado) não derruba a
        thread -- só pula aquela leitura e tenta de novo no próximo ciclo,
        mesma política do resto do projeto."""
        intervalo = CONFIG.sensors.SENSOR_READ_INTERVAL
        while self.running:
            try:
                leituras = {}

                try:
                    leituras["ultrasonic_cm"] = self.ultrasonic.get_distance()
                except Exception:
                    pass  # sensor solto/timeout momentâneo -- só não atualiza esta leitura

                if self.adc is not None:
                    try:
                        divisor = 3 if self.adc.pcb_version == 1 else 2
                        leituras["battery_v"] = round(self.adc.read_adc(2) * divisor, 2)
                    except Exception:
                        pass

                if leituras:
                    self.safety.update_sensor_data(leituras)

            except Exception as e:
                print(f"⚠️ erro no sensor loop: {e}")
            time.sleep(intervalo)

    # ------------------ Segurança (atalhos) ------------------
    def estop(self, motivo: str = "comando remoto"):
        """Aciona parada de emergência. Sempre seguro chamar, de
        qualquer fonte -- nunca deveria ser bloqueado por arbitragem."""
        self.safety.trigger_emergency_stop(motivo)

    def reset_estop(self) -> bool:
        """Tenta resetar o emergency stop. Devolve False se ainda não
        for seguro (ver safety._check_safe_to_reset)."""
        return self.safety.reset_emergency_stop()

    def heartbeat(self):
        """Alimenta o watchdog. Chamar regularmente enquanto alguém
        (humano ou EVA) estiver de fato supervisionando o robô.

        Também marca que o primeiro heartbeat de verdade já chegou --
        ver _watchdog_loop: antes do primeiro heartbeat, o watchdog não
        pune "ninguém conectou ainda" como se fosse "perdeu conexão no
        meio do movimento". São situações diferentes; só a segunda é o
        que o watchdog existe pra proteger contra."""
        self.safety.heartbeat()
        self._recebeu_primeiro_heartbeat = True

    # ------------------ Motores (discretos) ------------------
    def _apply_inv(self, fl, bl, fr, br):
        return (
            int(fl * self.invert_left),
            int(bl * self.invert_left),
            int(fr * self.invert_right),
            int(br * self.invert_right),
        )

    def move_forward(self, speed=1500) -> bool:
        ok, motivo = self.safety.validate_drive_command(vx=1.0, vy=0.0, vz=0.0)
        if not ok:
            print(f"⛔ move_forward bloqueado pela segurança: {motivo}")
            return False
        fl, bl, fr, br = self._apply_inv(speed, speed, speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True

    def move_backward(self, speed=1500) -> bool:
        ok, motivo = self.safety.validate_drive_command(vx=-1.0, vy=0.0, vz=0.0)
        if not ok:
            print(f"⛔ move_backward bloqueado pela segurança: {motivo}")
            return False
        fl, bl, fr, br = self._apply_inv(-speed, -speed, -speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True

    def turn_left(self, speed=1500) -> bool:
        ok, motivo = self.safety.validate_drive_command(vx=0.0, vy=0.0, vz=-1.0)
        if not ok:
            print(f"⛔ turn_left bloqueado pela segurança: {motivo}")
            return False
        fl, bl, fr, br = self._apply_inv(-speed, -speed, speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True

    def turn_right(self, speed=1500) -> bool:
        ok, motivo = self.safety.validate_drive_command(vx=0.0, vy=0.0, vz=1.0)
        if not ok:
            print(f"⛔ turn_right bloqueado pela segurança: {motivo}")
            return False
        fl, bl, fr, br = self._apply_inv(speed, speed, -speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True

    def strafe_left(self, speed=1500) -> bool:
        ok, motivo = self.safety.validate_drive_command(vx=0.0, vy=-1.0, vz=0.0)
        if not ok:
            print(f"⛔ strafe_left bloqueado pela segurança: {motivo}")
            return False
        # mecanum (ajuste se seu chassi for outro)
        fl, bl, fr, br = self._apply_inv(-speed, speed, speed, -speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True

    def strafe_right(self, speed=1500) -> bool:
        ok, motivo = self.safety.validate_drive_command(vx=0.0, vy=1.0, vz=0.0)
        if not ok:
            print(f"⛔ strafe_right bloqueado pela segurança: {motivo}")
            return False
        fl, bl, fr, br = self._apply_inv(speed, -speed, -speed, speed)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True

    def stop_motors(self):
        self.motor.set_motor_model(0, 0, 0, 0)
        STATE.set_motors(0, 0, 0, 0)

    # ------------------ Motores (vetor contínuo -- alvo da EVA) ------------------
    def drive_vector(self, vx: float, vy: float, vz: float,
                      speed_scale: float = 0.6) -> "tuple[bool, str]":
        """
        Movimento contínuo estilo drone/FPV: vx=frente(+)/trás(-),
        vy=lateral direita(+)/esquerda(-), vz=giro horário(+)/anti(-),
        todos de -1.0 a 1.0. speed_scale (0..1) limita a autoridade
        máxima -- pensado pra quem chama de fora (ex:
        eva_command_server.py) poder aplicar um teto mais conservador
        pra comandos vindos da EVA do que de controle manual.

        SEMPRE valida antes de tocar no motor. Se a validação falhar,
        para o robô (não deixa em estado indefinido) e devolve o motivo.
        """
        vx = max(-1.0, min(1.0, float(vx)))
        vy = max(-1.0, min(1.0, float(vy)))
        vz = max(-1.0, min(1.0, float(vz)))
        speed_scale = max(0.0, min(1.0, float(speed_scale)))

        ok, motivo = self.safety.validate_drive_command(vx, vy, vz)
        if not ok:
            self.stop_motors()
            return False, motivo

        base = 1500
        scale = int(400 * speed_scale)

        fl = int(base + scale * (vx - vy - vz))
        bl = int(base + scale * (vx + vy - vz))
        fr = int(base + scale * (vx + vy + vz))
        br = int(base + scale * (vx - vy + vz))

        fl, bl, fr, br = self._apply_inv(fl, bl, fr, br)
        self.motor.set_motor_model(fl, bl, fr, br)
        STATE.set_motors(fl, bl, fr, br)
        return True, "ok"

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
