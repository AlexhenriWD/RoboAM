#!/usr/bin/env python3
"""
EVA ROBOT - COMMAND SERVER
Substitui eva_server.py como o ponto de entrada de rede pra comandos.

O QUE MUDA EM RELAÇÃO A eva_server.py:
- Protocolo passa de string CSV ("CMD_FORWARD,1500") para JSON, um
  objeto por linha, no formato de robot_protocol.CommandEnvelope (que já
  existia no projeto pronto pra isso -- source/priority/seq/ttl_ms/cmd/
  params -- mas não estava ligado em lugar nenhum).
- Todo comando de movimento ("drive"/"head") passa por arbitragem por
  fonte: se um comando "manual" chegou nos últimos MANUAL_OVERRIDE_WINDOW_S
  segundos, qualquer comando "eva" de movimento é recusado (não hackeado
  como prioridade numérica -- humano sempre corta EVA, sem negociação).
- "stop" e "estop" NUNCA são bloqueados por arbitragem, de nenhuma fonte
  -- parar tem que sempre ser possível.
- ttl_ms é respeitado de verdade (CommandEnvelope.is_expired) -- medido
  inteiramente pelo relógio do SERVIDOR (do recv() na rede até o
  processamento), nunca comparando com o relógio de quem mandou. Isso
  não é a implementação original: a primeira versão comparava com
  sent_ts do CLIENTE, e em uso real (PC da EVA + Raspberry Pi, relógios
  não sincronizados no nível de milissegundos) isso fazia TODO comando
  expirar instantaneamente, mesmo com a rede respondendo na hora -- ver
  histórico em robot_protocol.CommandEnvelope.is_expired.
- Todo comando de movimento aceito alimenta o watchdog
  (safety.heartbeat()) -- mas não é só isso que alimenta: ver
  eva_robot.py e robot_tools.py (lado EVA) para o heartbeat contínuo
  independente de movimento.
- speed_scale de comandos "drive" vindos de source="eva" é limitado a
  EVA_ROBOT_MAX_SPEED_SCALE (0.6 por padrão) mesmo que o cliente peça
  mais -- teto de autoridade conservador por padrão, ajustável.

LIMITAÇÃO CONHECIDA (não resolvida nesta rodada): o transporte
(server.py/tcp_server.py) lê até 1024 bytes por recv() e trata como UMA
mensagem -- não tem framing de verdade para múltiplas mensagens no mesmo
pacote TCP nem mensagens maiores que isso. Pro uso atual (um comando por
send(), como já era com o protocolo CSV) isso é suficiente, mas não é
robusto contra fragmentação/coalescência de pacotes sob carga. Se isso
virar problema real (comandos perdidos ou concatenados), o próximo passo
é dar a tcp_server.py um framing de verdade (delimitador \\n com buffer
por conexão), não inventar outro workaround aqui.

CONFLITO CONHECIDO (decisão pendente, não resolvida nesta rodada):
eva_gamepad_server.py instancia seu PRÓPRIO EVARobot (seu próprio
SafetyController, seu próprio acesso a I2C/PWM). Rodar este servidor E
o eva_gamepad_server.py ao mesmo tempo significa DOIS processos escrevendo
no mesmo hardware sem coordenação nenhuma entre si -- isso é perigoso,
não só logicamente incorreto. Por ora: rode só UM dos dois de cada vez.
Unificar os dois numa arbitragem de verdade (gamepad como source="manual"
dentro deste mesmo processo) é o passo natural seguinte.
"""

import json
import os
import struct
import sys
import threading
import time
from typing import Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server import Server
from eva_robot import EVARobot, RobotMode
from camera_manager import CameraType
from robot_protocol import CommandEnvelope, parse_command, as_float


MANUAL_OVERRIDE_WINDOW_S = float(os.environ.get("EVA_ROBOT_MANUAL_WINDOW_S", "2.0"))
EVA_MAX_SPEED_SCALE = float(os.environ.get("EVA_ROBOT_MAX_SPEED_SCALE", "0.6"))
DEFAULT_DRIVE_TTL_MS = int(os.environ.get("EVA_ROBOT_DEFAULT_DRIVE_TTL_MS", "500"))
# Duração do "pulso" de movimento da EVA antes de parar sozinho -- ver
# _agendar_autostop_eva(). Chute conservador de partida; ajuste depois de
# observar em uso real (mesma filosofia do resto do projeto).
EVA_DRIVE_AUTOSTOP_S = float(os.environ.get("EVA_ROBOT_DRIVE_AUTOSTOP_S", "1.0"))


