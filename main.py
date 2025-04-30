#!/usr/bin/env python3
"""
main.py - Main script for the AI-controlled car system (main computer side)
"""

import os
import sys
import logging
import asyncio
import signal
import json
import argparse
import time
from typing import Dict, Any, List, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ai_car_control.log')
    ]
)
logger = logging.getLogger(__name__)

# Import our modules
from ai_interface.llm_interface import LLMInterface
from ai_interface.prompt_templates import get_system_prompt
from memory.context_manager import ContextManager
from memory.retrieval import ContextRetriever
from speech.tts import TTS
from speech.stt import STT
from car_control.command_processor import CommandProcessor
from car_control.movement_controller import MovementController
from car_control.safety_checks import SafetyChecker
from communication.connection import CarConnection
from communication.protocol import Command, CommandType, MovementType

class AICarController:
    """Main AI car control system"""
    
    def __init__(
        self, 
        car_host: str = "raspberrypi.local", 
        car_port: int = 8765,
        api_key: Optional[str] = None,
        model: str = "llama3-70b-8192",
        vision_model: str = "meta-llama/llama-4-maverick-17b-128e-instruct",
        data_dir: str = "./data",
        use_tts: bool = True,
        use_stt: bool = True
    ):
        """
        Initialize the AI car controller
        
        Args:
            car_host (str, optional): Hostname or IP of the car
            car_port (int, optional): Port number of the car
            api_key (str, optional): API key for Groq
            model (str, optional): LLM model to use
            vision_model (str, optional): Vision model to use
            data_dir (str, optional): Directory to store data
            use_tts (bool, optional): Whether to use text-to-speech
            use_stt (bool, optional): Whether to use speech-to-text
        """
        self.car_host = car_host
        self.car_port = car_port
        
        # LLM interface
        self.llm = LLMInterface(api_key, model)
        
        # Memory and context
        self.context_manager = ContextManager("all-MiniLM-L6-v2", data_dir)
        self.context_retriever = ContextRetriever(self.context_manager)
        
        # Speech
        self.use_tts = use_tts
        self.use_stt = use_stt
        
        if use_tts:
            self.tts = TTS("auto")
        
        if use_stt:
            self.stt = STT("base")
        
        # Car control
        self.command_processor = CommandProcessor()
        self.movement_controller = MovementController()
        self.safety_checker = SafetyChecker()
        
        # Car connection
        self.car_connection = CarConnection(car_host, car_port)
        
        # State
        self.running = False
        self.connected = False
        self.tasks = []
        
        # Register event handlers
        self.car_connection.register_event_handler("sensor_update", self.handle_sensor_update)
    
    async def start(self):
        """Start the AI car controller"""
        self.running = True
        
        # Set up signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
        
        try:
            # Connect to the car
            logger.info(f"Connecting to car at {self.car_host}:{self.car_port}...")
            connected = await self.car_connection.connect()
            
            if not connected:
                logger.error("Failed to connect to car")
                return
            
            self.connected = True
            logger.info("Connected to car")
            
            # Welcome message
            if self.use_tts:
                self.tts.say("AI car control system initialized and connected.")
            
            # Start main interaction loop
            await self.interaction_loop()
        
        except Exception as e:
            logger.error(f"Error in AI car controller: {e}")
        
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shut down the AI car controller"""
        if not self.running:
            return
        
        self.running = False
        logger.info("Shutting down AI car controller...")
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Disconnect from car
        if self.connected:
            await self.car_connection.disconnect()
            self.connected = False
        
        # Clean up TTS
        if self.use_tts:
            self.tts.cleanup()
        
        logger.info("AI car controller shut down")
    
    async def interaction_loop(self):
        """Main interaction loop"""
        help_message = (
            "Welcome to the AI-controlled car system!\n\n"
            "You can control the car using natural language commands, such as:\n"
            "- 'Move forward at speed 2000'\n"
            "- 'Turn left'\n"
            "- 'Stop the car'\n"
            "- 'Look for obstacles in front of the car'\n"
            "- 'Switch to light tracking mode'\n\n"
            "You can also ask the car questions about its status, or use voice commands "
            "by saying 'listen to me' followed by your command."
        )
        
        print(help_message)
        
        while self.running:
            try:
                # Get user input
                user_input = input("\nEnter command (or 'quit' to exit): ")
                
                if user_input.lower() in ["quit", "exit", "q"]:
                    break
                
                # Check for voice command
                if user_input.lower() in ["listen", "listen to me", "voice command"]:
                    if self.use_stt:
                        print("Listening... (speak now)")
                        result = self.stt.listen(5.0)
                        user_input = result.get("text", "")
                        print(f"You said: {user_input}")
                    else:
                        print("Speech-to-text is not enabled")
                        continue
                
                # Skip empty input
                if not user_input.strip():
                    continue
                
                # Process with LLM
                await self.process_command(user_input)
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Error in interaction loop: {e}")
                print(f"Error: {e}")
    
    async def process_command(self, user_input: str):
        """
        Process a user command
        
        Args:
            user_input (str): User input
        """
        try:
            # Add to context manager
            self.context_manager.add_user_message(user_input)
            
            # Get prompt with context
            system_prompt = get_system_prompt()
            prompt_data = self.context_retriever.get_prompt_with_context(system_prompt, user_input)
            
            # Query LLM
            logger.info(f"Sending query to LLM: {user_input}")
            llm_response = self.llm.query(
                prompt_data["system_prompt"],
                user_input,
                conversation_history=prompt_data["messages"][1:-1],  # Exclude system prompt and current user message
                temperature=0.7
            )
            
            # Add to context manager
            self.context_manager.add_assistant_message(llm_response)
            
            # Process LLM response
            print(f"\nAI: {llm_response}")
            
            # Extract and execute commands
            commands = self.command_processor.process_llm_output(llm_response)
            
            if commands:
                logger.info(f"Extracted commands: {commands}")
                
                for cmd in commands:
                    # Check command safety
                    if not self.safety_checker.is_safe(cmd):
                        logger.warning(f"Unsafe command detected: {cmd}")
                        print(f"Safety check failed for command: {cmd['command_type']}")
                        continue
                    
                    # Execute command
                    await self.execute_command(cmd)
            else:
                logger.info("No commands extracted")
            
            # Speak response if TTS is enabled
            if self.use_tts:
                # Exclude technical details when speaking
                speak_text = llm_response
                if "```" in speak_text:
                    # Remove code blocks
                    parts = speak_text.split("```")
                    speak_text = "".join(parts[::2])  # Keep only non-code parts
                
                self.tts.say(speak_text)
        
        except Exception as e:
            logger.error(f"Error processing command: {e}")
            print(f"Error: {e}")
    
    async def execute_command(self, command: Dict[str, Any]):
        """
        Execute a command
        
        Args:
            command (Dict[str, Any]): Command to execute
        """
        try:
            command_type = command.get("command_type")
            
            if command_type == "movement":
                await self.execute_movement_command(command)
            
            elif command_type == "camera":
                await self.execute_camera_command(command)
            
            elif command_type == "mode":
                await self.execute_mode_command(command)
            
            else:
                logger.warning(f"Unknown command type: {command_type}")
        
        except Exception as e:
            logger.error(f"Error executing command: {e}")
    
    async def execute_movement_command(self, command: Dict[str, Any]):
        """
        Execute a movement command
        
        Args:
            command (Dict[str, Any]): Movement command
        """
        try:
            movement_type = command.get("movement_type")
            speed = command.get("speed", 2000)
            
            if movement_type == "forward":
                data = {"movement_type": "forward", "speed": speed}
            elif movement_type == "backward":
                data = {"movement_type": "backward", "speed": speed}
            elif movement_type == "left":
                data = {"movement_type": "left", "speed": speed}
            elif movement_type == "right":
                data = {"movement_type": "right", "speed": speed}
            elif movement_type == "left_translate":
                data = {"movement_type": "left_translate", "speed": speed}
            elif movement_type == "right_translate":
                data = {"movement_type": "right_translate", "speed": speed}
            elif movement_type == "front_left_diagonal":
                data = {"movement_type": "front_left_diagonal", "speed": speed}
            elif movement_type == "front_right_diagonal":
                data = {"movement_type": "front_right_diagonal", "speed": speed}
            elif movement_type == "rear_left_diagonal":
                data = {"movement_type": "rear_left_diagonal", "speed": speed}
            elif movement_type == "rear_right_diagonal":
                data = {"movement_type": "rear_right_diagonal", "speed": speed}
            elif movement_type == "rotate":
                direction = command.get("direction", "clockwise")
                data = {"movement_type": "rotate", "direction": direction, "speed": speed}
            elif movement_type == "stop":
                data = {"movement_type": "stop"}
            else:
                logger.warning(f"Unknown movement type: {movement_type}")
                return
            
            # Add duration if specified
            if "duration" in command:
                data["duration"] = command["duration"]
            
            # Send command to car
            movement_command = Command(CommandType.MOVEMENT, data)
            await self.car_connection.send_command(movement_command)
            
            logger.info(f"Sent movement command: {movement_type}")
        
        except Exception as e:
            logger.error(f"Error executing movement command: {e}")
    
    async def execute_camera_command(self, command: Dict[str, Any]):
        """
        Execute a camera command
        
        Args:
            command (Dict[str, Any]): Camera command
        """
        try:
            action = command.get("action")
            direction = command.get("direction")
            
            data = {"action": action}
            if direction:
                data["direction"] = direction
            
            # Send command to car
            camera_command = Command(CommandType.CAMERA, data)
            await self.car_connection.send_command(camera_command)
            
            logger.info(f"Sent camera command: {action}")
        
        except Exception as e:
            logger.error(f"Error executing camera command: {e}")
    
    async def execute_mode_command(self, command: Dict[str, Any]):
        """
        Execute a mode command
        
        Args:
            command (Dict[str, Any]): Mode command
        """
        try:
            mode = command.get("mode", 0)
            
            # Send command to car
            mode_command = Command(CommandType.MODE, {"mode": mode})
            await self.car_connection.send_command(mode_command)
            
            logger.info(f"Sent mode command: {mode}")
        
        except Exception as e:
            logger.error(f"Error executing mode command: {e}")
    
    def handle_sensor_update(self, event_data: Dict[str, Any]):
        """
        Handle sensor update event
        
        Args:
            event_data (Dict[str, Any]): Sensor data
        """
        # Add to context
        if "data" in event_data:
            sensor_data = event_data["data"]
            
            # Check battery level
            if "battery" in sensor_data:
                battery = sensor_data["battery"]
                voltage = battery.get("voltage", 0)
                
                # Warn if battery is low
                if voltage < 7.0:
                    print(f"\nWARNING: Battery voltage is low: {voltage}V")
                    if self.use_tts:
                        self.tts.say("Warning: Battery voltage is low.")


async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="AI-controlled car client")
    parser.add_argument("--host", default="raspberrypi.local", help="Hostname or IP of the car")
    parser.add_argument("--port", type=int, default=8765, help="Port number")
    parser.add_argument("--api-key", help="API key for Groq")
    parser.add_argument("--model", default="llama3-70b-8192", help="LLM model to use")
    parser.add_argument("--vision-model", default="meta-llama/llama-4-maverick-17b-128e-instruct", help="Vision model to use")
    parser.add_argument("--data-dir", default="./data", help="Directory to store data")
    parser.add_argument("--no-tts", action="store_true", help="Disable text-to-speech")
    parser.add_argument("--no-stt", action="store_true", help="Disable speech-to-text")
    args = parser.parse_args()
    
    # Get API key from environment if not provided
    api_key = args.api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        parser.error("API key not provided. Please provide it as a command line argument or set the GROQ_API_KEY environment variable.")
    
    # Create AI car controller
    controller = AICarController(
        car_host=args.host,
        car_port=args.port,
        api_key=api_key,
        model=args.model,
        vision_model=args.vision_model,
        data_dir=args.data_dir,
        use_tts=not args.no_tts,
        use_stt=not args.no_stt
    )
    
    # Start controller
    await controller.start()


if __name__ == "__main__":
    asyncio.run(main())