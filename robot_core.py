"""
Robot Core Module
Consolidates all hardware control classes for the robot car.
Includes: PCA9685, Servo, Motor, Ultrasonic, Infrared, ADC, Buzzer, Camera
"""

import time
import math
import smbus
import warnings
from gpiozero import DistanceSensor, PWMSoftwareFallback, DistanceSensorNoEcho, OutputDevice, InputDevice
from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder, JpegEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform
from threading import Condition
import io
from hardware_config import ParameterManager


# ============================================================================
# PCA9685 - 16-Channel PWM Driver
# ============================================================================

class PCA9685:
    """Raspi PCA9685 16-Channel PWM Servo Driver"""
    
    # Registers
    __SUBADR1 = 0x02
    __SUBADR2 = 0x03
    __SUBADR3 = 0x04
    __MODE1 = 0x00
    __PRESCALE = 0xFE
    __LED0_ON_L = 0x06
    __LED0_ON_H = 0x07
    __LED0_OFF_L = 0x08
    __LED0_OFF_H = 0x09
    __ALLLED_ON_L = 0xFA
    __ALLLED_ON_H = 0xFB
    __ALLLED_OFF_L = 0xFC
    __ALLLED_OFF_H = 0xFD

    def __init__(self, address: int = 0x40, debug: bool = False):
        """Initialize the PCA9685 driver."""
        self.bus = smbus.SMBus(1)
        self.address = address
        self.debug = debug
        self.write(self.__MODE1, 0x00)
    
    def write(self, reg: int, value: int) -> None:
        """Write an 8-bit value to the specified register."""
        self.bus.write_byte_data(self.address, reg, value)
      
    def read(self, reg: int) -> int:
        """Read an unsigned byte from the I2C device."""
        return self.bus.read_byte_data(self.address, reg)
    
    def set_pwm_freq(self, freq: float) -> None:
        """Set the PWM frequency."""
        prescaleval = 25000000.0 / 4096.0 / float(freq) - 1.0
        prescale = math.floor(prescaleval + 0.5)

        oldmode = self.read(self.__MODE1)
        newmode = (oldmode & 0x7F) | 0x10
        self.write(self.__MODE1, newmode)
        self.write(self.__PRESCALE, int(math.floor(prescale)))
        self.write(self.__MODE1, oldmode)
        time.sleep(0.005)
        self.write(self.__MODE1, oldmode | 0x80)

    def set_pwm(self, channel: int, on: int, off: int) -> None:
        """Set a single PWM channel."""
        self.write(self.__LED0_ON_L + 4 * channel, on & 0xFF)
        self.write(self.__LED0_ON_H + 4 * channel, on >> 8)
        self.write(self.__LED0_OFF_L + 4 * channel, off & 0xFF)
        self.write(self.__LED0_OFF_H + 4 * channel, off >> 8)
    
    def set_motor_pwm(self, channel: int, duty: int) -> None:
        """Set the PWM duty cycle for a motor."""
        self.set_pwm(channel, 0, duty)

    def set_servo_pulse(self, channel: int, pulse: float) -> None:
        """Set the Servo Pulse (PWM frequency must be 50Hz)."""
        pulse = pulse * 4096 / 20000
        self.set_pwm(channel, 0, int(pulse))

    def close(self) -> None:
        """Close the I2C bus."""
        self.bus.close()


# ============================================================================
# Servo Controller
# ============================================================================

class Servo:
    """Servo motor controller using PCA9685."""
    
    def __init__(self):
        """Initialize the Servo controller."""
        self.pwm_frequency = 50
        self.initial_pulse = 1500
        self.pwm_channel_map = {
            '0': 8, '1': 9, '2': 10, '3': 11,
            '4': 12, '5': 13, '6': 14, '7': 15
        }
        self.pwm_servo = PCA9685(0x40, debug=True)
        self.pwm_servo.set_pwm_freq(self.pwm_frequency)
        for channel in self.pwm_channel_map.values():
            self.pwm_servo.set_servo_pulse(channel, self.initial_pulse)

    def set_servo_pwm(self, channel: str, angle: int, error: int = 10) -> None:
        """Set servo position by angle."""
        angle = int(angle)
        if channel not in self.pwm_channel_map:
            raise ValueError(f"Invalid channel: {channel}")
        
        pulse = 2500 - int((angle + error) / 0.09) if channel == '0' else 500 + int((angle + error) / 0.09)
        self.pwm_servo.set_servo_pulse(self.pwm_channel_map[channel], pulse)


# ============================================================================
# Motor Controller
# ============================================================================

