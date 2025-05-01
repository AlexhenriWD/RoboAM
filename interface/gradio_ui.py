import gradio as gr
import numpy as np
import time
import threading
import websocket
import json
import requests
import os
import cv2
import base64
from PIL import Image
import io
import logging

from config import LLM_MODELS, SERVER_CONFIG, CAMERA_CONFIG

logger = logging.getLogger("gradio_ui")

class WebSocketClient:
    """Cliente WebSocket para comunicação com o servidor"""
    
    def __init__(self, url, on_message=None, on_error=None, on_close=None, on_open=None):
        self.url = url
        self.ws = None
        self.connected = False
        self.lock = threading.Lock()
        
        # Callbacks
        self.on_message = on_message or (lambda ws, msg: None)
        self.on_error = on_error or (lambda ws, error: None)
        self.on_close = on_close or (lambda ws, close_status_code, close_msg: None)
        self.on_open = on_open or (lambda ws: None)
        
        # Thread do WebSocket
        self.ws_thread = None
    
    def connect(self):
        """Iniciar conexão WebSocket em thread separada"""
        if self.connected:
            return
            
        def _on_message(ws, message):
            self.on_message(ws, message)
            
        def _on_error(ws, error):
            self.connected = False
            self.on_error(ws, error)
            
        def _on_close(ws, close_status_code, close_msg):
            self.connected = False
            self.on_close(ws, close_status_code, close_msg)
            
        def _on_open(ws):
            self.connected = True
            self.on_open(ws)
        
        # Configurar WebSocket
        self.ws = websocket.WebSocketApp(
            self.url,
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
            on_open=_on_open
        )
        
        # Iniciar WebSocket em thread separada
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()
    
    def disconnect(self):
        """Desconectar WebSocket"""
        if self.ws:
            self.ws.close()
            self.connected = False
    
    def send(self, message):
        """Enviar mensagem pelo WebSocket"""
        if not self.connected or not self.ws:
            logger.error("WebSocket não conectado")
            return False
            
        with self.lock:
            try:
                self.ws.send(message)
                return True
            except Exception as e:
                logger.error(f"Erro ao enviar mensagem: {e}")
                return False

