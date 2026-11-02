#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIAP - Faculdade de Informática e Administração Paulista
Projeto CardioIA - Fase 3 (Ir Além 1: Comunicação Automatizada com REST e E-mail)
Grupo: Data Health Solutions

Módulo: servidor_api.py
-----------------------
API RESTful em Python (FastAPI + SQLite) para recebimento (POST) e consumo (GET)
de sinais vitais de pacientes cardiológicos, integrada ao motor de detecção de
riscos clínicos e ao robô de envio automatizado de e-mails (RPA).
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# Garante que o diretório src esteja no sys.path
DIRETORIO_SRC = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_SRC not in sys.path:
    sys.path.insert(0, DIRETORIO_SRC)

from automacao_email_rpa import AutomacaoEmailRPA
from motor_risco import AvaliadorRiscoCardioIA, PACIENTES_CARDIOIA

DIRETORIO_PROJETO = os.path.dirname(DIRETORIO_SRC)
PASTA_LOGS = os.path.join(DIRETORIO_PROJETO, "logs")
CAMINHO_BANCO_SQLITE = os.path.join(PASTA_LOGS, "cardioia_monitoramento.db")


class PayloadSinaisVitais(BaseModel):
    """Schema de entrada para envio de sinais vitais via POST /api/v1/sinais-vitais."""
    paciente_id: str = Field(default="PAC-001", description="Identificador único do paciente")
    paciente_nome: Optional[str] = Field(default=None, description="Nome do paciente (opcional)")
    bpm: int = Field(..., ge=20, le=260, description="Batimentos cardíacos por minuto (BPM)")
    temperatura_c: float = Field(..., ge=30.0, le=44.0, description="Temperatura corporal em °C")
    umidade_pct: float = Field(default=55.0, ge=0.0, le=100.0, description="Umidade relativa em %")
    aceleracao_g: float = Field(default=1.00, ge=0.0, le=10.0, description="Magnitude de aceleração (G)")
    em_movimento: bool = Field(default=True, description="Indica se há movimento ativo detectado")
    segundos_sem_movimento: int = Field(default=0, ge=0, description="Tempo contínuo sem movimento (s)")
    timestamp: Optional[str] = Field(default=None, description="Data/hora da leitura")


