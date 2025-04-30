"""
car_control/movement_controller.py - High-level movement abstractions
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

class MovementController:
    """High-level movement controller for the car"""
    
    def __init__(self):
        """Initialize the movement controller"""
        logger.info("Movement controller initialized")
    
    def move_with_path(self, path_points: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """
        Generate movement commands to follow a path
        
        Args:
            path_points (List[Tuple[float, float]]): Path points as (x, y) coordinates
        
        Returns:
            List[Dict[str, Any]]: List of movement commands
        """
        if not path_points or len(path_points) < 2:
            logger.warning("Path needs at least 2 points")
            return []
        
        commands = []
        
        for i in range(1, len(path_points)):
            prev_point = path_points[i-1]
            curr_point = path_points[i]
            
            # Calculate direction vector
            dx = curr_point[0] - prev_point[0]
            dy = curr_point[1] - prev_point[1]
            
            # Determine movement type and distance
            movement_cmd = self._get_movement_command(dx, dy)
            if movement_cmd:
                commands.append(movement_cmd)
        
        return commands
    
    def _get_movement_command(self, dx: float, dy: float) -> Optional[Dict[str, Any]]:
        """
        Get movement command for a direction vector
        
        Args:
            dx (float): X component of direction vector
            dy (float): Y component of direction vector
        
        Returns:
            Optional[Dict[str, Any]]: Movement command
        """
        # Determine dominant direction
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        
        # Calculate magnitude for speed
        magnitude = (abs_dx**2 + abs_dy**2)**0.5
        speed = min(int(magnitude * 500), 4000)  # Scale speed, max 4000
        
        if abs_dx < 0.1 and abs_dy < 0.1:
            # Too small movement, skip
            return None
        
        # Pure X movement
        if abs_dx > 0 and abs_dy < 0.1:
            if dx > 0:
                return {
                    "command_type": "movement",
                    "movement_type": "right_translate",
                    "speed": speed
                }
            else:
                return {
                    "command_type": "movement",
                    "movement_type": "left_translate",
                    "speed": speed
                }
        
        # Pure Y movement
        if abs_dx < 0.1 and abs_dy > 0:
            if dy > 0:
                return {
                    "command_type": "movement",
                    "movement_type": "forward",
                    "speed": speed
                }
            else:
                return {
                    "command_type": "movement",
                    "movement_type": "backward",
                    "speed": speed
                }
        
        # Diagonal movement
        if dx > 0 and dy > 0:
            return {
                "command_type": "movement",
                "movement_type": "front_right_diagonal",
                "speed": speed
            }
        elif dx < 0 and dy > 0:
            return {
                "command_type": "movement",
                "movement_type": "front_left_diagonal",
                "speed": speed
            }
        elif dx > 0 and dy < 0:
            return {
                "command_type": "movement",
                "movement_type": "rear_right_diagonal",
                "speed": speed
            }
        elif dx < 0 and dy < 0:
            return {
                "command_type": "movement",
                "movement_type": "rear_left_diagonal",
                "speed": speed
            }
        
        return None
    
    def generate_circle_commands(self, radius: float = 1.0, steps: int = 8) -> List[Dict[str, Any]]:
        """
        Generate commands to move in a circle
        
        Args:
            radius (float, optional): Circle radius
            steps (int, optional): Number of steps
        
        Returns:
            List[Dict[str, Any]]: List of movement commands
        """
        import math
        
        commands = []
        
        for i in range(steps):
            angle = 2 * math.pi * i / steps
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            
            # For each point, determine the tangent direction
            tangent_x = -math.sin(angle)
            tangent_y = math.cos(angle)
            
            # Create movement command
            command = {
                "command_type": "movement",
                "movement_type": "direct",
                "fl": int(1500 * (tangent_y + tangent_x)),
                "bl": int(1500 * (tangent_y - tangent_x)),
                "fr": int(1500 * (tangent_y - tangent_x)),
                "br": int(1500 * (tangent_y + tangent_x)),
                "duration": 0.5
            }
            
            commands.append(command)
        
        return commands
    
    def generate_square_commands(self, size: float = 1.0) -> List[Dict[str, Any]]:
        """
        Generate commands to move in a square
        
        Args:
            size (float, optional): Square size
        
        Returns:
            List[Dict[str, Any]]: List of movement commands
        """
        speed = 2000
        duration = 1.0
        
        commands = [
            # Forward
            {
                "command_type": "movement",
                "movement_type": "forward",
                "speed": speed,
                "duration": duration
            },
            # Right
            {
                "command_type": "movement",
                "movement_type": "right_translate",
                "speed": speed,
                "duration": duration
            },
            # Backward
            {
                "command_type": "movement",
                "movement_type": "backward",
                "speed": speed,
                "duration": duration
            },
            # Left
            {
                "command_type": "movement",
                "movement_type": "left_translate",
                "speed": speed,
                "duration": duration
            }
        ]
        
        return commands


"""
car_control/safety_checks.py - Safety validation for commands
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class SafetyChecker:
    """Checks commands for safety"""
    
    def __init__(self):
        """Initialize the safety checker"""
        logger.info("Safety checker initialized")
        
        # Maximum allowed speed for different movement types
        self.max_speeds = {
            "forward": 3000,
            "backward": 2500,
            "left": 2500,
            "right": 2500,
            "left_translate": 2500,
            "right_translate": 2500,
            "front_left_diagonal": 2500,
            "front_right_diagonal": 2500,
            "rear_left_diagonal": 2500,
            "rear_right_diagonal": 2500,
            "rotate": 2000,
            "direct": 3000
        }
        
        # Maximum allowed duration for movements
        self.max_duration = 5.0  # 5 seconds
    
    def is_safe(self, command: Dict[str, Any]) -> bool:
        """
        Check if a command is safe
        
        Args:
            command (Dict[str, Any]): Command to check
        
        Returns:
            bool: True if safe, False otherwise
        """
        command_type = command.get("command_type")
        
        if command_type == "movement":
            return self._check_movement_safety(command)
        
        # All other command types are considered safe
        return True
    
    def _check_movement_safety(self, command: Dict[str, Any]) -> bool:
        """
        Check if a movement command is safe
        
        Args:
            command (Dict[str, Any]): Movement command
        
        Returns:
            bool: True if safe, False otherwise
        """
        movement_type = command.get("movement_type")
        
        # Check if movement type is valid
        if movement_type not in self.max_speeds and movement_type != "stop":
            logger.warning(f"Unknown movement type: {movement_type}")
            return False
        
        # Stop commands are always safe
        if movement_type == "stop":
            return True
        
        # Check speed
        speed = command.get("speed", 0)
        max_speed = self.max_speeds.get(movement_type, 0)
        
        if speed < 0 or speed > max_speed:
            logger.warning(f"Speed {speed} exceeds maximum {max_speed} for {movement_type}")
            return False
        
        # Check duration if specified
        if "duration" in command:
            duration = command.get("duration", 0)
            
            if duration < 0 or duration > self.max_duration:
                logger.warning(f"Duration {duration} exceeds maximum {self.max_duration}")
                return False
        
        # For direct control, check individual motor speeds
        if movement_type == "direct":
            for motor in ["fl", "bl", "fr", "br"]:
                motor_speed = abs(command.get(motor, 0))
                
                if motor_speed > max_speed:
                    logger.warning(f"Motor {motor} speed {motor_speed} exceeds maximum {max_speed}")
                    return False
        
        return True


