#!/usr/bin/env python3
"""
EVA ROBOT NETWORK SERVER (Raspberry Pi) - CORRIGIDO
- Controle manual real via PC (WebSocket)
- CORREÇÃO 1: Handler websockets moderno (sem 'path')
- CORREÇÃO 2: Tratamento de porta em uso
- CORREÇÃO 3: Inicialização correta do camera system
- CORREÇÃO 4: Importações condicionais melhoradas
"""

from __future__ import annotations

import asyncio
import json
import traceback
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Set, Any, Tuple

import websockets
from websockets.asyncio.server import serve

from robot_protocol import parse_command, now_s, clamp, as_float, as_int

# Importar sistema de controle (corpo)
try:
    from eva_remote_control import ActuatorServer, EVAIntegration, RobotState
    from robot_core import EvaRobotCore
    ROBOT_AVAILABLE = True
except Exception as e:
    print(f"⚠️  Sistema de robô não disponível: {e}")
    ROBOT_AVAILABLE = False

# Importar sistema de câmeras
try:
    from eva_camera_system import SmartCameraSystem, CameraConfig
    CAMERA_AVAILABLE = True
except Exception as e:
    print(f"⚠️  Sistema de câmeras não disponível: {e}")
    CAMERA_AVAILABLE = False


@dataclass
class OwnershipConfig:
    manual_hold_seconds: float = 1.0
    watchdog_timeout_seconds: float = 0.6


class ControlArbiter:
    """Decide quem tem autoridade no controle"""

    def __init__(self, cfg: OwnershipConfig):
        self.cfg = cfg
        self.control_owner: str = "none"
        self.last_manual_ts: float = 0.0
        self.last_any_cmd_ts: float = now_s()
        self.estop: bool = False

    def note_command(self, source: str):
        t = now_s()
        self.last_any_cmd_ts = t
        if source == "manual":
            self.last_manual_ts = t
            self.control_owner = "manual"
        elif self.control_owner != "manual" and source == "eva":
            self.control_owner = "eva"

    def manual_active(self) -> bool:
        return (now_s() - self.last_manual_ts) <= self.cfg.manual_hold_seconds

    def can_drive(self, source: str) -> Tuple[bool, str]:
        if self.estop:
            return False, "estop_active"
        if source == "manual":
            return True, "ok"
        if self.manual_active():
            return False, "manual_override"
        return True, "ok"

    def watchdog_expired(self) -> bool:
        return (now_s() - self.last_any_cmd_ts) > self.cfg.watchdog_timeout_seconds

    def set_estop(self, value: bool):
        self.estop = value
        if value:
            self.control_owner = "manual"


