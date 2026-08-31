#!/usr/bin/env python3
"""
EVA ROBOT - SAFETY SYSTEM
Sistema de segurança: watchdog, emergency stop, limites
"""

import time
from typing import Optional, Callable, Dict
from collections import deque
from dataclasses import dataclass
from enum import Enum

from hardware_config import CONFIG

# ===========================================================================
# LIMITES DO CABO DA PICAM
#
# O flat CSI sobe da picam, atravessa o braço e desce até o Pi. Ele é o
# que limita este robô -- não os servos, que iriam bem além.
#
#   YAW_FRENTE  = 90   base apontando pra frente do carro (repouso)
#   YAW_LATERAL = 0    base virada pra DIREITA de quem olha o robô
#
# Nomeados aqui e derivados em todo o resto de propósito: o servo da
# base já foi remontado uma vez, e nessa hora é melhor ter dois números
# num lugar só do que ângulos crus espalhados por quatro arquivos.
# ===========================================================================
YAW_FRENTE = 90
YAW_LATERAL = 0

# A partir deste cotovelo o cabo estica, SE a base não estiver lateral.
COTOVELO_ESTICA_CABO = 160
# Yaw máximo ainda seguro com o cotovelo acima do limite acima.
# Conservador: 0 foi testado e é seguro, 90 é proibido; entre os dois não
# há medição, e 30 é o palpite informado do dono do hardware.
YAW_CABO_SEGURO = 30


# ============================================================================
# TIPOS E ENUMS
# ============================================================================

class SafetyLevel(Enum):
    """Níveis de alerta de segurança"""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class SafetyWarning:
    """Registro de warning de segurança"""
    timestamp: float
    level: SafetyLevel
    message: str
    sensor: Optional[str] = None
    value: Optional[float] = None


# ============================================================================
# WATCHDOG
# ============================================================================

class Watchdog:
    """
    Watchdog Timer - monitora heartbeats
    Se não receber heartbeat no prazo, aciona estop
    """
    
    def __init__(self, timeout: float = None):
        self.timeout = timeout or CONFIG.safety.WATCHDOG_TIMEOUT
        self.last_heartbeat = time.time()
        self.enabled = True
        self.on_timeout: Optional[Callable] = None
    
    def feed(self):
        """Alimenta o watchdog (heartbeat recebido)"""
        self.last_heartbeat = time.time()
    
    def check(self) -> bool:
        """
        Verifica se watchdog expirou
        
        Returns:
            True se OK, False se timeout
        """
        if not self.enabled:
            return True
        
        elapsed = time.time() - self.last_heartbeat
        
        if elapsed > self.timeout:
            if self.on_timeout:
                self.on_timeout(elapsed)
            return False
        
        return True
    
    def reset(self):
        """Reseta watchdog"""
        self.last_heartbeat = time.time()
    
    def disable(self):
        """Desabilita watchdog (CUIDADO!)"""
        self.enabled = False
    
    def enable(self):
        """Habilita watchdog"""
        self.enabled = True
        self.reset()


# ============================================================================
# SAFETY CONTROLLER
# ============================================================================

