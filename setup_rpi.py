#!/usr/bin/env python3
"""
setup_rpi.py - Installation script for Raspberry Pi
"""

import os
import sys
import subprocess
import logging
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_command(command, display=True):
    """Run a shell command and return the output"""
    try:
        if display:
            logger.info(f"Running: {command}")
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        output, error = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Error running command: {command}")
            logger.error(error.strip())
            return False
        
        return True
    except Exception as e:
        logger.error(f"Exception running command: {e}")
        return False

def install_dependencies():
    """Install system dependencies"""
    logger.info("Installing system dependencies...")
    
    # Update package lists
    run_command("sudo apt-get update")
    
    # Install required packages
    dependencies = [
        "python3-pip",
        "python3-numpy",
        "python3-dev",
        "python3-websockets",
        "libwebsockets-dev",
        "vlc",
        "python3-opencv",
        "python3-picamera"
    ]
    
    cmd = f"sudo apt-get install -y {' '.join(dependencies)}"
    return run_command(cmd)

def install_python_packages():
    """Install required Python packages"""
    logger.info("Installing Python packages...")
    
    packages = [
        "websockets",
        "numpy",
        "picamera2",
        "pillow"
    ]
    
    cmd = f"sudo pip3 install {' '.join(packages)}"
    return run_command(cmd)

def setup_freenove_code():
    """Set up Freenove code"""
    logger.info("Setting up Freenove code...")
    
    if not os.path.exists("Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi"):
        # Clone Freenove repository
        cmd = "git clone --depth 1 https://github.com/Freenove/Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi"
        if not run_command(cmd):
            return False
    
    # Run Freenove setup script
    freenove_setup = "cd Freenove_4WD_Smart_Car_Kit_for_Raspberry_Pi/Code && sudo python3 setup.py"
    return run_command(freenove_setup)

def enable_services():
    """Enable and start system services"""
    logger.info("Setting up system services...")
    
    # Create systemd service file
    service_content = """[Unit]
Description=AI Car Controller
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/ai_car_control/raspberry_pi/main.py
WorkingDirectory=/home/pi/ai_car_control/raspberry_pi
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
"""
    
    with open("ai_car_controller.service", "w") as f:
        f.write(service_content)
    
    # Install service
    run_command("sudo cp ai_car_controller.service /etc/systemd/system/")
    run_command("sudo systemctl daemon-reload")
    
    # Enable service to start on boot
    run_command("sudo systemctl enable ai_car_controller.service")
    
    logger.info("Service installed and enabled. To start it now, run:")
    logger.info("sudo systemctl start ai_car_controller.service")
    
    return True

def create_directory_structure():
    """Create the directory structure for the project"""
    logger.info("Creating directory structure...")
    
    directories = [
        "ai_car_control",
        "ai_car_control/raspberry_pi",
        "ai_car_control/raspberry_pi/communication",
        "ai_car_control/raspberry_pi/hardware"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    return True

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Setup script for AI Car Control (Raspberry Pi)")
    parser.add_argument("--no-services", action="store_true", help="Don't set up system services")
    args = parser.parse_args()
    
    logger.info("Starting setup for AI Car Control (Raspberry Pi)...")
    
    # Create directory structure
    if not create_directory_structure():
        logger.error("Failed to create directory structure")
        return 1
    
    # Install dependencies
    if not install_dependencies():
        logger.error("Failed to install system dependencies")
        return 1
    
    # Install Python packages
    if not install_python_packages():
        logger.error("Failed to install Python packages")
        return 1
    
    # Set up Freenove code
    if not setup_freenove_code():
        logger.error("Failed to set up Freenove code")
        return 1
    
    # Enable services if not disabled
    if not args.no_services:
        if not enable_services():
            logger.error("Failed to set up system services")
            return 1
    
    logger.info("Setup completed successfully!")
    logger.info("To start the car controller, run: python3 ai_car_control/raspberry_pi/main.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())


#!/usr/bin/env python3
"""
setup_computer.py - Installation script for main computer
"""

import os
import sys
import subprocess
import logging
import argparse
from typing import List, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_command(command, display=True):
    """Run a shell command and return the output"""
    try:
        if display:
            logger.info(f"Running: {command}")
        
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        output, error = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Error running command: {command}")
            logger.error(error.strip())
            return False
        
        return True
    except Exception as e:
        logger.error(f"Exception running command: {e}")
        return False

def install_python_packages():
    """Install required Python packages"""
    logger.info("Installing Python packages...")
    
    # Core packages
    core_packages = [
        "websockets",
        "numpy",
        "requests",
        "pillow",
        "sentence-transformers",
        "faiss-cpu"
    ]
    
    # TTS packages
    tts_packages = [
        "pyttsx3"
    ]
    
    # STT packages
    stt_packages = [
        "faster-whisper",
        "pyaudio"
    ]
    
    # Install core packages
    cmd = f"pip install {' '.join(core_packages)}"
    if not run_command(cmd):
        return False
    
    # Install TTS packages
    cmd = f"pip install {' '.join(tts_packages)}"
    if not run_command(cmd):
        logger.warning("Failed to install TTS packages, some features may not work")
    
    # Install STT packages
    cmd = f"pip install {' '.join(stt_packages)}"
    if not run_command(cmd):
        logger.warning("Failed to install STT packages, some features may not work")
    
    return True

def create_directory_structure():
    """Create the directory structure for the project"""
    logger.info("Creating directory structure...")
    
    directories = [
        "ai_car_control",
        "ai_car_control/main_computer",
        "ai_car_control/main_computer/ai_interface",
        "ai_car_control/main_computer/memory",
        "ai_car_control/main_computer/speech",
        "ai_car_control/main_computer/car_control",
        "ai_car_control/main_computer/communication",
        "ai_car_control/main_computer/data"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    return True

def check_requirements():
    """Check if the system meets the requirements"""
    logger.info("Checking system requirements...")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 7):
        logger.error("Python 3.7 or higher is required")
        return False
    
    return True

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Setup script for AI Car Control (Main Computer)")
    args = parser.parse_args()
    
    logger.info("Starting setup for AI Car Control (Main Computer)...")
    
    # Check requirements
    if not check_requirements():
        logger.error("System does not meet requirements")
        return 1
    
    # Create directory structure
    if not create_directory_structure():
        logger.error("Failed to create directory structure")
        return 1
    
    # Install Python packages
    if not install_python_packages():
        logger.error("Failed to install Python packages")
        return 1
    
    logger.info("Setup completed successfully!")
    logger.info("To start the car controller, run: python ai_car_control/main_computer/main.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())