#!/usr/bin/env python3
"""
EVA ROBOT - GAMEPAD CONTROLLER
Suporte a controles genéricos: PS4, PS5, Xbox One, Xbox Series
Usa evdev para input direto no Linux
"""

import os
import time
import threading
from typing import Optional, Callable, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    print("⚠️  evdev não disponível. Instale: pip install evdev")


class GamepadType(Enum):
    """Tipos de gamepad suportados"""
    GENERIC = "generic"
    PS4 = "ps4"
    PS5 = "ps5"
    XBOX_ONE = "xbox_one"
    XBOX_SERIES = "xbox_series"


@dataclass
class GamepadState:
    """Estado atual do gamepad"""
    # Analog sticks (-1.0 a 1.0)
    left_x: float = 0.0
    left_y: float = 0.0
    right_x: float = 0.0
    right_y: float = 0.0
    
    # Triggers (0.0 a 1.0)
    left_trigger: float = 0.0
    right_trigger: float = 0.0
    
    # D-Pad
    dpad_up: bool = False
    dpad_down: bool = False
    dpad_left: bool = False
    dpad_right: bool = False
    
    # Face buttons
    button_a: bool = False  # Cross (PS), A (Xbox)
    button_b: bool = False  # Circle (PS), B (Xbox)
    button_x: bool = False  # Square (PS), X (Xbox)
    button_y: bool = False  # Triangle (PS), Y (Xbox)
    
    # Shoulder buttons
    left_bumper: bool = False   # L1/LB
    right_bumper: bool = False  # R1/RB
    
    # Stick clicks
    left_stick_click: bool = False   # L3
    right_stick_click: bool = False  # R3
    
    # System buttons
    button_start: bool = False
    button_select: bool = False
    button_home: bool = False
    
    # Timestamp
    timestamp: float = 0.0