class Ordinary_Car:
    """4-wheel motor controller for the robot car."""
    
    def __init__(self):
        """Initialize the motor controller."""
        self.pwm = PCA9685(0x40, debug=True)
        self.pwm.set_pwm_freq(50)
    
    def duty_range(self, duty1, duty2, duty3, duty4):
        """Limit duty cycle values to valid range."""
        duties = [duty1, duty2, duty3, duty4]
        for i in range(4):
            if duties[i] > 4095:
                duties[i] = 4095
            elif duties[i] < -4095:
                duties[i] = -4095
        return tuple(duties)
    
    def left_upper_wheel(self, duty):
        """Control left upper wheel."""
        if duty > 0:
            self.pwm.set_motor_pwm(0, 0)
            self.pwm.set_motor_pwm(1, duty)
        elif duty < 0:
            self.pwm.set_motor_pwm(1, 0)
            self.pwm.set_motor_pwm(0, abs(duty))
        else:
            self.pwm.set_motor_pwm(0, 4095)
            self.pwm.set_motor_pwm(1, 4095)
    
    def left_lower_wheel(self, duty):
        """Control left lower wheel."""
        if duty > 0:
            self.pwm.set_motor_pwm(3, 0)
            self.pwm.set_motor_pwm(2, duty)
        elif duty < 0:
            self.pwm.set_motor_pwm(2, 0)
            self.pwm.set_motor_pwm(3, abs(duty))
        else:
            self.pwm.set_motor_pwm(2, 4095)
            self.pwm.set_motor_pwm(3, 4095)
    
    def right_upper_wheel(self, duty):
        """Control right upper wheel."""
        if duty > 0:
            self.pwm.set_motor_pwm(6, 0)
            self.pwm.set_motor_pwm(7, duty)
        elif duty < 0:
            self.pwm.set_motor_pwm(7, 0)
            self.pwm.set_motor_pwm(6, abs(duty))
        else:
            self.pwm.set_motor_pwm(6, 4095)
            self.pwm.set_motor_pwm(7, 4095)
    
    def right_lower_wheel(self, duty):
        """Control right lower wheel."""
        if duty > 0:
            self.pwm.set_motor_pwm(4, 0)
            self.pwm.set_motor_pwm(5, duty)
        elif duty < 0:
            self.pwm.set_motor_pwm(5, 0)
            self.pwm.set_motor_pwm(4, abs(duty))
        else:
            self.pwm.set_motor_pwm(4, 4095)
            self.pwm.set_motor_pwm(5, 4095)
    
    def set_motor_model(self, duty1, duty2, duty3, duty4):
        """Set all four motors with specified duty cycles."""
        duty1, duty2, duty3, duty4 = self.duty_range(duty1, duty2, duty3, duty4)
        self.left_upper_wheel(duty1)
        self.left_lower_wheel(duty2)
        self.right_upper_wheel(duty3)
        self.right_lower_wheel(duty4)

    def close(self):
        """Stop all motors and close PWM."""
        self.set_motor_model(0, 0, 0, 0)
        self.pwm.close()


# ============================================================================
# Ultrasonic Distance Sensor
# ============================================================================

