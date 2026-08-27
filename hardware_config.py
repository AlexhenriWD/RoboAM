#!/usr/bin/env python3
"""
EVA ROBOT - HARDWARE CONFIGURATION
Centraliza TODAS as configurações de hardware, limites e calibração
"""

from dataclasses import dataclass
from typing import Dict, Tuple


# ============================================================================
# CONFIGURAÇÃO DE PINOS GPIO
# ============================================================================

@dataclass
class PinConfig:
    """Configuração de pinos GPIO"""
    
    # Ultrasonic
    ULTRASONIC_TRIGGER: int = 27
    ULTRASONIC_ECHO: int = 22
    
    # Infrared (line tracking)
    INFRARED_LEFT: int = 14
    INFRARED_CENTER: int = 15
    INFRARED_RIGHT: int = 23
    
    # Buzzer
    BUZZER: int = 17
    
    # I2C
    I2C_BUS: int = 1
    PCA9685_ADDRESS: int = 0x40
    ADC_ADDRESS: int = 0x48


# ============================================================================
# CONFIGURAÇÃO DE MOTORES
# ============================================================================

@dataclass
class MotorConfig:
    """Configuração dos motores DC (4WD Mecanum)"""
    
    # Canais PWM (PCA9685)
    FL_FORWARD: int = 1   # Front Left Forward
    FL_BACKWARD: int = 0  # Front Left Backward
    
    BL_FORWARD: int = 2   # Back Left Forward
    BL_BACKWARD: int = 3  # Back Left Backward
    
    FR_FORWARD: int = 7   # Front Right Forward
    FR_BACKWARD: int = 6  # Front Right Backward
    
    BR_FORWARD: int = 5   # Back Right Forward
    BR_BACKWARD: int = 4  # Back Right Backward
    
    # Limites PWM
    PWM_MIN: int = 0
    PWM_MAX: int = 4095
    
    # Velocidades padrão
    DEFAULT_SPEED: int = 1500
    MAX_SAFE_SPEED: int = 3000
    MIN_SAFE_SPEED: int = 500
    
    # Compensação de direção (ajuste fino)
    # Se o robô puxa para um lado, ajuste aqui
    LEFT_COMPENSATION: float = 1.0   # Multiplicador lado esquerdo
    RIGHT_COMPENSATION: float = 1.0  # Multiplicador lado direito
    
    def get_motor_channels(self) -> Dict[str, Tuple[int, int]]:
        """Retorna mapeamento motor -> (canal_forward, canal_backward)"""
        return {
            'FL': (self.FL_FORWARD, self.FL_BACKWARD),
            'BL': (self.BL_FORWARD, self.BL_BACKWARD),
            'FR': (self.FR_FORWARD, self.FR_BACKWARD),
            'BR': (self.BR_FORWARD, self.BR_BACKWARD)
        }


# ============================================================================
# CONFIGURAÇÃO DE SERVOS (BRAÇO/CABEÇA)
# ============================================================================

@dataclass
class ServoLimits:
    """Limites de um servo individual"""
    min_angle: int
    max_angle: int
    home_angle: int
    name: str


