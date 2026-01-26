#!/usr/bin/env python3
"""
EVA CAMERA SYSTEM - Sistema Completo de Câmeras
Implementa troca automática entre Pi Camera e USB Webcam

INTEGRAÇÃO:
1. Adicionar ao eva_network_server.py
2. Substituir CameraStreamServer existente
3. Automático: troca quando garra/cabeça se move
"""

import asyncio
import base64
import io
import json
import time
from typing import Set, Optional, Dict
from dataclasses import dataclass
from enum import Enum

import cv2
from picamera2 import Picamera2
from PIL import Image


class CameraMode(Enum):
    """Modo de operação das câmeras"""
    NAVIGATION = "navigation"  # USB Webcam (movimento do carro)
    HEAD = "head"              # Pi Camera (quando usa garra/cabeça)
    AUTO = "auto"              # Troca automática


@dataclass
class CameraConfig:
    """Configuração das câmeras"""
    # Stream settings
    fps: int = 15
    width: int = 640
    height: int = 480
    quality: int = 70  # JPEG quality (0-100)
    
    # Auto-switch settings
    head_idle_timeout: float = 3.0  # Volta pra navegação após 3s parada
    movement_threshold: int = 5     # Graus de movimento pra ativar head cam


class SmartCameraSystem:
    """
    Sistema Inteligente de Câmeras
    
    ✅ Duas câmeras:
       - USB Webcam: navegação/movimento do carro
       - Pi Camera: garra/cabeça
    
    ✅ Troca automática:
       - Movimento de cabeça → ativa Pi Camera
       - 3s sem mover cabeça → volta pra USB Webcam
    
    ✅ Stream via WebSocket
    """
    
    def __init__(self, config: Optional[CameraConfig] = None):
        self.cfg = config or CameraConfig()
        
        # Câmeras
        self.picam: Optional[Picamera2] = None
        self.webcam: Optional[cv2.VideoCapture] = None
        
        # Estado
        self.picam_active = False
        self.webcam_active = False
        self.streaming = False
        
        # Modo atual
        self.mode = CameraMode.AUTO
        self.active_camera = "webcam"  # Começa com navegação
        
        # Clientes WebSocket
        self.clients: Set = set()
        
        # Auto-switch state
        self.last_head_position: Optional[Dict] = None
        self.last_head_move_time: float = 0.0
        self.head_is_moving = False
        
        print("📷 Smart Camera System criado")
    
    # ==========================================
    # INICIALIZAÇÃO
    # ==========================================
    
    def start(self) -> bool:
        """Inicializa as câmeras"""
        success = True
        
        # 1. USB Webcam (navegação)
        try:
            self.webcam = cv2.VideoCapture(1)  # /dev/video1 = REDRAGON
            if self.webcam.isOpened():
                self.webcam.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
                self.webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
                self.webcam.set(cv2.CAP_PROP_FPS, self.cfg.fps)
                
                # Testar
                ret, _ = self.webcam.read()
                if ret:
                    print("  ✅ USB Webcam OK (navegação)")
                    self.webcam_active = True
                else:
                    print("  ⚠️  Webcam não respondeu")
                    self.webcam.release()
                    self.webcam = None
                    success = False
            else:
                print("  ❌ Webcam não abriu")
                success = False
        
        except Exception as e:
            print(f"  ❌ Erro Webcam: {e}")
            success = False
        
        # 2. Pi Camera (cabeça)
        try:
            self.picam = Picamera2()
            config = self.picam.create_preview_configuration(
                main={"size": (self.cfg.width, self.cfg.height)}
            )
            self.picam.configure(config)
            print("  ✅ Pi Camera OK (cabeça)")
            # NÃO inicia ainda - só quando necessário
        
        except Exception as e:
            print(f"  ❌ Erro Pi Camera: {e}")
            self.picam = None
            # Não é crítico se só navegação funcionar
        
        return success
    
    # ==========================================
    # CAPTURA DE FRAMES
    # ==========================================
    
    def _capture_webcam_frame(self) -> Optional[bytes]:
        """Captura frame da USB Webcam"""
        if not self.webcam or not self.webcam.isOpened():
            return None
        
        try:
            ret, frame = self.webcam.read()
            if not ret:
                return None
            
            # Converter BGR -> RGB -> JPEG -> Base64
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=self.cfg.quality)
            
            jpeg_bytes = buffer.getvalue()
            b64_str = base64.b64encode(jpeg_bytes).decode('utf-8')
            
            return b64_str
        
        except Exception as e:
            print(f"❌ Erro captura webcam: {e}")
            return None
    
    def _capture_picam_frame(self) -> Optional[bytes]:
        """Captura frame da Pi Camera"""
        if not self.picam:
            return None
        
        try:
            # Iniciar câmera se necessário
            if not self.picam_active:
                self.picam.start()
                self.picam_active = True
                time.sleep(0.3)  # Estabilização
            
            # Capturar
            frame = self.picam.capture_array()
            
            # Converter -> JPEG -> Base64
            img = Image.fromarray(frame)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=self.cfg.quality)
            
            jpeg_bytes = buffer.getvalue()
            b64_str = base64.b64encode(jpeg_bytes).decode('utf-8')
            
            return b64_str
        
        except Exception as e:
            print(f"❌ Erro captura picam: {e}")
            return None
    
    def capture_frame(self) -> Optional[Dict]:
        """
        Captura frame da câmera ativa
        
        Returns:
            Dict com frame em base64 + metadata
        """
        # Escolher câmera
        if self.active_camera == "picam":
            frame_b64 = self._capture_picam_frame()
            camera = "picam"
            label = "Pi Camera (Cabeça)"
        else:
            frame_b64 = self._capture_webcam_frame()
            camera = "webcam"
            label = "USB Webcam (Navegação)"
        
        if not frame_b64:
            return None
        
        return {
            "type": "camera_frame",
            "camera": camera,
            "label": label,
            "mode": self.mode.value,
            "data": frame_b64,
            "timestamp": time.time()
        }
    
    # ==========================================
    # TROCA AUTOMÁTICA DE CÂMERAS
    # ==========================================
    
    def update_head_position(self, head_position: Dict):
        """
        Atualiza posição da cabeça e decide qual câmera usar
        
        Args:
            head_position: {"yaw": int, "pitch": int}
        """
        if self.mode != CameraMode.AUTO:
            return  # Troca manual desabilitada
        
        # Primeira leitura
        if self.last_head_position is None:
            self.last_head_position = head_position
            return
        
        # Calcular movimento
        yaw_delta = abs(head_position.get("yaw", 90) - 
                       self.last_head_position.get("yaw", 90))
        pitch_delta = abs(head_position.get("pitch", 90) - 
                         self.last_head_position.get("pitch", 90))
        
        total_movement = yaw_delta + pitch_delta
        
        # Detectar movimento
        if total_movement >= self.cfg.movement_threshold:
            # Cabeça movendo → ativar Pi Camera
            self.last_head_move_time = time.time()
            self.head_is_moving = True
            
            if self.active_camera != "picam":
                self._switch_to_head_camera()
        
        else:
            # Cabeça parada
            self.head_is_moving = False
            
            # Timeout: voltar pra navegação
            idle_time = time.time() - self.last_head_move_time
            
            if idle_time >= self.cfg.head_idle_timeout:
                if self.active_camera != "webcam":
                    self._switch_to_navigation_camera()
        
        self.last_head_position = head_position
    
    def _switch_to_head_camera(self):
        """Troca para Pi Camera (cabeça)"""
        if not self.picam:
            return
        
        print("📷 → Pi Camera (cabeça em movimento)")
        self.active_camera = "picam"
        
        # Parar webcam se ativa
        if self.webcam_active:
            # Não fechar, só pausar leitura
            pass
    
    def _switch_to_navigation_camera(self):
        """Troca para USB Webcam (navegação)"""
        if not self.webcam:
            return
        
        print("📷 → USB Webcam (navegação)")
        self.active_camera = "webcam"
        
        # Parar picam se ativa
        if self.picam_active:
            try:
                self.picam.stop()
                self.picam_active = False
            except:
                pass
    
    # ==========================================
    # CONTROLE MANUAL
    # ==========================================
    
    def set_mode(self, mode: str):
        """
        Define modo de operação
        
        Args:
            mode: "auto", "navigation", "head"
        """
        try:
            self.mode = CameraMode(mode)
            
            if mode == "navigation":
                self._switch_to_navigation_camera()
            elif mode == "head":
                self._switch_to_head_camera()
            
            print(f"📷 Modo: {self.mode.value}")
        
        except ValueError:
            print(f"❌ Modo inválido: {mode}")
    
    # ==========================================
    # STREAMING WEBSOCKET
    # ==========================================
    
    async def stream_loop(self):
        """Loop de streaming (envia frames para clientes)"""
        frame_delay = 1.0 / self.cfg.fps
        
        while self.streaming:
            try:
                if not self.clients:
                    await asyncio.sleep(0.1)
                    continue
                
                # Capturar frame
                frame_data = self.capture_frame()
                
                if frame_data:
                    message = json.dumps(frame_data)
                    
                    # Enviar para clientes
                    disconnected = set()
                    for client in self.clients:
                        try:
                            await client.send(message)
                        except:
                            disconnected.add(client)
                    
                    self.clients -= disconnected
                
                await asyncio.sleep(frame_delay)
            
            except Exception as e:
                print(f"❌ Erro stream loop: {e}")
                await asyncio.sleep(1.0)
    
    def add_client(self, websocket):
        """Adiciona cliente ao stream"""
        self.clients.add(websocket)
        print(f"📡 Cliente adicionado ao stream (total: {len(self.clients)})")
    
    def remove_client(self, websocket):
        """Remove cliente do stream"""
        self.clients.discard(websocket)
        print(f"📡 Cliente removido do stream (total: {len(self.clients)})")
    
    # ==========================================
    # CLEANUP
    # ==========================================
    
    def cleanup(self):
        """Para câmeras"""
        self.streaming = False
        
        if self.picam and self.picam_active:
            try:
                self.picam.stop()
                self.picam.close()
                print("🔴 Pi Camera parada")
            except:
                pass
        
        if self.webcam and self.webcam.isOpened():
            self.webcam.release()
            print("🔴 USB Webcam parada")


