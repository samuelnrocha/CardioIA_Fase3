#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIAP - Faculdade de Informática e Administração Paulista
Projeto CardioIA - Fase 3 (Ir Além 1: Comunicação Automatizada com REST e E-mail)
Grupo: Data Health Solutions

Módulo: motor_risco.py
----------------------
Implementa a lógica clínica determinística de verificação de riscos sobre
sinais vitais recebidos via API REST (batimentos cardíacos, temperatura,
umidade, aceleração e tempo sem movimento).
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional


# Cadastro base dos pacientes acompanhados desde a Fase 2 do CardioIA
PACIENTES_CARDIOIA: Dict[str, Dict[str, object]] = {
    "PAC-001": {
        "id": "PAC-001",
        "nome": "Ana Beatriz Souza",
        "idade": 58,
        "sexo": "F",
        "diagnostico_base": "Síndrome Coronariana Aguda",
        "medico_responsavel": "Dra. Helena Prado",
        "email_equipe": "helena.prado@cardioia.med.br",
    },
    "PAC-002": {
        "id": "PAC-002",
        "nome": "Carlos Eduardo Lima",
        "idade": 63,
        "sexo": "M",
        "diagnostico_base": "Infarto Agudo do Miocárdio",
        "medico_responsavel": "Dr. André Vasconcelos",
        "email_equipe": "andre.vasconcelos@cardioia.med.br",
    },
    "PAC-003": {
        "id": "PAC-003",
        "nome": "Mariana Ferreira",
        "idade": 47,
        "sexo": "F",
        "diagnostico_base": "Arritmia / Síncope Vasovagal",
        "medico_responsavel": "Dr. Marcos Tavares",
        "email_equipe": "marcos.tavares@cardioia.med.br",
    },
    "PAC-004": {
        "id": "PAC-004",
        "nome": "João Pedro Almeida",
        "idade": 39,
        "sexo": "M",
        "diagnostico_base": "Angina Instável",
        "medico_responsavel": "Dra. Sofia Mendes",
        "email_equipe": "sofia.mendes@cardioia.med.br",
    },
    "PAC-005": {
        "id": "PAC-005",
        "nome": "Luiza Martins",
        "idade": 71,
        "sexo": "F",
        "diagnostico_base": "Insuficiência Cardíaca Congestiva",
        "medico_responsavel": "Dra. Sofia Mendes",
        "email_equipe": "sofia.mendes@cardioia.med.br",
    },
}


@dataclass
class ResultadoAvaliacaoRisco:
    """Estrutura de retorno da análise clínica de risco de uma leitura."""
    paciente_id: str
    paciente_nome: str
    medico_responsavel: str
    email_destino: str
    timestamp_avaliacao: str
    bpm: int
    temperatura_c: float
    umidade_pct: float
    aceleracao_g: float
    em_movimento: bool
    segundos_sem_movimento: int
    nivel_risco: str              # BAIXO | MODERADO | ALTO | CRITICO
    escore_gravidade: int         # 0 a 100
    requer_alerta_email: bool
    anomalias_detectadas: List[str]
    conduta_clinica_sugerida: str

    def para_dict(self) -> dict:
        return asdict(self)


