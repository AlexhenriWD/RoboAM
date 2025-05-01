import asyncio
import logging
import threading
from typing import Dict, List, Optional, Any
import time

from config import LLM_MODELS
from server.memory_engine import MemoryEngine
from server.personality_loader import PersonalityLoader

logger = logging.getLogger("command_center")

class CommandCenter:
    """Centro de comando que coordena a comunicação entre modelos e ferramentas"""
    
    def __init__(self):
        self.active_models = {
            "decision": LLM_MODELS["decision"]["default"],
            "vision": LLM_MODELS["vision"]["default"],
            "navigation": LLM_MODELS["navigation"]["default"],
            "conversation": LLM_MODELS["conversation"]["default"],
            "embedding": LLM_MODELS["embedding"]["default"]
        }
        
        self.model_locks = {
            "decision": threading.Lock(),
            "vision": threading.Lock(),
            "navigation": threading.Lock(),
            "conversation": threading.Lock(),
            "embedding": threading.Lock()
        }
        
        # Inicializar adaptadores de modelo (lazy loading)
        self.model_adapters = {}
        
        # Inicializar o motor de memória
        self.memory_engine = MemoryEngine()
        
        # Inicializar o carregador de personalidade
        self.personality_loader = PersonalityLoader()
        
        # Status do sistema
        self.system_status = {
            "online": True,
            "camera_active": False,
            "pi_connected": False,
            "last_command": None,
            "battery_level": None,
            "sensors": {}
        }
        
        # Callbacks para eventos
        self.event_callbacks = {
            "on_pi_connect": [],
            "on_pi_disconnect": [],
            "on_command_sent": [],
            "on_sensor_update": []
        }
        
        logger.info("Centro de comando inicializado")

    def get_model_adapter(self, model_type):
        """Obter adaptador para um tipo de modelo específico (lazy loading)"""
        if model_type not in self.model_adapters:
            model_name = self.active_models[model_type]
            provider = self._get_provider_for_model(model_name)
            
            if provider == "groq":
                from server.llm_modules.groq_adapter import GroqModelAdapter
                self.model_adapters[model_type] = GroqModelAdapter(model_name)
            elif provider == "lmstudio":
                from server.llm_modules.lmstudio_adapter import LmStudioModelAdapter
                self.model_adapters[model_type] = LmStudioModelAdapter(model_name)
            else:
                raise ValueError(f"Provedor não suportado: {provider}")
                
        return self.model_adapters[model_type]
    
    def _get_provider_for_model(self, model_name):
        """Determinar o provedor com base no nome do modelo"""
        for model_type, config in LLM_MODELS.items():
            if model_name in config["options"]:
                return config["provider"]
        raise ValueError(f"Modelo não encontrado: {model_name}")
    
    def change_model(self, model_type, new_model_name):
        """Alterar modelo em tempo de execução"""
        if model_type not in self.active_models:
            raise ValueError(f"Tipo de modelo inválido: {model_type}")
            
        if new_model_name not in LLM_MODELS[model_type]["options"]:
            raise ValueError(f"Modelo não disponível: {new_model_name}")
            
        with self.model_locks[model_type]:
            logger.info(f"Alterando modelo {model_type} de {self.active_models[model_type]} para {new_model_name}")
            self.active_models[model_type] = new_model_name
            
            # Remover o adaptador antigo para que um novo seja criado sob demanda
            if model_type in self.model_adapters:
                del self.model_adapters[model_type]
                
        return True
    
    async def process_input(self, input_text, input_type="text", with_memory=True):
        """Processar entrada do usuário e determinar ação"""
        # Obter contexto da memória, se necessário
        context = await self.memory_engine.get_relevant_context(input_text) if with_memory else None
        
        # Obter o adaptador para o modelo de decisão
        decision_adapter = self.get_model_adapter("decision")
        
        # Preparar o prompt para o modelo de decisão
        prompt = self._prepare_decision_prompt(input_text, context)
        
        # Obter a decisão do modelo
        decision = await decision_adapter.generate(prompt)
        
        # Analisar a decisão para determinar próximos passos
        action_plan = self._parse_decision(decision)
        
        # Executar ações conforme determinado pelo modelo de decisão
        response = await self._execute_action_plan(action_plan, input_text, context)
        
        # Armazenar interação na memória
        if with_memory:
            await self.memory_engine.store_interaction(input_text, response)
        
        return response
    
    def _prepare_decision_prompt(self, input_text, context=None):
        """Preparar prompt para o modelo de decisão"""
        # Implementação básica - em produção, seria mais elaborado
        prompt = "Você é uma IA veicular. "
        prompt += "Decida a melhor maneira de responder com base na entrada do usuário.\n\n"
        
        if context:
            prompt += f"Contexto da memória:\n{context}\n\n"
            
        prompt += f"Entrada do usuário: {input_text}\n\n"
        prompt += "Decida entre:\n"
        prompt += "1. Usar visão computacional\n"
        prompt += "2. Enviar comando de movimento\n"
        prompt += "3. Responder diretamente\n"
        prompt += "4. Consultar memória adicional\n\n"
        prompt += "Formato de resposta: [DECISÃO]: número e motivo"
        
        return prompt
    
    def _parse_decision(self, decision_text):
        """Analisar o texto da decisão para extrair ação"""
        # Implementação simplificada - em produção, seria mais robusto
        action_plan = {
            "action_type": None,
            "reason": "",
            "details": {}
        }
        
        if "[DECISÃO]: 1" in decision_text:
            action_plan["action_type"] = "vision"
        elif "[DECISÃO]: 2" in decision_text:
            action_plan["action_type"] = "movement"
        elif "[DECISÃO]: 3" in decision_text:
            action_plan["action_type"] = "conversation"
        elif "[DECISÃO]: 4" in decision_text:
            action_plan["action_type"] = "memory"
        else:
            action_plan["action_type"] = "conversation"  # Fallback
            
        return action_plan
    
    async def _execute_action_plan(self, action_plan, input_text, context=None):
        """Executar o plano de ação decidido pelo modelo"""
        action_type = action_plan["action_type"]
        
        if action_type == "vision":
            # Usar o modelo de visão
            # Em um cenário real, capturaria uma imagem da câmera primeiro
            vision_adapter = self.get_model_adapter("vision")
            prompt = f"Descreva o que você vê. Contexto: {input_text}"
            return await vision_adapter.generate(prompt)
            
        elif action_type == "movement":
            # Usar o modelo de navegação para determinar movimentos
            navigation_adapter = self.get_model_adapter("navigation")
            prompt = f"Determine como o veículo deve se mover. Entrada: {input_text}"
            movement_command = await navigation_adapter.generate(prompt)
            
            # Em um sistema real, enviaria o comando para o Raspberry Pi
            # self.send_command_to_pi(self._parse_movement(movement_command))
            
            return f"Executando movimento: {movement_command}"
            
        elif action_type == "memory":
            # Buscar mais contexto da memória
            additional_context = await self.memory_engine.get_detailed_context(input_text)
            
            # Usar o modelo de conversação com o contexto expandido
            conversation_adapter = self.get_model_adapter("conversation")
            prompt = f"Contexto:\n{additional_context}\n\nEntrada do usuário: {input_text}"
            return await conversation_adapter.generate(prompt)
            
        else:  # conversation ou fallback
            # Usar o modelo de conversação
            conversation_adapter = self.get_model_adapter("conversation")
            prompt = f"Responda à entrada do usuário. Contexto: {context or 'Nenhum contexto relevante.'}\n\nEntrada: {input_text}"
            return await conversation_adapter.generate(prompt)
    
    def register_callback(self, event_type, callback):
        """Registrar callback para eventos do sistema"""
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)
        else:
            raise ValueError(f"Tipo de evento inválido: {event_type}")
    
    def update_system_status(self, key, value):
        """Atualizar status do sistema"""
        if key in self.system_status:
            self.system_status[key] = value
            
            # Acionar callbacks relevantes
            if key == "pi_connected" and value:
                for callback in self.event_callbacks["on_pi_connect"]:
                    callback()
            elif key == "pi_connected" and not value:
                for callback in self.event_callbacks["on_pi_disconnect"]:
                    callback()
            elif key == "last_command":
                for callback in self.event_callbacks["on_command_sent"]:
                    callback(value)
            elif key == "sensors":
                for callback in self.event_callbacks["on_sensor_update"]:
                    callback(value)