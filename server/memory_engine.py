import asyncio
import logging
from typing import List, Dict, Any, Optional
import time
import uuid

from db.vector_db import QdrantClient
from config import LLM_MODELS

logger = logging.getLogger("memory_engine")

class MemoryEngine:
    """Motor de memória para armazenar e recuperar informações do histórico"""
    
    def __init__(self):
        # Inicializar cliente Qdrant
        self.db_client = QdrantClient()
        
        # Inicializar adaptador de embeddings
        self.embedding_model = None
        
        logger.info("Motor de memória inicializado")
    
    def _get_embedding_model(self):
        """Obter adaptador para o modelo de embeddings (lazy loading)"""
        if self.embedding_model is None:
            from server.llm_modules.lmstudio_adapter import EmbeddingModelAdapter
            self.embedding_model = EmbeddingModelAdapter(LLM_MODELS["embedding"]["default"])
        return self.embedding_model
    
    async def get_text_embedding(self, text):
        """Obter embedding para um texto"""
        embedding_model = self._get_embedding_model()
        return await embedding_model.get_embedding(text)
    
    async def store_interaction(self, input_text, response_text):
        """Armazenar interação na memória"""
        try:
            # Gerar embedding para a interação
            combined_text = f"User: {input_text}\nAI: {response_text}"
            vector = await self.get_text_embedding(combined_text)
            
            # Preparar payload
            payload = {
                "user_input": input_text,
                "ai_response": response_text,
                "timestamp": time.time(),
                "type": "interaction"
            }
            
            # Adicionar ao Qdrant
            point_id = str(uuid.uuid4())
            success = await self.db_client.add_point(vector, payload, id=point_id)
            
            if success:
                logger.info(f"Interação armazenada com ID: {point_id}")
            else:
                logger.error("Falha ao armazenar interação")
                
            return success
        except Exception as e:
            logger.error(f"Erro ao armazenar interação: {e}")
            return False
    
    async def store_document(self, title, content, metadata=None):
        """Armazenar documento na memória"""
        try:
            # Gerar embedding para o documento
            vector = await self.get_text_embedding(content)
            
            # Preparar payload
            payload = {
                "title": title,
                "content": content,
                "timestamp": time.time(),
                "type": "document"
            }
            
            if metadata:
                payload["metadata"] = metadata
            
            # Adicionar ao Qdrant
            point_id = str(uuid.uuid4())
            success = await self.db_client.add_point(vector, payload, id=point_id)
            
            if success:
                logger.info(f"Documento armazenado com ID: {point_id}")
            else:
                logger.error("Falha ao armazenar documento")
                
            return success
        except Exception as e:
            logger.error(f"Erro ao armazenar documento: {e}")
            return False
    
    async def get_relevant_context(self, query, limit=3):
        """Obter contexto relevante para uma consulta"""
        try:
            # Gerar embedding para a consulta
            vector = await self.get_text_embedding(query)
            
            # Buscar pontos similares
            results = await self.db_client.search(vector, limit=limit)
            
            if not results:
                return None
            
            # Formatar contexto
            context = "Contexto relevante:\n\n"
            
            for i, result in enumerate(results):
                payload = result["payload"]
                score = result["score"]
                
                if payload["type"] == "interaction":
                    context += f"{i+1}. Interação anterior (relevância: {score:.2f}):\n"
                    context += f"   Usuário: {payload['user_input']}\n"
                    context += f"   IA: {payload['ai_response']}\n\n"
                elif payload["type"] == "document":
                    context += f"{i+1}. Documento: {payload['title']} (relevância: {score:.2f}):\n"
                    # Limitar tamanho do conteúdo para evitar tokens muito grandes
                    content = payload['content']
                    if len(content) > 500:
                        content = content[:497] + "..."
                    context += f"   {content}\n\n"
            
            return context
        except Exception as e:
            logger.error(f"Erro ao obter contexto relevante: {e}")
            return None
    
    async def get_detailed_context(self, query, limit=5):
        """Obter contexto detalhado para uma consulta"""
        try:
            # Gerar embedding para a consulta
            vector = await self.get_text_embedding(query)
            
            # Buscar pontos similares
            results = await self.db_client.search(vector, limit=limit)
            
            if not results:
                return None
            
            # Formatar contexto detalhado
            context = "Contexto detalhado:\n\n"
            
            for i, result in enumerate(results):
                payload = result["payload"]
                score = result["score"]
                
                if payload["type"] == "interaction":
                    context += f"{i+1}. Interação anterior (relevância: {score:.2f}):\n"
                    context += f"   Usuário: {payload['user_input']}\n"
                    context += f"   IA: {payload['ai_response']}\n\n"
                elif payload["type"] == "document":
                    context += f"{i+1}. Documento: {payload['title']} (relevância: {score:.2f}):\n"
                    content = payload['content']
                    context += f"   {content}\n\n"
            
            return context
        except Exception as e:
            logger.error(f"Erro ao obter contexto detalhado: {e}")
            return None