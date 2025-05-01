import os
import asyncio
import logging
import httpx
import numpy as np
from typing import Dict, List, Any, Optional

logger = logging.getLogger("lmstudio_adapter")

class LmStudioModelAdapter:
    """Adaptador para modelos do LM Studio"""
    
    def __init__(self, model_name):
        self.model_name = model_name
        self.api_url = os.environ.get("LMSTUDIO_API_URL", "http://localhost:1234/v1")
        logger.info(f"Adaptador LM Studio inicializado para modelo: {model_name}")
    
    async def generate(self, prompt):
        """Gerar texto usando o modelo LM Studio"""
        try:
            # Preparar payload para a API
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 1024
            }
            
            # Fazer requisição HTTP para o LM Studio
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    json=payload,
                    timeout=60.0  # Timeout de 60 segundos
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Erro na API do LM Studio: {response.status_code} - {response.text}")
                    return f"Erro na API: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Erro ao gerar texto com LM Studio: {e}")
            return f"Erro de geração: {str(e)}"


class EmbeddingModelAdapter:
    """Adaptador para modelos de embedding do LM Studio"""
    
    def __init__(self, model_name):
        self.model_name = model_name
        self.api_url = os.environ.get("LMSTUDIO_API_URL", "http://localhost:1234/v1")
        logger.info(f"Adaptador de Embedding inicializado para modelo: {model_name}")
    
    async def get_embedding(self, text):
        """Obter embedding para um texto"""
        try:
            # Preparar payload para a API
            payload = {
                "model": self.model_name,
                "input": text
            }
            
            # Fazer requisição HTTP para o LM Studio
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/embeddings",
                    json=payload,
                    timeout=30.0  # Timeout de 30 segundos
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["data"][0]["embedding"]
                else:
                    logger.error(f"Erro na API de embeddings: {response.status_code} - {response.text}")
                    # Retornar vetor aleatório em caso de erro (uso apenas para desenvolvimento)
                    return np.random.rand(768).tolist()
                
        except Exception as e:
            logger.error(f"Erro ao gerar embedding: {e}")
            # Retornar vetor aleatório em caso de erro (uso apenas para desenvolvimento)
            return np.random.rand(768).tolist()