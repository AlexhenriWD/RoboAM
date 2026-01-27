#!/bin/bash
# EVA Robot - Script de Instalação (Raspberry Pi)

set -e

echo "=================================="
echo "🤖 EVA ROBOT - Instalação"
echo "=================================="
echo ""

# Verificar sistema
if [ ! -f /proc/device-tree/model ]; then
    echo "❌ Erro: Este script deve ser executado em um Raspberry Pi"
    exit 1
fi

echo "✅ Raspberry Pi detectado:"
cat /proc/device-tree/model
echo ""

# Atualizar sistema
echo "📦 Atualizando sistema..."
sudo apt-get update
sudo apt-get upgrade -y

# Instalar dependências
echo ""
echo "📚 Instalando dependências..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-opencv \
    python3-numpy \
    python3-pil \
    python3-smbus \
    i2c-tools \
    git

# Instalar bibliotecas Python
echo ""
echo "🐍 Instalando bibliotecas Python..."
pip3 install --user gpiozero RPi.GPIO smbus2

# Habilitar I2C
echo ""
echo "🔧 Habilitando I2C..."
sudo raspi-config nonint do_i2c 0

# Habilitar câmera
echo ""
echo "📷 Habilitando câmera..."
sudo raspi-config nonint do_camera 0

# Configurar permissões
echo ""
echo "🔐 Configurando permissões..."
sudo usermod -a -G video $USER
sudo usermod -a -G i2c $USER
sudo usermod -a -G gpio $USER

# Criar estrutura de diretórios
echo ""
echo "📁 Criando estrutura de diretórios..."
cd /home/pi
mkdir -p eva_robot/{core,config,logs}

# Copiar arquivos originais do Freenove
if [ -d "/home/pi/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi/Code/Server" ]; then
    echo ""
    echo "📋 Copiando arquivos originais do Freenove..."
    cp /home/pi/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi/Code/Server/robot_core.py eva_robot/core/
    echo "✅ robot_core.py copiado"
else
    echo ""
    echo "⚠️  Arquivos do Freenove não encontrados"
    echo "   Por favor, instale o kit original primeiro"
fi

# Configurar inicialização automática (opcional)
echo ""
read -p "Deseja configurar inicialização automática do servidor? (s/n): " AUTO_START

if [ "$AUTO_START" = "s" ] || [ "$AUTO_START" = "S" ]; then
    echo "🚀 Configurando serviço systemd..."
    
    sudo tee /etc/systemd/system/eva-robot.service > /dev/null <<EOF
[Unit]
Description=EVA Robot Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/eva_robot
ExecStart=/usr/bin/python3 /home/pi/eva_robot/eva_server.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable eva-robot.service
    
    echo "✅ Serviço configurado"
    echo "   Use: sudo systemctl start eva-robot"
fi

# Verificar instalação
echo ""
echo "🔍 Verificando instalação..."

echo "Câmeras detectadas:"
ls -l /dev/video* 2>/dev/null || echo "  Nenhuma câmera encontrada"

echo ""
echo "Dispositivos I2C:"
sudo i2cdetect -y 1

echo ""
echo "=================================="
echo "✅ Instalação concluída!"
echo "=================================="
echo ""
echo "Próximos passos:"
echo "1. Reinicie o Raspberry Pi: sudo reboot"
echo "2. Clone/copie os arquivos do EVA Robot para /home/pi/eva_robot"
echo "3. Execute: python3 eva_server.py"
echo ""
echo "Para testar as câmeras:"
echo "  python3 core/camera_manager.py"
echo ""
echo "Para testar o braço:"
echo "  python3 core/arm_controller.py"
echo ""