#!/usr/bin/env python3
"""
EVA ROBOT - SAFETY SYSTEM
Sistema de segurança: watchdog, emergency stop, limites
"""

import time
from typing import Optional, Callable, Dict
from collections import deque
from dataclasses import dataclass
from enum import Enum

from hardware_config import CONFIG


# ============================================================================
# TIPOS E ENUMS
# ============================================================================

class SafetyLevel(Enum):
    """Níveis de alerta de segurança"""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class SafetyWarning:
    """Registro de warning de segurança"""
    timestamp: float
    level: SafetyLevel
    message: str
    sensor: Optional[str] = None
    value: Optional[float] = None


# ============================================================================
# WATCHDOG
# ============================================================================

class Watchdog:
    """
    Watchdog Timer - monitora heartbeats
    Se não receber heartbeat no prazo, aciona estop
    """
    
    def __init__(self, timeout: float = None):
        self.timeout = timeout or CONFIG.safety.WATCHDOG_TIMEOUT
        self.last_heartbeat = time.time()
        self.enabled = True
        self.on_timeout: Optional[Callable] = None
    
    def feed(self):
        """Alimenta o watchdog (heartbeat recebido)"""
        self.last_heartbeat = time.time()
    
    def check(self) -> bool:
        """
        Verifica se watchdog expirou
        
        Returns:
            True se OK, False se timeout
        """
        if not self.enabled:
            return True
        
        elapsed = time.time() - self.last_heartbeat
        
        if elapsed > self.timeout:
            if self.on_timeout:
                self.on_timeout(elapsed)
            return False
        
        return True
    
    def reset(self):
        """Reseta watchdog"""
        self.last_heartbeat = time.time()
    
    def disable(self):
        """Desabilita watchdog (CUIDADO!)"""
        self.enabled = False
    
    def enable(self):
        """Habilita watchdog"""
        self.enabled = True
        self.reset()


# ============================================================================
# SAFETY CONTROLLER
# ============================================================================

