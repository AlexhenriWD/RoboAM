# Configurações do sistema de IA veicular

# Modelos disponíveis
LLM_MODELS = {
    "decision": {
        "default": "meta-llama/llama-4-maverick-17b-128e",
        "provider": "groq",
        "options": ["meta-llama/llama-4-maverick-17b-128e"]
    },
    "vision": {
        "default": "meta-llama/llama-4-maverick-17b-128e",
        "provider": "groq",
        "options": ["meta-llama/llama-4-maverick-17b-128e", "llava-v1.5-7b-llamafile"]
    },
    "navigation": {
        "default": "llama3-70b-8192",
        "provider": "groq",
        "options": ["llama3-70b-8192"]
    },
    "conversation": {
        "default": "l3-8b-lunaris-v1",
        "provider": "lmstudio",
        "options": ["l3-8b-lunaris-v1"]
    },
    "embedding": {
        "default": "text-embedding-granite-embedding-278m",
        "provider": "lmstudio",
        "options": ["text-embedding-granite-embedding-278m"]
    }
}

# Configurações de serviço
SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "websocket_path": "/ws"
}

# Configurações do Raspberry Pi
PI_CONFIG = {
    "host": "raspberrypi.local",  # Ou IP específico
    "port": 8765,
    "reconnect_interval": 5  # segundos
}

VECTOR_DB_CONFIG = {
    "db_path": "db/memory.db",
    "collection_name": "car_memory",
    "vector_size": 768
}

# Configurações de personalidade
PERSONALITY_CONFIG = {
    "name": "AIVA",  # Auto Intelligent Vehicle Assistant
    "default_prompt": "Sou AIVA, uma assistente de veículo inteligente. Posso ajudar com navegação, informações e controle do veículo."
}

# Configurações da câmera
CAMERA_CONFIG = {
    "resolution": (640, 480),
    "framerate": 15,
    "rotation": 180  # Ajustar conforme a orientação da câmera
}

# Configurações do carro Freenove
FREENOVE_CONFIG = {
    "connection_board_version": 1,  # Versão da placa de conexão (1 ou 2)
    "motor_speed_range": (-4096, 4096),
    "servo_angle_range": (0, 180),
    "ultrasonic_threshold": 30  # cm
}