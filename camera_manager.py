#!/usr/bin/env python3
"""
EVA ROBOT - DUAL CAMERA MANAGER
Gerencia duas câmeras: USB Webcam (navegação) e Pi Camera (braço/cabeça)
"""

import cv2
import numpy as np
import time
import threading
from typing import Optional, Tuple
from enum import Enum


class CameraType(Enum):
    """Tipos de câmera disponíveis"""
    USB = "usb"
    PICAM = "picam"


class CameraManager:
    """Gerenciador de câmeras dual com switch automático"""
    
    def __init__(self, usb_device_id: int = 1, picam_device_id: int = 0):
        """
        Inicializa o gerenciador de câmeras
        
        Args:
            usb_device_id: ID da webcam USB (/dev/video1)
            picam_device_id: ID da Pi Camera (/dev/video0)
        """
        self.usb_device_id = usb_device_id
        self.picam_device_id = picam_device_id
        
        # Câmeras
        self.usb_camera: Optional[cv2.VideoCapture] = None
        self.picam_camera: Optional[cv2.VideoCapture] = None
        
        # Estado
        self.active_camera = CameraType.USB
        self.is_streaming = False
        self.current_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        
        # Thread de captura
        self.capture_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Estatísticas
        self.frame_count = 0
        self.fps = 0
        self.last_fps_update = time.time()
        
        print("📷 CameraManager inicializado")
    
    def start(self) -> bool:
        """Inicia ambas as câmeras e o streaming"""
        print("\n🚀 Iniciando câmeras...")
        
        # Iniciar USB Camera
        if not self._init_usb_camera():
            print("⚠️  Webcam USB não disponível")
        
        # Iniciar Pi Camera
        if not self._init_picam():
            print("⚠️  Pi Camera não disponível")
        
        # Verificar se pelo menos uma câmera está ativa
        if self.usb_camera is None and self.picam_camera is None:
            print("❌ Nenhuma câmera disponível!")
            return False
        
        # Definir câmera ativa padrão
        if self.usb_camera is not None:
            self.active_camera = CameraType.USB
        else:
            self.active_camera = CameraType.PICAM
        
        # Iniciar thread de captura
        self.is_streaming = True
        self.stop_event.clear()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        print(f"✅ Streaming iniciado (câmera ativa: {self.active_camera.value})")
        return True
    
    def _init_usb_camera(self) -> bool:
        """Inicializa a webcam USB"""
        try:
            self.usb_camera = cv2.VideoCapture(self.usb_device_id)
            
            if not self.usb_camera.isOpened():
                self.usb_camera = None
                return False
            
            # Configurar resolução
            self.usb_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.usb_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.usb_camera.set(cv2.CAP_PROP_FPS, 15)
            
            print(f"✅ USB Camera iniciada (/dev/video{self.usb_device_id})")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao iniciar USB Camera: {e}")
            self.usb_camera = None
            return False
    
    def _init_picam(self) -> bool:
        """Inicializa a Pi Camera"""
        try:
            self.picam_camera = cv2.VideoCapture(self.picam_device_id)
            
            if not self.picam_camera.isOpened():
                self.picam_camera = None
                return False
            
            # Configurar resolução
            self.picam_camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.picam_camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.picam_camera.set(cv2.CAP_PROP_FPS, 15)
            
            print(f"✅ Pi Camera iniciada (/dev/video{self.picam_device_id})")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao iniciar Pi Camera: {e}")
            self.picam_camera = None
            return False
    
    def _capture_loop(self):
        """Loop principal de captura de frames"""
        while not self.stop_event.is_set() and self.is_streaming:
            try:
                frame = self._grab_frame()
                
                if frame is not None:
                    with self.frame_lock:
                        self.current_frame = frame
                    
                    # Atualizar FPS
                    self.frame_count += 1
                    if time.time() - self.last_fps_update >= 1.0:
                        self.fps = self.frame_count
                        self.frame_count = 0
                        self.last_fps_update = time.time()
                
                time.sleep(0.03)  # ~30 FPS max
                
            except Exception as e:
                print(f"⚠️  Erro no loop de captura: {e}")
                time.sleep(0.1)
    
    def _grab_frame(self) -> Optional[np.ndarray]:
        """Captura frame da câmera ativa"""
        camera = self.get_active_camera_object()
        
        if camera is None:
            return None
        
        ret, frame = camera.read()
        
        if not ret or frame is None:
            return None
        
        # Corrigir rotação da Pi Camera (90° para direita)
        if self.active_camera == CameraType.PICAM:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
        return frame
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Retorna o frame atual (thread-safe)"""
        with self.frame_lock:
            return self.current_frame.copy() if self.current_frame is not None else None
    
    def get_frame_encoded(self, quality: int = 70) -> Optional[bytes]:
        """Retorna frame atual como JPEG comprimido"""
        frame = self.get_frame()
        
        if frame is None:
            return None
        
        # Adicionar overlay com informações
        frame = self._add_overlay(frame)
        
        # Codificar como JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        
        return buffer.tobytes()
    
    def _add_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Adiciona overlay com informações no frame"""
        # Nome da câmera
        camera_name = "USB CAM" if self.active_camera == CameraType.USB else "PI CAM"
        cv2.putText(frame, camera_name, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # FPS
        cv2.putText(frame, f"FPS: {self.fps}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return frame
    
    def switch_camera(self, camera_type: Optional[CameraType] = None):
        """
        Alterna entre câmeras
        
        Args:
            camera_type: Câmera específica ou None para alternar
        """
        if camera_type is None:
            # Alternar entre câmeras
            if self.active_camera == CameraType.USB:
                camera_type = CameraType.PICAM
            else:
                camera_type = CameraType.USB
        
        # Verificar se câmera está disponível
        if camera_type == CameraType.USB and self.usb_camera is None:
            print("⚠️  USB Camera não disponível")
            return
        
        if camera_type == CameraType.PICAM and self.picam_camera is None:
            print("⚠️  Pi Camera não disponível")
            return
        
        self.active_camera = camera_type
        print(f"📷 Câmera alternada para: {camera_type.value.upper()}")
    
    def get_active_camera_object(self) -> Optional[cv2.VideoCapture]:
        """Retorna objeto da câmera ativa"""
        if self.active_camera == CameraType.USB:
            return self.usb_camera
        else:
            return self.picam_camera
    
    def get_active_camera_type(self) -> CameraType:
        """Retorna tipo da câmera ativa"""
        return self.active_camera
    
    def is_usb_active(self) -> bool:
        """Verifica se USB camera está ativa"""
        return self.active_camera == CameraType.USB
    
    def is_picam_active(self) -> bool:
        """Verifica se Pi Camera está ativa"""
        return self.active_camera == CameraType.PICAM
    
    def get_status(self) -> dict:
        """Retorna status das câmeras"""
        return {
            'active_camera': self.active_camera.value,
            'usb_available': self.usb_camera is not None,
            'picam_available': self.picam_camera is not None,
            'streaming': self.is_streaming,
            'fps': self.fps
        }
    
    def stop(self):
        """Para o streaming e libera recursos"""
        print("\n🛑 Parando câmeras...")
        
        self.is_streaming = False
        self.stop_event.set()
        
        # Aguardar thread
        if self.capture_thread is not None:
            self.capture_thread.join(timeout=2.0)
        
        # Liberar câmeras
        if self.usb_camera is not None:
            self.usb_camera.release()
            self.usb_camera = None
        
        if self.picam_camera is not None:
            self.picam_camera.release()
            self.picam_camera = None
        
        print("✅ Câmeras finalizadas")
    
    def __del__(self):
        """Destrutor - garante liberação de recursos"""
        self.stop()


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("📷 TESTE: DUAL CAMERA MANAGER")
    print("="*60 + "\n")
    
    manager = CameraManager()
    
    if not manager.start():
        print("❌ Falha ao iniciar câmeras")
        exit(1)
    
    print("\n💡 Controles:")
    print("   SPACE: Alternar câmera")
    print("   Q: Sair")
    print("\n")
    
    try:
        while True:
            frame = manager.get_frame()
            
            if frame is not None:
                cv2.imshow('EVA Robot - Camera Test', frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord(' '):
                manager.switch_camera()
            
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário")
    
    finally:
        manager.stop()
        cv2.destroyAllWindows()
        print("\n✅ Teste finalizado")