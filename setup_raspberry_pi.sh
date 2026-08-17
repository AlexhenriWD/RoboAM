#!/usr/bin/env bash
# setup_raspberry_pi.sh
#
# Instala e ativa tudo que eva_robot.py / eva_command_server.py / robot_core.py
# / camera_manager.py / gamepad_controller.py precisam pra rodar no Raspberry Pi.
#
# CONFIRMADO contra os imports reais do seu robot_core.py (smbus, gpiozero,
# picamera2, libcamera) -- isto é mais novo que o manual do Freenove que veio
# com o kit, que ainda fala de python-smbus/opencv do jeito antigo.
#
# TUDO AQUI VEM DO apt, NADA PRECISA DE pip. Isso não é preguiça -- é porque
# picamera2/libcamera/gpiozero são pacotes que o próprio time do Raspberry Pi
# recomenda instalar via apt, não via pip (pip install picamera2 tem histórico
# de quebrar por incompatibilidade binária com a libcamera do sistema,
# principalmente no Pi 5). Como seu código não usa mais nenhuma biblioteca
# Python que só existe no PyPI, dá pra pular venv completamente aqui.
#
# Seguro rodar mais de uma vez (idempotente) -- apt install já pula o que
# estiver instalado, raspi-config nonint só aplica o estado.
#
# Uso:
#   chmod +x setup_raspberry_pi.sh
#   ./setup_raspberry_pi.sh

set -e  # para no primeiro erro -- melhor travar aqui do que na metade com estado inconsistente

echo "=============================================="
echo " EVA Robot -- setup de dependências (Raspberry Pi)"
echo "=============================================="
echo

echo "--- [1/5] Atualizando lista de pacotes ---"
sudo apt update

echo
echo "--- [2/5] Ativando I2C e câmera (sem menu interativo) ---"
# do_i2c 0 / do_camera 0 = "habilitar" (a convenção do raspi-config nonint é
# 0=on, 1=off, invertido do que se esperaria -- não é erro de digitação)
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_camera 0
echo "I2C e câmera marcados como habilitados em /boot/firmware/config.txt (ou /boot/config.txt)."
echo "Só valem de verdade DEPOIS de reiniciar -- o script avisa no final."

echo
echo "--- [3/5] Instalando pacotes de sistema (I2C, PWM, sensores) ---"
sudo apt install -y \
    i2c-tools \
    python3-smbus \
    python3-gpiozero \
    python3-dev

echo
echo "--- [4/5] Instalando pacotes de câmera (picamera2 + libcamera) ---"
sudo apt install -y \
    python3-picamera2 \
    python3-libcamera \
    --no-install-recommends

echo
echo "--- [5/5] Instalando visão computacional (webcam USB) e gamepad ---"
sudo apt install -y \
    python3-opencv \
    python3-numpy \
    python3-evdev

echo
echo "--- Permissões: garantindo que seu usuário está nos grupos certos ---"
# i2c/gpio/video geralmente já vêm certos por udev no Raspberry Pi OS, mas
# 'input' (necessário pro evdev ler o gamepad sem sudo) às vezes não --
# adiciona de forma idempotente (não duplica se já estiver no grupo).
for grupo in i2c gpio video input dialout; do
    if getent group "$grupo" > /dev/null 2>&1; then
        sudo usermod -aG "$grupo" "$USER"
    fi
done
echo "Usuário '$USER' adicionado aos grupos: i2c, gpio, video, input, dialout (os que existirem no sistema)."
echo "Isso só tem efeito depois de um novo login (ou reboot) -- mesma janela do I2C/câmera abaixo."

echo
echo "=============================================="
echo " Instalação concluída."
echo "=============================================="
echo
echo "IMPORTANTE -- reinicie agora antes de testar qualquer coisa:"
echo "    sudo reboot"
echo
echo "Depois do reboot, rode o script de verificação:"
echo "    ./verificar_raspberry_pi.sh"