class GamepadController:
    """
    Controller genérico de gamepad
    
    Características:
    ✅ Auto-detecção de controles
    ✅ Deadzone configurável
    ✅ Smoothing de input
    ✅ Callbacks para eventos
    ✅ Thread-safe
    """
    
    def __init__(
        self,
        device_path: Optional[str] = None,
        deadzone: float = 0.15,
        smoothing: float = 0.2,
        auto_detect: bool = True
    ):
        """
        Args:
            device_path: Caminho do device (/dev/input/eventX) ou None para auto
            deadzone: Zona morta dos analógicos (0.0-0.5)
            smoothing: Suavização de movimento (0.0-1.0, 0=sem smoothing)
            auto_detect: Detectar automaticamente controle
        """
        if not EVDEV_AVAILABLE:
            raise RuntimeError("evdev não disponível")
        
        self.device_path = device_path
        self.deadzone = max(0.0, min(0.5, deadzone))
        self.smoothing = max(0.0, min(1.0, smoothing))
        
        # Device
        self.device: Optional[InputDevice] = None
        self.gamepad_type = GamepadType.GENERIC
        
        # Estado
        self.state = GamepadState()
        self.prev_state = GamepadState()
        
        # Raw values para conversão
        self._raw_axes: Dict[int, int] = {}
        self._axis_ranges: Dict[int, Tuple[int, int]] = {}
        
        # Thread
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._state_lock = threading.Lock()
        
        # Callbacks
        self.on_state_change: Optional[Callable[[GamepadState], None]] = None
        self.on_button_press: Optional[Callable[[str], None]] = None
        self.on_button_release: Optional[Callable[[str], None]] = None
        
        # Auto-detect
        if auto_detect and not device_path:
            self.device_path = self._auto_detect_gamepad()
        
        print(f"🎮 GamepadController criado")
        print(f"   Deadzone: {self.deadzone:.2f}")
        print(f"   Smoothing: {self.smoothing:.2f}")
    
    # ========================================
    # AUTO-DETECÇÃO
    # ========================================
    
    def _auto_detect_gamepad(self) -> Optional[str]:
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

        for device in devices:
            caps = device.capabilities()

            has_keys = ecodes.EV_KEY in caps
            has_abs = ecodes.EV_ABS in caps
            is_mouse = ecodes.EV_REL in caps  # touchpad / mouse

            if has_keys and has_abs and not is_mouse:
                print(f"✅ Gamepad detectado corretamente: {device.name}")
                print(f"   Caminho: {device.path}")

                name = device.name.lower()
                if 'dualsense' in name or 'ps5' in name:
                    self.gamepad_type = GamepadType.PS5
                elif 'ps4' in name:
                    self.gamepad_type = GamepadType.PS4
                elif 'xbox' in name:
                    self.gamepad_type = GamepadType.XBOX_ONE

                return device.path

        print("⚠️  Nenhum gamepad válido encontrado")
        return None


    
    # ========================================
    # START / STOP
    # ========================================
    
    def start(self) -> bool:
        """Inicia leitura do gamepad"""
        if not self.device_path:
            print("❌ Nenhum device especificado")
            return False
        
        try:
            self.device = InputDevice(self.device_path)
            print(f"✅ Conectado: {self.device.name}")

            # 🔥 CRÍTICO: garantir exclusividade (DualSense BT)
            try:
                self.device.grab()
                print("🔒 Device grabbed (exclusive access)")
            except Exception as e:
                print(f"⚠️  Não foi possível grab device: {e}")

            
            # Detectar ranges dos eixos
            self._detect_axis_ranges()
            
            # Iniciar thread
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            
            return True
        
        except Exception as e:
            print(f"❌ Erro ao iniciar: {e}")
            return False
    
    def stop(self):
        """Para leitura do gamepad"""
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=2.0)
        
        if self.device:
            try:
                self.device.ungrab()
            except Exception:
                pass
            self.device.close()

        
        print("✅ Gamepad desconectado")
    
    def _detect_axis_ranges(self):
        """Detecta ranges dos eixos analógicos"""
        caps = self.device.capabilities(verbose=False)
        
        if ecodes.EV_ABS in caps:
            for axis_code, axis_info in caps[ecodes.EV_ABS]:
                if isinstance(axis_info, evdev.AbsInfo):
                    self._axis_ranges[axis_code] = (axis_info.min, axis_info.max)
    
    # ========================================
    # LEITURA
    # ========================================
    
    def _read_loop(self):
        print("🎮 Iniciando loop de leitura...")

        try:
            for event in self.device.read_loop():
                if not self.running:
                    break

                self._process_event(event)

        except OSError as e:
            print(f"⚠️  Device desconectado ({e})")

        except Exception as e:
            print(f"⚠️  Erro na leitura do gamepad: {e}")

    
    def _process_event(self, event):
        updated = False

        if event.type == ecodes.EV_ABS:
            self._process_axis(event.code, event.value)
            updated = True

        elif event.type == ecodes.EV_KEY:
            self._process_button(event.code, event.value)
            updated = True

        elif event.type == ecodes.EV_SYN:
            updated = True

        if updated:
            with self._state_lock:
                self.state.timestamp = time.time()
                self._apply_deadzone_and_smoothing()
                if self.on_state_change:
                    self.on_state_change(self.get_state())


    
    def _process_axis(self, code: int, value: int):
        """Processa eixo analógico"""
        self._raw_axes[code] = value
        
        # Normalizar (-1.0 a 1.0)
        normalized = self._normalize_axis(code, value)
        
        # Mapear para estado
        # PS4/PS5 layout
        if code == ecodes.ABS_X:  # Left stick X
            self.state.left_x = normalized
        elif code == ecodes.ABS_Y:  # Left stick Y
            self.state.left_y = -normalized  # Inverter Y
        elif code == ecodes.ABS_RX:  # Right stick X
            self.state.right_x = normalized
        elif code == ecodes.ABS_RY:  # Right stick Y
            self.state.right_y = -normalized  # Inverter Y
        elif code == ecodes.ABS_Z:  # Left trigger (PS4/Xbox)
            self.state.left_trigger = (normalized + 1.0) / 2.0
        elif code == ecodes.ABS_RZ:  # Right trigger (PS4/Xbox)
            self.state.right_trigger = (normalized + 1.0) / 2.0
        
        # D-Pad (HAT)
        elif code == ecodes.ABS_HAT0X:
            self.state.dpad_left = value < 0
            self.state.dpad_right = value > 0
        elif code == ecodes.ABS_HAT0Y:
            self.state.dpad_up = value < 0
            self.state.dpad_down = value > 0
    
    def _process_button(self, code: int, value: int):
        """Processa botão"""
        pressed = value == 1
        
        # Mapear botões (layout genérico)
        button_map = {
            ecodes.BTN_SOUTH: 'button_a',      # Cross/A
            ecodes.BTN_EAST: 'button_b',       # Circle/B
            ecodes.BTN_WEST: 'button_x',       # Square/X
            ecodes.BTN_NORTH: 'button_y',      # Triangle/Y
            ecodes.BTN_TL: 'left_bumper',      # L1/LB
            ecodes.BTN_TR: 'right_bumper',     # R1/RB
            ecodes.BTN_SELECT: 'button_select',
            ecodes.BTN_START: 'button_start',
            ecodes.BTN_MODE: 'button_home',
            ecodes.BTN_THUMBL: 'left_stick_click',
            ecodes.BTN_THUMBR: 'right_stick_click',
        }
        
        if code in button_map:
            attr_name = button_map[code]
            setattr(self.state, attr_name, pressed)
            
            # Callback
            if pressed and self.on_button_press:
                self.on_button_press(attr_name)
            elif not pressed and self.on_button_release:
                self.on_button_release(attr_name)
    
    def _normalize_axis(self, code: int, value: int) -> float:
        """Normaliza valor do eixo para -1.0 a 1.0"""
        if code not in self._axis_ranges:
            # Fallback genérico
            return value / 32768.0
        
        min_val, max_val = self._axis_ranges[code]
        center = (max_val + min_val) / 2
        range_half = (max_val - min_val) / 2
        
        if range_half == 0:
            return 0.0
        
        normalized = (value - center) / range_half
        return max(-1.0, min(1.0, normalized))
    
    def _apply_deadzone_and_smoothing(self):
        """Aplica deadzone e smoothing aos sticks"""
        # Deadzone radial (mais preciso que axial)
        left_magnitude = (self.state.left_x**2 + self.state.left_y**2)**0.5
        right_magnitude = (self.state.right_x**2 + self.state.right_y**2)**0.5
        
        # Left stick
        if left_magnitude < self.deadzone:
            self.state.left_x = 0.0
            self.state.left_y = 0.0
        elif left_magnitude > 0:
            # Remapear para compensar deadzone
            scale = (left_magnitude - self.deadzone) / (1.0 - self.deadzone)
            scale = min(1.0, scale / left_magnitude)
            self.state.left_x *= scale
            self.state.left_y *= scale
        
        # Right stick
        if right_magnitude < self.deadzone:
            self.state.right_x = 0.0
            self.state.right_y = 0.0
        elif right_magnitude > 0:
            scale = (right_magnitude - self.deadzone) / (1.0 - self.deadzone)
            scale = min(1.0, scale / right_magnitude)
            self.state.right_x *= scale
            self.state.right_y *= scale
        
        # Smoothing (exponential moving average)
        if self.smoothing > 0:
            alpha = 1.0 - self.smoothing
            
            self.state.left_x = alpha * self.state.left_x + self.smoothing * self.prev_state.left_x
            self.state.left_y = alpha * self.state.left_y + self.smoothing * self.prev_state.left_y
            self.state.right_x = alpha * self.state.right_x + self.smoothing * self.prev_state.right_x
            self.state.right_y = alpha * self.state.right_y + self.smoothing * self.prev_state.right_y
        
        # Salvar estado anterior
        self.prev_state.left_x = self.state.left_x
        self.prev_state.left_y = self.state.left_y
        self.prev_state.right_x = self.state.right_x
        self.prev_state.right_y = self.state.right_y
    
    # ========================================
    # API
    # ========================================
    
    def get_state(self) -> GamepadState:
        """Retorna estado atual (thread-safe)"""
        with self._state_lock:
            # Retornar cópia
            import copy
            return copy.copy(self.state)
    
    def is_connected(self) -> bool:
        """Verifica se gamepad está conectado"""
        return self.running and self.device is not None
    
    def get_info(self) -> Dict:
        """Retorna informações do gamepad"""
        if not self.device:
            return {}
        
        return {
            'name': self.device.name,
            'path': self.device.path,
            'type': self.gamepad_type.value,
            'connected': self.is_connected()
        }


