#!/usr/bin/env python3
"""
EVA ROBOT - DRONE CONTROL MODE
Controle estilo FPV Drone com gamepad

LAYOUT PADRÃO (Mode 2 - mais comum em drones):
  Left Stick Y  → Throttle (frente/trás)
  Left Stick X  → Strafe (esquerda/direita)
  Right Stick Y → Tilt cabeça (cima/baixo)
  Right Stick X → Pan cabeça (esquerda/direita)
  
  Left Trigger  → Slow mode (precision)
  Right Trigger → Turbo mode (fast)
  
  D-Pad         → Preset positions
  A/Cross       → Switch camera
  B/Circle      → Emergency stop
  X/Square      → Home position (cabeça)
  Y/Triangle    → Auto-level (cabeça center)
"""

import time
import math
from typing import Optional, Dict
from dataclasses import dataclass

from gamepad_controller import GamepadController, GamepadState


@dataclass
class DroneControlConfig:
    """Configuração do modo drone"""
    # Sensibilidades (0.0-1.0)
    drive_sensitivity: float = 0.8
    head_pan_sensitivity: float = 1.0
    head_tilt_sensitivity: float = 0.8
    
    # Velocidades
    normal_speed_scale: float = 0.7   # 70% da velocidade máxima
    slow_speed_scale: float = 0.3     # 30% (precision)
    turbo_speed_scale: float = 1.0    # 100% (máximo)
    
    # Limites de cabeça
    head_yaw_min: int = 0
    head_yaw_max: int = 180
    head_pitch_min: int = 40
    head_pitch_max: int = 110
    
    # Smoothing
    head_smooth_speed: int = 5  # graus por update
    
    # Camera switch delay
    camera_switch_cooldown: float = 1.0  # segundos


