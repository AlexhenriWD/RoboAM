import React, { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, Activity, Zap, WifiOff, Wifi } from 'lucide-react';

const RaspberryPiServoCalibrator = () => {
  const [servos, setServos] = useState([
    { id: 0, name: 'Base (Rotação)', angle: 90, min: 0, max: 180, safe_min: 10, safe_max: 170, color: '#3b82f6' },
    { id: 1, name: 'Ombro (Elevação)', angle: 90, min: 0, max: 180, safe_min: 20, safe_max: 160, color: '#10b981' },
    { id: 2, name: 'Cotovelo', angle: 90, min: 0, max: 180, safe_min: 30, safe_max: 150, color: '#f59e0b' },
    { id: 3, name: 'Garra', angle: 90, min: 0, max: 180, safe_min: 40, safe_max: 140, color: '#ef4444' }
  ]);
  
  const [testing, setTesting] = useState(false);
  const [currentTest, setCurrentTest] = useState(null);
  const [logs, setLogs] = useState([]);
  const [connected, setConnected] = useState(false);
  const [serverUrl, setServerUrl] = useState('http://192.168.1.100:5001');
  const [connecting, setConnecting] = useState(false);

  const addLog = (message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, { message, type, timestamp }].slice(-10));
  };

  const checkConnection = async () => {
    try {
      const response = await fetch(`${serverUrl}/status`);
      const data = await response.json();
      setConnected(data.status === 'ok');
      return data.status === 'ok';
    } catch (error) {
      setConnected(false);
      return false;
    }
  };

  const connectToRaspberryPi = async () => {
    setConnecting(true);
    addLog('🔌 Conectando ao Raspberry Pi...', 'info');
    
    try {
      const isConnected = await checkConnection();
      if (isConnected) {
        addLog('✓ Conectado ao Raspberry Pi!', 'success');
        setConnected(true);
      } else {
        addLog('✗ Falha na conexão', 'error');
        setConnected(false);
      }
    } catch (error) {
      addLog('✗ Erro: ' + error.message, 'error');
      setConnected(false);
    } finally {
      setConnecting(false);
    }
  };

  const sendServoCommand = async (channel, angle) => {
    if (!connected) {
      addLog('✗ Não conectado ao Raspberry Pi', 'error');
      return false;
    }

    try {
      const response = await fetch(`${serverUrl}/servo/move`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ channel, angle })
      });
      
      const data = await response.json();
      return data.success;
    } catch (error) {
      addLog('✗ Erro ao enviar comando: ' + error.message, 'error');
      return false;
    }
  };

  const updateServo = async (id, angle) => {
    const servo = servos[id];
    const safeAngle = Math.max(servo.min, Math.min(servo.max, angle));
    
    setServos(prev => prev.map(s => 
      s.id === id ? { ...s, angle: safeAngle } : s
    ));

    if (connected) {
      const success = await sendServoCommand(id, safeAngle);
      if (success) {
        addLog(`${servo.name} → ${safeAngle}°`, 'success');
      } else {
        addLog(`Falha ao mover ${servo.name}`, 'error');
      }
    }
  };

  const isAngleSafe = (servo) => {
    return servo.angle >= servo.safe_min && servo.angle <= servo.safe_max;
  };

  const testServo = async (servo) => {
    if (!connected) {
      addLog('✗ Conecte-se ao Raspberry Pi primeiro', 'error');
      return;
    }

    setTesting(true);
    setCurrentTest(servo.id);
    addLog(`🔧 Testando ${servo.name}...`, 'info');

    const steps = [90, servo.safe_min, 90, servo.safe_max, 90];
    
    for (let step of steps) {
      await new Promise(resolve => setTimeout(resolve, 800));
      await updateServo(servo.id, step);
    }

    addLog(`✓ ${servo.name} testado com sucesso!`, 'success');
    setCurrentTest(null);
    setTesting(false);
  };

  const testAllServos = async () => {
    if (!connected) {
      addLog('✗ Conecte-se ao Raspberry Pi primeiro', 'error');
      return;
    }

    setTesting(true);
    addLog('🚀 Iniciando teste completo...', 'info');
    
    for (let servo of servos) {
      await testServo(servo);
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    addLog('✓ Todos os servos testados!', 'success');
    setTesting(false);
  };

  const resetAll = async () => {
    if (!connected) {
      addLog('✗ Conecte-se ao Raspberry Pi primeiro', 'error');
      return;
    }

    for (let servo of servos) {
      await updateServo(servo.id, 90);
    }
    addLog('↺ Todos os servos retornaram a 90°', 'info');
  };

  const emergencyStop = async () => {
    if (!connected) return;
    
    try {
      await fetch(`${serverUrl}/servo/stop`, { method: 'POST' });
      addLog('🛑 PARADA DE EMERGÊNCIA', 'error');
    } catch (error) {
      addLog('Erro na parada de emergência', 'error');
    }
  };

  const generatePythonCode = () => {
    const code = `#!/usr/bin/env python3
"""
Código de calibração gerado pelo Calibrador Web
Execute no Raspberry Pi com os servos conectados
"""

import sys
from pathlib import Path

# Adicionar pasta hardware ao path
sys.path.insert(0, str(Path(__file__).parent))

from hardware.servo import Servo
import time

def calibrate_servos():
    servo = Servo()
    
    # Ângulos calibrados
    servo_angles = {
${servos.map(s => `        ${s.id}: ${s.angle}  # ${s.name}`).join(',\n')}
    }
    
    print("🔧 Aplicando calibração...")
    
    for channel, angle in servo_angles.items():
        print(f"  Servo {channel} → {angle}°")
        servo.set_servo_pwm(str(channel), angle)
        time.sleep(0.3)
    
    print("✓ Servos calibrados!")

if __name__ == '__main__':
    try:
        calibrate_servos()
    except KeyboardInterrupt:
        print("\\n⚠️  Interrompido pelo usuário")
    except Exception as e:
        print(f"✗ Erro: {e}")
`;
    
    navigator.clipboard.writeText(code);
    addLog('📋 Código Python copiado!', 'success');
  };

  useEffect(() => {
    const interval = setInterval(checkConnection, 5000);
    return () => clearInterval(interval);
  }, [serverUrl]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <Activity className="w-8 h-8 text-blue-400" />
            <h1 className="text-2xl md:text-3xl font-bold">Calibrador de Servos - Raspberry Pi</h1>
          </div>
          <p className="text-slate-400">Configure os servos MG90S do braço robótico Freenove remotamente</p>
        </div>

        {/* Connection Panel */}
        <div className="bg-slate-800/50 backdrop-blur-sm border-2 border-slate-700 rounded-xl p-6 mb-6">
          <div className="flex flex-col md:flex-row items-start md:items-center gap-4">
            <div className="flex-1">
              <label className="block text-sm text-slate-400 mb-2">Endereço do Raspberry Pi</label>
              <input
                type="text"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                disabled={connected || connecting}
                className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:border-blue-500 disabled:opacity-50"
                placeholder="http://192.168.1.100:5001"
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={connectToRaspberryPi}
                disabled={connected || connecting}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                {connecting ? '⏳ Conectando...' : connected ? '✓ Conectado' : '🔌 Conectar'}
              </button>
              {connected && (
                <button
                  onClick={emergencyStop}
                  className="px-6 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-medium transition-colors"
                >
                  🛑 PARAR
                </button>
              )}
            </div>
          </div>
          
          <div className="mt-4 flex items-center gap-2">
            {connected ? (
              <>
                <Wifi className="w-5 h-5 text-green-400" />
                <span className="text-green-400">Conectado ao Raspberry Pi</span>
              </>
            ) : (
              <>
                <WifiOff className="w-5 h-5 text-red-400" />
                <span className="text-red-400">Desconectado</span>
              </>
            )}
          </div>
        </div>

        {/* Controles principais */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {/* Painéis de controle dos servos */}
          <div className="lg:col-span-2 space-y-4">
            {servos.map(servo => (
              <div 
                key={servo.id} 
                className={`bg-slate-800/50 backdrop-blur-sm border-2 rounded-xl p-4 md:p-6 transition-all ${
                  currentTest === servo.id ? 'border-yellow-400 shadow-lg shadow-yellow-400/20' : 'border-slate-700'
                }`}
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between mb-4 gap-4">
                  <div className="flex items-center gap-3">
                    <div 
                      className="w-4 h-4 rounded-full flex-shrink-0" 
                      style={{ backgroundColor: servo.color }}
                    />
                    <div>
                      <h3 className="text-lg font-semibold">{servo.name}</h3>
                      <p className="text-sm text-slate-400">Canal {servo.id}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="text-3xl font-bold" style={{ color: servo.color }}>
                        {servo.angle}°
                      </div>
                      <div className={`text-xs flex items-center gap-1 ${
                        isAngleSafe(servo) ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        {isAngleSafe(servo) ? <CheckCircle className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                        {isAngleSafe(servo) ? 'Seguro' : 'Atenção'}
                      </div>
                    </div>
                    
                    <button
                      onClick={() => testServo(servo)}
                      disabled={testing || !connected}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 rounded-lg font-medium transition-colors flex items-center gap-2"
                    >
                      <Zap className="w-4 h-4" />
                      Testar
                    </button>
                  </div>
                </div>

                {/* Slider principal */}
                <div className="space-y-2">
                  <input
                    type="range"
                    min={servo.min}
                    max={servo.max}
                    value={servo.angle}
                    onChange={(e) => updateServo(servo.id, parseInt(e.target.value))}
                    disabled={testing || !connected}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
                    style={{
                      background: `linear-gradient(to right, 
                        #ef4444 0%, 
                        #ef4444 ${(servo.safe_min / 180) * 100}%, 
                        ${servo.color} ${(servo.safe_min / 180) * 100}%, 
                        ${servo.color} ${(servo.safe_max / 180) * 100}%, 
                        #ef4444 ${(servo.safe_max / 180) * 100}%, 
                        #ef4444 100%)`
                    }}
                  />
                  
                  {/* Indicadores de limites */}
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Min: {servo.min}°</span>
                    <span className="text-green-400">Seguro: {servo.safe_min}° - {servo.safe_max}°</span>
                    <span>Max: {servo.max}°</span>
                  </div>
                </div>

                {/* Controles rápidos */}
                <div className="grid grid-cols-3 gap-2 mt-4">
                  <button
                    onClick={() => updateServo(servo.id, servo.safe_min)}
                    disabled={testing || !connected}
                    className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg text-sm transition-colors"
                  >
                    Min Seguro
                  </button>
                  <button
                    onClick={() => updateServo(servo.id, 90)}
                    disabled={testing || !connected}
                    className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg text-sm transition-colors"
                  >
                    Centro (90°)
                  </button>
                  <button
                    onClick={() => updateServo(servo.id, servo.safe_max)}
                    disabled={testing || !connected}
                    className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg text-sm transition-colors"
                  >
                    Max Seguro
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Painel lateral */}
          <div className="space-y-6">
            {/* Ações globais */}
            <div className="bg-slate-800/50 backdrop-blur-sm border-2 border-slate-700 rounded-xl p-6">
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Zap className="w-5 h-5 text-yellow-400" />
                Ações
              </h3>
              
              <div className="space-y-3">
                <button
                  onClick={testAllServos}
                  disabled={testing || !connected}
                  className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 rounded-lg font-medium transition-colors"
                >
                  {testing ? '⏳ Testando...' : '🚀 Testar Todos'}
                </button>
                
                <button
                  onClick={resetAll}
                  disabled={testing || !connected}
                  className="w-full px-4 py-3 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg font-medium transition-colors"
                >
                  ↺ Reset (90°)
                </button>
                
                <button
                  onClick={generatePythonCode}
                  className="w-full px-4 py-3 bg-green-600 hover:bg-green-700 rounded-lg font-medium transition-colors"
                >
                  📋 Copiar Código Python
                </button>
              </div>
            </div>

            {/* Log de atividades */}
            <div className="bg-slate-800/50 backdrop-blur-sm border-2 border-slate-700 rounded-xl p-6">
              <h3 className="text-lg font-semibold mb-4">📝 Log</h3>
              
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {logs.length === 0 ? (
                  <p className="text-slate-500 text-sm">Nenhuma atividade ainda...</p>
                ) : (
                  logs.map((log, idx) => (
                    <div 
                      key={idx}
                      className={`text-xs p-2 rounded ${
                        log.type === 'success' ? 'bg-green-900/30 text-green-300' :
                        log.type === 'error' ? 'bg-red-900/30 text-red-300' :
                        'bg-blue-900/30 text-blue-300'
                      }`}
                    >
                      <span className="text-slate-400">[{log.timestamp}]</span> {log.message}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Instruções de instalação */}
            <div className="bg-blue-900/20 border-2 border-blue-500/50 rounded-xl p-6">
              <h3 className="text-lg font-semibold text-blue-400 mb-2">📦 Servidor Python</h3>
              <p className="text-sm text-blue-200 mb-2">Execute no Raspberry Pi:</p>
              <code className="block bg-slate-900 p-2 rounded text-xs text-green-400 overflow-x-auto">
                python3 servo_server.py
              </code>
            </div>
          </div>
        </div>

        {/* Avisos de segurança */}
        <div className="bg-red-900/20 border-2 border-red-500/50 rounded-xl p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-6 h-6 text-red-400 flex-shrink-0 mt-1" />
            <div>
              <h3 className="text-lg font-semibold text-red-400 mb-2">⚠️ Avisos de Segurança</h3>
              <ul className="space-y-1 text-sm text-red-200">
                <li>• <strong>SEMPRE</strong> teste movimentos incrementalmente (5° por vez)</li>
                <li>• Mantenha tensão estável (5V recomendado para MG90S)</li>
                <li>• Evite ângulos extremos (0° e 180°) - use margens de 10°</li>
                <li>• Aguarde 300ms entre comandos para evitar sobrecarga</li>
                <li>• Se o servo travar ou vibrar, use o botão PARAR imediatamente</li>
                <li>• Verifique colisões mecânicas antes de testar ângulos extremos</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RaspberryPiServoCalibrator;