class SafetyController:
    """
    Controlador de Segurança Principal
    
    Funções:
    - Monitora sensores
    - Valida comandos
    - Aciona emergency stop
    - Mantém log de warnings
    """
    
    def __init__(self, robot_core):
        self.robot = robot_core
        
        # Estado
        self.enabled = True
        self.emergency_stop_active = False
        self.safety_level = SafetyLevel.NORMAL
        
        # Warnings
        self.warnings = deque(maxlen=100)
        self.warning_callbacks = []
        
        # Watchdog
        self.watchdog = Watchdog(CONFIG.safety.WATCHDOG_TIMEOUT)
        self.watchdog.on_timeout = self._watchdog_timeout
        
        # Última leitura de sensores
        self.last_sensor_data: Dict = {}
        
        print("✅ Safety Controller inicializado")
    
    # ========================================
    # VALIDAÇÃO DE COMANDOS
    # ========================================
    
    def validate_drive_command(
        self, 
        vx: float, 
        vy: float, 
        vz: float
    ) -> tuple[bool, str]:
        """
        Valida comando de movimento
        
        Returns:
            (is_safe, reason)
        """
        if not self.enabled:
            return True, "Safety desabilitado"
        
        if self.emergency_stop_active:
            return False, "EMERGENCY STOP ativo"
        
        # Verificar se está indo para frente
        if vx > 0:
            # Ler sensor ultrasonic
            distance = self.last_sensor_data.get('ultrasonic_cm')
            
            if distance is not None:
                # Obstáculo muito próximo
                if distance < CONFIG.safety.EMERGENCY_STOP_DISTANCE:
                    self.trigger_emergency_stop(
                        f"Obstáculo crítico: {distance:.1f}cm"
                    )
                    return False, f"Obstáculo muito próximo ({distance:.1f}cm)"
                
                # Warning
                if distance < CONFIG.safety.MIN_OBSTACLE_DISTANCE:
                    self.add_warning(
                        SafetyLevel.WARNING,
                        f"Obstáculo detectado: {distance:.1f}cm",
                        sensor="ultrasonic",
                        value=distance
                    )
                    return False, f"Obstáculo próximo ({distance:.1f}cm)"
        
        # Verificar bateria
        battery_v = self.last_sensor_data.get('battery_v')
        
        if battery_v is not None:
            if battery_v < CONFIG.safety.CRITICAL_BATTERY_VOLTAGE:
                self.trigger_emergency_stop(
                    f"Bateria crítica: {battery_v:.1f}V"
                )
                return False, f"Bateria crítica ({battery_v:.1f}V)"
            
            if battery_v < CONFIG.safety.LOW_BATTERY_VOLTAGE:
                self.add_warning(
                    SafetyLevel.WARNING,
                    f"Bateria baixa: {battery_v:.1f}V",
                    sensor="battery",
                    value=battery_v
                )
        
        return True, "OK"
    
    def validate_servo_command(
        self, 
        channel: int, 
        angle: int
    ) -> tuple[bool, str]:
        """
        Valida comando de servo
        
        Returns:
            (is_safe, reason)
        """
        if not self.enabled:
            return True, "Safety desabilitado"
        
        if self.emergency_stop_active:
            return False, "EMERGENCY STOP ativo"
        
        # Verificar limites
        limits = CONFIG.servos.get_limit(channel)
        
        if not (limits.min_angle <= angle <= limits.max_angle):
            return False, f"Ângulo fora dos limites ({limits.min_angle}°-{limits.max_angle}°)"
        
        return True, "OK"
    
    # ========================================
    # MONITORAMENTO DE SENSORES
    # ========================================
    
    def update_sensor_data(self, sensor_data: Dict):
        """
        Atualiza leituras de sensores e verifica limites
        
        Args:
            sensor_data: {"ultrasonic_cm": float, "battery_v": float, ...}
        """
        self.last_sensor_data = sensor_data
        
        # Verificar bateria
        if 'battery_v' in sensor_data:
            voltage = sensor_data['battery_v']
            
            if voltage < CONFIG.safety.CRITICAL_BATTERY_VOLTAGE:
                self.add_warning(
                    SafetyLevel.CRITICAL,
                    f"Bateria crítica: {voltage:.1f}V",
                    sensor="battery",
                    value=voltage
                )
            elif voltage < CONFIG.safety.LOW_BATTERY_VOLTAGE:
                self.add_warning(
                    SafetyLevel.WARNING,
                    f"Bateria baixa: {voltage:.1f}V",
                    sensor="battery",
                    value=voltage
                )
        
        # Verificar distância
        if 'ultrasonic_cm' in sensor_data:
            distance = sensor_data['ultrasonic_cm']
            
            if distance < CONFIG.safety.EMERGENCY_STOP_DISTANCE:
                self.add_warning(
                    SafetyLevel.CRITICAL,
                    f"Obstáculo muito próximo: {distance:.1f}cm",
                    sensor="ultrasonic",
                    value=distance
                )
    
    # ========================================
    # EMERGENCY STOP
    # ========================================
    
    def trigger_emergency_stop(self, reason: str):
        """
        Aciona parada de emergência
        
        Para TODOS os motores imediatamente
        """
        if self.emergency_stop_active:
            return  # Já ativo
        
        self.emergency_stop_active = True
        self.safety_level = SafetyLevel.EMERGENCY
        
        # Parar robô
        try:
            self.robot.stop()
        except Exception as e:
            print(f"❌ Erro ao parar robô: {e}")
        
        # Log
        self.add_warning(
            SafetyLevel.EMERGENCY,
            f"EMERGENCY STOP: {reason}",
            sensor="system"
        )
        
        print(f"\n🚨 PARADA DE EMERGÊNCIA: {reason}\n")
    
    def reset_emergency_stop(self) -> bool:
        """
        Reseta emergency stop
        
        Returns:
            True se resetado com sucesso
        """
        if not self.emergency_stop_active:
            return True
        
        # Verificar se é seguro resetar
        safe, reason = self._check_safe_to_reset()
        
        if not safe:
            print(f"⚠️  Não é seguro resetar: {reason}")
            return False
        
        self.emergency_stop_active = False
        self.safety_level = SafetyLevel.NORMAL
        self.watchdog.reset()
        
        print("✅ Emergency stop resetado")
        return True
    
    def _check_safe_to_reset(self) -> tuple[bool, str]:
        """Verifica se é seguro resetar emergency stop"""
        
        # Verificar bateria
        battery_v = self.last_sensor_data.get('battery_v')
        if battery_v and battery_v < CONFIG.safety.CRITICAL_BATTERY_VOLTAGE:
            return False, f"Bateria ainda crítica: {battery_v:.1f}V"
        
        # Verificar obstáculos
        distance = self.last_sensor_data.get('ultrasonic_cm')
        if distance and distance < CONFIG.safety.EMERGENCY_STOP_DISTANCE:
            return False, f"Obstáculo ainda presente: {distance:.1f}cm"
        
        return True, "OK"
    
    # ========================================
    # WARNINGS
    # ========================================
    
    def add_warning(
        self,
        level: SafetyLevel,
        message: str,
        sensor: Optional[str] = None,
        value: Optional[float] = None
    ):
        """Adiciona warning ao log"""
        
        warning = SafetyWarning(
            timestamp=time.time(),
            level=level,
            message=message,
            sensor=sensor,
            value=value
        )
        
        self.warnings.append(warning)
        
        # Atualizar nível de segurança
        if level.value == SafetyLevel.EMERGENCY.value:
            self.safety_level = SafetyLevel.EMERGENCY
        elif level.value == SafetyLevel.CRITICAL.value and self.safety_level != SafetyLevel.EMERGENCY:
            self.safety_level = SafetyLevel.CRITICAL
        elif level.value == SafetyLevel.WARNING.value and self.safety_level == SafetyLevel.NORMAL:
            self.safety_level = SafetyLevel.WARNING
        
        # Callbacks
        for callback in self.warning_callbacks:
            try:
                callback(warning)
            except Exception as e:
                print(f"❌ Erro em callback: {e}")
        
        # Log
        symbols = {
            SafetyLevel.NORMAL: "ℹ️ ",
            SafetyLevel.WARNING: "⚠️ ",
            SafetyLevel.CRITICAL: "🔴",
            SafetyLevel.EMERGENCY: "🚨"
        }
        
        symbol = symbols.get(level, "⚠️ ")
        print(f"{symbol} SAFETY [{level.value.upper()}]: {message}")
    
    def get_recent_warnings(self, count: int = 10) -> list:
        """Retorna warnings recentes"""
        return list(self.warnings)[-count:]
    
    def clear_warnings(self):
        """Limpa histórico de warnings"""
        self.warnings.clear()
        self.safety_level = SafetyLevel.NORMAL
    
    # ========================================
    # WATCHDOG
    # ========================================
    
    def heartbeat(self):
        """Recebe heartbeat (mantém watchdog ativo)"""
        self.watchdog.feed()
    
    def _watchdog_timeout(self, elapsed: float):
        """Callback quando watchdog expira"""
        self.trigger_emergency_stop(
            f"Watchdog timeout ({elapsed:.1f}s sem heartbeat)"
        )
    
    # ========================================
    # CONTROLE
    # ========================================
    
    def enable(self):
        """Habilita sistema de segurança"""
        self.enabled = True
        self.watchdog.enable()
        print("✅ Safety habilitado")
    
    def disable(self):
        """Desabilita sistema de segurança (CUIDADO!)"""
        self.enabled = False
        self.watchdog.disable()
        print("⚠️  Safety DESABILITADO")
    
    def get_status(self) -> Dict:
        """Retorna status do sistema de segurança"""
        return {
            'enabled': self.enabled,
            'emergency_stop': self.emergency_stop_active,
            'level': self.safety_level.value,
            'watchdog_ok': self.watchdog.check(),
            'recent_warnings': len(self.get_recent_warnings()),
            'last_sensor_data': self.last_sensor_data
        }


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🛡️  EVA ROBOT - SAFETY SYSTEM TEST")
    print("="*60 + "\n")
    
    # Mock robot
    class MockRobot:
        def stop(self):
            print("🛑 Robot stopped")
    
    robot = MockRobot()
    safety = SafetyController(robot)
    
    # Teste 1: Validação de comando normal
    print("1️⃣  Teste: Comando normal")
    safety.update_sensor_data({'ultrasonic_cm': 50.0, 'battery_v': 7.5})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 2: Obstáculo próximo
    print("2️⃣  Teste: Obstáculo próximo")
    safety.update_sensor_data({'ultrasonic_cm': 12.0, 'battery_v': 7.5})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 3: Obstáculo crítico
    print("3️⃣  Teste: Obstáculo crítico")
    safety.update_sensor_data({'ultrasonic_cm': 8.0, 'battery_v': 7.5})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 4: Bateria baixa
    print("4️⃣  Teste: Bateria baixa")
    safety.emergency_stop_active = False  # Reset
    safety.update_sensor_data({'ultrasonic_cm': 50.0, 'battery_v': 6.3})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 5: Status
    print("5️⃣  Status final:")
    status = safety.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    print("\n" + "="*60 + "\n")