#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIAP - Projeto CardioIA (Fase 3 - Parte 2)
Grupo: Data Health Solutions

Simulador Python de Telemetria MQTT do ESP32 (Wearable CardioIA)
----------------------------------------------------------------
Permite testar a Dashboard do Node-RED em tempo real enviando exatamente os
mesmos payloads JSON e tópicos publicados pelo firmware C++ do ESP32 no Wokwi.
Suporta simulação de estados Normais, Alertas Clínicos (Taquicardia + Febre)
e Resiliência Offline (SPIFFS -> Sincronização em Lote).
"""

import argparse
import json
import math
import random
import time
import paho.mqtt.client as mqtt

TOPICO_TELEMETRIA = "cardioia/fase3/telemetria"
TOPICO_ALERTAS = "cardioia/fase3/alertas"
TOPICO_BPM = "cardioia/fase3/bpm"
TOPICO_TEMPERATURA = "cardioia/fase3/temperatura"
TOPICO_UMIDADE = "cardioia/fase3/umidade"
TOPICO_STATUS = "cardioia/fase3/status"


def gerar_amostra(seq: int, modo: str = "ciclo") -> dict:
    """Gera uma leitura fisiológica realista para a paciente Ana Beatriz Souza."""
    if modo == "normal" or (modo == "ciclo" and (seq % 16) < 10):
        bpm = int(74 + 12 * math.sin(seq * 0.4) + random.randint(-3, 3))
        temperatura = round(36.5 + 0.3 * math.sin(seq * 0.25) + random.uniform(-0.1, 0.1), 1)
        umidade = round(54.0 + 3.0 * math.cos(seq * 0.2), 1)
        aceleracao = round(1.04 + random.uniform(-0.08, 0.18), 2)
        em_movimento = True
    else:
        # Simula episódio agudo de Taquicardia + Febre / Imobilidade
        bpm = random.randint(128, 152)
        temperatura = round(random.uniform(38.3, 39.2), 1)
        umidade = round(random.uniform(62.0, 68.5), 1)
        aceleracao = round(random.uniform(0.98, 1.02), 2)
        em_movimento = False

    taquicardia = bpm > 120
    bradicardia = bpm < 50
    febre = temperatura > 38.0
    hipotermia = temperatura < 35.0

    alerta_critico = False
    nivel_risco = "BAIXO"
    diagnostico = "SINAIS_ESTAVEIS"

    if taquicardia and febre:
        alerta_critico = True
        nivel_risco = "CRITICO"
        diagnostico = "ALERTA_COMBINADO_TAQUICARDIA_E_FEBRE"
    elif taquicardia:
        alerta_critico = True
        nivel_risco = "ALTO"
        diagnostico = "ALERTA_TAQUICARDIA_ACIMA_120BPM"
    elif bradicardia:
        alerta_critico = True
        nivel_risco = "ALTO"
        diagnostico = "ALERTA_BRADICARDIA_ABAIXO_50BPM"
    elif febre:
        alerta_critico = True
        nivel_risco = "ALTO"
        diagnostico = "ALERTA_FEBRE_ACIMA_38C"
    elif hipotermia:
        alerta_critico = True
        nivel_risco = "ALTO"
        diagnostico = "ALERTA_HIPOTERMIA_ABAIXO_35C"

    return {
        "paciente_id": "PAC-001",
        "paciente": "Ana Beatriz Souza",
        "seq": seq,
        "timestamp_ms": seq * 3000,
        "temperatura_c": temperatura,
        "umidade_pct": umidade,
        "bpm": bpm,
        "aceleracao_g": aceleracao,
        "em_movimento": em_movimento,
        "alerta_critico": alerta_critico,
        "nivel_risco": nivel_risco,
        "diagnostico_borda": diagnostico,
        "origem_envio": "TEMPO_REAL",
    }


def publicar_amostra(client: mqtt.Client, amostra: dict) -> None:
    payload = json.dumps(amostra, ensure_ascii=False)
    client.publish(TOPICO_TELEMETRIA, payload, qos=0)
    client.publish(TOPICO_BPM, str(amostra["bpm"]), qos=0)
    client.publish(TOPICO_TEMPERATURA, f"{amostra['temperatura_c']:.1f}", qos=0)
    client.publish(TOPICO_UMIDADE, f"{amostra['umidade_pct']:.1f}", qos=0)
    if amostra["alerta_critico"]:
        client.publish(TOPICO_ALERTAS, payload, qos=0)
    print(f"[MQTT -> {TOPICO_TELEMETRIA}] {payload}")


def main():
    parser = argparse.ArgumentParser(description="Simulador MQTT do ESP32 CardioIA")
    parser.add_argument("--broker", default="broker.hivemq.com", help="Endereço do Broker MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Porta do Broker MQTT")
    parser.add_argument("--modo", choices=["ciclo", "normal", "alerta"], default="ciclo")
    parser.add_argument("--amostras", type=int, default=0, help="Total de amostras (0 = contínuo)")
    parser.add_argument("--intervalo", type=float, default=2.0, help="Segundos entre envios")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"CardioIA-Sim-{random.randint(1000,9999)}")
    print(f"Conectando ao broker MQTT {args.broker}:{args.port}...")
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()
    client.publish(TOPICO_STATUS, json.dumps({"status": "ONLINE", "paciente_id": "PAC-001"}), retain=True)

    seq = 1
    try:
        while args.amostras == 0 or seq <= args.amostras:
            amostra = gerar_amostra(seq, args.modo)
            publicar_amostra(client, amostra)
            seq += 1
            if args.amostras == 0 or seq <= args.amostras:
                time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nSimulação encerrada pelo usuário.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