class EVACommandServer:
    """Servidor de comando + telemetria de vídeo. Dono único do
    EVARobot -- todo comando de movimento passa por aqui."""

    def __init__(self):
        self.server = Server()
        self.robot: Optional[EVARobot] = None

        self.is_running = False
        self.stop_event = threading.Event()

        self.command_thread: Optional[threading.Thread] = None
        self.video_thread: Optional[threading.Thread] = None

        # Arbitragem: timestamp do último comando de MOVIMENTO com
        # source="manual" aceito. Comando "eva" de movimento é recusado
        # se estivermos dentro da janela desde esse timestamp.
        self._last_manual_ts = 0.0

        # Auto-stop pra comandos "drive" vindos da EVA -- ver
        # _agendar_autostop_eva() pra motivo completo. Reagendado a cada
        # novo comando drive da EVA; cancelado se ela mandar stop/estop.
        self._eva_drive_autostop_timer: Optional[threading.Timer] = None

        print("✅ EVACommandServer inicializado")

    # ========================================
    # START / STOP
    # ========================================

    def start(self, command_port: int = 5000, video_port: int = 8000) -> bool:
        print(f"\n🚀 Iniciando EVA Command Server nas portas {command_port}/{video_port}...\n")

        self.robot = EVARobot()
        if not self.robot.start():
            print("⚠️  Robô iniciado em modo limitado")

        try:
            self.server.start_tcp_servers(
                command_port=command_port,
                video_port=video_port,
                # max_clients=6 no comando -- dá espaço confortável pra
                # várias ferramentas ao mesmo tempo: EVA (robot_tools.py,
                # 1 conexão), controle_manual_robo.py (1 conexão
                # compartilhada entre teclado/heartbeat/monitor),
                # ver_camera_robo.py (1 conexão pra consultar estado),
                # testar_robo.py ocasional, com folga. Achado em uso
                # real: com max_clients=2 (valor original), só o
                # controle_manual_robo.py sozinho já enchia as duas vagas
                # (principal + heartbeat, antes de virarem uma conexão
                # compartilhada -- ver controle_manual_robo.py), e
                # qualquer ferramenta extra tentando conectar entrava em
                # loop de "Rejected (max clients)" pra sempre.
                max_clients=6,
                listen_count=6,
            )
            # O watchdog precisa saber se ainda há alguém conectado --
            # sem isso ele dispara estop de escopo total a cada 5s com o
            # robô ocioso, e o reset pelo dashboard não sobrevive nem até
            # o próximo comando. Ver EVARobot._watchdog_loop.
            self.robot.ha_cliente_conectado = self.server.is_command_server_connected

            print(f"✅ Servidor TCP iniciado em {self.server.ip_address}:{command_port} "
                  f"(vídeo: {video_port})")
        except Exception as e:
            print(f"❌ Erro ao iniciar servidor TCP: {e}")
            return False

        self.is_running = True
        self.stop_event.clear()

        self.command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self.command_thread.start()

        self.video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self.video_thread.start()

        print("✅ EVA Command Server pronto\n")
        return True

    def stop(self):
        print("\n🛑 Parando EVA Command Server...")
        self.is_running = False
        self.stop_event.set()

        if self.command_thread:
            self.command_thread.join(timeout=2.0)
        if self.video_thread:
            self.video_thread.join(timeout=2.0)

        self.server.stop_tcp_servers()

        if self.robot:
            self.robot.stop()

        print("✅ EVA Command Server finalizado")

    # ========================================
    # LOOPS
    # ========================================

    def _command_loop(self):
        fila = self.server.read_data_from_command_server()
        while not self.stop_event.is_set() and self.is_running:
            try:
                if fila.qsize() == 0:
                    time.sleep(0.01)
                    continue

                # 3 elementos: tcp_server.py agora carimba o horário de
                # chegada de verdade (na rede, no recv()), não só quando
                # este loop processa -- ver robot_protocol.is_expired.
                client_address, mensagem, chegou_em = fila.get()
                resposta = self._processar_mensagem(mensagem, chegou_em)
                self.server.send_data_to_command_client(
                    json.dumps(resposta, ensure_ascii=False) + "\n",
                    client_address,
                )
            except Exception as e:
                print(f"⚠️ Erro no command loop: {e}")
                time.sleep(0.05)

    def _video_loop(self):
        falhas_consecutivas = 0
        ultimo_log_falha = 0.0
        while not self.stop_event.is_set() and self.is_running:
            try:
                if not self.server.is_video_server_connected():
                    falhas_consecutivas = 0
                    time.sleep(0.1)
                    continue

                if self.robot.camera_manager.switching:
                    time.sleep(0.02)
                    continue

                frame_data = self.robot.get_camera_frame_encoded(quality=70)
                if frame_data is None or len(frame_data) < 100:
                    falhas_consecutivas += 1
                    agora = time.time()
                    # Log com throttle (a cada 5s, não a cada tentativa) --
                    # achado em uso real: sem isso, quando a câmera parava
                    # de produzir frame por qualquer motivo, este loop
                    # ficava mudo pra sempre (só sleep+continue) -- o
                    # único sintoma visível era do OUTRO lado (cliente de
                    # vídeo reconectando sem parar), nunca a causa.
                    if agora - ultimo_log_falha > 5.0:
                        cm = self.robot.camera_manager
                        print(f"⚠️  vídeo sem frame há {falhas_consecutivas} tentativas -- "
                              f"active={cm.active_camera_type.value} switching={cm.switching} "
                              f"cap_aberto={cm.cap is not None} picam2_iniciado={cm.picam2_started}")
                        ultimo_log_falha = agora
                    time.sleep(0.02)
                    continue

                falhas_consecutivas = 0
                packet = struct.pack('<L', len(frame_data)) + frame_data
                self.server.send_data_to_video_client(packet)
                time.sleep(1 / 15)

            except (BrokenPipeError, ConnectionResetError, OSError):
                time.sleep(0.2)
            except Exception as e:
                print(f"⚠️ Erro no vídeo: {e}")
                time.sleep(0.1)

    # ========================================
    # PROCESSAMENTO DE COMANDO
    # ========================================

    def _processar_mensagem(self, bruto: str, chegou_em: float) -> dict:
        bruto = (bruto or "").strip()
        if not bruto:
            return {"ok": False, "erro": "mensagem_vazia"}

        try:
            msg = json.loads(bruto)
        except json.JSONDecodeError:
            return {"ok": False, "erro": "json_invalido", "detalhe": bruto[:150]}

        env: CommandEnvelope = parse_command(msg)
        recebido_em = chegou_em

        if env.is_expired(recebido_em):
            return {"ok": False, "erro": "comando_expirado", "seq": env.seq}

        if env.source == "manual" and env.cmd in ("drive", "head", "stop"):
            self._last_manual_ts = recebido_em

        # stop/estop nunca são bloqueados por arbitragem -- de qualquer
        # fonte, sempre passam.
        if env.cmd == "estop":
            motivo = (env.params or {}).get("motivo", f"estop remoto (source={env.source})")
            self._cancelar_autostop_eva()
            self.robot.estop(motivo)
            return {"ok": True, "cmd": "estop", "seq": env.seq}

        if env.cmd == "reset_estop":
            ok = self.robot.reset_estop()
            motivo = None if ok else "ainda não é seguro resetar (ver bateria/obstáculo)"
            return {"ok": ok, "cmd": "reset_estop", "seq": env.seq,
                    "erro": motivo, "detalhe": motivo}

        if env.cmd == "stop":
            self._cancelar_autostop_eva()
            self.robot.stop_motors()
            return {"ok": True, "cmd": "stop", "seq": env.seq}

        if env.cmd == "heartbeat":
            self.robot.heartbeat()
            return {"ok": True, "cmd": "heartbeat", "seq": env.seq}

        if env.cmd == "get_state":
            return {"ok": True, "cmd": "get_state", "seq": env.seq,
                    "estado": self.robot.get_status()}

        if env.cmd == "camera_switch":
            # Não é comando de movimento -- não passa pela arbitragem
            # manual/eva (trocar câmera não move nada fisicamente, não
            # há razão pra bloquear mesmo com controle manual ativo ou
            # emergency stop em curso -- pode ser útil olhar em volta
            # justamente durante um estop).
            p = env.params or {}
            tipo = (p.get("tipo") or "").strip().lower()
            camera_type = None  # None = alterna (ver EVARobot.switch_camera)
            if tipo == "usb":
                camera_type = CameraType.USB
            elif tipo == "picam":
                camera_type = CameraType.PICAM
            elif tipo:
                return {"ok": False, "erro": "tipo_invalido", "cmd": "camera_switch",
                        "seq": env.seq, "detalhe": "use 'usb', 'picam', ou omita pra alternar"}
            try:
                self.robot.switch_camera(camera_type)
                ativa = self.robot.camera_manager.get_active_camera_type().value
                return {"ok": True, "cmd": "camera_switch", "seq": env.seq, "camera_ativa": ativa}
            except Exception as e:
                return {"ok": False, "erro": "falha_troca_camera", "cmd": "camera_switch",
                        "seq": env.seq, "detalhe": str(e)[:150]}

        # a partir daqui: comandos que MOVEM -- sujeitos a arbitragem
        if env.source == "eva" and (recebido_em - self._last_manual_ts) < MANUAL_OVERRIDE_WINDOW_S:
            return {"ok": False, "erro": "manual_ativo", "seq": env.seq,
                    "detalhe": f"controle manual ativo há menos de {MANUAL_OVERRIDE_WINDOW_S:.0f}s"}

        if env.cmd == "drive":
            return self._cmd_drive(env, recebido_em)

        if env.cmd == "head":
            return self._cmd_head(env)

        return {"ok": False, "erro": "comando_desconhecido", "cmd": env.cmd, "seq": env.seq}

    def _agendar_autostop_eva(self):
        """Movimento vindo da EVA para sozinho depois de EVA_DRIVE_AUTOSTOP_S
        segundos, a menos que outro comando 'drive' da EVA chegue antes e
        reagende. Ver docstring de _cmd_drive acima pra motivo completo."""
        self._cancelar_autostop_eva()
        timer = threading.Timer(EVA_DRIVE_AUTOSTOP_S, self._autostop_disparou)
        timer.daemon = True
        self._eva_drive_autostop_timer = timer
        timer.start()

    def _cancelar_autostop_eva(self):
        if self._eva_drive_autostop_timer is not None:
            self._eva_drive_autostop_timer.cancel()
            self._eva_drive_autostop_timer = None

    def _autostop_disparou(self):
        # Não usa self.robot.stop_motors() bruto porque isso não atualiza
        # STATE nem loga -- robot.stop_motors() (EVARobot) já faz os dois.
        try:
            self.robot.stop_motors()
            print(f"⏱️  Auto-stop: {EVA_DRIVE_AUTOSTOP_S:.1f}s sem novo comando drive da EVA")
        except Exception as e:
            print(f"⚠️ Erro no auto-stop: {e}")

    def _cmd_drive(self, env: CommandEnvelope, recebido_em: float) -> dict:
        p = env.params or {}
        vx = as_float(p.get("vx", 0.0))
        vy = as_float(p.get("vy", 0.0))
        vz = as_float(p.get("vz", 0.0))
        speed_scale = as_float(p.get("speed_scale", EVA_MAX_SPEED_SCALE))

        # Teto de autoridade conservador por padrão para comandos "eva" --
        # mesmo que o cliente peça mais, não passa disso aqui.
        if env.source == "eva":
            speed_scale = min(speed_scale, EVA_MAX_SPEED_SCALE)

        ok, motivo = self.robot.drive_vector(vx, vy, vz, speed_scale=speed_scale)

        # Qualquer comando de movimento ACEITO conta como sinal de vida
        # -- alimenta o watchdog. Se foi recusado pela segurança, não
        # alimenta (não faz sentido "provar que está vivo" com um
        # comando que a própria segurança rejeitou).
        if ok:
            self.robot.heartbeat()
            if env.source == "eva":
                self._agendar_autostop_eva()

        # "erro" além de "detalhe" -- ANTES só tinha "detalhe", e
        # qualquer código do lado do cliente que checasse "erro" primeiro
        # (convenção do resto do projeto, ver registry.py) não
        # encontrava nada e tratava como resposta desconhecida, mesmo
        # com o motivo real disponível em "detalhe" o tempo todo (achado
        # em uso real: controle_manual_robo.py mostrava "resposta
        # inesperada" para uma recusa perfeitamente normal).
        #
        # distancia_obstaculo_cm: vem de graça em TODA chamada de drive,
        # não só quando pedido via robo_estado -- achado em uso real: a
        # única forma de saber a distância era chamar robo_estado, e a
        # ferramenta só instrui fazer isso DEPOIS de um erro, nunca antes
        # de decidir se mover. Sem isso ela literalmente não tinha como
        # saber o quão perto de algo estava até já ter sido recusada (ou
        # pior, até bater, se o comando anterior ainda estava valendo).
        return {"ok": ok, "cmd": "drive", "seq": env.seq,
                "erro": None if ok else motivo, "detalhe": motivo,
                "distancia_obstaculo_cm": self.robot.safety.last_sensor_data.get("ultrasonic_cm")}

    def _cmd_head(self, env: CommandEnvelope) -> dict:
        p = env.params or {}
        smooth = bool(p.get("smooth", False))
        resultados = []

        if "yaw" in p and p["yaw"] is not None:
            ok, motivo = self.robot.arm_set_angle(0, int(as_float(p["yaw"])), smooth=smooth)
            resultados.append({"servo": "yaw", "ok": bool(ok), "detalhe": motivo})

        if "pitch" in p and p["pitch"] is not None:
            ok, motivo = self.robot.arm_set_angle(1, int(as_float(p["pitch"])), smooth=smooth)
            resultados.append({"servo": "pitch", "ok": bool(ok), "detalhe": motivo})

        # Canal 3 -- cabeça (montagem da PiCam), diferente de yaw/pitch
        # (que são o pan/tilt do braço todo). Não tinha NENHUM comando de
        # rede apontando pra ele até agora -- arm_set_angle()/safety.py já
        # aceitavam o canal, só nada no dispatcher chamava.
        if "cabeca" in p and p["cabeca"] is not None:
            ok, motivo = self.robot.arm_set_angle(3, int(as_float(p["cabeca"])), smooth=smooth)
            resultados.append({"servo": "cabeca", "ok": bool(ok), "detalhe": motivo})

        # Canal 2 -- cotovelo. NÃO é exposto como parâmetro livre do lado
        # da EVA (ver robot_tools.robo_olhar, que omite este eixo de
        # propósito): o cotovelo acima de 160° trava todos os outros eixos
        # por segurança (safety.validate_servo_command, regra 1), então
        # dar o controle dele ao modelo é dar um jeito de ela se paralisar
        # sozinha. O caminho existe aqui porque ela precisa de UMA saída
        # com destino fixo quando o braço é deixado travado pelo gamepad
        # -- robo_destravar_braco, que manda sempre o mesmo ângulo.
        if "cotovelo" in p and p["cotovelo"] is not None:
            ok, motivo = self.robot.arm_set_angle(2, int(as_float(p["cotovelo"])), smooth=smooth)
            resultados.append({"servo": "cotovelo", "ok": bool(ok), "detalhe": motivo})

        if not resultados:
            return {"ok": False, "erro": "sem_parametros", "cmd": "head", "seq": env.seq,
                    "detalhe": "informe yaw, pitch, cabeca e/ou cotovelo"}

        todos_ok = all(r["ok"] for r in resultados)
        if todos_ok:
            self.robot.heartbeat()

        # top-level erro/detalhe -- pega o motivo do primeiro resultado
        # que falhou. Achado em uso real: sem isso, _desembrulhar() (do
        # lado da EVA, em robot_tools.py) não tinha onde ler o motivo e
        # caía em 'falha_desconhecida'/null, mesmo com o servidor já
        # sabendo exatamente por que recusou (ver arm_set_angle).
        motivo_falha = next((r["detalhe"] for r in resultados if not r["ok"]), "falha_desconhecida")

        return {"ok": todos_ok, "cmd": "head", "seq": env.seq,
                "resultados": resultados,
                "erro": None if todos_ok else motivo_falha,
                "detalhe": "ok" if todos_ok else motivo_falha}


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "=" * 60)
    print("🤖 EVA ROBOT - COMMAND SERVER")
    print("=" * 60 + "\n")

    servidor = EVACommandServer()

    try:
        if not servidor.start(command_port=5000, video_port=8000):
            print("❌ Falha ao iniciar servidor")
            return 1

        print("💡 Rodando. Ctrl+C para sair.\n")
        # NÃO usar input() aqui -- descoberto em uso real: se o stdin
        # não estiver anexado como terminal interativo de verdade
        # (depende de como o processo foi lançado), input() bate EOF
        # NA HORA, o loop antigo saía sem avisar, e o processo inteiro
        # morria segundos depois de subir -- sem Ctrl+C, sem 'q', sem
        # nenhum log explicando por quê. time.sleep() não depende de
        # stdin nenhum; Ctrl+C (KeyboardInterrupt) continua funcionando
        # do mesmo jeito pra parar de propósito.
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário")

    finally:
        servidor.stop()
        print("\n✅ Programa finalizado")

    return 0


if __name__ == "__main__":
    sys.exit(main())