class SafetyController:
    """
    Controlador de Segurança Principal
    
    Funções:
    - Monitora sensores
    - Valida comandos
    - Aciona emergency stop
    - Mantém log de warnings
    """
    
    def __init__(self, robot_core):
        self.robot = robot_core
        
        # Estado
        self.enabled = True
        self.emergency_stop_active = False
        self.safety_level = SafetyLevel.NORMAL

        # ESCOPO do emergency stop ativo. Nem todo motivo de parada é o
        # mesmo tipo de parada:
        #
        #   servos_bloqueados=True   "pare de operar" -- painel, bateria
        #                            crítica, watchdog. Trava tudo.
        #   servos_bloqueados=False  "não dirija por aí" -- ultrassom.
        #                            Trava as rodas, deixa a cabeça livre.
        #
        # BUG REAL que isto fecha: o ultrassom mede o que está na frente
        # do CHASSI, e disparava um estop que também bloqueava
        # validate_servo_command. Com o robô parado em cima de uma mesa
        # com uma parede a 8cm, a EVA ficou uma sessão inteira sem poder
        # mexer a cabeça -- e como o obstáculo não sai da frente sozinho,
        # o ciclo reset/estop repetia indefinidamente. Girar a câmera não
        # aproxima o robô de nada; não havia razão física pro bloqueio.
        self.servos_bloqueados = True
        # Por que o estop atual foi acionado, pra saber se pode sair
        # sozinho quando a condição passar (só o de obstáculo pode).
        self.motivo_estop: Optional[str] = None
        
        # Warnings
        self.warnings = deque(maxlen=100)
        self.warning_callbacks = []
        
        # Watchdog
        self.watchdog = Watchdog(CONFIG.safety.WATCHDOG_TIMEOUT)
        self.watchdog.on_timeout = self._watchdog_timeout
        
        # Última leitura de sensores
        self.last_sensor_data: Dict = {}
        
        print("✅ Safety Controller inicializado")
    
    # ========================================
    # VALIDAÇÃO DE COMANDOS
    # ========================================
    
    def validate_drive_command(
        self, 
        vx: float, 
        vy: float, 
        vz: float
    ) -> tuple[bool, str]:
        """
        Valida comando de movimento
        
        Returns:
            (is_safe, reason)
        """
        if not self.enabled:
            return True, "Safety desabilitado"
        
        if self.emergency_stop_active:
            return False, "EMERGENCY STOP ativo"
        
        # Verificar se está indo para frente
        if vx > 0:
            # Ler sensor ultrasonic
            distance = self.last_sensor_data.get('ultrasonic_cm')
            
            if distance is not None:
                # Obstáculo muito próximo
                if distance < CONFIG.safety.EMERGENCY_STOP_DISTANCE:
                    self.trigger_emergency_stop(
                        f"Obstáculo crítico: {distance:.1f}cm",
                        bloqueia_servos=False,
                        motivo_tipo="obstaculo",
                    )
                    return False, f"Obstáculo muito próximo ({distance:.1f}cm)"
                
                # Warning
                if distance < CONFIG.safety.MIN_OBSTACLE_DISTANCE:
                    self.add_warning(
                        SafetyLevel.WARNING,
                        f"Obstáculo detectado: {distance:.1f}cm",
                        sensor="ultrasonic",
                        value=distance
                    )
                    return False, f"Obstáculo próximo ({distance:.1f}cm)"
        
        # Verificar bateria
        battery_v = self.last_sensor_data.get('battery_v')
        
        if battery_v is not None:
            if battery_v < CONFIG.safety.CRITICAL_BATTERY_VOLTAGE:
                self.trigger_emergency_stop(
                    f"Bateria crítica: {battery_v:.1f}V"
                )
                return False, f"Bateria crítica ({battery_v:.1f}V)"
            
            if battery_v < CONFIG.safety.LOW_BATTERY_VOLTAGE:
                self.add_warning(
                    SafetyLevel.WARNING,
                    f"Bateria baixa: {battery_v:.1f}V",
                    sensor="battery",
                    value=battery_v
                )
        
        return True, "OK"
    
    def validate_servo_command(
        self,
        channel: int,
        angle: int
    ) -> tuple[bool, str]:
        """
        Valida comando de servo com regras físicas e cinemáticas reais
        """

        if not self.enabled:
            return True, "Safety desabilitado"

        # Só bloqueia servo quando o estop é do tipo "pare de operar".
        # Estop de obstáculo (ultrassom) trava as rodas e deixa a cabeça
        # livre -- ver self.servos_bloqueados no __init__.
        if self.emergency_stop_active and self.servos_bloqueados:
            return False, "EMERGENCY STOP ativo"

        # ===============================
        # LIMITES FÍSICOS ABSOLUTOS
        # ===============================
        # yaw e cabeça têm exceções condicionais tratadas abaixo, à
        # parte, porque dependem do estado de outros canais -- não dá
        # pra expressar isso numa tabela plana de min/max.
        physical_limits = {
            0: (0, 90),     # yaw / base -- NÃO vai até 180, testado e confirmado
            1: (40, 110),   # pitch / ombro
            2: (90, 180),   # cotovelo
            3: (0, 117),    # cabeça -- baseline; ver regra 2 abaixo (relaxa com pitch baixo)
        }

        if channel not in physical_limits:
            return False, "Canal de servo inválido"

        # ===============================
        # ESTADO ATUAL DO BRAÇO
        # ===============================
        try:
            arm = self.robot.arm.current_angles
            elbow = arm.get(2, 90)
            pitch = arm.get(1, 90)
            yaw = arm.get(0, 90)   # regra do cabo da picam, abaixo
        except Exception:
            # Falha ao ler estado → não movimenta
            return False, "Estado do braço indisponível"

        # ===============================
        # REGRAS ESPECIAIS (calibração real)
        # ===============================

        # 1) REGRA DO CABO DA PICAM.
        #
        # NÃO é cinemática do braço, apesar do nome que esta regra tinha
        # antes ("cotovelo em posição crítica"). É o flat CSI: com o
        # cotovelo alto E a base apontando pra FRENTE, o cabo que sobe da
        # picam até o Pi estica além do que aguenta.
        #
        # Isso importa porque o dano é CUMULATIVO E INVISÍVEL -- o cabo
        # não quebra na hora; começa a falhar de forma intermitente
        # semanas depois, e a procura vai parar no software.
        #
        # Com a base lateral (yaw <= YAW_CABO_SEGURO) o braço sobe sobre
        # ar livre e o cabo tem folga -- confirmado fisicamente com
        # cotovelo em 165/170 e yaw 0, sem tensão e sem colisão.
        #
        # A versão antiga desta regra travava pitch/cabeça e deixava o
        # CANAL 2 passar sempre (`channel != 2`). Isso era o pior dos
        # dois mundos: não impedia a combinação que danifica o cabo (o
        # cotovelo subia igual, confirmado em uso real chegando a 175°) e
        # ainda paralisava a EVA na postura mais útil que este corpo tem
        # -- ela chegava na altura de um rosto e congelava, sem conseguir
        # virar pra ninguém.
        #
        # Bloqueia nos DOIS sentidos de propósito: subir o cotovelo com a
        # base de frente, E girar a base pra frente com o cotovelo já
        # alto. Barrar só um lado deixaria a mesma combinação acessível
        # pelo outro caminho -- foi assim que o 175° passou.
        if channel == 2 and angle >= COTOVELO_ESTICA_CABO and yaw > YAW_CABO_SEGURO:
            return False, (f"Cotovelo {angle}° com a base em {yaw}° estica o cabo "
                           f"da picam -- gire a base para <= {YAW_CABO_SEGURO}° antes")

        if channel == 0 and angle > YAW_CABO_SEGURO and elbow >= COTOVELO_ESTICA_CABO:
            return False, (f"Girar a base para {angle}° com o cotovelo em {elbow}° "
                           f"estica o cabo da picam -- recolha o cotovelo antes")

        # 2) Cabeça (canal 3): teto normal 117°, mas com pitch baixo
        # (<=50°) há curso livre a mais -- até 180°. Tem que checar
        # ANTES do teto físico geral da tabela acima, senão o teto de
        # 117 já barra antes da relaxação valer.
        if channel == 3:
            teto = 180 if pitch <= 50 else 117
            if not (0 <= angle <= teto):
                motivo = (f"Cabeça fora do limite ({teto}° com pitch <= 50°)"
                          if pitch <= 50 else "Cabeça acima do limite seguro (117°)")
                return False, motivo
            return True, "OK"

        # ===============================
        # LIMITE FÍSICO DO CANAL (yaw / pitch / cotovelo)
        # ===============================
        min_a, max_a = physical_limits[channel]
        if not (min_a <= angle <= max_a):
            return False, f"Fora do limite físico ({min_a}°–{max_a}°)"

        # ===============================
        # SE PASSOU POR TUDO → SEGURO
        # ===============================
        return True, "OK"

    
    # ========================================
    # MONITORAMENTO DE SENSORES
    # ========================================
    
    def update_sensor_data(self, sensor_data: Dict):
        """
        Atualiza leituras de sensores e verifica limites
        
        Args:
            sensor_data: {"ultrasonic_cm": float, "battery_v": float, ...}
        """
        self.last_sensor_data = sensor_data
        
        # Verificar bateria
        if 'battery_v' in sensor_data:
            voltage = sensor_data['battery_v']
            
            if voltage < CONFIG.safety.CRITICAL_BATTERY_VOLTAGE:
                # CORRIGIDO: antes só logava (add_warning) -- o robô podia
                # continuar andando com bateria crítica até o próximo
                # comando `drive` ser validado. Agora para de verdade,
                # assim que a leitura chega, sem esperar comando nenhum.
                self.trigger_emergency_stop(f"Bateria crítica: {voltage:.1f}V")
            elif voltage < CONFIG.safety.LOW_BATTERY_VOLTAGE:
                self.add_warning(
                    SafetyLevel.WARNING,
                    f"Bateria baixa: {voltage:.1f}V",
                    sensor="battery",
                    value=voltage
                )
        
        # Verificar distância
        if 'ultrasonic_cm' in sensor_data:
            distance = sensor_data['ultrasonic_cm']
            
            if distance < CONFIG.safety.EMERGENCY_STOP_DISTANCE:
                # CORRIGIDO (bug real visto em teste ao vivo): antes só
                # logava CRITICAL aqui -- quem realmente parava o robô
                # era validate_drive_command(), e só no instante exato de
                # um comando `drive` chegar. Com o robô já em movimento
                # (TTL do comando anterior ainda rodando) e nenhum
                # comando novo chegando entre um tick de sensor e outro,
                # ele seguia andando na direção do obstáculo já detectado
                # como crítico, esperando esse próximo comando -- ou,
                # como aconteceu, esperando alguém apertar o estop manual
                # no dashboard. Agora o monitoramento contínuo (chamado a
                # cada CONFIG.sensors.SENSOR_READ_INTERVAL, não só a cada
                # comando) para de verdade assim que vê a leitura crítica.
                self.trigger_emergency_stop(
                    f"Obstáculo crítico: {distance:.1f}cm",
                    bloqueia_servos=False,
                    motivo_tipo="obstaculo",
                )
            elif distance < CONFIG.safety.MIN_OBSTACLE_DISTANCE:
                self.add_warning(
                    SafetyLevel.WARNING,
                    f"Obstáculo detectado: {distance:.1f}cm",
                    sensor="ultrasonic",
                    value=distance
                )

            # Sai sozinho do estop de obstáculo quando o caminho abre.
            #
            # HISTERESE de propósito: entra em EMERGENCY_STOP_DISTANCE
            # (10cm) e só sai em MIN_OBSTACLE_DISTANCE (15cm). Com um
            # único limiar, uma leitura oscilando em torno dele faria o
            # robô entrar e sair de emergência várias vezes por segundo.
            #
            # Só o estop de obstáculo se limpa sozinho: ele responde a uma
            # condição do mundo que o próprio sensor consegue desfazer
            # (o obstáculo saiu, ou alguém moveu o robô). Painel, bateria
            # e watchdog continuam exigindo reset explícito -- nenhum dos
            # três "passa" só porque a leitura seguinte foi melhor.
            elif (self.emergency_stop_active
                    and self.motivo_estop == "obstaculo"
                    and distance >= CONFIG.safety.MIN_OBSTACLE_DISTANCE):
                self.emergency_stop_active = False
                self.servos_bloqueados = True
                self.motivo_estop = None
                self.safety_level = SafetyLevel.NORMAL
                self.watchdog.reset()
                print(f"✅ Caminho livre ({distance:.1f}cm) -- saindo do estop de obstáculo")
    
    # ========================================
    # EMERGENCY STOP
    # ========================================
    
    def trigger_emergency_stop(self, reason: str, *,
                               bloqueia_servos: bool = True,
                               motivo_tipo: Optional[str] = None):
        """
        Aciona parada de emergência

        Para os MOTORES imediatamente -- não desliga o robô inteiro.

        CORRIGIDO (achado em uso real): chamava self.robot.stop() --
        EVARobot.stop() inteiro, que desliga a câmera e zera
        self.running, o que por sua vez matava as threads de watchdog e
        sensor (que checam `while self.running`). Resultado: depois de
        QUALQUER emergency stop, o robô ficava com câmera morta e
        monitoramento morto pra sempre, e reset_emergency_stop() (que só
        desliga a flag) não desfazia nada disso -- só reiniciar o
        processo resolvia. A própria existência de reset_emergency_stop()
        já indica que a intenção sempre foi "pausa recuperável", não
        "desligar tudo" -- trocar por stop_motors() (só motor) é o que
        faz reset_emergency_stop() significar o que o nome diz.
        """
        # Um estop mais restritivo SOBREPÕE um mais permissivo já ativo.
        # Sem isto, um estop de obstáculo (servos livres) já ativo faria o
        # `return` engolir um estop de bateria crítica logo depois, e os
        # servos continuariam liberados com a bateria no fim.
        if self.emergency_stop_active:
            if bloqueia_servos and not self.servos_bloqueados:
                self.servos_bloqueados = True
                self.motivo_estop = motivo_tipo
                print(f"\n🚨 ESCALANDO PARADA: {reason} (servos também travados)\n")
            return  # Já ativo
        
        self.emergency_stop_active = True
        self.servos_bloqueados = bloqueia_servos
        self.motivo_estop = motivo_tipo
        self.safety_level = SafetyLevel.EMERGENCY
        
        # Parar motores -- NÃO o robô inteiro (câmera/threads continuam
        # vivas, é isso que torna reset_emergency_stop() de fato
        # reversível sem reiniciar o processo).
        try:
            self.robot.stop_motors()
        except Exception as e:
            print(f"❌ Erro ao parar motores: {e}")
        
        # Log
        self.add_warning(
            SafetyLevel.EMERGENCY,
            f"EMERGENCY STOP: {reason}",
            sensor="system"
        )
        
        escopo = "tudo travado" if bloqueia_servos else "rodas travadas, cabeça livre"
        print(f"\n🚨 PARADA DE EMERGÊNCIA: {reason} ({escopo})\n")
    
    def reset_emergency_stop(self) -> bool:
        """
        Reseta emergency stop
        
        Returns:
            True se resetado com sucesso
        """
        if not self.emergency_stop_active:
            return True
        
        # Verificar se é seguro resetar
        safe, reason = self._check_safe_to_reset()
        
        if not safe:
            print(f"⚠️  Não é seguro resetar: {reason}")
            return False
        
        self.emergency_stop_active = False
        self.servos_bloqueados = True
        self.motivo_estop = None
        self.safety_level = SafetyLevel.NORMAL
        self.watchdog.reset()
        
        print("✅ Emergency stop resetado")
        return True
    
    def _check_safe_to_reset(self) -> tuple[bool, str]:
        """Verifica se é seguro resetar emergency stop"""
        
        # Bateria crítica IMPEDE: ali o reset seria fingimento -- a
        # condição não passa sozinha e não há escopo reduzido que ajude.
        battery_v = self.last_sensor_data.get('battery_v')
        if battery_v and battery_v < CONFIG.safety.CRITICAL_BATTERY_VOLTAGE:
            return False, f"Bateria ainda crítica: {battery_v:.1f}V"
        
        # Obstáculo NÃO impede mais -- DEADLOCK REAL que isto fecha:
        # o obstáculo bloqueava o reset de QUALQUER estop, inclusive dos
        # que não têm nada a ver com ele. Com o robô parado em cima de
        # uma mesa com uma parede a 8cm, um estop de WATCHDOG ficava
        # impossível de resetar pelo dashboard, para sempre, e só
        # reiniciar o processo resolvia -- a mesa não sai da frente.
        #
        # Se o obstáculo continuar lá depois do reset, update_sensor_data
        # dispara em seguida um estop de OBSTÁCULO, que trava só as rodas
        # e deixa a cabeça livre (ver servos_bloqueados). Estado correto e
        # recuperável, contra um deadlock que não era nem uma coisa nem
        # outra.
        distance = self.last_sensor_data.get('ultrasonic_cm')
        if distance and distance < CONFIG.safety.EMERGENCY_STOP_DISTANCE:
            print(f"ℹ️  resetando com obstáculo a {distance:.1f}cm -- as rodas devem "
                  f"voltar pro estop de obstáculo em seguida; a cabeça não")
        
        return True, "OK"
    
    # ========================================
    # WARNINGS
    # ========================================
    
    def add_warning(
        self,
        level: SafetyLevel,
        message: str,
        sensor: Optional[str] = None,
        value: Optional[float] = None
    ):
        """Adiciona warning ao log"""
        
        warning = SafetyWarning(
            timestamp=time.time(),
            level=level,
            message=message,
            sensor=sensor,
            value=value
        )
        
        self.warnings.append(warning)
        
        # Atualizar nível de segurança
        if level.value == SafetyLevel.EMERGENCY.value:
            self.safety_level = SafetyLevel.EMERGENCY
        elif level.value == SafetyLevel.CRITICAL.value and self.safety_level != SafetyLevel.EMERGENCY:
            self.safety_level = SafetyLevel.CRITICAL
        elif level.value == SafetyLevel.WARNING.value and self.safety_level == SafetyLevel.NORMAL:
            self.safety_level = SafetyLevel.WARNING
        
        # Callbacks
        for callback in self.warning_callbacks:
            try:
                callback(warning)
            except Exception as e:
                print(f"❌ Erro em callback: {e}")
        
        # Log
        symbols = {
            SafetyLevel.NORMAL: "ℹ️ ",
            SafetyLevel.WARNING: "⚠️ ",
            SafetyLevel.CRITICAL: "🔴",
            SafetyLevel.EMERGENCY: "🚨"
        }
        
        symbol = symbols.get(level, "⚠️ ")
        print(f"{symbol} SAFETY [{level.value.upper()}]: {message}")
    
    def get_recent_warnings(self, count: int = 10) -> list:
        """Retorna warnings recentes"""
        return list(self.warnings)[-count:]
    
    def clear_warnings(self):
        """Limpa histórico de warnings"""
        self.warnings.clear()
        self.safety_level = SafetyLevel.NORMAL
    
    # ========================================
    # WATCHDOG
    # ========================================
    
    def heartbeat(self):
        """Recebe heartbeat (mantém watchdog ativo)"""
        self.watchdog.feed()
    
    def _watchdog_timeout(self, elapsed: float):
        """Callback quando watchdog expira"""
        self.trigger_emergency_stop(
            f"Watchdog timeout ({elapsed:.1f}s sem heartbeat)"
        )
    
    # ========================================
    # CONTROLE
    # ========================================
    
    def enable(self):
        """Habilita sistema de segurança"""
        self.enabled = True
        self.watchdog.enable()
        print("✅ Safety habilitado")
    
    def disable(self):
        """Desabilita sistema de segurança (CUIDADO!)"""
        self.enabled = False
        self.watchdog.disable()
        print("⚠️  Safety DESABILITADO")
    
    def get_status(self) -> Dict:
        """Retorna status do sistema de segurança"""
        return {
            'enabled': self.enabled,
            'emergency_stop': self.emergency_stop_active,
            # Quem lê o estado precisa saber se a cabeça ainda responde --
            # 'emergency_stop: true' sozinho fazia parecer que o robô
            # estava inteiramente parado quando só as rodas estavam.
            #
            # Reportado como estado EFETIVO, não como o atributo cru:
            # self.servos_bloqueados é o ESCOPO do estop e vale True em
            # repouso (é o escopo padrão do próximo estop). Publicar o
            # atributo direto fazia um robô perfeitamente livre reportar
            # 'servos_bloqueados: true, motivo_estop: null' -- travado
            # por um estop que não existe. Aqui o campo significa o que o
            # nome diz: os servos estão bloqueados NESTE MOMENTO.
            'servos_bloqueados': self.emergency_stop_active and self.servos_bloqueados,
            'motivo_estop': self.motivo_estop,
            'level': self.safety_level.value,
            'watchdog_ok': self.watchdog.check(),
            'recent_warnings': len(self.get_recent_warnings()),
            'last_sensor_data': self.last_sensor_data
        }


