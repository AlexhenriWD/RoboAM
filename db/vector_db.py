import asyncio
import logging
import sqlite3
import json
import numpy as np
import uuid
import os

logger = logging.getLogger("vector_db")

class SQLiteVectorStore:
    """Cliente de banco de dados vetorial usando SQLite"""
    
    def __init__(self, db_path="memory.db", collection_name="car_memory", vector_size=768):
        self.db_path = db_path
        self.collection_name = collection_name
        self.vector_size = vector_size
        
        # Inicializar banco de dados
        self._initialize_db()
    
    def _initialize_db(self):
        """Inicializar banco de dados SQLite"""
        try:
            # Criar diretório para o banco se não existir
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # Conectar ao banco
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Criar tabela para vetores
            cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.collection_name} (
                id TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                payload TEXT NOT NULL,
                type TEXT NOT NULL
            )
            ''')
            
            # Índice para buscas por tipo
            cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_type ON {self.collection_name} (type)')
            
            conn.commit()
            conn.close()
            
            logger.info(f"Banco SQLite inicializado: {self.db_path}")
        except Exception as e:
            logger.error(f"Erro ao inicializar banco SQLite: {e}")
    
    async def add_point(self, vector, payload, id=None):
        """Adicionar ponto ao banco"""
        try:
            if id is None:
                id = str(uuid.uuid4())
                
            # Converter vetor para bytes
            if isinstance(vector, np.ndarray):
                vector_bytes = vector.tobytes()
            else:
                vector_bytes = np.array(vector, dtype=np.float32).tobytes()
            
            # Converter payload para JSON
            payload_json = json.dumps(payload)
            
            # Extrair tipo do payload
            point_type = payload.get("type", "unknown")
            
            # Conectar ao banco e inserir
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                f"INSERT OR REPLACE INTO {self.collection_name} (id, vector, payload, type) VALUES (?, ?, ?, ?)",
                (id, vector_bytes, payload_json, point_type)
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"Ponto adicionado com sucesso: {id}")
            return True
        except Exception as e:
            logger.error(f"Erro ao adicionar ponto: {e}")
            return False
    
    async def search(self, vector, limit=5, filter=None):
        """Buscar pontos similares usando distância de cosseno"""
        try:
            # Converter vetor para numpy
            if not isinstance(vector, np.ndarray):
                query_vector = np.array(vector, dtype=np.float32)
            else:
                query_vector = vector
                
            # Normalizar vetor de consulta
            query_norm = np.linalg.norm(query_vector)
            if query_norm > 0:
                query_vector = query_vector / query_norm
            
            # Criar conexão ao banco
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Construir consulta SQL com filtro opcional
            query = f"SELECT id, vector, payload FROM {self.collection_name}"
            if filter and "type" in filter:
                query += f" WHERE type = '{filter['type']}'"
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Calcular similaridade para cada resultado
            similarities = []
            for row in results:
                id, vector_bytes, payload_json = row
                
                # Converter bytes para vetor
                db_vector = np.frombuffer(vector_bytes, dtype=np.float32)
                
                # Normalizar vetor do banco
                db_norm = np.linalg.norm(db_vector)
                if db_norm > 0:
                    db_vector = db_vector / db_norm
                
                # Calcular similaridade de cosseno
                similarity = np.dot(query_vector, db_vector)
                
                # Desserializar payload
                payload = json.loads(payload_json)
                
                similarities.append({
                    "id": id,
                    "payload": payload,
                    "score": float(similarity)
                })
            
            # Ordenar por similaridade (maior para menor)
            similarities.sort(key=lambda x: x["score"], reverse=True)
            
            # Limitar resultados
            return similarities[:limit]
        except Exception as e:
            logger.error(f"Erro ao buscar pontos: {e}")
            return []
    
    async def delete_point(self, id):
        """Excluir ponto do banco"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(f"DELETE FROM {self.collection_name} WHERE id = ?", (id,))
            
            deleted = cursor.rowcount > 0
            
            conn.commit()
            conn.close()
            
            if deleted:
                logger.info(f"Ponto {id} excluído com sucesso")
            else:
                logger.warning(f"Ponto {id} não encontrado")
                
            return deleted
        except Exception as e:
            logger.error(f"Erro ao excluir ponto: {e}")
            return False