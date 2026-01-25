# robot_protocol.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal
import time

Source = Literal["manual", "eva", "script", "unknown"]
Cmd = Literal["drive", "head", "stop", "estop", "heartbeat", "get_state"]

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

    def is_expired(self, server_received_ts: float) -> bool:
        ttl = max(0, int(self.ttl_ms))
        if ttl == 0:
            return False
        # Se client mandou sent_ts, usamos ele; senão usamos received_ts (menos rigor, mas ok)
        base = self.sent_ts if self.sent_ts else server_received_ts
        return (server_received_ts - base) * 1000.0 > ttl

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
