# robot_protocol.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal
import time

Source = Literal["manual", "eva", "script", "unknown"]
Cmd = Literal["drive", "head", "stop", "estop", "reset_estop", "heartbeat", "get_state"]

def now_s() -> float:
    return time.time()

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def as_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

@dataclass
class CommandEnvelope:
    type: str = "command"
    source: Source = "unknown"
    priority: int = 0
    seq: int = 0
    ttl_ms: int = 300
    cmd: Cmd = "stop"
    params: Dict[str, Any] = None
    sent_ts: float = 0.0  # opcional (client pode mandar)

    def is_expired(self, enfileirado_em: float) -> bool:
        """TTL medido SÓ pelo relógio do servidor, do início ao fim --
        `enfileirado_em` é o timestamp (relógio do SERVIDOR) de quando a
        mensagem chegou pela rede, capturado em tcp_server.py no momento
        do recv(), não de quando o comando foi processado.

        HISTÓRICO -- por que não usar sent_ts do cliente: parecia mais
        preciso (capturaria atraso de decisão do lado de quem manda, ex:
        EVA levando 2s pensando antes de mandar o comando), mas depende
        dos dois relógios (PC da EVA e Raspberry Pi, máquinas
        diferentes) estarem sincronizados no nível de milissegundos --
        e não estavam, o que fazia TODO comando expirar na hora, mesmo
        com a rede respondendo instantaneamente (confirmado em uso
        real: 100% dos comandos vinham 'comando_expirado', mesmo os
        mais simples como get_state).

        O que TTL protege de verdade neste desenho (fila processada uma
        mensagem de cada vez -- ver eva_command_server._command_loop) é
        comando parado tempo demais na fila do SERVIDOR antes de ser
        executado -- isso agora é medido do início (recv na rede) ao fim
        (prestes a executar), inteiramente com o relógio do servidor,
        sem depender do relógio de quem mandou. sent_ts continua
        guardado no envelope (útil pra log/diagnóstico de latência
        aproximada), só não entra mais nesta conta."""
        ttl = max(0, int(self.ttl_ms))
        if ttl == 0:
            return False
        return (now_s() - enfileirado_em) * 1000.0 > ttl

def parse_command(msg: Dict[str, Any]) -> CommandEnvelope:
    params = msg.get("params") or {}
    return CommandEnvelope(
        type=msg.get("type", "command"),
        source=msg.get("source", "unknown"),
        priority=as_int(msg.get("priority", 0), 0),
        seq=as_int(msg.get("seq", 0), 0),
        ttl_ms=as_int(msg.get("ttl_ms", 300), 300),
        cmd=msg.get("cmd") or msg.get("action") or "stop",  # compat c/ legado
        params=params,
        sent_ts=as_float(msg.get("sent_ts", 0.0), 0.0),
    )