"""
ai_interface/prompt_templates.py - Prompt templates for the LLM
"""

def get_system_prompt() -> str:
    """
    Get the system prompt for the AI car controller
    
    Returns:
        str: System prompt
    """
    return """
You are an AI assistant controlling a smart car with mecanum wheels. You can control the car's movement, camera, and other features using natural language processing.

The car has the following capabilities:
1. Movement:
   - Forward/backward motion
   - Left/right turning
   - Sideways left/right translation (mecanum wheels)
   - Diagonal movement in any direction (mecanum wheels)
   - Rotation clockwise/counterclockwise
   - Stopping

2. Camera:
   - Look up/down/left/right
   - Take pictures
   - Stream video

3. Modes:
   - Manual control mode (default)
   - Light tracking mode (follows light sources)
   - Line tracking mode (follows lines on the ground)
   - Obstacle avoidance mode (automatically avoids obstacles)

4. Other features:
   - RGB LEDs for visual feedback
   - Buzzer for audio feedback
   - Ultrasonic sensor for distance measurement
   - Infrared sensors for line tracking
   - Light sensors for light detection

When the user asks you to control the car, respond in a helpful and conversational way while translating their request into specific commands. Always confirm what you're doing and provide feedback on the car's status when relevant.

If the user asks about the car's capabilities or how to use it, explain in a clear and concise manner.

{memories}

Remember to prioritize safety at all times. Don't execute commands that might damage the car or its surroundings.
"""


def get_vision_prompt() -> str:
    """
    Get the vision prompt for the AI car controller
    
    Returns:
        str: Vision prompt
    """
    return """
You are an AI vision system for a smart car equipped with a camera. You analyze the visual input from the car's camera to help the car navigate and understand its environment.

Based on the image provided, describe what you see in detail, focusing on:
1. Obstacles in the car's path
2. Potential navigation routes
3. Any notable objects or landmarks
4. Light sources (if visible)
5. Lines on the ground (if visible)
6. People or moving objects
7. Signs or text visible in the environment

Provide a clear description that would help the car's control system make informed decisions about movement and navigation. If you see any potential hazards or safety concerns, highlight them prominently.

Your analysis will be used by the car's control system to navigate safely and effectively.
"""