def create_interface(command_center):
    """Criar interface Gradio"""
    
    # Estado da interface
    state = {
        "ws_client": None,
        "connected": False,
        "chat_history": [],
        "system_status": {
            "battery": 0,
            "ultrasonic": 0,
            "light_left": 0,
            "light_right": 0,
            "pi_connected": False
        },
        "current_mode": "manual",  # manual, auto, light, sonic, line
        "active_models": command_center.active_models.copy()
    }
    
    # Callbacks para WebSocket
    def on_ws_message(ws, message):
        try:
            data = json.loads(message)
            
            # Atualizar status do sistema
            if "sensor" in data:
                if data["sensor"] == "ultrasonic":
                    state["system_status"]["ultrasonic"] = data["value"]
            
            if "battery" in data:
                state["system_status"]["battery"] = data["battery"]
                
            if "light" in data:
                state["system_status"]["light_left"] = data["light"]["left"]
                state["system_status"]["light_right"] = data["light"]["right"]
        except:
            pass
    
    def on_ws_open(ws):
        state["connected"] = True
        logger.info("WebSocket conectado")
    
    def on_ws_close(ws, close_status_code, close_msg):
        state["connected"] = False
        logger.info(f"WebSocket desconectado: {close_status_code}, {close_msg}")
    
    def on_ws_error(ws, error):
        state["connected"] = False
        logger.error(f"Erro no WebSocket: {error}")
    
    # Funções auxiliares da interface
    def connect_websocket():
        """Conectar ao servidor WebSocket"""
        if state["ws_client"] is None:
            url = f"ws://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/ws/ui"
            state["ws_client"] = WebSocketClient(
                url,
                on_message=on_ws_message,
                on_open=on_ws_open,
                on_close=on_ws_close,
                on_error=on_ws_error
            )
        
        state["ws_client"].connect()
        return "Conectando ao servidor..."
    
    def disconnect_websocket():
        """Desconectar do servidor WebSocket"""
        if state["ws_client"]:
            state["ws_client"].disconnect()
            state["connected"] = False
        return "Desconectado do servidor"
    
    def send_command(action, **kwargs):
        """Enviar comando para o Raspberry Pi"""
        if not state["connected"] or not state["ws_client"]:
            return "Não conectado ao servidor"
            
        command = {"action": action, "target": "pi"}
        command.update(kwargs)
        
        success = state["ws_client"].send(json.dumps(command))
        return "Comando enviado" if success else "Falha ao enviar comando"
    
    def process_message(message):
        """Processar mensagem do usuário"""
        if not message.strip():
            return state["chat_history"]
            
        # Adicionar mensagem do usuário ao histórico
        state["chat_history"].append((message, None))
        
        try:
            # Enviar requisição para processar a mensagem
            response = requests.post(
                f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/api/process",
                json={"text": message, "type": "text", "with_memory": True}
            )
            
            if response.status_code == 200:
                ai_response = response.json()["response"]
                state["chat_history"][-1] = (message, ai_response)
            else:
                state["chat_history"][-1] = (message, "Erro ao processar mensagem")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")
            state["chat_history"][-1] = (message, f"Erro: {str(e)}")
        
        return state["chat_history"]
    
    def change_model(model_type, model_name):
        """Alterar modelo de IA"""
        try:
            response = requests.post(
                f"http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}/api/models/{model_type}",
                params={"model_name": model_name}
            )
            
            if response.status_code == 200:
                state["active_models"][model_type] = model_name
                return f"Modelo {model_type} alterado para {model_name}"
            else:
                return f"Erro ao alterar modelo: {response.text}"
        except Exception as e:
            logger.error(f"Erro ao alterar modelo: {e}")
            return f"Erro: {str(e)}"
    
    def update_status():
        """Atualizar exibição de status"""
        status = state["system_status"]
        return (
            f"Bateria: {status['battery']:.2f}V | " +
            f"Distância: {status['ultrasonic']}cm | " +
            f"Luz: L={status['light_left']:.2f}V, R={status['light_right']:.2f}V | " +
            f"Conexão Pi: {'Conectado' if status['pi_connected'] else 'Desconectado'}"
        )
    
    def change_mode(mode):
        """Alterar modo de operação"""
        state["current_mode"] = mode
        
        # Enviar comando para alterar modo
        if state["connected"] and state["ws_client"]:
            command = {
                "action": "mode",
                "target": "pi",
                "mode": mode
            }
            state["ws_client"].send(json.dumps(command))
        
        return f"Modo alterado para: {mode}"
    
    # Componentes da interface
    with gr.Blocks(title="Sistema de IA Veicular") as interface:
        with gr.Row():
            with gr.Column(scale=2):
                # Título e status
                gr.Markdown("# 🤖 Sistema de IA Veicular")
                status_text = gr.Textbox(label="Status do Sistema", interactive=False)
                
                # Chat
                chatbot = gr.Chatbot(value=state["chat_history"], height=400)
                msg = gr.Textbox(label="Mensagem", placeholder="Digite uma mensagem...")
                send_btn = gr.Button("Enviar")
                
                # Histórico de comandos
                command_history = gr.Textbox(label="Histórico de Comandos", interactive=False, lines=5)
            
            with gr.Column(scale=1):
                # Conexão
                gr.Markdown("## Conexão")
                with gr.Row():
                    connect_btn = gr.Button("Conectar")
                    disconnect_btn = gr.Button("Desconectar")
                
                # Controle do carro
                gr.Markdown("## Controle do Carro")
                with gr.Row():
                    forward_btn = gr.Button("⬆️")
                with gr.Row():
                    left_btn = gr.Button("⬅️")
                    stop_btn = gr.Button("⏹️")
                    right_btn = gr.Button("➡️")
                with gr.Row():
                    backward_btn = gr.Button("⬇️")
                
                # Movimento lateral (mecanum)
                gr.Markdown("## Movimento Mecanum")
                with gr.Row():
                    move_left_btn = gr.Button("◀️ Lateral")
                    move_right_btn = gr.Button("Lateral ▶️")
                
                # Modos de operação
                gr.Markdown("## Modos de Operação")
                mode_radio = gr.Radio(
                    ["manual", "light", "sonic", "line"],
                    label="Modo",
                    value="manual"
                )
                
                # Controle da câmera
                gr.Markdown("## Controle da Câmera")
                with gr.Row():
                    cam_up_btn = gr.Button("Câmera ⬆️")
                with gr.Row():
                    cam_left_btn = gr.Button("Câmera ⬅️")
                    cam_center_btn = gr.Button("Centro")
                    cam_right_btn = gr.Button("Câmera ➡️")
                with gr.Row():
                    cam_down_btn = gr.Button("Câmera ⬇️")
        
        with gr.Row():
            # Configuração de modelos
            gr.Markdown("## Configuração de Modelos")
            
            with gr.Column():
                decision_model = gr.Dropdown(
                    choices=LLM_MODELS["decision"]["options"],
                    value=state["active_models"]["decision"],
                    label="Modelo de Decisão"
                )
            
            with gr.Column():
                vision_model = gr.Dropdown(
                    choices=LLM_MODELS["vision"]["options"],
                    value=state["active_models"]["vision"],
                    label="Modelo de Visão"
                )
            
            with gr.Column():
                navigation_model = gr.Dropdown(
                    choices=LLM_MODELS["navigation"]["options"],
                    value=state["active_models"]["navigation"],
                    label="Modelo de Navegação"
                )
            
            with gr.Column():
                conversation_model = gr.Dropdown(
                    choices=LLM_MODELS["conversation"]["options"],
                    value=state["active_models"]["conversation"],
                    label="Modelo de Conversação"
                )
        
        # Eventos
        # Botões de conexão
        connect_btn.click(connect_websocket, outputs=command_history)
        disconnect_btn.click(disconnect_websocket, outputs=command_history)
        
        # Botões de controle do carro
        forward_btn.click(lambda: send_command("move", dir="forward", speed=70), outputs=command_history)
        backward_btn.click(lambda: send_command("move", dir="backward", speed=70), outputs=command_history)
        left_btn.click(lambda: send_command("move", dir="left", speed=70), outputs=command_history)
        right_btn.click(lambda: send_command("move", dir="right", speed=70), outputs=command_history)
        stop_btn.click(lambda: send_command("move", dir="stop"), outputs=command_history)
        move_left_btn.click(lambda: send_command("move", dir="move_left", speed=70), outputs=command_history)
        move_right_btn.click(lambda: send_command("move", dir="move_right", speed=70), outputs=command_history)
        
        # Botões de controle da câmera
        cam_up_btn.click(lambda: send_command("camera", servo="1", angle=120), outputs=command_history)
        cam_down_btn.click(lambda: send_command("camera", servo="1", angle=60), outputs=command_history)
        cam_left_btn.click(lambda: send_command("camera", servo="0", angle=120), outputs=command_history)
        cam_right_btn.click(lambda: send_command("camera", servo="0", angle=60), outputs=command_history)
        cam_center_btn.click(
            lambda: send_command("camera", servo="0", angle=90) or send_command("camera", servo="1", angle=90),
            outputs=command_history
        )
        
        # Alteração de modo
        mode_radio.change(change_mode, inputs=mode_radio, outputs=command_history)
        
        # Alteração de modelos
        decision_model.change(
            lambda model: change_model("decision", model),
            inputs=decision_model,
            outputs=command_history
        )
        vision_model.change(
            lambda model: change_model("vision", model),
            inputs=vision_model,
            outputs=command_history
        )
        navigation_model.change(
            lambda model: change_model("navigation", model),
            inputs=navigation_model,
            outputs=command_history
        )
        conversation_model.change(
            lambda model: change_model("conversation", model),
            inputs=conversation_model,
            outputs=command_history
        )
        
        # Processamento de mensagens
        send_btn.click(process_message, inputs=msg, outputs=chatbot)
        msg.submit(process_message, inputs=msg, outputs=chatbot)
        
        # Atualização automática de status
        interface.load(update_status, outputs=status_text)
        
        # Atualização periódica
        gr.Textbox(visible=False).every(1, update_status, outputs=status_text)
    
    return interface