class DroneControlMode:
    """
    Controle estilo Drone FPV
    
    Traduz input do gamepad em comandos suaves para o robô
    """
    
    def __init__(
        self,
        robot,
        gamepad: GamepadController,
        config: Optional[DroneControlConfig] = None
    ):
        """
        Args:
            robot: Instância EVARobot
            gamepad: GamepadController
            config: Configuração ou None para padrão
        """
        self.robot = robot
        self.gamepad = gamepad
        self.config = config or DroneControlConfig()
        
        # Estado
        self.enabled = False
        self.speed_mode = 'normal'  # 'slow', 'normal', 'turbo'
        
        # Posição alvo da cabeça
        self.target_head_yaw = 90
        self.target_head_pitch = 90
        
        # Cooldowns
        self.last_camera_switch = 0.0
        
        # Estatísticas
        self.stats = {
            'commands_sent': 0,
            'estops_triggered': 0,
            'camera_switches': 0
        }
        
        print("🚁 Drone Control Mode inicializado")
        print(f"   Drive sensitivity: {self.config.drive_sensitivity}")
        print(f"   Head sensitivity: Pan={self.config.head_pan_sensitivity}, "
              f"Tilt={self.config.head_tilt_sensitivity}")
    
    # ========================================
    # ENABLE / DISABLE
    # ========================================
    
    def enable(self):
        """Habilita modo drone"""
        if self.enabled:
            return
        
        self.enabled = True
        
        # Setup callbacks
        self.gamepad.on_state_change = self._on_gamepad_update
        self.gamepad.on_button_press = self._on_button_press
        
        # Centralizar cabeça
        self.target_head_yaw = 90
        self.target_head_pitch = 90
        self.robot.arm.set_angle(0, 90, smooth=True)
        self.robot.arm.set_angle(1, 90, smooth=True)
        
        print("✅ Drone mode ATIVADO")
        print("\n" + "="*60)
        print("🚁 CONTROLES DRONE MODE")
        print("="*60)
        print("Left Stick Y/X   → Movimento (frente/trás/esquerda/direita)")
        print("Right Stick X/Y  → Cabeça (pan/tilt)")
        print("Left Trigger     → Slow mode (precisão)")
        print("Right Trigger    → Turbo mode (rápido)")
        print("A/Cross          → Switch camera")
        print("B/Circle         → EMERGENCY STOP")
        print("X/Square         → Home cabeça")
        print("Y/Triangle       → Center cabeça")
        print("="*60 + "\n")
    
    def disable(self):
        """Desabilita modo drone"""
        if not self.enabled:
            return
        
        self.enabled = False
        
        # Parar robô
        self.robot.stop_motors()
        
        # Remover callbacks
        self.gamepad.on_state_change = None
        self.gamepad.on_button_press = None
        
        print("⚪ Drone mode DESATIVADO")
    
    # ========================================
    # GAMEPAD CALLBACKS
    # ========================================
    
    def _on_gamepad_update(self, state: GamepadState):
        """Callback chamado quando estado do gamepad muda"""
        if not self.enabled:
            return
        
        # 🐛 DEBUG - verificar se callback está sendo chamado
        # Descomentar para debug:
        if abs(state.left_x) > 0.05 or abs(state.left_y) > 0.05:
            print(f"🎮 UPDATE: LX={state.left_x:.2f} LY={state.left_y:.2f}")
        
        # Determinar modo de velocidade
        self._update_speed_mode(state)
        
        # Processar movimento
        self._process_drive(state)
        
        # Processar cabeça
        self._process_head(state)
    
    def _on_button_press(self, button: str):
        """Callback para botões pressionados"""
        if not self.enabled:
            return
        
        # B/Circle → Emergency Stop
        if button == 'button_b':
            print("🚨 EMERGENCY STOP")
            self.robot.stop_motors()
            self.stats['estops_triggered'] += 1
        
        # A/Cross → Switch camera
        elif button == 'button_a':
            now = time.time()
            if now - self.last_camera_switch > self.config.camera_switch_cooldown:
                print("📷 Switching camera...")
                self.robot.switch_camera()
                self.last_camera_switch = now
                self.stats['camera_switches'] += 1
        
        # X/Square → Home cabeça
        elif button == 'button_x':
            print("🏠 Home position")
            self.target_head_yaw = 90
            self.target_head_pitch = 90
            self.robot.arm.move_to_home()
        
        # Y/Triangle → Center cabeça
        elif button == 'button_y':
            print("🎯 Center cabeça")
            self.target_head_yaw = 90
            self.target_head_pitch = 90
            self.robot.arm.look_center()
        
        # D-Pad → Presets
        elif button == 'dpad_up':
            self._head_preset_forward()
        elif button == 'dpad_down':
            self._head_preset_down()
        elif button == 'dpad_left':
            self._head_preset_left()
        elif button == 'dpad_right':
            self._head_preset_right()
    
    # ========================================
    # PROCESSAMENTO
    # ========================================
    
    def _update_speed_mode(self, state: GamepadState):
        """Atualiza modo de velocidade baseado nos triggers"""
        # Left trigger → Slow
        if state.left_trigger > 0.5:
            if self.speed_mode != 'slow':
                self.speed_mode = 'slow'
                print("🐌 SLOW mode")
        
        # Right trigger → Turbo
        elif state.right_trigger > 0.5:
            if self.speed_mode != 'turbo':
                self.speed_mode = 'turbo'
                print("⚡ TURBO mode")
        
        # Normal
        else:
            if self.speed_mode != 'normal':
                self.speed_mode = 'normal'
                print("➡️  NORMAL mode")
    
    def _process_drive(self, state: GamepadState):
        """Processa movimento do robô"""
        # 🔧 Heartbeat para Safety (evita watchdog timeout)
        try:
            self.robot.safety.heartbeat()
        except Exception:
            pass
        
        # Ler sticks
        # Left Y → forward/backward (invertido porque stick pra cima = negativo)
        vx = -state.left_y * self.config.drive_sensitivity
        
        # Left X → strafe left/right
        vy = state.left_x * self.config.drive_sensitivity
        
        # Rotation pode ser mapeado para bumpers ou stick direito X
        # Usando bumpers: L1 = esquerda, R1 = direita
        vz = 0.0
        if state.left_bumper:
            vz = -0.5  # Girar esquerda
        elif state.right_bumper:
            vz = 0.5   # Girar direita
        
        # Aplicar escala de velocidade
        speed_scale = {
            'slow': self.config.slow_speed_scale,
            'normal': self.config.normal_speed_scale,
            'turbo': self.config.turbo_speed_scale
        }[self.speed_mode]
        
        vx *= speed_scale
        vy *= speed_scale
        vz *= speed_scale
        
        # Deadzone total (parar se input muito pequeno)
        if abs(vx) < 0.05 and abs(vy) < 0.05 and abs(vz) < 0.05:
            self.robot.stop_motors()
            return
        
        # Calcular PWM para Mecanum wheels
        # Mecanum permite movimento omnidirecional
        speed_base = 1500  # PWM base
        
        # Fórmula Mecanum:
        # FL = vx - vy - vz
        # BL = vx + vy - vz
        # FR = vx + vy + vz
        # BR = vx - vy + vz
        
        fl = int(speed_base * (vx - vy - vz))
        bl = int(speed_base * (vx + vy - vz))
        fr = int(speed_base * (vx + vy + vz))
        br = int(speed_base * (vx - vy + vz))
        
        # Aplicar ao robô
        self.robot.motor.set_motor_model(fl, bl, fr, br)
        self.stats['commands_sent'] += 1
    
    def _process_head(self, state: GamepadState):
        """Processa movimento da cabeça"""
        # Right stick → Pan (X) e Tilt (Y)
        pan_input = state.right_x * self.config.head_pan_sensitivity
        tilt_input = -state.right_y * self.config.head_tilt_sensitivity  # Invertido
        
        # Atualizar alvos
        if abs(pan_input) > 0.05:
            # Pan speed proporcional ao input
            pan_delta = pan_input * self.config.head_smooth_speed
            self.target_head_yaw += pan_delta
            
            # Clamp
            self.target_head_yaw = max(
                self.config.head_yaw_min,
                min(self.config.head_yaw_max, self.target_head_yaw)
            )
        
        if abs(tilt_input) > 0.05:
            tilt_delta = tilt_input * self.config.head_smooth_speed
            self.target_head_pitch += tilt_delta
            
            # Clamp
            self.target_head_pitch = max(
                self.config.head_pitch_min,
                min(self.config.head_pitch_max, self.target_head_pitch)
            )
        
        # Aplicar (sem smooth para responsividade)
        current_yaw = self.robot.arm.current_angles.get(0, 90)
        current_pitch = self.robot.arm.current_angles.get(1, 90)
        
        # Só mover se diferença significativa
        if abs(self.target_head_yaw - current_yaw) > 2:
            self.robot.arm.set_angle(0, int(self.target_head_yaw), smooth=False)
        
        if abs(self.target_head_pitch - current_pitch) > 2:
            self.robot.arm.set_angle(1, int(self.target_head_pitch), smooth=False)
    
    # ========================================
    # PRESETS
    # ========================================
    
    def _head_preset_forward(self):
        """Cabeça para frente (navegação)"""
        print("⬆️  Preset: Forward")
        self.target_head_yaw = 90
        self.target_head_pitch = 110
        self.robot.arm.set_angle(0, 90, smooth=True)
        self.robot.arm.set_angle(1, 110, smooth=True)
    
    def _head_preset_down(self):
        """Cabeça para baixo (chão)"""
        print("⬇️  Preset: Down")
        self.target_head_yaw = 90
        self.target_head_pitch = 140
        self.robot.arm.set_angle(0, 90, smooth=True)
        self.robot.arm.set_angle(1, 140, smooth=True)
    
    def _head_preset_left(self):
        """Cabeça para esquerda"""
        print("⬅️  Preset: Left")
        self.target_head_yaw = 45
        self.target_head_pitch = 110
        self.robot.arm.set_angle(0, 45, smooth=True)
        self.robot.arm.set_angle(1, 110, smooth=True)
    
    def _head_preset_right(self):
        """Cabeça para direita"""
        print("➡️  Preset: Right")
        self.target_head_yaw = 135
        self.target_head_pitch = 110
        self.robot.arm.set_angle(0, 135, smooth=True)
        self.robot.arm.set_angle(1, 110, smooth=True)
    
    # ========================================
    # STATUS
    # ========================================
    
    def get_status(self) -> Dict:
        """Retorna status do modo drone"""
        return {
            'enabled': self.enabled,
            'speed_mode': self.speed_mode,
            'target_head': {
                'yaw': self.target_head_yaw,
                'pitch': self.target_head_pitch
            },
            'stats': self.stats,
            'gamepad_connected': self.gamepad.is_connected()
        }


# ============================================================================
# TESTE STANDALONE
# ============================================================================

if __name__ == '__main__':
    print("\n⚠️  Este módulo requer EVARobot")
    print("Execute via eva_gamepad_server.py\n")