# ============================================================================
# TESTE
# ============================================================================

def test_gamepad():
    """Teste do gamepad controller"""
    print("\n" + "="*60)
    print("🎮 GAMEPAD CONTROLLER TEST")
    print("="*60 + "\n")
    
    controller = GamepadController(
        device_path="/dev/input/event5",
        deadzone=0.15,
        smoothing=0.2,
        auto_detect=True
    )
    
    if not controller.start():
        print("❌ Falha ao iniciar")
        return
    
    print("\n✅ Iniciado!")
    print("Pressione Ctrl+C para sair\n")
    
    def on_button_press(button: str):
        print(f"🔘 {button} pressionado")
    
    controller.on_button_press = on_button_press
    
    try:
        while True:
            state = controller.get_state()
            
            # Mostrar apenas se há input
            if abs(state.left_x) > 0.01 or abs(state.left_y) > 0.01:
                print(f"\r🕹️  L: ({state.left_x:+.2f}, {state.left_y:+.2f})  "
                      f"R: ({state.right_x:+.2f}, {state.right_y:+.2f})  "
                      f"LT: {state.left_trigger:.2f}  RT: {state.right_trigger:.2f}",
                      end="", flush=True)
            
            time.sleep(0.05)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido")
    
    finally:
        controller.stop()
        print("✅ Finalizado")


if __name__ == '__main__':
    test_gamepad()