class RobotWebSocketServer:
    def __init__(
        self,
        actuator_server: ActuatorServer,
        eva_integration: EVAIntegration,
        host: str = "0.0.0.0",
        port: int = 8765,
        cfg: OwnershipConfig = None
    ):
        self.actuator = actuator_server
        self.eva = eva_integration
        self.host = host
        self.port = port

        self.clients: Set = set()

        self.cfg = cfg or OwnershipConfig()
        self.arbiter = ControlArbiter(self.cfg)

        self._state_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._camera_task: Optional[asyncio.Task] = None
        self._server = None

        # Sistema de câmeras inteligente (opcional)
        self.camera_system = None
        if CAMERA_AVAILABLE:
            try:
                self.camera_system = SmartCameraSystem(CameraConfig())
                if self.camera_system.start():
                    self.camera_system.streaming = True
                    print("✅ Sistema de câmeras iniciado")
                else:
                    print("⚠️  Câmeras não disponíveis, continuando sem elas")
                    self.camera_system = None
            except Exception as e:
                print(f"⚠️  Erro ao iniciar câmeras: {e}")
                self.camera_system = None

        self.stats = {
            "total_connections": 0,
            "total_commands": 0,
            "total_errors": 0,
            "start_time": datetime.now().isoformat()
        }

        self.running = False

        print(f"✅ WebSocket Server configurado: ws://{host}:{port}")

    async def start(self):
        """Inicia o servidor"""
        print("\n🚀 Iniciando servidor WebSocket (Raspberry)...")
        print(f"   Host: {self.host}")
        print(f"   Porta: {self.port}")
        print()

        # Iniciar tasks de background
        self._state_task = asyncio.create_task(self._broadcast_state_loop())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        
        # Task de câmera (se disponível)
        if self.camera_system:
            self._camera_task = asyncio.create_task(self.camera_system.stream_loop())

        self.running = True

        try:
            # ✅ CORREÇÃO: Usar serve() moderno do websockets
            async with serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=10,
                max_size=2_000_000
            ) as server:
                self._server = server
                print("✅ Servidor rodando. Aguardando conexões...\n")
                
                # Manter servidor rodando
                await asyncio.Future()

        except OSError as e:
            if e.errno == 98:  # Address already in use
                print(f"\n❌ ERRO: Porta {self.port} já está em uso!")
                print("\n💡 SOLUÇÕES:")
                print(f"   1. Matar processo na porta: sudo fuser -k {self.port}/tcp")
                print(f"   2. Usar outra porta: python {sys.argv[0]} --port 8766")
                print(f"   3. Encontrar processo: sudo lsof -i :{self.port}")
                raise
            else:
                raise

    async def stop(self):
        """Para o servidor graciosamente"""
        print("\n🔴 Parando servidor...")
        
        self.running = False

        # Cancelar tasks
        for task in [self._state_task, self._watchdog_task, self._camera_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Fechar câmeras
        if self.camera_system:
            self.camera_system.cleanup()

        # Desconectar clientes
        if self.clients:
            await asyncio.gather(
                *[ws.close() for ws in self.clients],
                return_exceptions=True
            )
        
        print("✅ Servidor parado")

    async def _handle_client(self, websocket):
        """
        ✅ CORREÇÃO: Handler moderno sem 'path'
        Compatível com websockets >= 13.0
        """
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        print(f"📡 Cliente conectado: {client_id}")
        
        self.clients.add(websocket)
        self.stats["total_connections"] += 1

        try:
            # Mensagem de boas-vindas
            welcome = {
                "type": "welcome",
                "message": "Conectado ao EVA Robot (Raspberry)",
                "client_id": client_id,
                "server_time": datetime.now().isoformat(),
                "state": self._get_state_payload()
            }
            await websocket.send(json.dumps(welcome))
            
            # Registrar cliente para stream de câmera
            if self.camera_system:
                self.camera_system.add_client(websocket)

            # Loop de mensagens
            async for raw in websocket:
                try:
                    await self._process_message(websocket, raw)
                except Exception as e:
                    self.stats["total_errors"] += 1
                    print(f"❌ Erro processando mensagem: {e}")
                    traceback.print_exc()
                    await self._send_error(websocket, str(e))

        except websockets.exceptions.ConnectionClosed:
            print(f"📡 Conexão fechada: {client_id}")
        
        except Exception as e:
            print(f"❌ Erro no handler: {e}")
            traceback.print_exc()
        
        finally:
            self.clients.discard(websocket)
            if self.camera_system:
                self.camera_system.remove_client(websocket)
            print(f"📡 Cliente desconectado: {client_id}")

    async def _process_message(self, websocket, raw_message: str):
        """Processa mensagem recebida"""
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send_error(websocket, "invalid_json")
            return

        msg_type = msg.get("type")
        request_id = msg.get("request_id")

        # Compat: heartbeat/get_state legado
        if msg_type in ("heartbeat", "get_state"):
            result = await self._handle_legacy(msg_type)
            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": "ok",
                "data": result
            }))
            return

        if msg_type != "command":
            await self._send_error(websocket, "unknown_type", request_id=request_id)
            return

        # Processar comando
        env = parse_command(msg)
        received_ts = now_s()

        self.stats["total_commands"] += 1

        # Verificar expiração
        if env.is_expired(received_ts):
            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": "blocked",
                "data": {"reason": "expired_ttl"}
            }))
            return

        # HEARTBEAT
        if env.cmd in ("heartbeat",):
            self.arbiter.note_command(env.source)
            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": "ok",
                "data": {"ok": True, "ts": received_ts}
            }))
            return

        # E-STOP
        if env.cmd in ("estop",):
            self.arbiter.note_command(env.source)
            self.arbiter.set_estop(True)
            self.actuator.stop()
            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": "ok",
                "data": {"ok": True, "reason": "estop_set"}
            }))
            return

        # STOP
        if env.cmd in ("stop",):
            self.arbiter.note_command(env.source)
            self.actuator.stop()
            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": "ok",
                "data": {"ok": True}
            }))
            return

        # Verificar E-STOP
        if self.arbiter.estop:
            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": "blocked",
                "data": {"reason": "estop_active"}
            }))
            return

        # DRIVE
        if env.cmd == "drive":
            self.arbiter.note_command(env.source)
            allowed, reason = self.arbiter.can_drive(env.source)
            
            if not allowed:
                await websocket.send(json.dumps({
                    "type": "response",
                    "request_id": request_id,
                    "status": "blocked",
                    "data": {"reason": reason}
                }))
                return

            vx = clamp(as_float(env.params.get("vx", 0.0), 0.0), -1.0, 1.0)
            vy = clamp(as_float(env.params.get("vy", 0.0), 0.0), -1.0, 1.0)
            vz = clamp(as_float(env.params.get("vz", 0.0), 0.0), -1.0, 1.0)

            # Normalizar
            m = max(1.0, abs(vx) + abs(vy) + abs(vz))
            vx, vy, vz = vx / m, vy / m, vz / m

            result = self.actuator.drive(vx=vx, vy=vy, vz=vz)

            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": result.get("status", "ok"),
                "data": result
            }))
            return

        # HEAD
        if env.cmd == "head":
            self.arbiter.note_command(env.source)

            yaw = env.params.get("yaw", None)
            pitch = env.params.get("pitch", None)
            smooth = bool(env.params.get("smooth", True))

            yaw_i = as_int(yaw, 0) if yaw is not None else None
            pitch_i = as_int(pitch, 0) if pitch is not None else None

            result = self.actuator.move_head(yaw=yaw_i, pitch=pitch_i, smooth=smooth)

            # Atualizar sistema de câmera
            if self.camera_system and (yaw is not None or pitch is not None):
                state = self.actuator.get_state()
                head_pos = state.get('head_position', {})
                self.camera_system.update_head_position({
                    "yaw": yaw_i if yaw_i is not None else head_pos.get("yaw", 90),
                    "pitch": pitch_i if pitch_i is not None else head_pos.get("pitch", 90)
                })

            await websocket.send(json.dumps({
                "type": "response",
                "request_id": request_id,
                "status": result.get("status", "ok"),
                "data": result
            }))
            return

        # Comando desconhecido
        await self._send_error(
            websocket, 
            f"unknown_cmd:{env.cmd}", 
            request_id=request_id
        )

    async def _handle_legacy(self, msg_type: str) -> Dict[str, Any]:
        """Comandos legados (compatibilidade)"""
        if msg_type == "get_state":
            return self._get_state_payload()
        
        if msg_type == "heartbeat":
            self.actuator.heartbeat()
            self.arbiter.note_command("manual")
            return {"ok": True, "ts": now_s()}
        
        return {}

    def _get_state_payload(self) -> Dict[str, Any]:
        """Monta payload de estado"""
        state = self.actuator.get_state()
        state["control_owner"] = "manual" if self.arbiter.manual_active() else self.arbiter.control_owner
        state["estop"] = self.arbiter.estop
        state["watchdog_timeout_s"] = self.cfg.watchdog_timeout_seconds
        return state

    async def _broadcast_state_loop(self):
        """Loop de broadcast de estado (10Hz)"""
        while self.running:
            try:
                if self.clients:
                    payload = {
                        "type": "state",
                        "timestamp": datetime.now().isoformat(),
                        "data": self._get_state_payload()
                    }
                    raw = json.dumps(payload)

                    # Enviar para todos os clientes
                    disconnected = set()
                    for ws in self.clients:
                        try:
                            await ws.send(raw)
                        except Exception:
                            disconnected.add(ws)
                    
                    # Remover desconectados
                    self.clients -= disconnected

                    # Atualizar câmera com estado da cabeça
                    if self.camera_system:
                        state = self.actuator.get_state()
                        head_pos = state.get('head_position')
                        if head_pos:
                            self.camera_system.update_head_position(head_pos)

                await asyncio.sleep(0.1)  # 10Hz
            
            except Exception as e:
                print(f"⚠️  broadcast loop error: {e}")
                await asyncio.sleep(1.0)

    async def _watchdog_loop(self):
        """Loop de watchdog"""
        while self.running:
            try:
                if self.arbiter.watchdog_expired():
                    self.actuator.stop()
                
                await asyncio.sleep(0.1)
            
            except Exception:
                await asyncio.sleep(1.0)

    async def _send_error(
        self, 
        websocket, 
        error_message: str, 
        request_id: Optional[str] = None
    ):
        """Envia mensagem de erro"""
        await websocket.send(json.dumps({
            "type": "error",
            "request_id": request_id,
            "error": error_message
        }))