class Ultrasonic:
    """Ultrasonic distance sensor controller."""
    
    def __init__(self, trigger_pin: int = 27, echo_pin: int = 22, max_distance: float = 3.0):
        """Initialize the ultrasonic sensor."""
        warnings.filterwarnings("ignore", category=DistanceSensorNoEcho)
        warnings.filterwarnings("ignore", category=PWMSoftwareFallback)
        self.trigger_pin = trigger_pin
        self.echo_pin = echo_pin
        self.max_distance = max_distance
        self.sensor = DistanceSensor(
            echo=self.echo_pin,
            trigger=self.trigger_pin,
            max_distance=self.max_distance
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def get_distance(self) -> float:
        """Get distance measurement in centimeters."""
        try:
            distance = self.sensor.distance * 100
            return round(float(distance), 1)
        except RuntimeWarning as e:
            print(f"Warning: {e}")
            return None

    def close(self):
        """Close the distance sensor."""
        self.sensor.close()


# ============================================================================
# Infrared Line Tracking Sensors
# ============================================================================

class Infrared:
    """Infrared line tracking sensor controller."""
    
    def __init__(self):
        """Initialize infrared sensors."""
        self.IR01 = 14
        self.IR02 = 15
        self.IR03 = 23
        self.infrared_01 = InputDevice(self.IR01)
        self.infrared_02 = InputDevice(self.IR02)
        self.infrared_03 = InputDevice(self.IR03)

    def read_infrared(self, pin_number: int) -> int:
        """Read a single infrared sensor."""
        if pin_number == self.IR01:
            return 0 if self.infrared_01.is_active else 1
        elif pin_number == self.IR02:
            return 0 if self.infrared_02.is_active else 1
        elif pin_number == self.IR03:
            return 0 if self.infrared_03.is_active else 1
        return -1

    def read_all_infrared(self) -> int:
        """Read all infrared sensors and return combined value."""
        val_01 = self.read_infrared(self.IR01)
        val_02 = self.read_infrared(self.IR02)
        val_03 = self.read_infrared(self.IR03)
        return val_01 * 4 + val_02 * 2 + val_03

    def close(self):
        """Close all infrared sensors."""
        self.infrared_01.close()
        self.infrared_02.close()
        self.infrared_03.close()


# ============================================================================
# ADC (Analog to Digital Converter)
# ============================================================================

class ADC:
    """ADC controller for analog sensors (photoresistors, voltage)."""
    
    def __init__(self):
        """Initialize the ADC."""
        self.I2C_ADDRESS = 0x48
        self.ADS7830_COMMAND = 0x84
        self.parameter_manager = ParameterManager()
        self.pcb_version = self.parameter_manager.get_pcb_version()
        self.adc_voltage_coefficient = 3.3 if self.pcb_version == 1 else 5.2
        self.i2c_bus = smbus.SMBus(1)

    def _read_stable_byte(self) -> int:
        """Read a stable byte from the ADC."""
        while True:
            value1 = self.i2c_bus.read_byte(self.I2C_ADDRESS)
            value2 = self.i2c_bus.read_byte(self.I2C_ADDRESS)
            if value1 == value2:
                return value1

    def read_adc(self, channel: int) -> float:
        """Read the ADC value for the specified channel."""
        command_set = self.ADS7830_COMMAND | ((((channel << 2) | (channel >> 1)) & 0x07) << 4)
        self.i2c_bus.write_byte(self.I2C_ADDRESS, command_set)
        value = self._read_stable_byte()
        voltage = value / 255.0 * self.adc_voltage_coefficient
        return round(voltage, 2)

    def scan_i2c_bus(self) -> None:
        """Scan the I2C bus for connected devices."""
        print("Scanning I2C bus...")
        for device in range(128):
            try:
                self.i2c_bus.read_byte_data(device, 0)
                print(f"Device found at address: 0x{device:02X}")
            except OSError:
                pass

    def close_i2c(self) -> None:
        """Close the I2C bus."""
        self.i2c_bus.close()


# ============================================================================
# Buzzer
# ============================================================================

class Buzzer:
    """Buzzer controller."""
    
    def __init__(self):
        """Initialize the buzzer."""
        self.PIN = 17
        self.buzzer_pin = OutputDevice(self.PIN)

    def set_state(self, state: bool) -> None:
        """Set the state of the buzzer."""
        self.buzzer_pin.on() if state else self.buzzer_pin.off()

    def close(self) -> None:
        """Close the buzzer pin."""
        self.buzzer_pin.close()


# ============================================================================
# Camera System
# ============================================================================

class StreamingOutput(io.BufferedIOBase):
    """Streaming output buffer for camera."""
    
    def __init__(self):
        """Initialize streaming output."""
        self.frame = None
        self.condition = Condition()

    def write(self, buf: bytes) -> int:
        """Write buffer to frame and notify waiting threads."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        return len(buf)


class Camera:
    """Camera controller for Raspberry Pi Camera."""
    
    def __init__(self, preview_size: tuple = (640, 480), hflip: bool = True, 
                 vflip: bool = True, stream_size: tuple = (400, 300)):
        """Initialize the camera."""
        self.camera = Picamera2()
        self.transform = Transform(hflip=1 if hflip else 0, vflip=1 if vflip else 0)
        preview_config = self.camera.create_preview_configuration(
            main={"size": preview_size},
            transform=self.transform
        )
        self.camera.configure(preview_config)
        
        self.stream_size = stream_size
        self.stream_config = self.camera.create_video_configuration(
            main={"size": stream_size},
            transform=self.transform
        )
        self.streaming_output = StreamingOutput()
        self.streaming = False

    def start_image(self) -> None:
        """Start camera preview and capture."""
        self.camera.start_preview(Preview.QTGL)
        self.camera.start()

    def save_image(self, filename: str) -> dict:
        """Capture and save an image."""
        try:
            metadata = self.camera.capture_file(filename)
            return metadata
        except Exception as e:
            print(f"Error capturing image: {e}")
            return None

    def start_stream(self, filename: str = None) -> None:
        """Start video stream or recording."""
        if not self.streaming:
            if self.camera.started:
                self.camera.stop()
            
            self.camera.configure(self.stream_config)
            if filename:
                encoder = H264Encoder()
                output = FileOutput(filename)
            else:
                encoder = JpegEncoder()
                output = FileOutput(self.streaming_output)
            self.camera.start_recording(encoder, output)
            self.streaming = True

    def stop_stream(self) -> None:
        """Stop video stream or recording."""
        if self.streaming:
            try:
                self.camera.stop_recording()
                self.streaming = False
            except Exception as e:
                print(f"Error stopping stream: {e}")

    def get_frame(self) -> bytes:
        """Get current frame from streaming output."""
        with self.streaming_output.condition:
            self.streaming_output.condition.wait()
            return self.streaming_output.frame

    def save_video(self, filename: str, duration: int = 10) -> None:
        """Save a video for specified duration."""
        self.start_stream(filename)
        time.sleep(duration)
        self.stop_stream()

    def close(self) -> None:
        """Close the camera."""
        if self.streaming:
            self.stop_stream()
        self.camera.close()


# ============================================================================
# Main Testing
# ============================================================================

if __name__ == '__main__':
    print('Robot Core Module - Testing Individual Components')
    print('This module should be imported, not run directly.')
    print('Individual component tests should be done through dedicated test scripts.')