class ServoConfig:
    """Configuração dos servos (braço como cabeça)"""
    
    # Canais PWM (PCA9685) - baseado no arm_calibration.py
    CHANNEL_MAP: Dict[str, int] = {
        '0': 8,   # Yaw (base - rotação)
        '1': 9,   # Pitch (ombro - altura)
        '2': 10,  # Cotovelo
        '3': 11,  # Cabeça extra
       
    }
    
    # Limites seguros (baseado no arm_calibration.py)
    LIMITS: Dict[int, ServoLimits] = {
        0: ServoLimits(min_angle=0, max_angle=180, home_angle=90, name="Yaw"),
        1: ServoLimits(min_angle=0, max_angle=180, home_angle=90, name="Pitch"),
        2: ServoLimits(min_angle=0, max_angle=180, home_angle=90, name="Cotovelo"),
        3: ServoLimits(min_angle=0, max_angle=180, home_angle=90, name="Cabeça"),
       
    }
    
    # Configurações de movimento
    PWM_FREQUENCY: int = 50  # Hz (padrão para servos)
    INITIAL_PULSE: int = 1500  # µs
    
    MIN_DELAY: float = 0.15  # Segundos entre comandos
    TOLERANCE_DEG: int = 2   # Tolerância para "já está na posição"
    
    # Movimento suave
    SMOOTH_STEP: int = 2         # Graus por passo
    SMOOTH_DELAY: float = 0.03   # Segundos entre passos
    
    @classmethod
    def get_limit(cls, channel: int) -> ServoLimits:
        """Retorna limites de um servo"""
        return cls.LIMITS.get(channel, ServoLimits(0, 180, 90, "Unknown"))
    
    @classmethod
    def angle_to_pulse(cls, angle: int, channel: str = '1') -> int:
        """
        Converte ângulo (0-180) para pulso PWM (500-2500µs)
        
        Baseado na fórmula do arm_calibration.py
        """
        # Canal 0 (yaw) é invertido
        if channel == '0':
            pulse = 2500 - int(angle / 0.09)
        else:
            pulse = 500 + int(angle / 0.09)
        
        return max(500, min(2500, pulse))


# ============================================================================
# CONFIGURAÇÃO DE CÂMERAS
# ============================================================================

@dataclass
class CameraConfig:
    """Configuração do sistema de câmeras"""
    
    # USB Webcam (navegação)
    USB_DEVICE_ID: int = 1  # /dev/video1
    USB_WIDTH: int = 640
    USB_HEIGHT: int = 480
    USB_FPS: int = 15
    
    # Pi Camera (cabeça/braço)
    PICAM_WIDTH: int = 640
    PICAM_HEIGHT: int = 480
    PICAM_FORMAT: str = "RGB888"
    
    # Streaming
    JPEG_QUALITY: int = 70  # 0-100
    STREAM_FPS: int = 15
    
    # Auto-switch
    HEAD_IDLE_TIMEOUT: float = 3.0  # Segundos sem movimento -> volta USB
    MOVEMENT_THRESHOLD: int = 5     # Graus mínimos para detectar movimento


# ============================================================================
# CONFIGURAÇÃO DE SENSORES
# ============================================================================

@dataclass
class SensorConfig:
    """Configuração de sensores"""
    
    # Ultrasonic
    ULTRASONIC_MAX_DISTANCE: float = 3.0  # Metros
    ULTRASONIC_TIMEOUT: float = 0.5       # Segundos
    
    # ADC
    ADC_COMMAND: int = 0x84
    ADC_VOLTAGE_V1: float = 3.3  # PCB v1
    ADC_VOLTAGE_V2: float = 5.2  # PCB v2
    
    # Leituras
    SENSOR_READ_INTERVAL: float = 0.1  # Segundos (10Hz)


# ============================================================================
# LIMITES DE SEGURANÇA
# ============================================================================

@dataclass
class SafetyLimits:
    """Limites de segurança do robô"""
    
    # Distâncias
    MIN_OBSTACLE_DISTANCE: float = 15.0  # cm
    EMERGENCY_STOP_DISTANCE: float = 10.0  # cm
    
    # Bateria
    LOW_BATTERY_VOLTAGE: float = 6.5   # V
    CRITICAL_BATTERY_VOLTAGE: float = 6.0  # V
    
    # Motores
    MAX_MOTOR_TEMP: float = 60.0  # °C (se tiver sensor)
    MOTOR_TIMEOUT: float = 5.0    # Segundos sem heartbeat
    
    # Inclinação (se tiver IMU)
    MAX_TILT_ANGLE: float = 45.0  # Graus
    
    # Timeouts
    WATCHDOG_TIMEOUT: float = 5.0     # Segundos
    COMMAND_TIMEOUT: float = 0.3      # Segundos (TTL padrão)
    HEARTBEAT_INTERVAL: float = 1.0   # Segundos


# ============================================================================
# POSES PRÉ-DEFINIDAS (BRAÇO/CABEÇA)
# ============================================================================

