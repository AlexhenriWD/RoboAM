#!/usr/bin/env python3
"""
EVA ROBOT - UNIFIED STATE
Estado oficial único do robô - SINGLE SOURCE OF TRUTH
"""

import time
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading


# ============================================================================
# ENUMS
# ============================================================================

class RobotMode(Enum):
    """Modo de operação do robô"""
    MANUAL = "manual"
    AUTONOMOUS = "autonomous"
    EMERGENCY = "emergency"
    IDLE = "idle"


class CameraMode(Enum):
    """Modo de câmera ativa"""
    NAVIGATION = "navigation"  # USB Webcam
    HEAD = "head"              # Pi Camera
    AUTO = "auto"              # Troca automática


# ============================================================================
# ESTADO CENTRAL
# ============================================================================

@dataclass
class RobotState:
    """
    Estado completo do robô
    
    SINGLE SOURCE OF TRUTH - todos os componentes consultam/atualizam aqui
    """
    
    # ========================================
    # TIMESTAMP
    # ========================================
    timestamp: float = field(default_factory=time.time)
    
    # ========================================
    # MODO
    # ========================================
    mode: RobotMode = RobotMode.IDLE
    camera_mode: CameraMode = CameraMode.AUTO
    
    # ========================================
    # POSIÇÃO ESTIMADA
    # ========================================
    # Odometria estimada (sem encoders = impreciso)
    position_x: float = 0.0
    position_y: float = 0.0
    heading: float = 0.0  # Graus (0-360)
    
    # ========================================
    # MOTORES
    # ========================================
    motor_fl: int = 0  # Front Left PWM
    motor_bl: int = 0  # Back Left PWM
    motor_fr: int = 0  # Front Right PWM
    motor_br: int = 0  # Back Right PWM
    
    is_moving: bool = False
    
    # ========================================
    # SERVOS (BRAÇO/CABEÇA)
    # ========================================
    servo_positions: Dict[int, int] = field(default_factory=lambda: {
        0: 90,  # Yaw
        1: 90,  # Pitch
        2: 90,  # Cotovelo
        3: 90,  # Cabeça
    })
    
    # ========================================
    # SENSORES
    # ========================================
    ultrasonic_cm: Optional[float] = None
    battery_voltage: Optional[float] = None
    
    # ========================================
    # CÂMERA
    # ========================================
    active_camera: str = "webcam"  # "webcam" ou "picam"
    last_camera_switch: float = 0.0
    
    # ========================================
    # SEGURANÇA
    # ========================================
    emergency_stop: bool = False
    safety_level: str = "normal"  # "normal", "warning", "critical", "emergency"
    
    # ========================================
    # CONTROLE
    # ========================================
    last_command: Optional[str] = None
    last_command_time: float = 0.0
    last_heartbeat: float = 0.0
    
    # ========================================
    # EVA INTEGRATION
    # ========================================
    eva_is_thinking: bool = False
    eva_is_speaking: bool = False
    
    # ========================================
    # MÉTODOS
    # ========================================
    
    def update_timestamp(self):
        """Atualiza timestamp"""
        self.timestamp = time.time()
    
    def set_motors(self, fl: int, bl: int, fr: int, br: int):
        """Atualiza valores dos motores"""
        self.motor_fl = fl
        self.motor_bl = bl
        self.motor_fr = fr
        self.motor_br = br
        self.is_moving = any([fl, bl, fr, br])
        self.update_timestamp()
    
    def set_servo(self, channel: int, angle: int):
        """Atualiza posição de um servo"""
        self.servo_positions[channel] = angle
        self.update_timestamp()
    
    def update_sensors(self, ultrasonic: Optional[float] = None, battery: Optional[float] = None):
        """Atualiza leituras de sensores"""
        if ultrasonic is not None:
            self.ultrasonic_cm = ultrasonic
        if battery is not None:
            self.battery_voltage = battery
        self.update_timestamp()
    
    def to_dict(self) -> Dict:
        """Exporta estado como dict"""
        data = asdict(self)
        data['mode'] = self.mode.value
        data['camera_mode'] = self.camera_mode.value
        return data
    
    def to_json_safe(self) -> Dict:
        """Exporta estado em formato JSON-safe (sem Enums)"""
        return {
            'timestamp': self.timestamp,
            'mode': self.mode.value,
            'camera_mode': self.camera_mode.value,
            
            'position': {
                'x': self.position_x,
                'y': self.position_y,
                'heading': self.heading
            },
            
            'motors': {
                'fl': self.motor_fl,
                'bl': self.motor_bl,
                'fr': self.motor_fr,
                'br': self.motor_br,
                'is_moving': self.is_moving
            },
            
            'servos': self.servo_positions.copy(),
            
            'sensors': {
                'ultrasonic_cm': self.ultrasonic_cm,
                'battery_v': self.battery_voltage
            },
            
            'camera': {
                'active': self.active_camera,
                'mode': self.camera_mode.value,
                'last_switch': self.last_camera_switch
            },
            
            'safety': {
                'emergency_stop': self.emergency_stop,
                'level': self.safety_level
            },
            
            'control': {
                'last_command': self.last_command,
                'last_command_time': self.last_command_time,
                'last_heartbeat': self.last_heartbeat
            },
            
            'eva': {
                'is_thinking': self.eva_is_thinking,
                'is_speaking': self.eva_is_speaking
            }
        }