class AvaliadorRiscoCardioIA:
    """
    Motor de regras clínicas inspirado no protocolo NEWS2 (National Early Warning Score)
    adaptado para monitoramento cardiológico vestível contínuo.
    """

    # Limiares fisiológicos clínicos
    BPM_TAQUICARDIA_CRITICA = 120
    BPM_TAQUICARDIA_MODERADA = 100
    BPM_BRADICARDIA_CRITICA = 50
    BPM_BRADICARDIA_LIMITE = 58

    TEMP_HIPERTERMIA_SEVERA_C = 39.0
    TEMP_FEBRE_C = 38.0
    TEMP_SUBFEBRIL_C = 37.5
    TEMP_HIPOTERMIA_C = 35.0

    TEMPO_IMOBILIDADE_ALERTA_S = 120   # >= 120s imóvel
    ACELERACAO_QUEDA_BRUSCA_G = 2.30   # Pico de impacto > 2.3G

    def avaliar_sinais_vitais(self, dados: dict) -> ResultadoAvaliacaoRisco:
        """
        Analisa um dicionário de sinais vitais e retorna o diagnóstico de risco,
        as anomalias encontradas e a decisão de disparo de alerta RPA por e-mail.
        """
        paciente_id = str(dados.get("paciente_id", "PAC-001")).upper()
        cadastro = PACIENTES_CARDIOIA.get(
            paciente_id,
            {
                "id": paciente_id,
                "nome": dados.get("paciente_nome", "Paciente Monitorado"),
                "idade": 60,
                "diagnostico_base": "Monitoramento Cardiológico Geral",
                "medico_responsavel": "Dra. Helena Prado",
                "email_equipe": "plantao@cardioia.med.br",
            },
        )

        bpm = int(dados.get("bpm", 75))
        temperatura_c = float(dados.get("temperatura_c", 36.5))
        umidade_pct = float(dados.get("umidade_pct", 55.0))
        aceleracao_g = float(dados.get("aceleracao_g", 1.00))
        em_movimento = bool(dados.get("em_movimento", True))
        segundos_sem_mov = int(dados.get("segundos_sem_movimento", 0 if em_movimento else 180))
        timestamp_str = str(dados.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        anomalias: List[str] = []
        escore = 0

        # 1. Verificação de Frequência Cardíaca (BPM)
        if bpm > self.BPM_TAQUICARDIA_CRITICA:
            anomalias.append(f"Taquicardia Severa ({bpm} BPM > {self.BPM_TAQUICARDIA_CRITICA} BPM)")
            escore += 45
        elif bpm > self.BPM_TAQUICARDIA_MODERADA:
            anomalias.append(f"Taquicardia Moderada ({bpm} BPM > {self.BPM_TAQUICARDIA_MODERADA} BPM)")
            escore += 20
        elif bpm < self.BPM_BRADICARDIA_CRITICA:
            anomalias.append(f"Bradicardia Crítica ({bpm} BPM < {self.BPM_BRADICARDIA_CRITICA} BPM)")
            escore += 45
        elif bpm < self.BPM_BRADICARDIA_LIMITE:
            anomalias.append(f"Bradicardia Limítrofe ({bpm} BPM)")
            escore += 15

        # 2. Verificação de Temperatura Corporal (DHT22)
        if temperatura_c > self.TEMP_HIPERTERMIA_SEVERA_C:
            anomalias.append(f"Febre Alta / Hipertermia Severa ({temperatura_c:.1f} °C > 39.0 °C)")
            escore += 40
        elif temperatura_c > self.TEMP_FEBRE_C:
            anomalias.append(f"Febre Confirmada ({temperatura_c:.1f} °C > {self.TEMP_FEBRE_C:.1f} °C)")
            escore += 30
        elif temperatura_c > self.TEMP_SUBFEBRIL_C:
            anomalias.append(f"Estado Subfebril ({temperatura_c:.1f} °C)")
            escore += 10
        elif temperatura_c < self.TEMP_HIPOTERMIA_C:
            anomalias.append(f"Hipotermia Clínica ({temperatura_c:.1f} °C < {self.TEMP_HIPOTERMIA_C:.1f} °C)")
            escore += 40

        # 3. Verificação de Movimento, Imobilidade e Queda (MPU6050)
        ausencia_movimento = (not em_movimento) or (segundos_sem_mov >= self.TEMPO_IMOBILIDADE_ALERTA_S)
        if aceleracao_g >= self.ACELERACAO_QUEDA_BRUSCA_G and ausencia_movimento:
            anomalias.append(
                f"Impacto de Queda Brusca ({aceleracao_g:.2f} G) seguido de Ausência de Movimento ({segundos_sem_mov}s)"
            )
            escore += 50
        elif ausencia_movimento:
            anomalias.append(f"Ausência Prolongada de Movimento ({segundos_sem_mov}s sem atividade motora)")
            escore += 30

        # 4. Verificação de Sudorese / Umidade Anormal Combinada
        if umidade_pct >= 75.0 and (bpm > 105 or temperatura_c < 35.8):
            anomalias.append(f"Sudorese Profusa / Diaforese Detectada (Umidade {umidade_pct:.1f}%)")
            escore += 15

        # 5. Sinergia Clínica (Agravamento por múltiplos sinais alterados simultaneamente)
        if (bpm > self.BPM_TAQUICARDIA_CRITICA or bpm < self.BPM_BRADICARDIA_CRITICA) and ausencia_movimento:
            anomalias.append("Risco Elevado de Síncope Cardiogênica (Arritmia + Imobilidade)")
            escore += 25
        if bpm > self.BPM_TAQUICARDIA_CRITICA and temperatura_c > self.TEMP_FEBRE_C:
            anomalias.append("Descompensação Cardiotérmica (Taquicardia + Febre)")
            escore += 20

        escore = min(100, escore)

        # Classificação final de risco e recomendação médica
        if escore >= 60:
            nivel_risco = "CRITICO"
            requer_alerta = True
            conduta = (
                "ACIONAMENTO IMEDIATO DE EMERGÊNCIA: Contatar paciente e familiar imediatamente, "
                "avaliar envio de ambulância/SAMU e preparar leito de estabilização hemodinâmica."
            )
        elif escore >= 30:
            nivel_risco = "ALTO"
            requer_alerta = True
            conduta = (
                "INTERVENÇÃO MÉDICA PRIORITÁRIA: Realizar teleconsulta de urgência em até 15 minutos, "
                "revisar medicação antiarrítmica/antitérmica e manter telemetria contínua."
            )
        elif escore >= 15:
            nivel_risco = "MODERADO"
            requer_alerta = False
            conduta = (
                "OBSERVAÇÃO ATIVA: Acompanhar evolução nas próximas 3 coletas e orientar repouso."
            )
        else:
            nivel_risco = "BAIXO"
            requer_alerta = False
            conduta = "Sinais vitais dentro dos parâmetros fisiológicos. Manter monitoramento de rotina."

        return ResultadoAvaliacaoRisco(
            paciente_id=str(cadastro["id"]),
            paciente_nome=str(cadastro["nome"]),
            medico_responsavel=str(cadastro["medico_responsavel"]),
            email_destino=str(dados.get("email_destino") or cadastro["email_equipe"]),
            timestamp_avaliacao=timestamp_str,
            bpm=bpm,
            temperatura_c=round(temperatura_c, 1),
            umidade_pct=round(umidade_pct, 1),
            aceleracao_g=round(aceleracao_g, 2),
            em_movimento=not ausencia_movimento,
            segundos_sem_movimento=segundos_sem_mov,
            nivel_risco=nivel_risco,
            escore_gravidade=escore,
            requer_alerta_email=requer_alerta,
            anomalias_detectadas=anomalias if anomalias else ["Nenhuma anomalia detectada (Sinais Estáveis)"],
            conduta_clinica_sugerida=conduta,
        )
