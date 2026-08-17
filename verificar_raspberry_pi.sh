#!/usr/bin/env bash
# verificar_raspberry_pi.sh
#
# Testa CADA dependência que eva_robot.py precisa, uma por uma, com
# resultado explícito (OK / FALHOU) -- pra você ver exatamente o que
# funciona antes de rodar eva_command_server.py de verdade com o robô
# ligado. Mesmo espírito do resto do projeto: verificar antes de confiar.
#
# Não move motores nem servos -- só testa import, presença de dispositivo,
# e leitura passiva (ex: i2cdetect, listar câmeras). Seguro rodar a
# qualquer momento, robô ligado ou não.
#
# Uso:
#   chmod +x verificar_raspberry_pi.sh
#   ./verificar_raspberry_pi.sh

OK="\033[32mOK\033[0m"
FALHOU="\033[31mFALHOU\033[0m"
AVISO="\033[33mAVISO\033[0m"

falhas=0

checar() {
    local descricao="$1"
    local comando="$2"
    printf "%-55s" "$descricao"
    if eval "$comando" > /tmp/_verif_out 2>&1; then
        echo -e "[$OK]"
    else
        echo -e "[$FALHOU]"
        sed 's/^/      /' /tmp/_verif_out | head -5
        falhas=$((falhas + 1))
    fi
}

echo "=============================================="
echo " EVA Robot -- verificação de dependências"
echo "=============================================="
echo

echo "--- Python ---"
checar "python3 instalado" "command -v python3"
python3 --version
echo

echo "--- Módulos Python (import direto, sem tocar hardware) ---"
checar "smbus (I2C)"            "python3 -c 'import smbus'"
checar "gpiozero (ultrassônico/buzzer)" "python3 -c 'import gpiozero'"
checar "picamera2 (câmera da garra)"    "python3 -c 'from picamera2 import Picamera2'"
checar "libcamera"              "python3 -c 'import libcamera'"
checar "cv2/opencv (webcam USB)" "python3 -c 'import cv2'"
checar "numpy"                  "python3 -c 'import numpy'"
checar "evdev (gamepad)"        "python3 -c 'import evdev'"
echo

echo "--- I2C: barramento e dispositivos esperados ---"
checar "módulo i2c carregado no kernel" "lsmod | grep -qi i2c"
if command -v i2cdetect > /dev/null 2>&1; then
    echo "Saída de 'i2cdetect -y 1' (procure 40 e 48 na grade -- são o PCA9685"
    echo "de servo/motor e o ADC de bateria, respectivamente):"
    echo
    i2cdetect -y 1 2>/dev/null || echo -e "[$FALHOU] i2cdetect -y 1 deu erro -- I2C está habilitado? (raspi-config, ou rode setup_raspberry_pi.sh e reinicie)"
    echo
    if i2cdetect -y 1 2>/dev/null | grep -qi " 40 "; then
        echo -e "  PCA9685 (0x40, servos/motores): [$OK]"
    else
        echo -e "  PCA9685 (0x40, servos/motores): [$FALHOU] -- não apareceu na grade. Fiação/alimentação da placa?"
        falhas=$((falhas + 1))
    fi
    if i2cdetect -y 1 2>/dev/null | grep -qi " 48 "; then
        echo -e "  ADC/ADS7830 (0x48, bateria):    [$OK]"
    else
        echo -e "  ADC/ADS7830 (0x48, bateria):    [$AVISO] -- não apareceu. Sem isso, leitura de bateria fica sempre vazia (ver eva_robot.py, self.adc)."
    fi
else
    echo -e "[$FALHOU] i2c-tools não instalado (rode setup_raspberry_pi.sh)"
    falhas=$((falhas + 1))
fi
echo

echo "--- Câmeras ---"
echo "Dispositivos USB (webcam de navegação) encontrados em /dev/video*:"
ls /dev/video* 2>/dev/null || echo -e "  [$AVISO] nenhum /dev/videoN encontrado -- webcam conectada?"
echo
if command -v rpicam-hello > /dev/null 2>&1; then
    checar "PiCam (garra) detectada -- rpicam-hello --list-cameras" "rpicam-hello --list-cameras"
elif command -v libcamera-hello > /dev/null 2>&1; then
    checar "PiCam (garra) detectada -- libcamera-hello --list-cameras" "libcamera-hello --list-cameras"
else
    echo -e "  [$AVISO] nem rpicam-hello nem libcamera-hello encontrados -- normal se python3-picamera2 acabou de ser instalado sem os utilitários de linha de comando; o teste de import acima (picamera2/libcamera) já é o que importa pro código em si."
fi
echo

echo "--- Gamepad (opcional -- só se for usar eva_gamepad_server.py) ---"
if ls /dev/input/event* > /dev/null 2>&1; then
    echo "Dispositivos de input encontrados:"
    ls /dev/input/event*
    echo "(isso inclui teclado/mouse também -- não significa necessariamente que o gamepad está aqui)"
else
    echo -e "  [$AVISO] nenhum /dev/input/eventN -- normal se nenhum gamepad estiver plugado agora."
fi
echo

echo "=============================================="
if [ "$falhas" -eq 0 ]; then
    echo -e " Resultado: [$OK] nenhuma falha crítica encontrada."
    echo " Ainda assim, teste eva_command_server.py com o robô no chão livre"
    echo " antes de confiar em qualquer movimento maior (ver LEIA-ME_integracao_robo.md)."
else
    echo -e " Resultado: [$FALHOU] $falhas checagem(ns) falharam -- veja acima."
    echo " Rode setup_raspberry_pi.sh se ainda não rodou, e confirme que"
    echo " reiniciou depois (I2C/câmera só valem após reboot)."
fi
echo "=============================================="