# ============================================================================
# STATE MANAGER (Thread-Safe)
# ============================================================================

class StateManager:
    """
    Gerenciador de estado thread-safe
    
    Permite múltiplas threads lerem/escreverem estado com segurança
    """
    
    def __init__(self):
        self.state = RobotState()
        self.lock = threading.RLock()  # Reentrant lock
        self.callbacks: List = []
        
        print("✅ State Manager inicializado")
    
    def get_state(self) -> RobotState:
        """Retorna CÓPIA do estado (thread-safe)"""
        with self.lock:
            # Retorna cópia para evitar modificação acidental
            import copy
            return copy.deepcopy(self.state)
    
    def update(self, **kwargs):
        """
        Atualiza estado
        
        Exemplo:
            state_manager.update(motor_fl=1500, is_moving=True)
        """
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)
            
            self.state.update_timestamp()
            self._notify_callbacks()
    
    def set_motors(self, fl: int, bl: int, fr: int, br: int):
        """Atualiza motores (thread-safe)"""
        with self.lock:
            self.state.set_motors(fl, bl, fr, br)
            self._notify_callbacks()
    
    def set_servo(self, channel: int, angle: int):
        """Atualiza servo (thread-safe)"""
        with self.lock:
            self.state.set_servo(channel, angle)
            self._notify_callbacks()
    
    def update_sensors(self, ultrasonic: Optional[float] = None, battery: Optional[float] = None):
        """Atualiza sensores (thread-safe)"""
        with self.lock:
            self.state.update_sensors(ultrasonic, battery)
            self._notify_callbacks()
    
    def trigger_emergency_stop(self, reason: str):
        """Aciona emergency stop"""
        with self.lock:
            self.state.emergency_stop = True
            self.state.mode = RobotMode.EMERGENCY
            self.state.safety_level = "emergency"
            self.state.last_command = f"ESTOP: {reason}"
            self.state.update_timestamp()
            self._notify_callbacks()
    
    def reset_emergency_stop(self):
        """Reseta emergency stop"""
        with self.lock:
            self.state.emergency_stop = False
            self.state.mode = RobotMode.IDLE
            self.state.safety_level = "normal"
            self.state.update_timestamp()
            self._notify_callbacks()
    
    def to_dict(self) -> Dict:
        """Exporta estado como dict (thread-safe)"""
        with self.lock:
            return self.state.to_json_safe()
    
    def register_callback(self, callback):
        """
        Registra callback para mudanças de estado
        
        Callback recebe: callback(state_dict)
        """
        self.callbacks.append(callback)
    
    def _notify_callbacks(self):
        """Notifica callbacks sobre mudança de estado"""
        state_dict = self.state.to_json_safe()
        
        for callback in self.callbacks:
            try:
                callback(state_dict)
            except Exception as e:
                print(f"❌ Erro em callback: {e}")


# ============================================================================
# INSTÂNCIA GLOBAL
# ============================================================================

# Singleton - importar em outros módulos
STATE = StateManager()


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🗂️  EVA ROBOT - STATE MANAGER TEST")
    print("="*60 + "\n")
    
    state_mgr = StateManager()
    
    # Callback de teste
    def on_state_change(state_dict):
        print(f"📡 Estado mudou: timestamp={state_dict['timestamp']:.2f}")
    
    state_mgr.register_callback(on_state_change)
    
    # Teste 1: Atualizar motores
    print("1️⃣  Atualizando motores...")
    state_mgr.set_motors(1500, 1500, 1500, 1500)
    
    # Teste 2: Atualizar servo
    print("\n2️⃣  Atualizando servo...")
    state_mgr.set_servo(0, 120)
    
    # Teste 3: Atualizar sensores
    print("\n3️⃣  Atualizando sensores...")
    state_mgr.update_sensors(ultrasonic=25.5, battery=7.2)
    
    # Teste 4: Emergency stop
    print("\n4️⃣  Emergency stop...")
    state_mgr.trigger_emergency_stop("Teste")
    
    # Teste 5: Exportar estado
    print("\n5️⃣  Estado final:")
    state_dict = state_mgr.to_dict()
    
    print("\n📋 Motores:")
    for key, value in state_dict['motors'].items():
        print(f"   {key}: {value}")
    
    print("\n🦾 Servos:")
    for ch, angle in state_dict['servos'].items():
        print(f"   Canal {ch}: {angle}°")
    
    print("\n📡 Sensores:")
    for key, value in state_dict['sensors'].items():
        print(f"   {key}: {value}")
    
    print("\n🛡️  Segurança:")
    for key, value in state_dict['safety'].items():
        print(f"   {key}: {value}")
    
    print("\n" + "="*60 + "\n")