class PredefinedPoses:
    """Poses comuns do braço/cabeça"""
    
    HOME = {
        0: 90,   # Yaw
        1: 90,   # Pitch
        2: 90,   # Cotovelo
        3: 90,   # Cabeça
    }
    
    LOOK_FORWARD = {
        0: 90,   # Yaw
        1: 110,  # Pitch
        2: 90,   # Cotovelo
        3: 90,   # Cabeça
    }
    
    LOOK_DOWN = {
        0: 90,   # Yaw
        1: 110,  # Pitch -- teto físico real confirmado (era 140, inválido)
        2: 120,  # Cotovelo
    }
    
    SCAN_LEFT = {
        0: 45,   # Yaw
        1: 110,  # Pitch
    }
    
    SCAN_RIGHT = {
        0: 135,  # Yaw
        1: 110,  # Pitch
    }


# ============================================================================
# CONFIGURAÇÃO GLOBAL
# ============================================================================

class HardwareConfig:
    """Configuração global de hardware"""
    
    def __init__(self):
        self.pins = PinConfig()
        self.motors = MotorConfig()
        self.servos = ServoConfig()
        self.cameras = CameraConfig()
        self.sensors = SensorConfig()
        self.safety = SafetyLimits()
        self.poses = PredefinedPoses()
    
    def to_dict(self) -> dict:
        """Exporta configuração como dict"""
        return {
            'pins': self.pins.__dict__,
            'motors': self.motors.__dict__,
            'cameras': self.cameras.__dict__,
            'sensors': self.sensors.__dict__,
            'safety': self.safety.__dict__,
        }
    
    def validate(self) -> bool:
        """Valida configuração"""
        # Verificar limites PWM
        if self.motors.PWM_MAX > 4095:
            print("❌ PWM_MAX inválido (máx: 4095)")
            return False
        
        # Verificar ângulos dos servos
        for channel, limits in self.servos.LIMITS.items():
            if limits.min_angle < 0 or limits.max_angle > 180:
                print(f"❌ Limites inválidos para servo {channel}")
                return False
            
            if not (limits.min_angle <= limits.home_angle <= limits.max_angle):
                print(f"❌ Home fora dos limites para servo {channel}")
                return False
        
        print("✅ Configuração validada")
        return True


# ============================================================================
# INSTÂNCIA GLOBAL
# ============================================================================

# Singleton - importar em outros módulos
CONFIG = HardwareConfig()


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔧 EVA ROBOT - HARDWARE CONFIGURATION")
    print("="*60 + "\n")
    
    config = HardwareConfig()
    
    if config.validate():
        print("\n📋 CONFIGURAÇÃO:")
        print(f"\n🔌 Pinos:")
        print(f"   Ultrasonic: Trigger={config.pins.ULTRASONIC_TRIGGER}, Echo={config.pins.ULTRASONIC_ECHO}")
        print(f"   Buzzer: GPIO {config.pins.BUZZER}")
        
        print(f"\n🚗 Motores:")
        print(f"   PWM: {config.motors.PWM_MIN}-{config.motors.PWM_MAX}")
        print(f"   Velocidade padrão: {config.motors.DEFAULT_SPEED}")
        
        print(f"\n🦾 Servos:")
        for ch, limits in config.servos.LIMITS.items():
            print(f"   Canal {ch} ({limits.name}): {limits.min_angle}°-{limits.max_angle}° (home: {limits.home_angle}°)")
        
        print(f"\n📷 Câmeras:")
        print(f"   USB: /dev/video{config.cameras.USB_DEVICE_ID} ({config.cameras.USB_WIDTH}x{config.cameras.USB_HEIGHT})")
        print(f"   Pi Camera: {config.cameras.PICAM_WIDTH}x{config.cameras.PICAM_HEIGHT}")
        
        print(f"\n🛡️  Segurança:")
        print(f"   Distância mín: {config.safety.MIN_OBSTACLE_DISTANCE}cm")
        print(f"   Bateria baixa: {config.safety.LOW_BATTERY_VOLTAGE}V")
        print(f"   Watchdog: {config.safety.WATCHDOG_TIMEOUT}s")
    
    print("\n" + "="*60 + "\n")