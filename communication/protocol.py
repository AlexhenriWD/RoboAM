"""
communication/protocol.py - Communication protocol between main computer and Raspberry Pi
"""

import json
import time
from enum import Enum

class CommandType(Enum):
    """Types of commands that can be sent to the car"""
    MOVEMENT = "movement"  # Basic movement commands
    CAMERA = "camera"      # Camera control
    SERVO = "servo"        # Servo control
    LED = "led"            # LED control
    BUZZER = "buzzer"      # Buzzer control
    MODE = "mode"          # Car operation mode
    QUERY = "query"        # Query sensor data
    SYSTEM = "system"      # System-level commands (shutdown, reboot, etc.)

class MovementType(Enum):
    """Types of movement commands"""
    FORWARD = "forward"
    BACKWARD = "backward"
    LEFT = "left"
    RIGHT = "right"
    STOP = "stop"
    LEFT_TRANSLATE = "left_translate"    # Mecanum wheel sideways movement
    RIGHT_TRANSLATE = "right_translate"  # Mecanum wheel sideways movement
    FRONT_LEFT_DIAGONAL = "front_left_diagonal"    # Mecanum wheel diagonal movement
    FRONT_RIGHT_DIAGONAL = "front_right_diagonal"  # Mecanum wheel diagonal movement
    REAR_LEFT_DIAGONAL = "rear_left_diagonal"      # Mecanum wheel diagonal movement
    REAR_RIGHT_DIAGONAL = "rear_right_diagonal"    # Mecanum wheel diagonal movement
    ROTATE = "rotate"      # In-place rotation

class Command:
    """Command object that can be serialized for transmission"""
    
    def __init__(self, command_type, data=None):
        """
        Initialize a new command
        
        Args:
            command_type (CommandType): Type of command
            data (dict): Command data
        """
        self.command_type = command_type
        self.data = data or {}
        self.timestamp = time.time()
        self.id = f"{int(self.timestamp * 1000)}"
    
    def to_json(self):
        """Convert command to JSON string"""
        cmd_dict = {
            "command_type": self.command_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "id": self.id
        }
        return json.dumps(cmd_dict)
    
    @classmethod
    def from_json(cls, json_str):
        """Create command from JSON string"""
        cmd_dict = json.loads(json_str)
        cmd = cls(CommandType(cmd_dict["command_type"]))
        cmd.data = cmd_dict["data"]
        cmd.timestamp = cmd_dict["timestamp"]
        cmd.id = cmd_dict["id"]
        return cmd

def create_movement_command(movement_type, speed=2000, duration=None):
    """
    Create a movement command
    
    Args:
        movement_type (MovementType): Type of movement
        speed (int): Speed of movement (0-4056)
        duration (float, optional): Duration of movement in seconds
    
    Returns:
        Command: Movement command
    """
    data = {
        "movement_type": movement_type.value,
        "speed": speed
    }
    
    if duration is not None:
        data["duration"] = duration
    
    return Command(CommandType.MOVEMENT, data)

def create_motor_command(fl, bl, fr, br):
    """
    Create a command to directly control the four motors
    
    Args:
        fl (int): Front left motor speed (-4056 to 4056)
        bl (int): Back left motor speed (-4056 to 4056)
        fr (int): Front right motor speed (-4056 to 4056)
        br (int): Back right motor speed (-4056 to 4056)
    
    Returns:
        Command: Motor command
    """
    data = {
        "movement_type": "direct",
        "fl": fl,
        "bl": bl,
        "fr": fr,
        "br": br
    }
    
    return Command(CommandType.MOVEMENT, data)

def create_servo_command(servo_id, angle):
    """
    Create a command to control a servo
    
    Args:
        servo_id (str): Servo ID ('0' or '1')
        angle (int): Servo angle (0-180)
    
    Returns:
        Command: Servo command
    """
    data = {
        "servo_id": servo_id,
        "angle": angle
    }
    
    return Command(CommandType.SERVO, data)

def create_camera_command(action, value=None):
    """
    Create a command to control the camera
    
    Args:
        action (str): Camera action (capture, stream_start, stream_stop)
        value (any, optional): Additional value for the action
    
    Returns:
        Command: Camera command
    """
    data = {
        "action": action
    }
    
    if value is not None:
        data["value"] = value
    
    return Command(CommandType.CAMERA, data)

def create_led_command(led_id, r, g, b):
    """
    Create a command to control an LED
    
    Args:
        led_id (int): LED ID (0-7 or 0xFF for all)
        r (int): Red value (0-255)
        g (int): Green value (0-255)
        b (int): Blue value (0-255)
    
    Returns:
        Command: LED command
    """
    data = {
        "led_id": led_id,
        "r": r,
        "g": g,
        "b": b
    }
    
    return Command(CommandType.LED, data)

def create_mode_command(mode):
    """
    Create a command to set the car's operation mode
    
    Args:
        mode (int): Mode (0: manual, 1: light_tracking, 2: line_tracking, 3: obstacle_avoidance)
    
    Returns:
        Command: Mode command
    """
    data = {
        "mode": mode
    }
    
    return Command(CommandType.MODE, data)

class Response:
    """Response object for feedback from the car"""
    
    def __init__(self, status, command_id=None, data=None):
        """
        Initialize a new response
        
        Args:
            status (str): Status of the command (success, error)
            command_id (str, optional): ID of the command this is responding to
            data (dict, optional): Additional response data
        """
        self.status = status
        self.command_id = command_id
        self.data = data or {}
        self.timestamp = time.time()
    
    def to_json(self):
        """Convert response to JSON string"""
        resp_dict = {
            "status": self.status,
            "command_id": self.command_id,
            "data": self.data,
            "timestamp": self.timestamp
        }
        return json.dumps(resp_dict)
    
    @classmethod
    def from_json(cls, json_str):
        """Create response from JSON string"""
        resp_dict = json.loads(json_str)
        resp = cls(resp_dict["status"], resp_dict["command_id"])
        resp.data = resp_dict["data"]
        resp.timestamp = resp_dict["timestamp"]
        return resp