async def main():
    """Função principal"""
    if not ROBOT_AVAILABLE:
        print("❌ Rode isso no Raspberry com hardware/arquivos presentes.")
        return

    print("\n" + "="*60)
    print("🤖 EVA ROBOT NETWORK SERVER")
    print("="*60 + "\n")

    # Inicializar hardware
    robot = EvaRobotCore()
    ok = robot.initialize(enable_arm=True, enable_cameras=False)
    
    if not ok:
        print("❌ Falha ao inicializar hardware")
        return

    # Criar servidor de atuadores
    actuator = ActuatorServer(robot)
    actuator.start_monitoring()

    # Integração EVA
    eva_integration = EVAIntegration(actuator)
    eva_integration.enable_autonomous()

    # Servidor WebSocket
    server = RobotWebSocketServer(
        actuator_server=actuator,
        eva_integration=eva_integration,
        host="0.0.0.0",
        port=8765
    )

    # Tratamento de sinais
    def signal_handler(sig, frame):
        print("\n⚠️  Sinal recebido, encerrando...")
        asyncio.create_task(server.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await server.start()
    
    except KeyboardInterrupt:
        print("\n⚠️  Ctrl+C detectado")
    
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        traceback.print_exc()
    
    finally:
        await server.stop()
        actuator.stop_monitoring()
        robot.cleanup()
        print("✅ Encerrado com segurança\n")


if __name__ == "__main__":
    asyncio.run(main())