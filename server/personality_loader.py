import logging
import os
import json

logger = logging.getLogger("personality_loader")

class PersonalityLoader:
    """Carregador de personalidade para o assistente IA veicular"""
    
    def __init__(self, personality_file=None):
        self.personality_file = personality_file or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "db",
            "personality.json"
        )
        self.personality = self._load_personality()
        logger.info("Carregador de personalidade inicializado")
    
    def _load_personality(self):
        """Carregar personalidade do arquivo JSON"""
        try:
            if os.path.exists(self.personality_file):
                with open(self.personality_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Criar personalidade padrão
                default_personality = {
                    "name": "AIVA",
                    "description": "Assistente Inteligente de Veículo Autônomo",
                    "personality_traits": [
                        "Prestativa",
                        "Informativa",
                        "Segura",
                        "Confiável"
                    ],
                    "responses": {
                        "greeting": "Olá, sou a AIVA, sua assistente veicular. Como posso ajudar?",
                        "farewell": "Até logo! Tenha uma ótima viagem.",
                        "unknown": "Desculpe, não entendi. Poderia reformular?"
                    }
                }
                
                # Salvar personalidade padrão
                os.makedirs(os.path.dirname(self.personality_file), exist_ok=True)
                with open(self.personality_file, 'w', encoding='utf-8') as f:
                    json.dump(default_personality, f, indent=4, ensure_ascii=False)
                
                return default_personality
        except Exception as e:
            logger.error(f"Erro ao carregar personalidade: {e}")
            return {
                "name": "AIVA",
                "description": "Assistente Inteligente de Veículo Autônomo",
                "personality_traits": ["Prestativa"],
                "responses": {"greeting": "Olá, como posso ajudar?"}
            }
    
    def get_personality(self):
        """Obter personalidade carregada"""
        return self.personality
    
    def get_system_prompt(self):
        """Gerar prompt de sistema com base na personalidade"""
        personality = self.personality
        
        prompt = f"Você é {personality['name']}, {personality['description']}.\n\n"
        
        if "personality_traits" in personality:
            prompt += "Seus traços de personalidade são: " + ", ".join(personality["personality_traits"]) + ".\n\n"
        
        prompt += "Você é um assistente veicular que ajuda com navegação, informações e controle do veículo.\n"
        prompt += "Você pode responder perguntas, controlar funções do veículo e ajudar com informações de viagem.\n"
        
        return prompt
    
    def update_personality(self, new_personality):
        """Atualizar personalidade e salvar no arquivo"""
        try:
            # Atualizar personalidade
            self.personality.update(new_personality)
            
            # Salvar no arquivo
            with open(self.personality_file, 'w', encoding='utf-8') as f:
                json.dump(self.personality, f, indent=4, ensure_ascii=False)
            
            logger.info("Personalidade atualizada com sucesso")
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar personalidade: {e}")
            return False