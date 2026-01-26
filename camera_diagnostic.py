#!/usr/bin/env python3
"""
DIAGNÓSTICO DE CÂMERAS - EVA ROBOT
Testa TODAS as câmeras possíveis e mostra qual funciona

RODE NO RASPBERRY PI:
    python3 camera_diagnostic.py
"""

import cv2
import time
import sys
from pathlib import Path

print("\n" + "="*60)
print("📷 DIAGNÓSTICO DE CÂMERAS - EVA ROBOT")
print("="*60 + "\n")

# ==========================================
# TESTE 1: Pi Camera (Picamera2)
# ==========================================

print("🔍 TESTE 1: Raspberry Pi Camera (Picamera2)")
print("-" * 60)

try:
    from picamera2 import Picamera2
    
    print("  ✅ Picamera2 instalado")
    
    try:
        print("  🔧 Inicializando Pi Camera...")
        
        picam = Picamera2()
        
        # Listar câmeras disponíveis
        print(f"  📋 Câmeras disponíveis: {Picamera2.global_camera_info()}")
        
        # Configuração SIMPLES
        config = picam.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"}
        )
        
        picam.configure(config)
        
        print("  ▶️  Iniciando câmera...")
        picam.start()
        
        # Aguardar estabilização
        print("  ⏳ Aguardando estabilização (2s)...")
        time.sleep(2.0)
        
        # Capturar frame de teste
        print("  📸 Capturando frame de teste...")
        frame = picam.capture_array()
        
        if frame is not None and frame.size > 0:
            print(f"  ✅ SUCESSO! Frame capturado: {frame.shape}")
            print(f"     Resolução: {frame.shape[1]}x{frame.shape[0]}")
            print(f"     Formato: {frame.dtype}")
            
            # Salvar imagem de teste
            test_file = Path("test_picam.jpg")
            
            # Converter RGB -> BGR para OpenCV
            import numpy as np
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(test_file), frame_bgr)
            
            print(f"     Imagem salva: {test_file}")
            
            picam.stop()
            picam.close()
            
            print("\n  ✅ PI CAMERA FUNCIONA!")
            print("     Use: self.camera = Picamera2()")
        
        else:
            print("  ❌ Frame vazio ou inválido")
            picam.stop()
            picam.close()
    
    except Exception as e:
        print(f"  ❌ Erro ao usar Pi Camera: {e}")
        
        import traceback
        print("\n  📋 Detalhes do erro:")
        traceback.print_exc()

except ImportError:
    print("  ❌ Picamera2 não instalado")
    print("     Instale: sudo apt install python3-picamera2")

print()

# ==========================================
# TESTE 2: USB Webcams (OpenCV)
# ==========================================

print("🔍 TESTE 2: USB Webcams (OpenCV)")
print("-" * 60)

try:
    import cv2
    print("  ✅ OpenCV instalado")
    
    # Testar índices 0, 1, 2, 3
    for idx in range(4):
        print(f"\n  🔧 Testando /dev/video{idx}...")
        
        try:
            cap = cv2.VideoCapture(idx)
            
            if not cap.isOpened():
                print(f"     ❌ Não abre")
                continue
            
            # Tentar capturar
            ret, frame = cap.read()
            
            if not ret or frame is None:
                print(f"     ❌ Abre mas não captura")
                cap.release()
                continue
            
            # SUCESSO!
            print(f"     ✅ FUNCIONA!")
            print(f"        Resolução: {frame.shape[1]}x{frame.shape[0]}")
            print(f"        Formato: {frame.dtype}")
            
            # Salvar imagem de teste
            test_file = Path(f"test_video{idx}.jpg")
            cv2.imwrite(str(test_file), frame)
            print(f"        Imagem salva: {test_file}")
            
            # Tentar configurar
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 15)
            
            actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            
            print(f"        Config: {int(actual_w)}x{int(actual_h)} @ {int(actual_fps)} FPS")
            
            print(f"\n     ✅ USB WEBCAM /dev/video{idx} FUNCIONA!")
            print(f"        Use: cv2.VideoCapture({idx})")
            
            cap.release()
        
        except Exception as e:
            print(f"     ❌ Erro: {e}")

except ImportError:
    print("  ❌ OpenCV não instalado")
    print("     Instale: pip install opencv-python")

print()

# ==========================================
# TESTE 3: Listar dispositivos /dev/video*
# ==========================================

print("🔍 TESTE 3: Dispositivos /dev/video*")
print("-" * 60)

video_devices = list(Path('/dev').glob('video*'))

if video_devices:
    print(f"  Encontrados {len(video_devices)} dispositivos:")
    
    for device in sorted(video_devices):
        print(f"    • {device}")
        
        # Tentar ler info (se tiver v4l2)
        try:
            import subprocess
            result = subprocess.run(
                ['v4l2-ctl', '--device', str(device), '--info'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                # Pegar só a primeira linha (nome do device)
                first_line = result.stdout.split('\n')[0]
                print(f"      {first_line}")
        except:
            pass
else:
    print("  ❌ Nenhum dispositivo /dev/video* encontrado")
    print("     Verifique se as câmeras estão conectadas")

print()

# ==========================================
# RESUMO
# ==========================================

print("="*60)
print("📋 RESUMO E RECOMENDAÇÕES")
print("="*60)

print("\n✅ CÂMERAS QUE FUNCIONARAM:")

# Verificar quais imagens de teste foram criadas
test_images = list(Path('.').glob('test_*.jpg'))

if test_images:
    for img in test_images:
        print(f"   • {img.stem.replace('test_', '').upper()}: {img}")
else:
    print("   ❌ Nenhuma câmera funcionou!")

print("\n💡 PRÓXIMOS PASSOS:")

if any('picam' in str(img) for img in test_images):
    print("   1. Use Pi Camera no código:")
    print("      from picamera2 import Picamera2")
    print("      picam = Picamera2()")
    print("      picam.start()")
    print("      frame = picam.capture_array()")

elif any('video' in str(img) for img in test_images):
    # Descobrir qual índice funcionou
    working_idx = None
    for img in test_images:
        if 'video' in str(img):
            working_idx = str(img).replace('test_video', '').replace('.jpg', '')
            break
    
    print(f"   1. Use USB Webcam no código:")
    print(f"      import cv2")
    print(f"      cap = cv2.VideoCapture({working_idx})")
    print(f"      ret, frame = cap.read()")

else:
    print("   1. Verifique as conexões físicas das câmeras")
    print("   2. Certifique-se que a câmera está habilitada:")
    print("      sudo raspi-config -> Interface Options -> Camera")
    print("   3. Reinicie o Raspberry Pi")
    print("   4. Execute este script novamente")

print("\n" + "="*60 + "\n")