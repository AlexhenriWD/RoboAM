from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional

logger = logging.getLogger("api_router")




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
    
   