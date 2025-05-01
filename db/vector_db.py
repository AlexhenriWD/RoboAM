import asyncio
import httpx
import logging
from typing import List, Dict, Any, Optional
import numpy as np
import json

from config import QDRANT_CONFIG

logger = logging.getLogger("vector_db")

class QdrantClient:
    """Cliente para o banco de dados vetorial Qdrant"""
    
    def __init__(self, url=None, collection_name=None):
        self.url = url or QDRANT_CONFIG["url"]
        self.collection_name = collection_name or QDRANT_CONFIG["collection_name"]
        self.vector_size = QDRANT_CONFIG["vector_size"]
        
        # Verificar se a coleção existe, caso contrário criar
        self._initialize_collection()
    
    def _initialize_collection(self):
        """Inicializar coleção no Qdrant"""
        try:
            response = httpx.get(f"{self.url}/collections/{self.collection_name}")
            
            if response.status_code == 404:
                # Coleção não existe, criar
                self._create_collection()
            elif response.status_code == 200:
                logger.info(f"Coleção {self.collection_name} já existe")
            else:
                logger.error(f"Erro ao verificar coleção: {response.text}")
        except Exception as e:
            logger.error(f"Erro ao inicializar coleção: {e}")
    
    def _create_collection(self):
        """Criar coleção no Qdrant"""
        try:
            payload = {
                "vectors": {
                    "size": self.vector_size,
                    "distance": "Cosine"
                }
            }
            
            response = httpx.put(
                f"{self.url}/collections/{self.collection_name}",
                json=payload
            )
            
            if response.status_code == 200:
                logger.info(f"Coleção {self.collection_name} criada com sucesso")
            else:
                logger.error(f"Erro ao criar coleção: {response.text}")
        except Exception as e:
            logger.error(f"Erro ao criar coleção: {e}")
    
    async def add_point(self, vector, payload, id=None):
        """Adicionar ponto ao Qdrant"""
        try:
            # Converter vetor para lista, se for numpy array
            if isinstance(vector, np.ndarray):
                vector = vector.tolist()
            
            point_data = {
                "vectors": vector,
                "payload": payload
            }
            
            if id is not None:
                point_data["id"] = id
            
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.url}/points/{self.collection_name}",
                    json={"points": [point_data]}
                )
                
                if response.status_code == 200:
                    logger.info(f"Ponto adicionado com sucesso: {id}")
                    return True
                else:
                    logger.error(f"Erro ao adicionar ponto: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao adicionar ponto: {e}")
            return False
    
    async def search(self, vector, limit=5, filter=None):
        """Buscar pontos similares no Qdrant"""
        try:
            # Converter vetor para lista, se for numpy array
            if isinstance(vector, np.ndarray):
                vector = vector.tolist()
            
            payload = {
                "vector": vector,
                "limit": limit
            }
            
            if filter:
                payload["filter"] = filter
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.url}/points/{self.collection_name}/search",
                    json=payload
                )
                
                if response.status_code == 200:
                    return response.json()["result"]
                else:
                    logger.error(f"Erro ao buscar pontos: {response.text}")
                    return []
        except Exception as e:
            logger.error(f"Erro ao buscar pontos: {e}")
            return []
    
    async def delete_point(self, id):
        """Excluir ponto do Qdrant"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.url}/points/{self.collection_name}/{id}"
                )
                
                if response.status_code == 200:
                    logger.info(f"Ponto {id} excluído com sucesso")
                    return True
                else:
                    logger.error(f"Erro ao excluir ponto: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao excluir ponto: {e}")
            return False