"""
Cliente Groq para processamento de visão e decisões do carro autônomo
Com rate limiting e cache para evitar erro 429
"""

import os
import json
import base64
import time
from typing import Dict, List, Optional, Tuple
from collections import deque
import requests
from io import BytesIO

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("OpenCV não disponível - funcionalidade de visão limitada")


class RateLimiter:
    """Rate limiter simples para controlar requisições"""
    
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        """
        Args:
            max_requests: Número máximo de requisições
            time_window: Janela de tempo em segundos
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
    
    def can_make_request(self) -> bool:
        """Verifica se pode fazer uma requisição"""
        now = time.time()
        
        # Remover requisições antigas
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        
        return len(self.requests) < self.max_requests
    
    def add_request(self):
        """Registra uma nova requisição"""
        self.requests.append(time.time())
    
    def wait_if_needed(self):
        """Espera se necessário antes de fazer requisição"""
        while not self.can_make_request():
            sleep_time = self.requests[0] + self.time_window - time.time()
            if sleep_time > 0:
                print(f"⏳ Rate limit: aguardando {sleep_time:.1f}s...")
                time.sleep(min(sleep_time + 0.5, 5))
            else:
                break


class GroqVisionClient:
    """Cliente para usar Groq API com visão computacional"""
    
    def __init__(self, api_key: Optional[str] = None, rate_limit: int = 10):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("GROQ_API_KEY não encontrada. Configure no .env ou passe como parâmetro")
        
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.2-90b-vision-preview"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Rate limiter (10 requisições por minuto por padrão)
        self.rate_limiter = RateLimiter(max_requests=rate_limit, time_window=60)
        
        # Cache de decisões (evita requisições repetidas)
        self.last_decision = None
        self.last_decision_time = 0
        self.cache_duration = 2.0  # Reutilizar decisão por 2 segundos
        
        # Retry configuration
        self.max_retries = 2
        self.retry_delay = 2.0
        
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

            def _make_request(self, payload: Dict, use_cache: bool = True) -> Dict:
        """
        Faz requisição à API com rate limiting e retry
        
        Args:
            payload: Dados da requisição
            use_cache: Se deve usar cache de decisões
        
        Returns:
            Resposta da API ou decisão em cache
        """
        # Verificar cache
        if use_cache and self.last_decision:
            time_since_last = time.time() - self.last_decision_time
            if time_since_last < self.cache_duration:
                print(f"📦 Usando decisão em cache ({time_since_last:.1f}s atrás)")
                return {
                    'success': True,
                    'decision': self.last_decision,
                    'cached': True
                }
        
        # Rate limiting
        self.rate_limiter.wait_if_needed()
        
        # Tentar fazer requisição com retry
        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.add_request()
                
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=15
                )
                
                # Tratar erro 429 especificamente
                if response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (attempt + 1)
                        print(f"⏳ Rate limit atingido, aguardando {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        # Última tentativa falhou, retornar fallback
                        return {'success': False, 'error': 'Rate limit excedido'}
                
                response.raise_for_status()
                return {'success': True, 'response': response.json()}
                
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    print(f"⏱️ Timeout, tentativa {attempt + 2}/{self.max_retries}...")
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': 'Timeout na API'}
                
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1 and '429' not in str(e):
                    time.sleep(self.retry_delay)
                    continue
                return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'Máximo de tentativas excedido'}
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

Retorne APENAS um JSON válido (sem markdown, sem explicações):
{{
  "recommended_action": "forward|backward|left|right|stop",
  "speed": 0-100,
  "reason": "explicação curta",
  "safety_level": "safe|caution|danger"
}}

IMPORTANTE:
- Distância < 30cm: STOP ou BACKWARD
- Velocidade máxima: 60
- Retorne APENAS o JSON"""

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 150
        }
        
        result = self._make_request(payload)
        
        if not result['success']:
            print(f"❌ Erro na API: {result.get('error')}")
            return {
                'success': False,
                'error': result.get('error'),
                'decision': self._get_safe_fallback(sensor_data)
            }
        
        # Se veio do cache
        if result.get('cached'):
            return result
        
        try:
            content = result['response']['choices'][0]['message']['content']
            
            # Limpar markdown
            content = content.strip()
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            decision = json.loads(content.strip())
            
            # Validar
            required = ['recommended_action', 'speed', 'reason', 'safety_level']
            if not all(k in decision for k in required):
                raise ValueError("Campos obrigatórios faltando")
            
            # Cachear
            self.last_decision = decision
            self.last_decision_time = time.time()
            
            return {
                'success': True,
                'decision': decision
            }
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"❌ Erro ao parsear: {e}")
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