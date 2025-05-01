from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional

logger = logging.getLogger("api_router")

class ConnectionManager:
    """Gerenciador de conexões WebSocket"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Cliente {client_id} conectado")
        
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Cliente {client_id} desconectado")
            
    async def send_message(self, client_id: str, message: str):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_text(message)
                return True
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem para {client_id}: {e}")
                return False
        return False
        
    async def broadcast(self, message: str, exclude: Optional[str] = None):
        for client_id, connection in self.active_connections.items():
            if exclude and client_id == exclude:
                continue
                
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Erro ao transmitir mensagem para {client_id}: {e}")

# Criar gerenciador de conexão
connection_manager = ConnectionManager()

def setup_routes(app, command_center):
    """Configurar rotas da API e WebSocket"""
    
    # Criar router
    router = APIRouter()
    
    # Rota para status
    @router.get("/status")
    async def get_status():
        return {
            "status": "online",
            "active_models": command_center.active_models,
            "system_status": command_center.system_status
        }
    
    # Rota para listar modelos disponíveis
    @router.get("/models")
    async def list_models():
        from config import LLM_MODELS
        return {
            "active": command_center.active_models,
            "available": LLM_MODELS
        }
    
    # Rota para alterar modelo
    @router.post("/models/{model_type}")
    async def change_model(model_type: str, model_name: str):
        try:
            success = command_center.change_model(model_type, model_name)
            return {"success": success, "model_type": model_type, "new_model": model_name}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    # Rota para processar entrada de texto
    @router.post("/process")
    async def process_input(input_data: Dict[str, Any]):
        try:
            input_text = input_data.get("text", "")
            input_type = input_data.get("type", "text")
            with_memory = input_data.get("with_memory", True)
            
            response = await command_center.process_input(input_text, input_type, with_memory)
            return {"response": response}
        except Exception as e:
            logger.error(f"Erro ao processar entrada: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Rota WebSocket para Raspberry Pi
    @app.websocket("/ws/pi")
    async def websocket_pi(websocket: WebSocket):
        await connection_manager.connect(websocket, "pi")
        command_center.update_system_status("pi_connected", True)
        
        try:
            while True:
                data = await websocket.receive_text()
                
                # Processar dados recebidos do Pi
                try:
                    message = json.loads(data)
                    
                    # Atualizar status do sistema com base nos dados recebidos
                    if "sensor" in message:
                        current_sensors = command_center.system_status.get("sensors", {})
                        current_sensors[message["sensor"]] = message["value"]
                        command_center.update_system_status("sensors", current_sensors)
                    
                    if "battery" in message:
                        command_center.update_system_status("battery_level", message["battery"])
                        
                    # Broadcast dos dados para outros clientes (interface)
                    await connection_manager.broadcast(data, exclude="pi")
                    
                except json.JSONDecodeError:
                    logger.error(f"Dados inválidos do Pi: {data}")
                
        except WebSocketDisconnect:
            connection_manager.disconnect("pi")
            command_center.update_system_status("pi_connected", False)
    
    # Rota WebSocket para Interface
    @app.websocket("/ws/ui")
    async def websocket_ui(websocket: WebSocket):
        # Gerar ID único para a interface
        import uuid
        ui_id = f"ui-{uuid.uuid4()}"
        
        await connection_manager.connect(websocket, ui_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                
                # Processar comandos da interface
                try:
                    command = json.loads(data)
                    
                    # Se for um comando para o Pi, encaminhar
                    if "action" in command and command.get("target") == "pi":
                        command_center.update_system_status("last_command", command)
                        await connection_manager.send_message("pi", json.dumps(command))
                    
                    # Se for um comando para o sistema de IA
                    elif "action" in command and command.get("target") == "ai":
                        if command["action"] == "process":
                            response = await command_center.process_input(
                                command.get("text", ""),
                                command.get("type", "text"),
                                command.get("with_memory", True)
                            )
                            await websocket.send_text(json.dumps({
                                "type": "response",
                                "response": response
                            }))
                    
                except json.JSONDecodeError:
                    logger.error(f"Comando inválido da interface: {data}")
                
        except WebSocketDisconnect:
            connection_manager.disconnect(ui_id)
    
    # Adicionar router ao app
    app.include_router(router, prefix="/api")