# ==========================================
# INTEGRAÇÃO COM eva_network_server.py
# ==========================================

"""
COMO INTEGRAR NO eva_network_server.py:

1. Substituir import:
   
   # REMOVER:
   # from camera_stream_server import CameraStreamServer
   
   # ADICIONAR:
   from eva_camera_system import SmartCameraSystem

2. No __init__ da RobotWebSocketServer:
   
   self.camera = SmartCameraSystem()

3. No método start():
   
   self.camera.start()
   self.camera.streaming = True
   self._camera_task = asyncio.create_task(self.camera.stream_loop())

4. No _handle_client():
   
   self.camera.add_client(websocket)
   
   # No finally:
   self.camera.remove_client(websocket)

5. No _broadcast_state_loop(), ADICIONAR:
   
   # Atualizar sistema de câmeras
   state = self.actuator.get_state()
   head_pos = state.get('head_position')
   
   if head_pos:
       self.camera.update_head_position(head_pos)

6. No cleanup/main finally:
   
   self.camera.cleanup()

7. OPCIONAL - Adicionar comando para controle manual:
   
   elif env.cmd == "camera":
       mode = env.params.get("mode", "auto")
       self.camera.set_mode(mode)
       return {"status": "ok", "mode": mode}
"""


# ==========================================
# TESTE STANDALONE
# ==========================================

