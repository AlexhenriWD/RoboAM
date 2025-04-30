"""
Main Computer: communication/connection.py - Manages connection to the Raspberry Pi
"""

import asyncio
import websockets
import logging
import json
import time
from .protocol import Command, Response

logger = logging.getLogger(__name__)

class CarConnection:
    """Manages connection to the car (Raspberry Pi)"""
    
    def __init__(self, host="raspberrypi.local", port=8765):
        """
        Initialize connection to the car
        
        Args:
            host (str): Hostname or IP of the Raspberry Pi
            port (int): Port number
        """
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False
        self.command_callbacks = {}  # Command ID -> callback function
        self.event_handlers = {}     # Event type -> handler function
        self.loop = None
        self.recv_task = None
    
    async def connect(self):
        """Connect to the car"""
        uri = f"ws://{self.host}:{self.port}"
        try:
            self.websocket = await websockets.connect(uri)
            self.connected = True
            logger.info(f"Connected to car at {uri}")
            
            # Start receiver task
            self.loop = asyncio.get_event_loop()
            self.recv_task = self.loop.create_task(self._receiver())
            
            return True
        except Exception as e:
            logger.error(f"Failed to connect to car: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the car"""
        if self.connected and self.websocket:
            if self.recv_task:
                self.recv_task.cancel()
                try:
                    await self.recv_task
                except asyncio.CancelledError:
                    pass
            
            await self.websocket.close()
            self.websocket = None
            self.connected = False
            logger.info("Disconnected from car")
    
    async def send_command(self, command, callback=None):
        """
        Send a command to the car
        
        Args:
            command (Command): Command to send
            callback (callable, optional): Callback for when response is received
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to car")
            return False
        
        try:
            # Register callback if provided
            if callback:
                self.command_callbacks[command.id] = callback
            
            # Send command
            await self.websocket.send(command.to_json())
            logger.debug(f"Sent command: {command.command_type.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return False
    
    async def _receiver(self):
        """Background task that receives messages from the car"""
        try:
            while self.connected:
                try:
                    message = await self.websocket.recv()
                    await self._handle_message(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection closed by car")
                    self.connected = False
                    break
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            logger.error(f"Error in receiver task: {e}")
            self.connected = False
    
    async def _handle_message(self, message):
        """
        Handle an incoming message
        
        Args:
            message (str): Message received from the car
        """
        try:
            # Try to parse as Response
            data = json.loads(message)
            
            if "command_id" in data:
                # This is a response
                response = Response.from_json(message)
                
                # Call callback if registered
                if response.command_id in self.command_callbacks:
                    callback = self.command_callbacks[response.command_id]
                    callback(response)
                    # Remove callback after use
                    del self.command_callbacks[response.command_id]
            
            elif "event_type" in data:
                # This is an event
                event_type = data["event_type"]
                if event_type in self.event_handlers:
                    handler = self.event_handlers[event_type]
                    handler(data)
            
            else:
                logger.warning(f"Received unknown message: {message}")
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def register_event_handler(self, event_type, handler):
        """
        Register a handler for a specific event type
        
        Args:
            event_type (str): Type of event to handle
            handler (callable): Function to call when event is received
        """
        self.event_handlers[event_type] = handler


"""
Raspberry Pi: communication/receiver.py - Receives commands from the main computer
"""

import asyncio
import websockets
import logging
import json
from .protocol import Command, Response

logger = logging.getLogger(__name__)

class CommandReceiver:
    """Receives and processes commands from the main computer"""
    
    def __init__(self, host="0.0.0.0", port=8765):
        """
        Initialize the command receiver
        
        Args:
            host (str): Host to bind to
            port (int): Port to listen on
        """
        self.host = host
        self.port = port
        self.websocket = None
        self.command_handlers = {}  # Command type -> handler function
        self.server = None
    
    async def start(self):
        """Start the command receiver"""
        self.server = await websockets.serve(
            self._handle_connection, self.host, self.port
        )
        logger.info(f"Command receiver started on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the command receiver"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Command receiver stopped")
    
    def register_command_handler(self, command_type, handler):
        """
        Register a handler for a specific command type
        
        Args:
            command_type (CommandType): Type of command to handle
            handler (callable): Function to call when command is received
        """
        self.command_handlers[command_type] = handler
    
    async def _handle_connection(self, websocket, path):
        """
        Handle a new connection
        
        Args:
            websocket: WebSocket connection
            path: Connection path
        """
        logger.info(f"New connection from {websocket.remote_address}")
        self.websocket = websocket
        
        try:
            async for message in websocket:
                await self._handle_command(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection closed from {websocket.remote_address}")
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
        finally:
            self.websocket = None
    
    async def _handle_command(self, message):
        """
        Handle a received command
        
        Args:
            message (str): Command message
        """
        try:
            command = Command.from_json(message)
            logger.debug(f"Received command: {command.command_type.value}")
            
            # Find and call handler
            if command.command_type in self.command_handlers:
                handler = self.command_handlers[command.command_type]
                response = await handler(command)
                
                # Send response if available
                if response and self.websocket:
                    await self.websocket.send(response.to_json())
            else:
                logger.warning(f"No handler for command type: {command.command_type.value}")
                
                # Send error response
                if self.websocket:
                    response = Response("error", command.id, {
                        "error": f"No handler for command type: {command.command_type.value}"
                    })
                    await self.websocket.send(response.to_json())
        
        except Exception as e:
            logger.error(f"Error handling command: {e}")
            
            # Try to send error response
            try:
                if self.websocket:
                    response = Response("error", None, {
                        "error": f"Error handling command: {str(e)}"
                    })
                    await self.websocket.send(response.to_json())
            except:
                pass
    
    async def send_event(self, event_type, data=None):
        """
        Send an event to the main computer
        
        Args:
            event_type (str): Type of event
            data (dict, optional): Event data
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.websocket:
            logger.warning("No active connection to send event")
            return False
        
        try:
            event = {
                "event_type": event_type,
                "data": data or {},
                "timestamp": time.time()
            }
            
            await self.websocket.send(json.dumps(event))
            return True
        except Exception as e:
            logger.error(f"Failed to send event: {e}")
            return False