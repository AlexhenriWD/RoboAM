"""
Cliente Groq para processamento de visão e decisões do carro autônomo
"""

import os
import json
import base64
from typing import Dict, List, Optional, Tuple
import requests
from io import BytesIO

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("OpenCV não disponível - funcionalidade de visão limitada")


class GroqVisionClient:
    """Cliente para usar Groq API com visão computacional"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("GROQ_API_KEY não encontrada. Configure no .env ou passe como parâmetro")
        
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "meta-llama/llama-4-maverick-17b-128e-instruct"  # Modelo com visão
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
    def encode_image(self, image) -> str:
        """Codifica imagem para base64"""
        if not OPENCV_AVAILABLE:
            raise RuntimeError("OpenCV não disponível")
        
        # Redimensionar para economizar tokens
        h, w = image.shape[:2]
        if w > 512:
            ratio = 512 / w
            image = cv2.resize(image, (512, int(h * ratio)))
        
        # Converter para JPEG
        _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode('utf-8')
    
    def analyze_scene(self, image, sensor_data: Dict) -> Dict:
        """
        Analisa a cena e retorna decisões de navegação
        
        Args:
            image: Frame da câmera (numpy array)
            sensor_data: Dados dos sensores (ultrassom, infrared, luz, etc)
            
        Returns:
            Dict com análise e comando de movimento
        """
        
        # Preparar contexto dos sensores
        sensor_context = f"""
Dados dos sensores do robô:
- Distância ultrasônica: {sensor_data.get('ultrasonic', 'N/A')} cm
- Sensores infravermelhos: {sensor_data.get('infrared', [])}
- Luz esquerda: {sensor_data.get('light_left', 'N/A')} V
- Luz direita: {sensor_data.get('light_right', 'N/A')} V
- Bateria: {sensor_data.get('battery', 'N/A')} V
"""
        
        # Codificar imagem
        image_base64 = self.encode_image(image)
        
        # Prompt para análise
        prompt = f"""Você é o sistema de visão de um robô autônomo Freenove Smart Car.

{sensor_context}

Analise a imagem da câmera e os dados dos sensores, então retorne APENAS um JSON válido (sem markdown) com:
{{
  "scene_description": "descrição breve do que vê",
  "obstacles": ["lista de obstáculos detectados"],
  "recommended_action": "forward|backward|left|right|stop",
  "speed": 0-100,
  "reason": "explicação da decisão",
  "safety_level": "safe|caution|danger"
}}

Considere:
1. Obstáculos próximos (< 30cm) exigem parada ou desvio
2. Prefira movimentos suaves
3. Use os sensores infravermelhos para detectar linhas
4. Mantenha bateria acima de 6.5V"""

        # Fazer requisição
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.3,  # Baixa temperatura para respostas mais consistentes
            "max_tokens": 500
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Extrair JSON da resposta
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            
            decision = json.loads(content.strip())
            
            return {
                'success': True,
                'decision': decision,
                'raw_response': content
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Erro na API: {str(e)}',
                'decision': self._get_safe_fallback(sensor_data)
            }
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'error': f'Erro ao parsear JSON: {str(e)}',
                'decision': self._get_safe_fallback(sensor_data)
            }
    
    def _get_safe_fallback(self, sensor_data: Dict) -> Dict:
        """Retorna decisão segura em caso de erro na IA"""
        distance = sensor_data.get('ultrasonic', 100)
        
        if distance < 20:
            action = 'stop'
            reason = 'Obstáculo muito próximo - modo seguro'
        elif distance < 40:
            action = 'backward'
            reason = 'Obstáculo próximo - recuando'
        else:
            action = 'stop'
            reason = 'Erro na IA - parando por segurança'
        
        return {
            'scene_description': 'Modo seguro ativado',
            'obstacles': ['Desconhecido'],
            'recommended_action': action,
            'speed': 30,
            'reason': reason,
            'safety_level': 'caution'
        }
    
    def simple_decision(self, sensor_data: Dict) -> Dict:
        """
        Decisão baseada apenas em sensores (sem visão)
        Útil para quando a câmera não está disponível
        """
        
        prompt = f"""Você é o sistema de controle de um robô autônomo.

Dados dos sensores:
- Distância ultrasônica: {sensor_data.get('ultrasonic', 'N/A')} cm
- Sensores infravermelhos (linha): {sensor_data.get('infrared', [])}
- Luz esquerda: {sensor_data.get('light_left', 'N/A')} V
- Luz direita: {sensor_data.get('light_right', 'N/A')} V
- Bateria: {sensor_data.get('battery', 'N/A')} V

Retorne APENAS um JSON válido com sua decisão:
{{
  "recommended_action": "forward|backward|left|right|stop",
  "speed": 0-100,
  "reason": "explicação breve",
  "safety_level": "safe|caution|danger"
}}"""

        payload = {
            "model": "llama-3.3-70b-versatile",  # Modelo texto-only mais rápido
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 200
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
            
            content = response.json()['choices'][0]['message']['content']
            
            # Limpar markdown
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            
            decision = json.loads(content.strip())
            
            return {
                'success': True,
                'decision': decision
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'decision': self._get_safe_fallback(sensor_data)
            }


# Exemplo de uso
if __name__ == '__main__':
    # Teste sem visão
    client = GroqVisionClient()
    
    sensor_data = {
        'ultrasonic': 45.5,
        'infrared': [0, 1, 0],
        'light_left': 2.3,
        'light_right': 2.5,
        'battery': 7.2
    }
    
    print("Testando decisão baseada em sensores...")
    result = client.simple_decision(sensor_data)
    print(json.dumps(result, indent=2, ensure_ascii=False))