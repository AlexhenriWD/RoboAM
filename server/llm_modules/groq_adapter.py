import os
import asyncio
import logging
import groq
from typing import Dict, List, Any, Optional

logger = logging.getLogger("groq_adapter")

class GroqModelAdapter:
    """Adaptador para modelos da Groq"""
    
    def __init__(self, model_name):
        self.model_name = model_name
        self.api_key = os.environ.get("GROQ_API_KEY")
        
        if not self.api_key:
            logger.warning("GROQ_API_KEY não encontrada nas variáveis de ambiente")
            
        self.client = groq.Client(api_key=self.api_key)
        logger.info(f"Adaptador Groq inicializado para modelo: {model_name}")
    
    async def generate(self, prompt):
        """Gerar texto usando o modelo Groq"""
        try:
            # Usar asyncio para evitar bloqueio do event loop
            loop = asyncio.get_event_loop()
            
            # Criar a chamada à API de forma assíncrona
            completion = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1024
                )
            )
            
            # Extrair e retornar o texto gerado
            response = completion.choices[0].message.content
            return response
            
        except Exception as e:
            logger.error(f"Erro ao gerar texto com Groq: {e}")
            return f"Erro de geração: {str(e)}"