# ============================================================================
# TESTE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🛡️  EVA ROBOT - SAFETY SYSTEM TEST")
    print("="*60 + "\n")
    
    # Mock robot
    class MockRobot:
        def stop_motors(self):
            print("🛑 Motores parados")
    
    robot = MockRobot()
    safety = SafetyController(robot)
    
    # Teste 1: Validação de comando normal
    print("1️⃣  Teste: Comando normal")
    safety.update_sensor_data({'ultrasonic_cm': 50.0, 'battery_v': 7.5})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 2: Obstáculo próximo
    print("2️⃣  Teste: Obstáculo próximo")
    safety.update_sensor_data({'ultrasonic_cm': 12.0, 'battery_v': 7.5})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 3: Obstáculo crítico
    print("3️⃣  Teste: Obstáculo crítico")
    safety.update_sensor_data({'ultrasonic_cm': 8.0, 'battery_v': 7.5})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 4: Bateria baixa
    print("4️⃣  Teste: Bateria baixa")
    safety.emergency_stop_active = False  # Reset
    safety.update_sensor_data({'ultrasonic_cm': 50.0, 'battery_v': 6.3})
    ok, msg = safety.validate_drive_command(1.0, 0, 0)
    print(f"   {'✅' if ok else '❌'} {msg}\n")
    
    # Teste 5: Status
    print("5️⃣  Status final:")
    status = safety.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    print("\n" + "="*60 + "\n")