#!/usr/bin/env python3
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import threading
import logging
import argparse
import os

from config import SERVER_CONFIG
from server.api_router import setup_routes
from server.command_center import CommandCenter
from interface.gradio_ui import create_interface

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ia_car.log")
    ]
)
logger = logging.getLogger("main")

# Criar aplicação FastAPI
app = FastAPI(title="Sistema de IA Veicular")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar o centro de comando
command_center = CommandCenter()

# Configurar rotas da API
setup_routes(app, command_center)

# Função para iniciar o servidor FastAPI
def start_fastapi():
    uvicorn.run(
        app,
        host=SERVER_CONFIG["host"],
        port=SERVER_CONFIG["port"]
    )

# Função para iniciar a interface Gradio
def start_gradio():
    interface = create_interface(command_center)
    interface.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sistema de IA Veicular")
    parser.add_argument("--no-ui", action="store_true", help="Executar sem interface Gradio")
    parser.add_argument("--no-server", action="store_true", help="Executar sem servidor FastAPI")
    args = parser.parse_args()
    
    # Iniciar o servidor FastAPI em uma thread separada, se necessário
    if not args.no_server:
        fastapi_thread = threading.Thread(target=start_fastapi)
        fastapi_thread.daemon = True
        fastapi_thread.start()
        logger.info(f"Servidor FastAPI iniciado em {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    
    # Iniciar a interface Gradio, se necessário
    if not args.no_ui:
        logger.info("Iniciando interface Gradio...")
        start_gradio()
    else:
        # Se não iniciar a interface, manter o programa em execução
        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            logger.info("Encerrando aplicação...")