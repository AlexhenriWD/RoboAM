#!/bin/bash

# Script de setup do Freenove AI Car
# Execute: bash setup.sh

echo "======================================"
echo "🤖 Freenove AI Car - Setup"
echo "======================================"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar se está no Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${RED}❌ Este script deve ser executado no Raspberry Pi${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Raspberry Pi detectado${NC}"

# Atualizar sistema
echo ""
echo "📦 Atualizando sistema..."
sudo apt-get update -qq

# Instalar dependências do sistema
echo ""
echo "📦 Instalando dependências..."
sudo apt-get install -y \
    python3-pip \
    python3-opencv \
    python3-numpy \
    git \
    i2c-tools \
    python3-smbus \
    libcamera-dev \
    python3-picamera2 \
    -qq

echo -e "${GREEN}✓ Dependências do sistema instaladas${NC}"

# Criar estrutura de diretórios
echo ""
echo "📁 Criando estrutura de diretórios..."

mkdir -p ai
mkdir -p hardware
mkdir -p logs

# Mover arquivos de hardware para a pasta hardware
if [ -f "motor.py" ]; then
    mv motor.py servo.py ultrasonic.py camera.py infrared.py adc.py buzzer.py pca9685.py hardware/ 2>/dev/null
    echo -e "${GREEN}✓ Arquivos de hardware organizados${NC}"
fi

# Instalar dependências Python
echo ""
echo "🐍 Instalando pacotes Python..."
pip3 install -r requirements.txt --quiet

echo -e "${GREEN}✓ Pacotes Python instalados${NC}"

# Criar arquivo de configuração
echo ""
echo "⚙️  Configurando..."

if [ ! -f "config.json" ]; then
    echo "Criando config.json..."
    cat > config.json << 'EOF'
{
  "groq_api_key": "",
  "ai_mode": "sensor_only",
  "decision_interval": 1.5,
  "max_speed": 60,
  "safety_distance": 30,
  "camera_enabled": true,
  "log_decisions": true
}
EOF
    echo -e "${YELLOW}⚠️  Configure sua GROQ_API_KEY em config.json${NC}"
else
    echo -e "${GREEN}✓ config.json já existe${NC}"
fi

# Habilitar I2C
echo ""
echo "🔧 Habilitando I2C..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt > /dev/null
    echo -e "${YELLOW}⚠️  I2C habilitado - reinicie o sistema${NC}"
else
    echo -e "${GREEN}✓ I2C já está habilitado${NC}"
fi

# Criar serviço systemd (opcional)
echo ""
read -p "❓ Deseja criar um serviço systemd para auto-iniciar? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_FILE="/etc/systemd/system/freenove-car.service"
    
    sudo bash -c "cat > $SERVICE_FILE" << EOF
[Unit]
Description=Freenove AI Car Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3 $(pwd)/server_web.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable freenove-car.service
    
    echo -e "${GREEN}✓ Serviço criado! Use: sudo systemctl start freenove-car${NC}"
fi

# Testar hardware
echo ""
echo "🧪 Testando hardware..."
python3 << 'PYEOF'
try:
    import sys
    sys.path.insert(0, 'hardware')
    from motor import Ordinary_Car
    from ultrasonic import Ultrasonic
    motor = Ordinary_Car()
    motor.close()
    ultrasonic = Ultrasonic()
    ultrasonic.close()
    print("✓ Hardware OK")
except Exception as e:
    print(f"⚠️  Erro no hardware: {e}")
PYEOF

# Configurar Git (se ainda não estiver)
echo ""
if [ ! -d ".git" ]; then
    read -p "❓ Deseja inicializar repositório Git? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git init
        git add .
        git commit -m "Initial commit - Freenove AI Car"
        echo -e "${GREEN}✓ Repositório Git inicializado${NC}"
        echo ""
        echo "Para conectar ao GitHub:"
        echo "  1. Crie um repositório em github.com"
        echo "  2. Execute:"
        echo "     git remote add origin https://github.com/seu-usuario/seu-repo.git"
        echo "     git push -u origin main"
    fi
fi

# Finalização
echo ""
echo "======================================"
echo -e "${GREEN}✅ Setup concluído!${NC}"
echo "======================================"
echo ""
echo "📝 Próximos passos:"
echo ""
echo "1. Configure a Groq API Key:"
echo "   nano config.json"
echo ""
echo "2. Teste o servidor web:"
echo "   python3 server_web.py"
echo "   Acesse: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "3. Teste o modo IA:"
echo "   python3 main_ai.py"
echo ""
echo "4. Para auto-deploy, configure as secrets no GitHub:"
echo "   - PI_HOST: $(hostname -I | awk '{print $1}')"
echo "   - PI_USER: $(whoami)"
echo "   - PI_SSH_KEY: (sua chave privada SSH)"
echo ""
echo "======================================"
