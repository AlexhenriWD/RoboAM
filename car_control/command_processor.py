"""
car_control/command_processor.py - Processes LLM outputs into car commands
"""

import logging
import re
import json
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)

class CommandProcessor:
    """Processes natural language commands from the LLM into car commands"""
    
    def __init__(self):
        """Initialize the command processor"""
        # Movement command patterns
        self.movement_patterns = {
            r'(?i)move\s+forward(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_forward,
            r'(?i)go\s+forward(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_forward,
            r'(?i)drive\s+forward(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_forward,
            
            r'(?i)move\s+backward(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_backward,
            r'(?i)go\s+backward(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_backward,
            r'(?i)drive\s+backward(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_backward,
            r'(?i)reverse(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_backward,
            
            r'(?i)turn\s+left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_turn_left,
            r'(?i)go\s+left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_turn_left,
            
            r'(?i)turn\s+right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_turn_right,
            r'(?i)go\s+right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_turn_right,
            
            r'(?i)move\s+sideways\s+(?:to\s+)?left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_left,
            r'(?i)move\s+left\s+sideways(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_left,
            r'(?i)translate\s+left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_left,
            r'(?i)slide\s+left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_left,
            
            r'(?i)move\s+sideways\s+(?:to\s+)?right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_right,
            r'(?i)move\s+right\s+sideways(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_right,
            r'(?i)translate\s+right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_right,
            r'(?i)slide\s+right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_translate_right,
            
            r'(?i)stop': self._process_stop,
            r'(?i)halt': self._process_stop,
            r'(?i)brake': self._process_stop,
            
            r'(?i)rotate\s+clockwise(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rotate_clockwise,
            r'(?i)turn\s+clockwise(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rotate_clockwise,
            r'(?i)spin\s+clockwise(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rotate_clockwise,
            
            r'(?i)rotate\s+counterclockwise(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rotate_counterclockwise,
            r'(?i)turn\s+counterclockwise(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rotate_counterclockwise,
            r'(?i)spin\s+counterclockwise(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rotate_counterclockwise,
            
            r'(?i)make\s+a\s+circle(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_make_circle,
            r'(?i)drive\s+in\s+a\s+circle(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_make_circle,
            r'(?i)move\s+in\s+a\s+circle(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_make_circle,

            r'(?i)move\s+diagonally\s+forward\s+left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_front_left_diagonal,
            r'(?i)move\s+diagonally\s+forward\s+right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_front_right_diagonal,
            r'(?i)move\s+diagonally\s+backward\s+left(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rear_left_diagonal,
            r'(?i)move\s+diagonally\s+backward\s+right(?:\s+(?:at|with))?\s+(?:speed|velocity)?\s*(\d+)?': self._process_rear_right_diagonal,
        }
        
        # Camera command patterns
        self.camera_patterns = {
            r'(?i)look\s+up': {'action': 'move', 'direction': 'up'},
            r'(?i)look\s+down': {'action': 'move', 'direction': 'down'},
            r'(?i)look\s+left': {'action': 'move', 'direction': 'left'},
            r'(?i)look\s+right': {'action': 'move', 'direction': 'right'},
            r'(?i)look\s+forward': {'action': 'move', 'direction': 'center'},
            r'(?i)look\s+straight': {'action': 'move', 'direction': 'center'},
            r'(?i)center\s+camera': {'action': 'move', 'direction': 'center'},
            r'(?i)reset\s+camera': {'action': 'move', 'direction': 'center'},
            r'(?i)take\s+(?:a\s+)?picture': {'action': 'capture'},
            r'(?i)capture\s+(?:a\s+)?photo': {'action': 'capture'},
            r'(?i)take\s+(?:a\s+)?photo': {'action': 'capture'},
            r'(?i)start\s+streaming': {'action': 'stream_start'},
            r'(?i)begin\s+streaming': {'action': 'stream_start'},
            r'(?i)stream\s+video': {'action': 'stream_start'},
            r'(?i)stop\s+streaming': {'action': 'stream_stop'},
            r'(?i)end\s+streaming': {'action': 'stream_stop'},
        }
        
        # Mode command patterns
        self.mode_patterns = {
            r'(?i)switch\s+to\s+manual\s+mode': {'mode': 0},
            r'(?i)enable\s+manual\s+mode': {'mode': 0},
            r'(?i)manual\s+mode': {'mode': 0},
            r'(?i)switch\s+to\s+light\s+tracking\s+mode': {'mode': 1},
            r'(?i)enable\s+light\s+tracking\s+mode': {'mode': 1},
            r'(?i)light\s+tracking\s+mode': {'mode': 1},
            r'(?i)follow\s+the\s+light': {'mode': 1},
            r'(?i)switch\s+to\s+line\s+tracking\s+mode': {'mode': 2},
            r'(?i)enable\s+line\s+tracking\s+mode': {'mode': 2},
            r'(?i)line\s+tracking\s+mode': {'mode': 2},
            r'(?i)follow\s+the\s+line': {'mode': 2},
            r'(?i)switch\s+to\s+obstacle\s+avoidance\s+mode': {'mode': 3},
            r'(?i)enable\s+obstacle\s+avoidance\s+mode': {'mode': 3},
            r'(?i)obstacle\s+avoidance\s+mode': {'mode': 3},
            r'(?i)avoid\s+obstacles': {'mode': 3},
        }
    
    def process_llm_output(self, llm_output: str) -> List[Dict[str, Any]]:
        """
        Process the LLM output to extract commands
        
        Args:
            llm_output (str): Output from the LLM
        
        Returns:
            List[Dict[str, Any]]: List of parsed commands
        """
        commands = []
        
        # Try to extract structured commands if the LLM provides them
        structured_commands = self._extract_structured_commands(llm_output)
        if structured_commands:
            return structured_commands
        
        # Process as natural language
        for command in self._split_into_commands(llm_output):
            parsed_command = self._parse_command(command)
            if parsed_command:
                commands.append(parsed_command)
        
        return commands
    
    def _extract_structured_commands(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract structured commands from text (if provided in JSON format)
        
        Args:
            text (str): Text to extract commands from
        
        Returns:
            List[Dict[str, Any]]: List of structured commands, or empty list if none found
        """
        # Look for JSON blocks in the text
        json_pattern = r'```json\s*([\s\S]*?)\s*```'
        matches = re.findall(json_pattern, text)
        
        commands = []
        for match in matches:
            try:
                # Parse JSON
                data = json.loads(match)
                
                # Handle single command or list of commands
                if isinstance(data, list):
                    commands.extend(data)
                else:
                    commands.append(data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON command: {match}")
        
        return commands
    
    def _split_into_commands(self, text: str) -> List[str]:
        """
        Split text into individual commands
        
        Args:
            text (str): Text to split
        
        Returns:
            List[str]: List of individual command strings
        """
        # Split by common sentence delimiters
        commands = re.split(r'[.!?;]\s+', text)
        
        # Filter out empty commands
        return [cmd.strip() for cmd in commands if cmd.strip()]
    
    def _parse_command(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single command
        
        Args:
            command (str): Command string
        
        Returns:
            Optional[Dict[str, Any]]: Parsed command or None if not recognized
        """
        # Check all movement patterns
        for pattern, handler in self.movement_patterns.items():
            match = re.search(pattern, command)
            if match:
                return handler(match)
        
        # Check camera patterns
        for pattern, action in self.camera_patterns.items():
            if re.search(pattern, command):
                return {
                    "command_type": "camera",
                    "action": action["action"],
                    "direction": action.get("direction")
                }
        
        # Check mode patterns
        for pattern, mode_data in self.mode_patterns.items():
            if re.search(pattern, command):
                return {
                    "command_type": "mode",
                    "mode": mode_data["mode"]
                }
        
        # If no pattern matched, return None
        logger.warning(f"No pattern matched for command: {command}")
        return None
    
    def _process_forward(self, match) -> Dict[str, Any]:
        """Process forward movement command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "forward",
            "speed": min(speed, 4056)
        }
    
    def _process_backward(self, match) -> Dict[str, Any]:
        """Process backward movement command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "backward",
            "speed": min(speed, 4056)
        }
    
    def _process_turn_left(self, match) -> Dict[str, Any]:
        """Process turn left command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "left",
            "speed": min(speed, 4056)
        }
    
    def _process_turn_right(self, match) -> Dict[str, Any]:
        """Process turn right command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "right",
            "speed": min(speed, 4056)
        }
    
    def _process_translate_left(self, match) -> Dict[str, Any]:
        """Process translate left command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "left_translate",
            "speed": min(speed, 4056)
        }
    
    def _process_translate_right(self, match) -> Dict[str, Any]:
        """Process translate right command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "right_translate",
            "speed": min(speed, 4056)
        }
    
    def _process_stop(self, match) -> Dict[str, Any]:
        """Process stop command"""
        return {
            "command_type": "movement",
            "movement_type": "stop"
        }
    
    def _process_rotate_clockwise(self, match) -> Dict[str, Any]:
        """Process rotate clockwise command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "rotate",
            "direction": "clockwise",
            "speed": min(speed, 4056)
        }
    
    def _process_rotate_counterclockwise(self, match) -> Dict[str, Any]:
        """Process rotate counterclockwise command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "rotate",
            "direction": "counterclockwise",
            "speed": min(speed, 4056)
        }
    
    def _process_make_circle(self, match) -> Dict[str, Any]:
        """Process make circle command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "circle",
            "speed": min(speed, 4056)
        }
    
    def _process_front_left_diagonal(self, match) -> Dict[str, Any]:
        """Process front left diagonal command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "front_left_diagonal",
            "speed": min(speed, 4056)
        }
    
    def _process_front_right_diagonal(self, match) -> Dict[str, Any]:
        """Process front right diagonal command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "front_right_diagonal",
            "speed": min(speed, 4056)
        }
    
    def _process_rear_left_diagonal(self, match) -> Dict[str, Any]:
        """Process rear left diagonal command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "rear_left_diagonal",
            "speed": min(speed, 4056)
        }
    
    def _process_rear_right_diagonal(self, match) -> Dict[str, Any]:
        """Process rear right diagonal command"""
        speed = int(match.group(1)) if match.group(1) else 2000
        return {
            "command_type": "movement",
            "movement_type": "rear_right_diagonal",
            "speed": min(speed, 4056)
        }


# Example usage
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Create command processor
    processor = CommandProcessor()
    
    # Test some commands
    test_commands = [
        "Move forward at speed 1000.",
        "Turn left.",
        "Slide to the right with speed 3000.",
        "Stop the car immediately!",
        "Take a picture of what's in front.",
        "Switch to obstacle avoidance mode.",
        "Rotate clockwise for 5 seconds."
    ]
    
    for cmd in test_commands:
        print(f"\nProcessing: {cmd}")
        results = processor.process_llm_output(cmd)
        
        for result in results:
            print(f"  {result}")