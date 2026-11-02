#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIAP - Faculdade de Informática e Administração Paulista
Projeto CardioIA - Fase 3 (Ir Além 1: Comunicação Automatizada com REST e E-mail)
Grupo: Data Health Solutions

Módulo: cliente_rest.py
-----------------------
Cliente REST em Python (biblioteca requests) para envio (POST) e recebimento/consumo
(GET) de sinais vitais na API REST CardioIA, demonstrando todo o fluxo de detecção
de riscos clínicos (taquicardia, febre, bradicardia, ausência de movimento) e disparo
automatizado de e-mails (RPA).
"""

import os
import socket
import sys
import threading
import time
from typing import Dict, List, Optional

import requests
import uvicorn

DIRETORIO_SRC = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_SRC not in sys.path:
    sys.path.insert(0, DIRETORIO_SRC)

from servidor_api import app

# Códigos ANSI para formatação visual no terminal
RESET = "\033[0m"
NEGRITO = "\033[1m"
AZUL = "\033[96m"
VERDE = "\033[92m"
AMARELO = "\033[93m"
VERMELHO = "\033[91m"
MAGENTA = "\033[95m"
CINZA = "\033[90m"


class ServidorSMTPLocalHomologacao(threading.Thread):
    """
    Servidor SMTP TCP leve embutido para capturar pacotes SMTP reais na porta 1025
    durante a execução da demonstração, garantindo que smtplib.SMTP execute todo o
    handshake (EHLO -> MAIL FROM -> RCPT TO -> DATA -> 250 OK) sem depender de internet.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 1025):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.rodando = True
        self.mensagens_recebidas = 0
        self._sock = None

    def run(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((self.host, self.port))
            self._sock.listen(5)
            self._sock.settimeout(0.5)
        except OSError:
            return

        while self.rodando:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with conn:
                conn.sendall(b"220 cardioia-smtp-local ESMTP Pronto\r\n")
                em_data = False
                buffer = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    if em_data:
                        if b"\r\n.\r\n" in buffer or b"\n.\n" in buffer:
                            self.mensagens_recebidas += 1
                            conn.sendall(b"250 2.0.0 OK Mensagem aceita para entrega RPA\r\n")
                            em_data = False
                            buffer = b""
                    else:
                        while b"\n" in buffer:
                            linha, buffer = buffer.split(b"\n", 1)
                            cmd = linha.strip().upper()
                            if cmd.startswith(b"EHLO") or cmd.startswith(b"HELO"):
                                conn.sendall(b"250-cardioia-smtp-local\r\n250 SIZE 10240000\r\n")
                            elif cmd.startswith(b"MAIL FROM") or cmd.startswith(b"RCPT TO"):
                                conn.sendall(b"250 2.1.0 OK\r\n")
                            elif cmd.startswith(b"DATA"):
                                conn.sendall(b"354 Envie o conteudo terminado com <CRLF>.<CRLF>\r\n")
                                em_data = True
                                break
                            elif cmd.startswith(b"QUIT"):
                                conn.sendall(b"221 2.0.0 Bye\r\n")
                                break
                            else:
                                conn.sendall(b"250 OK\r\n")

    def parar(self):
        self.rodando = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


class ClienteRESTCardioIA:
    """
    Cliente HTTP REST responsável por enviar (POST) e consumir (GET) dados de
    sinais vitais e alertas na API REST do sistema de monitoramento CardioIA.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.sessao = requests.Session()
        self.sessao.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CardioIA-Python-REST-Client/1.0",
        })

    def verificar_status_servidor(self) -> Dict[str, object]:
        """Consome GET /api/v1/health para validar conectividade com a API."""
        resp = self.sessao.get(f"{self.base_url}/api/v1/health", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def listar_pacientes(self) -> List[Dict[str, object]]:
        """Consome GET /api/v1/pacientes."""
        resp = self.sessao.get(f"{self.base_url}/api/v1/pacientes", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("pacientes", [])

    def enviar_sinais_vitais(self, leitura: Dict[str, object]) -> Dict[str, object]:
        """Envia uma leitura de sinais vitais via POST /api/v1/sinais-vitais."""
        resp = self.sessao.post(
            f"{self.base_url}/api/v1/sinais-vitais",
            json=leitura,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def consumir_sinais_vitais(
        self,
        paciente_id: Optional[str] = None,
        nivel_risco: Optional[str] = None,
        limite: int = 20,
    ) -> Dict[str, object]:
        """Consome GET /api/v1/sinais-vitais com suporte a filtros de consulta."""
        params: Dict[str, object] = {"limite": limite}
        if paciente_id:
            params["paciente_id"] = paciente_id
        if nivel_risco:
            params["nivel_risco"] = nivel_risco

        resp = self.sessao.get(
            f"{self.base_url}/api/v1/sinais-vitais",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def consumir_alertas_ativos(self) -> Dict[str, object]:
        """Consome GET /api/v1/alertas retornando apenas os episódios de risco elevado."""
        resp = self.sessao.get(f"{self.base_url}/api/v1/alertas", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()


def iniciar_api_em_background(host: str = "127.0.0.1", port: int = 8000):
    """Inicia o servidor FastAPI/Uvicorn em uma thread daemon caso a porta esteja livre."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    servidor = uvicorn.Server(config)
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    return servidor


def executar_simulacao_completa():
    """
    Executa o ciclo completo exigido no Ir Além 1:
      1. Sobe o receptor SMTP local (porta 1025) e a API REST (porta 8000).
      2. Envia (POST) 6 cenários clínicos cobrindo pacientes estáveis e emergências.
      3. Verifica o disparo automático de e-mail (RPA) nos casos de risco.
      4. Consome (GET) os sinais vitais e alertas armazenados na API REST.
    """
    print(f"{AZUL}{NEGRITO}=============================================================================={RESET}")
    print(f"{AZUL}{NEGRITO}   CARDIOIA - FASE 3 (IR ALÉM 1: CLIENTE/API REST + MOTOR DE RISCO + RPA)     {RESET}")
    print(f"{AZUL}{NEGRITO}   Grupo: Data Health Solutions - FIAP                                        {RESET}")
    print(f"{AZUL}{NEGRITO}=============================================================================={RESET}\n")

    smtp_local = ServidorSMTPLocalHomologacao(host="127.0.0.1", port=1025)
    smtp_local.start()

    servidor_uvicorn = iniciar_api_em_background(host="127.0.0.1", port=8000)
    time.sleep(1.2)

    cliente = ClienteRESTCardioIA(base_url="http://127.0.0.1:8000")

    status_api = cliente.verificar_status_servidor()
    print(f"{VERDE}✔ API REST Conectada:{RESET} {status_api['servico']} ({status_api['status']})")
    pacientes = cliente.listar_pacientes()
    print(f"{VERDE}✔ Pacientes Cadastrados (GET /api/v1/pacientes):{RESET} {len(pacientes)} pacientes ativos\n")

    cenarios_teste = [
        {
            "descricao": "Cenário 1 — Paciente em Repouso Domiciliar Estável",
            "payload": {
                "paciente_id": "PAC-001",
                "bpm": 74,
                "temperatura_c": 36.5,
                "umidade_pct": 54.0,
                "aceleracao_g": 1.04,
                "em_movimento": True,
                "segundos_sem_movimento": 0,
            },
        },
        {
            "descricao": "Cenário 2 — Atividade Leve / Elevação Moderada sem Alerta Crítico",
            "payload": {
                "paciente_id": "PAC-004",
                "bpm": 106,
                "temperatura_c": 37.2,
                "umidade_pct": 58.0,
                "aceleracao_g": 1.28,
                "em_movimento": True,
                "segundos_sem_movimento": 0,
            },
        },
        {
            "descricao": "Cenário 3 — Alerta de Taquicardia Isolada (> 120 BPM)",
            "payload": {
                "paciente_id": "PAC-001",
                "bpm": 134,
                "temperatura_c": 36.9,
                "umidade_pct": 60.0,
                "aceleracao_g": 1.12,
                "em_movimento": True,
                "segundos_sem_movimento": 0,
            },
        },
        {
            "descricao": "Cenário 4 — Alerta de Febre / Hipertermia (> 38.0 °C)",
            "payload": {
                "paciente_id": "PAC-005",
                "bpm": 96,
                "temperatura_c": 38.7,
                "umidade_pct": 63.5,
                "aceleracao_g": 1.02,
                "em_movimento": True,
                "segundos_sem_movimento": 0,
            },
        },
        {
            "descricao": "Cenário 5 — Alerta de Queda Brusca + Ausência Prolongada de Movimento",
            "payload": {
                "paciente_id": "PAC-003",
                "bpm": 46,
                "temperatura_c": 36.1,
                "umidade_pct": 76.0,
                "aceleracao_g": 2.45,
                "em_movimento": False,
                "segundos_sem_movimento": 210,
            },
        },
        {
            "descricao": "Cenário 6 — Emergência Combinada: Taquicardia Severa + Febre Alta + Imobilidade",
            "payload": {
                "paciente_id": "PAC-002",
                "bpm": 148,
                "temperatura_c": 39.2,
                "umidade_pct": 78.5,
                "aceleracao_g": 1.00,
                "em_movimento": False,
                "segundos_sem_movimento": 185,
            },
        },
    ]

    print(f"{NEGRITO}--- ETAPA 1: ENVIO DE SINAIS VITAIS VIA CLIENTE REST (HTTP POST) ---{RESET}")
    for idx, cenario in enumerate(cenarios_teste, 1):
        resposta = cliente.enviar_sinais_vitais(cenario["payload"])
        av = resposta["avaliacao_risco"]
        rpa = resposta["automacao_rpa_email"]

        cor_risco = (
            VERMELHO if av["nivel_risco"] in ("ALTO", "CRITICO")
            else (AMARELO if av["nivel_risco"] == "MODERADO" else VERDE)
        )

        print(f"\n{AZUL}{NEGRITO}▶ [{idx}/6] {cenario['descricao']}{RESET}")
        print(
            f"   Paciente: {NEGRITO}{av['paciente_nome']} ({av['paciente_id']}){RESET} | "
            f"Médico(a): {av['medico_responsavel']}"
        )
        str_mov = "SIM" if av["em_movimento"] else f"NÃO ({av['segundos_sem_movimento']}s imóvel)"
        print(
            f"   Sinais Enviados (POST): BPM={av['bpm']} | Temp={av['temperatura_c']}°C | "
            f"Umid={av['umidade_pct']}% | Accel={av['aceleracao_g']}G | "
            f"Movimento={str_mov}"
        )
        print(
            f"   Avaliação de Risco: {cor_risco}{NEGRITO}{av['nivel_risco']} "
            f"(Escore: {av['escore_gravidade']}/100){RESET}"
        )
        print(f"   Anomalias: {', '.join(av['anomalias_detectadas'])}")
        if rpa.get("email_disparado"):
            print(
                f"   {MAGENTA}{NEGRITO}✉ Automação RPA E-mail:{RESET} ENVIADO para <{rpa['destinatario']}> "
                f"[{rpa['status_transporte']}]"
            )
            print(f"   {CINZA}↳ Evidência HTML salva em: {os.path.basename(rpa['arquivo_html'])}{RESET}")
        else:
            print(f"   {CINZA}✉ Automação RPA E-mail: Não acionado ({rpa['status_transporte']}){RESET}")

    print(f"\n{NEGRITO}--- ETAPA 2: CONSUMO DE DADOS E AUDITORIA VIA CLIENTE REST (HTTP GET) ---{RESET}")
    historico = cliente.consumir_sinais_vitais(limite=10)
    alertas = cliente.consumir_alertas_ativos()

    print(f"{VERDE}✔ GET /api/v1/sinais-vitais:{RESET} {historico['total_retornado']} leituras recuperadas com sucesso.")
    print(f"{VERMELHO}✔ GET /api/v1/alertas:{RESET} {alertas['total_alertas']} alertas críticos/altos registrados e auditados.")
    print(f"{MAGENTA}✔ Pacotes SMTP entregues ao servidor local (127.0.0.1:1025):{RESET} {smtp_local.mensagens_recebidas} e-mails MIME.")

    servidor_uvicorn.should_exit = True
    smtp_local.parar()
    print(f"\n{VERDE}{NEGRITO}Simulação concluída com sucesso!{RESET}")


if __name__ == "__main__":
    executar_simulacao_completa()
