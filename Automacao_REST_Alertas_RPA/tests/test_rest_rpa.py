#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes Automatizados (Pytest) para o módulo Ir Além 1:
API REST, Cliente REST, Motor de Detecção de Riscos e Automação de E-mail (RPA).
"""

import os
import sys
from fastapi.testclient import TestClient

DIRETORIO_TESTS = os.path.dirname(os.path.abspath(__file__))
DIRETORIO_SRC = os.path.join(os.path.dirname(DIRETORIO_TESTS), "src")
if DIRETORIO_SRC not in sys.path:
    sys.path.insert(0, DIRETORIO_SRC)

from motor_risco import AvaliadorRiscoCardioIA
from servidor_api import app

client = TestClient(app)
avaliador = AvaliadorRiscoCardioIA()


def test_avaliador_sinais_normais():
    res = avaliador.avaliar_sinais_vitais({
        "paciente_id": "PAC-001",
        "bpm": 75,
        "temperatura_c": 36.5,
        "umidade_pct": 55.0,
        "aceleracao_g": 1.02,
        "em_movimento": True,
        "segundos_sem_movimento": 0,
    })
    assert res.nivel_risco == "BAIXO"
    assert res.requer_alerta_email is False
    assert res.escore_gravidade == 0


def test_avaliador_taquicardia_e_febre():
    res = avaliador.avaliar_sinais_vitais({
        "paciente_id": "PAC-002",
        "bpm": 142,
        "temperatura_c": 38.9,
        "umidade_pct": 65.0,
        "aceleracao_g": 1.00,
        "em_movimento": False,
        "segundos_sem_movimento": 180,
    })
    assert res.nivel_risco == "CRITICO"
    assert res.requer_alerta_email is True
    assert res.escore_gravidade >= 80
    assert any("Taquicardia" in a for a in res.anomalias_detectadas)
    assert any("Febre" in a for a in res.anomalias_detectadas)
    assert any("Ausência Prolongada de Movimento" in a for a in res.anomalias_detectadas)


def test_endpoints_rest_post_e_get():
    # 1. Verifica healthcheck
    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ONLINE"

    # 2. Envia leitura crítica via POST
    r_post = client.post(
        "/api/v1/sinais-vitais",
        json={
            "paciente_id": "PAC-001",
            "bpm": 136,
            "temperatura_c": 38.6,
            "umidade_pct": 64.0,
            "aceleracao_g": 1.00,
            "em_movimento": False,
            "segundos_sem_movimento": 150,
        },
    )
    assert r_post.status_code == 201
    dados_post = r_post.json()
    assert dados_post["avaliacao_risco"]["nivel_risco"] == "CRITICO"
    assert dados_post["automacao_rpa_email"]["email_disparado"] is True
    assert os.path.exists(dados_post["automacao_rpa_email"]["arquivo_html"])

    # 3. Consome leituras via GET
    r_get = client.get("/api/v1/sinais-vitais", params={"paciente_id": "PAC-001"})
    assert r_get.status_code == 200
    assert r_get.json()["total_retornado"] >= 1

    # 4. Consome alertas via GET
    r_alertas = client.get("/api/v1/alertas")
    assert r_alertas.status_code == 200
    assert r_alertas.json()["total_alertas"] >= 1