def inicializar_banco() -> None:
    """Cria a tabela SQLite de telemetria e alertas caso ainda não exista."""
    os.makedirs(PASTA_LOGS, exist_ok=True)
    with sqlite3.connect(CAMINHO_BANCO_SQLITE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leituras_sinais_vitais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paciente_id TEXT NOT NULL,
                paciente_nome TEXT NOT NULL,
                medico_responsavel TEXT NOT NULL,
                timestamp_avaliacao TEXT NOT NULL,
                bpm INTEGER NOT NULL,
                temperatura_c REAL NOT NULL,
                umidade_pct REAL NOT NULL,
                aceleracao_g REAL NOT NULL,
                em_movimento INTEGER NOT NULL,
                segundos_sem_movimento INTEGER NOT NULL,
                nivel_risco TEXT NOT NULL,
                escore_gravidade INTEGER NOT NULL,
                requer_alerta_email INTEGER NOT NULL,
                anomalias_json TEXT NOT NULL,
                conduta_clinica_sugerida TEXT NOT NULL,
                email_disparado INTEGER NOT NULL,
                status_email TEXT
            )
            """
        )
        conn.commit()


inicializar_banco()
avaliador_risco = AvaliadorRiscoCardioIA()
robo_email_rpa = AutomacaoEmailRPA()

app = FastAPI(
    title="CardioIA Conectada — API REST de Monitoramento e Alertas RPA",
    description=(
        "API RESTful da Fase 3 (Ir Além 1) do projeto CardioIA (FIAP) para recepção "
        "e consulta de sinais vitais IoT, triagem automática de risco e disparo de e-mails."
    ),
    version="1.0.0",
)


@app.get("/api/v1/health")
def verificar_saude_api():
    """Retorna o status operacional da API REST e métricas consolidadas do banco."""
    with sqlite3.connect(CAMINHO_BANCO_SQLITE) as conn:
        total_leituras = conn.execute("SELECT COUNT(*) FROM leituras_sinais_vitais").fetchone()[0]
        total_alertas = conn.execute(
            "SELECT COUNT(*) FROM leituras_sinais_vitais WHERE requer_alerta_email = 1"
        ).fetchone()[0]
    return {
        "status": "ONLINE",
        "servico": "CardioIA REST API & RPA Alert Engine",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_leituras_armazenadas": total_leituras,
        "total_alertas_disparados": total_alertas,
    }


@app.get("/api/v1/pacientes")
def listar_pacientes():
    """Retorna o catálogo de pacientes monitorados pelo CardioIA."""
    return {
        "total": len(PACIENTES_CARDIOIA),
        "pacientes": list(PACIENTES_CARDIOIA.values()),
    }


@app.post("/api/v1/sinais-vitais", status_code=201)
def receber_sinais_vitais(payload: PayloadSinaisVitais):
    """
    Recebe uma nova leitura de sinais vitais via HTTP POST, executa o motor de
    verificação de riscos e aciona a automação de envio de e-mail (RPA) se necessário.
    """
    avaliacao = avaliador_risco.avaliar_sinais_vitais(payload.model_dump())

    recibo_email = {
        "email_disparado": False,
        "status_transporte": "NAO_REQUERIDO (Sinais sem risco agudo)",
    }
    if avaliacao.requer_alerta_email:
        recibo_email = robo_email_rpa.disparar_alerta_email(avaliacao)

    with sqlite3.connect(CAMINHO_BANCO_SQLITE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO leituras_sinais_vitais (
                paciente_id, paciente_nome, medico_responsavel, timestamp_avaliacao,
                bpm, temperatura_c, umidade_pct, aceleracao_g, em_movimento,
                segundos_sem_movimento, nivel_risco, escore_gravidade,
                requer_alerta_email, anomalias_json, conduta_clinica_sugerida,
                email_disparado, status_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                avaliacao.paciente_id,
                avaliacao.paciente_nome,
                avaliacao.medico_responsavel,
                avaliacao.timestamp_avaliacao,
                avaliacao.bpm,
                avaliacao.temperatura_c,
                avaliacao.umidade_pct,
                avaliacao.aceleracao_g,
                1 if avaliacao.em_movimento else 0,
                avaliacao.segundos_sem_movimento,
                avaliacao.nivel_risco,
                avaliacao.escore_gravidade,
                1 if avaliacao.requer_alerta_email else 0,
                json.dumps(avaliacao.anomalias_detectadas, ensure_ascii=False),
                avaliacao.conduta_clinica_sugerida,
                1 if recibo_email.get("email_disparado") else 0,
                str(recibo_email.get("status_transporte")),
            ),
        )
        leitura_id = cursor.lastrowid
        conn.commit()

    return {
        "id_leitura": leitura_id,
        "mensagem": "Sinais vitais processados com sucesso pela API REST CardioIA.",
        "avaliacao_risco": avaliacao.para_dict(),
        "automacao_rpa_email": recibo_email,
    }


@app.get("/api/v1/sinais-vitais")
def consultar_sinais_vitais(
    paciente_id: Optional[str] = Query(default=None, description="Filtrar por ID do paciente"),
    nivel_risco: Optional[str] = Query(default=None, description="Filtrar por nível de risco"),
    limite: int = Query(default=50, ge=1, le=500, description="Quantidade máxima de registros"),
):
    """Consome (HTTP GET) o histórico de leituras de sinais vitais armazenadas."""
    query = "SELECT * FROM leituras_sinais_vitais WHERE 1=1"
    params: list = []

    if paciente_id:
        query += " AND paciente_id = ?"
        params.append(paciente_id.upper())
    if nivel_risco:
        query += " AND nivel_risco = ?"
        params.append(nivel_risco.upper())

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limite)

    with sqlite3.connect(CAMINHO_BANCO_SQLITE) as conn:
        conn.row_factory = sqlite3.Row
        linhas = conn.execute(query, params).fetchall()

    registros = []
    for l in linhas:
        registros.append({
            "id_leitura": l["id"],
            "paciente_id": l["paciente_id"],
            "paciente_nome": l["paciente_nome"],
            "medico_responsavel": l["medico_responsavel"],
            "timestamp": l["timestamp_avaliacao"],
            "bpm": l["bpm"],
            "temperatura_c": l["temperatura_c"],
            "umidade_pct": l["umidade_pct"],
            "aceleracao_g": l["aceleracao_g"],
            "em_movimento": bool(l["em_movimento"]),
            "segundos_sem_movimento": l["segundos_sem_movimento"],
            "nivel_risco": l["nivel_risco"],
            "escore_gravidade": l["escore_gravidade"],
            "requer_alerta_email": bool(l["requer_alerta_email"]),
            "anomalias_detectadas": json.loads(l["anomalias_json"]),
            "conduta_clinica_sugerida": l["conduta_clinica_sugerida"],
            "email_disparado": bool(l["email_disparado"]),
            "status_email": l["status_email"],
        })

    return {
        "total_retornado": len(registros),
        "leituras": registros,
    }


@app.get("/api/v1/alertas")
def consultar_alertas_ativos():
    """Consome (HTTP GET) exclusivamente os episódios de risco ALTO ou CRITICO."""
    with sqlite3.connect(CAMINHO_BANCO_SQLITE) as conn:
        conn.row_factory = sqlite3.Row
        linhas = conn.execute(
            "SELECT * FROM leituras_sinais_vitais WHERE requer_alerta_email = 1 ORDER BY id DESC"
        ).fetchall()

    alertas = [
        {
            "id_leitura": l["id"],
            "paciente_id": l["paciente_id"],
            "paciente_nome": l["paciente_nome"],
            "medico_responsavel": l["medico_responsavel"],
            "timestamp": l["timestamp_avaliacao"],
            "bpm": l["bpm"],
            "temperatura_c": l["temperatura_c"],
            "nivel_risco": l["nivel_risco"],
            "escore_gravidade": l["escore_gravidade"],
            "anomalias_detectadas": json.loads(l["anomalias_json"]),
            "conduta_clinica_sugerida": l["conduta_clinica_sugerida"],
            "status_email": l["status_email"],
        }
        for l in linhas
    ]
    return {
        "total_alertas": len(alertas),
        "alertas": alertas,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