async def test_camera_system():
    """Testa sistema de câmeras"""
    print("\n" + "="*60)
    print("📷 TESTE - SMART CAMERA SYSTEM")
    print("="*60 + "\n")
    
    camera = SmartCameraSystem()
    
    if not camera.start():
        print("❌ Falha ao inicializar câmeras")
        return
    
    print("\n🎮 TESTES:\n")
    
    # 1. Navegação
    print("1. Modo NAVEGAÇÃO (USB Webcam)")
    camera.set_mode("navigation")
    
    for i in range(3):
        frame = camera.capture_frame()
        if frame:
            print(f"   ✅ Frame {i+1}: {frame['camera']} - {len(frame['data'])} bytes")
        time.sleep(0.5)
    
    # 2. Cabeça
    print("\n2. Modo CABEÇA (Pi Camera)")
    camera.set_mode("head")
    
    for i in range(3):
        frame = camera.capture_frame()
        if frame:
            print(f"   ✅ Frame {i+1}: {frame['camera']} - {len(frame['data'])} bytes")
        time.sleep(0.5)
    
    # 3. Auto-switch
    print("\n3. Modo AUTO (troca automática)")
    camera.set_mode("auto")
    
    # Simular movimento de cabeça
    print("   Simulando movimento de cabeça...")
    camera.update_head_position({"yaw": 90, "pitch": 90})
    time.sleep(0.1)
    camera.update_head_position({"yaw": 110, "pitch": 100})  # Movimento!
    
    frame = camera.capture_frame()
    print(f"   ✅ Após movimento: {frame['camera'] if frame else 'erro'}")
    
    # Esperar idle
    print("   Aguardando idle (3s)...")
    time.sleep(3.5)
    
    frame = camera.capture_frame()
    print(f"   ✅ Após idle: {frame['camera'] if frame else 'erro'}")
    
    # Cleanup
    print("\n🔴 Encerrando...")
    camera.cleanup()
    
    print("\n✅ Teste completo!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_camera_system())
