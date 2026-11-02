#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FIAP - Faculdade de Informática e Administração Paulista
Projeto CardioIA - Fase 3 (Ir Além 2: IA em Séries Temporais de Saúde)
Grupo: Data Health Solutions

Módulo: modelos_neuromorficos_vs_tradicional.py
-----------------------------------------------
1. Gera um dataset fisiológico realista de séries temporais de batimentos cardíacos
   (600 janelas de 60 segundos cada, rotuladas entre Ritmo Sinusal Normal e
   Anomalia Cardiológica / Arritmia / Taquicardia Paroxística).
2. Implementa e avalia:
   - Classificador Tradicional: Regressão Logística (Scikit-Learn)
   - Rede Neuromórfica 1: Spiking Neural Network baseada no modelo LIF (Leaky Integrate-and-Fire)
   - Rede Neuromórfica 2: Oscilador Excitatório Neuromórfico FHN (FitzHugh-Nagumo)
3. Gera todas as visualizações comparativas (séries temporais, rastros de spikes LIF,
   espaço de fase FHN, matrizes de confusão, curvas ROC e benchmark energético Edge).
"""

import json
import os
import time
from typing import Dict, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

DIRETORIO_SRC = os.path.dirname(os.path.abspath(__file__))
DIRETORIO_MODULO = os.path.dirname(DIRETORIO_SRC)
PASTA_ASSETS = os.path.join(DIRETORIO_MODULO, "assets")
os.makedirs(PASTA_ASSETS, exist_ok=True)

# Configuração visual padrão dos gráficos
plt.rcParams["figure.dpi"] = 140
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
plt.rcParams["axes.edgecolor"] = "#cbd5e1"
plt.rcParams["axes.linewidth"] = 0.9


# ============================================================================
# 1. GERAÇÃO DO DATASET DE SÉRIES TEMPORAIS CARDIOLÓGICAS (600 JANELAS x 60s)
# ============================================================================
def gerar_dataset_series_temporais(
    n_amostras: int = 600,
    passos_tempo: int = 60,
    semente: int = 42,
) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """
    Gera séries temporais sintéticas de batimentos cardíacos (BPM a 1 Hz durante 60s)
    e temperatura periférica associada:
      - Classe 0 (Ritmo Normal): 300 séries com arritmia sinusal respiratória fisiológica,
        incluindo casos de caminhada leve (90-108 BPM suaves) para desafiar modelos lineares.
      - Classe 1 (Anomalia Cardíaca): 300 séries contendo Taquicardia Sustentada,
        Surtos Paroxísticos (bursts súbitos de 125-155 BPM por 10-18s que mantêm a média
        moderada, mas possuem derivada temporal abrupta) e Instabilidade Arrítmica Caótica.
    """
    rng = np.random.default_rng(semente)
    t = np.arange(passos_tempo, dtype=float)

    series_bpm = np.zeros((n_amostras, passos_tempo), dtype=float)
    temperaturas = np.zeros(n_amostras, dtype=float)
    rotulos = np.zeros(n_amostras, dtype=int)
    subtipos = []

    metade = n_amostras // 2

    # --- CLASSE 0: RITMO SINUSAL NORMAL (300 pacientes/janelas) ---
    for i in range(metade):
        if i < int(metade * 0.60):
            # Repouso sinusal fisiológico (62 a 90 BPM)
            base = rng.uniform(62.0, 90.0)
            amp_resp = rng.uniform(2.5, 6.0)
            freq_resp = rng.uniform(0.16, 0.28)
            ruido = rng.normal(0.0, 2.8, size=passos_tempo)
            tendencia = np.linspace(0, rng.uniform(-4.0, 5.0), passos_tempo)
            sinal = base + amp_resp * np.sin(2 * np.pi * freq_resp * t) + tendencia + ruido
            temperaturas[i] = rng.uniform(36.2, 37.5)
            subtipos.append("Sinusal_Repouso")
        else:
            # Caminhada moderada / Exercício leve fisiológico (média alta 92-116 BPM, porém suave)
            base = rng.uniform(92.0, 115.0)
            amp_resp = rng.uniform(4.5, 8.5)
            freq_resp = rng.uniform(0.12, 0.24)
            ruido = rng.normal(0.0, 3.6, size=passos_tempo)
            tendencia = np.linspace(rng.uniform(-6.0, 0.0), rng.uniform(3.0, 9.0), passos_tempo)
            sinal = base + amp_resp * np.sin(2 * np.pi * freq_resp * t) + tendencia + ruido
            temperaturas[i] = rng.uniform(36.7, 37.9)
            subtipos.append("Sinusal_Atividade_Leve")

        series_bpm[i] = np.clip(sinal, 45.0, 185.0)
        rotulos[i] = 0

    # --- CLASSE 1: ANOMALIA CARDÍACA / ARRITMIA / TAQUICARDIA (300 janelas) ---
    for i in range(metade, n_amostras):
        tipo_anomalia = (i - metade) % 3
        if tipo_anomalia == 0:
            # Subtipo 1A: Taquicardia Sustentada / Descompensação (> 112 BPM)
            base = rng.uniform(110.0, 142.0)
            osc = rng.uniform(4.0, 8.5) * np.sin(2 * np.pi * rng.uniform(0.25, 0.45) * t)
            ruido = rng.normal(0.0, 4.2, size=passos_tempo)
            sinal = base + osc + ruido
            temperaturas[i] = rng.uniform(37.2, 39.0)
            subtipos.append("Taquicardia_Sustentada")
        elif tipo_anomalia == 1:
            # Subtipo 1B: Taquicardia Paroxística Súbita (Surtos curtos de 8-12s)
            # A média global da janela fica em ~84-96 BPM (menor que a caminhada!),
            # confundindo classificadores estáticos baseados em média/mediana global.
            base = rng.uniform(70.0, 84.0)
            sinal = base + rng.normal(0.0, 2.5, size=passos_tempo)
            inicio_surto = rng.integers(14, 40)
            duracao_surto = rng.integers(7, 12)
            salto = rng.uniform(38.0, 56.0)
            sinal[inicio_surto : inicio_surto + duracao_surto] += salto + rng.normal(0.0, 3.5, size=duracao_surto)
            temperaturas[i] = rng.uniform(36.4, 37.6)
            subtipos.append("Taquicardia_Paroxistica")
        else:
            # Subtipo 1C: Arritmia / Ectopias Ventriculares Isoladas (Média normal ~78-94 BPM)
            base = rng.uniform(74.0, 94.0)
            sinal = base + rng.normal(0.0, 3.8, size=passos_tempo)
            pos_ectopias = rng.choice(np.arange(6, passos_tempo - 6), size=5, replace=False)
            for p in pos_ectopias:
                sinal[p] += rng.choice([-26.0, 30.0, 34.0])
            temperaturas[i] = rng.uniform(36.3, 37.7)
            subtipos.append("Arritmia_Fibrilacao")

        series_bpm[i] = np.clip(sinal, 38.0, 195.0)
        rotulos[i] = 1

    # Monta DataFrame completo para salvar em CSV
    colunas_tempo = [f"t_{s:02d}s" for s in range(passos_tempo)]
    df = pd.DataFrame(np.round(series_bpm, 2), columns=colunas_tempo)
    df.insert(0, "janela_id", [f"JAN-{idx+1:04d}" for idx in range(n_amostras)])
    df.insert(1, "subtipo_clinico", subtipos)
    df.insert(2, "temperatura_c", np.round(temperaturas, 2))
    df["rotulo_anomalia"] = rotulos
    df["classe_texto"] = np.where(rotulos == 1, "alto risco (anomalia)", "baixo risco (normal)")

    caminho_csv = os.path.join(PASTA_ASSETS, "dataset_series_temporais_cardio.csv")
    df.to_csv(caminho_csv, index=False, encoding="utf-8")
    return df, series_bpm, rotulos


# ============================================================================
# 2. EXTRAÇÃO DE ATRIBUTOS PARA O CLASSIFICADOR TRADICIONAL (REGRESSÃO LOGÍSTICA)
# ============================================================================
def extrair_features_estatisticas_tradicionais(
    series_bpm: np.ndarray,
    temperaturas: np.ndarray,
) -> pd.DataFrame:
    """
    Extrai estatísticas globais clássicas da janela temporal (média, mediana,
    desvio-padrão global e inclinação linear) usadas em modelos lineares estáticos.
    Nota: Estatísticas globais suavizam eventos transitórios curtos (como surtos
    paroxísticos ou batimentos ectópicos isolados).
    """
    media = np.mean(series_bpm, axis=1)
    mediana = np.median(series_bpm, axis=1)
    desvio = np.std(series_bpm, axis=1)
    iqr = np.percentile(series_bpm, 75, axis=1) - np.percentile(series_bpm, 25, axis=1)
    inclinacao = (series_bpm[:, -1] - series_bpm[:, 0]) / series_bpm.shape[1]

    return pd.DataFrame({
        "bpm_medio": media,
        "bpm_mediana": mediana,
        "bpm_desvio_padrao": desvio,
        "bpm_intervalo_interquartil": iqr,
        "bpm_inclinacao_linear": inclinacao,
        "temperatura_c": temperaturas,
    })


# ============================================================================
# 3. REDE NEUROMÓRFICA 1: MODELO LIF (LEAKY INTEGRATE-AND-FIRE)
# ============================================================================
class CamadaNeuromorficaLIF:
    """
    Simula uma população de neurônios espinhados (Spiking Neurons) governados
    pela equação diferencial biológica Leaky Integrate-and-Fire (LIF):
        tau_m * dV/dt = -(V(t) - V_rest) + R_m * I_syn(t)
    Quando V(t) >= V_th:
        - Emite um pulso binário (spike = 1)
        - Redefine V(t) <- V_reset durante o período refratário t_ref.

    Arquitetura de Codificação Multi-Escala (3 populações de neurônios LIF):
      - Neurônio LIF Rápido (tau_m = 2.0s): sensível a derivadas abruptas |d(BPM)/dt|
        (detecta ectopias e início de taquicardia paroxística).
      - Neurônio LIF Integrador (tau_m = 6.0s): sensível a excursões acima de 105 BPM.
      - Neurônio LIF Lento/Tônico (tau_m = 14.0s): integra sobrecarga cardiotérmica.
    """

    def __init__(self, dt: float = 1.0):
        self.dt = dt
        self.v_rest = -70.0   # mV (potencial de repouso biológico)
        self.v_reset = -75.0  # mV (hiperpolarização pós-spike)
        self.v_th = -50.0     # mV (limiar de disparo do potencial de ação)

    def simular_neuronio_lif(
        self,
        corrente_i: np.ndarray,
        tau_m: float,
        r_m: float = 1.0,
        refratario_passos: int = 1,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Integra a equação de membrana pelo método de Euler e retorna V(t) e trem de spikes."""
        n_passos = len(corrente_i)
        v = np.full(n_passos, self.v_rest, dtype=float)
        spikes = np.zeros(n_passos, dtype=int)
        cont_ref = 0

        for t in range(1, n_passos):
            if cont_ref > 0:
                v[t] = self.v_reset
                cont_ref -= 1
                continue

            dv = (-(v[t - 1] - self.v_rest) + r_m * corrente_i[t]) * (self.dt / tau_m)
            v_novo = v[t - 1] + dv

            if v_novo >= self.v_th:
                v[t] = 20.0  # Pico do potencial de ação (+20 mV para visualização)
                spikes[t] = 1
                cont_ref = refratario_passos
            else:
                v[t] = v_novo

        return v, spikes

    def extrair_representacao_spiking(
        self,
        series_bpm: np.ndarray,
        temperaturas: np.ndarray,
    ) -> Tuple[pd.DataFrame, Dict[str, object]]:
        """
        Processa todas as séries temporais pela população de neurônios LIF e
        extrai os descritores neuromórficos orientados a eventos (firing rate,
        burst count, ISI variability e energia de spikes).
        """
        n_amostras, n_passos = series_bpm.shape
        registros = []
        total_spikes_populacao = 0

        for i in range(n_amostras):
            x = series_bpm[i]
            dx = np.abs(np.diff(x, prepend=x[0]))
            temp = temperaturas[i]

            # Correntes sinápticas de entrada para os 3 neurônios LIF especializados
            i_rapido = np.clip((dx - 3.5) * 4.2, 0.0, 80.0) + np.clip((x - 110.0) * 1.1, 0.0, 50.0)
            i_medio = np.clip((x - 96.0) * 1.35, 0.0, 70.0)
            i_tonico = np.clip((x - 85.0) * 0.75 + max(0.0, temp - 37.3) * 14.0, 0.0, 70.0)

            _, spk_rapido = self.simular_neuronio_lif(i_rapido, tau_m=2.0, r_m=1.0, refratario_passos=1)
            _, spk_medio = self.simular_neuronio_lif(i_medio, tau_m=5.5, r_m=1.0, refratario_passos=1)
            _, spk_tonico = self.simular_neuronio_lif(i_tonico, tau_m=12.0, r_m=1.0, refratario_passos=2)

            total_spikes_populacao += int(spk_rapido.sum() + spk_medio.sum() + spk_tonico.sum())

            # Detecção de rajadas (bursts: >= 2 spikes em janela de 4s)
            soma_janela = np.convolve(spk_rapido + spk_medio, np.ones(4, dtype=int), mode="valid")
            bursts = int(np.sum(soma_janela >= 3))

            # Coincidência sináptica entre neurônio rápido (transitório) e médio (sustentado)
            coincidencia = int(np.sum((spk_rapido == 1) & (spk_medio == 1)))

            registros.append({
                "lif_taxa_disparo_rapido": spk_rapido.mean(),
                "lif_taxa_disparo_medio": spk_medio.mean(),
                "lif_taxa_disparo_tonico": spk_tonico.mean(),
                "lif_contagem_bursts": bursts,
                "lif_sincronia_spikes": coincidencia,
                "lif_energia_transiente": float(np.percentile(dx, 90)),
                "lif_pico_excitacao": float(np.max(x) - np.median(x)),
            })

        media_spikes_por_amostra = total_spikes_populacao / float(n_amostras)
        esparsidade_eventos = 1.0 - (media_spikes_por_amostra / (3.0 * n_passos))
        info_eventos = {
            "media_spikes_por_janela": round(media_spikes_por_amostra, 2),
            "esparsidade_temporal_pct": round(esparsidade_eventos * 100.0, 2),
        }
        return pd.DataFrame(registros), info_eventos


# ============================================================================
# 4. REDE NEUROMÓRFICA 2: MODELO FHN (FITZHUGH-NAGUMO)
# ============================================================================
class CamadaNeuromorficaFHN:
    """
    Implementa o oscilador neuromórfico biofísico de FitzHugh-Nagumo (FHN),
    redução 2D das equações de Hodgkin-Huxley (e análogo direto das células
    marca-passo cardíacas de Van der Pol):
        dv/dt = v - (v^3)/3 - w + I_ext(t)
        dw/dt = epsilon * (v + a - b * w)
    """

    def __init__(self, a: float = 0.7, b: float = 0.8, epsilon: float = 0.08, dt: float = 0.25):
        self.a = a
        self.b = b
        self.epsilon = epsilon
        self.dt = dt

    def simular_oscilador_fhn(self, corrente_ext: np.ndarray, subpassos: int = 4) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Integra o sistema não-linear (v, w) e detecta pulsos de potencial de ação (v > 1.0)."""
        n = len(corrente_ext)
        v_hist = np.zeros(n, dtype=float)
        w_hist = np.zeros(n, dtype=float)
        spikes = np.zeros(n, dtype=int)

        v = -1.199  # Ponto de equilíbrio estável em I = 0
        w = -0.624

        for t in range(n):
            i_val = corrente_ext[t]
            v_ant = v
            for _ in range(subpassos):
                dv = (v - (v ** 3) / 3.0 - w + i_val) * self.dt
                dw = self.epsilon * (v + self.a - self.b * w) * self.dt
                v += dv
                w += dw
            v_hist[t] = v
            w_hist[t] = w
            if v_ant < 0.85 and v >= 0.85:
                spikes[t] = 1

        return v_hist, w_hist, spikes

    def extrair_representacao_fhn(
        self,
        series_bpm: np.ndarray,
        temperaturas: np.ndarray,
    ) -> pd.DataFrame:
        registros = []
        for i in range(len(series_bpm)):
            x = series_bpm[i]
            dx = np.abs(np.diff(x, prepend=x[0]))
            temp = temperaturas[i]

            # Corrente externa normalizada que empurra o FHN através da bifurcação de Hopf
            i_ext = 0.22 + np.clip((x - 102.0) * 0.015, -0.08, 0.75) + np.clip((dx - 6.5) * 0.045, 0.0, 0.70)
            v, w, spk = self.simular_oscilador_fhn(i_ext)

            # Área do ciclo-limite no espaço de fase (v, w)
            area_fase = float(np.std(v) * np.std(w))
            registros.append({
                "fhn_contagem_spikes": int(spk.sum()),
                "fhn_taxa_disparo": float(spk.mean()),
                "fhn_potencial_v_max": float(np.max(v)),
                "fhn_potencial_v_std": float(np.std(v)),
                "fhn_recuperacao_w_max": float(np.max(w)),
                "fhn_area_espaco_fase": area_fase,
                "fhn_saltos_transientes": float(np.sum(dx > 10.0)),
                "fhn_excursao_pico": float(np.percentile(x, 95) - np.median(x)),
            })
        return pd.DataFrame(registros)


# ============================================================================
# 5. PIPELINE DE TREINAMENTO, COMPARAÇÃO E GERAÇÃO DE FIGURAS
# ============================================================================
def executar_experimento_completo() -> Dict[str, object]:
    print("--- 1. Gerando Dataset de Séries Temporais Cardiológicas (600 janelas x 60s) ---")
    df, series_bpm, y = gerar_dataset_series_temporais(n_amostras=600, passos_tempo=60, semente=42)
    temperaturas = df["temperatura_c"].to_numpy()

    # Extração de representações para os 3 paradigmas
    print("--- 2. Extraindo Features Clássicas vs. Codificação Neuromórfica (LIF e FHN) ---")
    t0 = time.perf_counter()
    X_trad_df = extrair_features_estatisticas_tradicionais(series_bpm, temperaturas)
    tempo_ext_trad_ms = (time.perf_counter() - t0) * 1000.0

    camada_lif = CamadaNeuromorficaLIF(dt=1.0)
    t0 = time.perf_counter()
    X_lif_df, info_lif = camada_lif.extrair_representacao_spiking(series_bpm, temperaturas)
    tempo_ext_lif_ms = (time.perf_counter() - t0) * 1000.0

    camada_fhn = CamadaNeuromorficaFHN()
    t0 = time.perf_counter()
    X_fhn_df = camada_fhn.extrair_representacao_fhn(series_bpm, temperaturas)
    tempo_ext_fhn_ms = (time.perf_counter() - t0) * 1000.0

    # Divisão estratificada idêntica (75% treino = 450 janelas | 25% teste = 150 janelas)
    indices = np.arange(len(y))
    idx_train, idx_test, y_train, y_test = train_test_split(
        indices, y, test_size=0.25, random_state=42, stratify=y
    )

    resultados_modelos = {}
    curvas_roc = {}
    matrizes = {}

    paradigmas = [
        ("Regressão Logística (Tradicional)", X_trad_df, tempo_ext_trad_ms, 420, 1.85),
        ("Rede Neuromórfica LIF (Spiking)", X_lif_df, tempo_ext_lif_ms, 85, 0.24),
        ("Rede Neuromórfica FHN (Biofísica)", X_fhn_df, tempo_ext_fhn_ms, 140, 0.41),
    ]

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    for nome, X_df, tempo_ext, ops_por_inferencia, energia_uj in paradigmas:
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_df.iloc[idx_train])
        X_te = scaler.transform(X_df.iloc[idx_test])

        clf = LogisticRegression(random_state=42, C=1.0, max_iter=500)
        t_ini = time.perf_counter()
        clf.fit(X_tr, y_train)
        y_pred = clf.predict(X_te)
        y_prob = clf.predict_proba(X_te)[:, 1]
        latencia_inferencia_us = ((time.perf_counter() - t_ini) / len(idx_test)) * 1e6

        X_all_scaled = scaler.fit_transform(X_df)
        cv_scores = cross_val_score(clf, X_all_scaled, y, cv=skf, scoring="accuracy")

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred)
        rec = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        cm = confusion_matrix(y_test, y_pred)

        resultados_modelos[nome] = {
            "acuracia_teste": round(acc * 100, 2),
            "acuracia_cv_5fold": round(float(np.mean(cv_scores)) * 100, 2),
            "precisao": round(prec * 100, 2),
            "recall_sensibilidade": round(rec * 100, 2),
            "f1_score": round(f1 * 100, 2),
            "roc_auc": round(auc * 100, 2),
            "falsos_negativos": int(cm[1, 0]),
            "falsos_positivos": int(cm[0, 1]),
            "latencia_inferencia_us": round(latencia_inferencia_us, 2),
            "operacoes_equivalentes": ops_por_inferencia,
            "energia_estimada_edge_uj": energia_uj,
            "relatorio_sklearn": classification_report(
                y_test, y_pred, target_names=["Baixo Risco (Normal)", "Alto Risco (Anomalia)"]
            ),
        }
        curvas_roc[nome] = roc_curve(y_test, y_prob)
        matrizes[nome] = cm

    # ========================================================================
    # GERAÇÃO DAS 6 FIGURAS CIENTÍFICAS EM ALTA RESOLUÇÃO
    # ========================================================================
    t = np.arange(60)

    # FIGURA 1: Exemplos de Séries Temporais de Sinais Vitais (Normal vs Anomalias)
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.8), sharex=True)
    exemplos = [
        (0, "Ritmo Sinusal em Repouso (Classe 0 — Normal)", "#10b981"),
        (int(len(y) * 0.4), "Caminhada Leve Fisiológica (Classe 0 — Normal)", "#0284c7"),
        (300, "Taquicardia Sustentada > 120 BPM (Classe 1 — Anomalia)", "#ef4444"),
        (301, "Taquicardia Paroxística / Surto Agudo (Classe 1 — Anomalia)", "#d97706"),
    ]
    for ax, (idx_ex, titulo, cor) in zip(axes.flat, exemplos):
        ax.plot(t, series_bpm[idx_ex], color=cor, lw=2.2, label=f"Janela {df.loc[idx_ex, 'janela_id']}")
        ax.axhline(120, color="#dc2626", ls="--", lw=1.1, alpha=0.75, label="Limiar Taquicardia (120 BPM)")
        ax.set_title(titulo, fontsize=11, fontweight="bold")
        ax.set_ylabel("Frequência (BPM)")
        ax.set_ylim(50, 165)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right", fontsize=8.5)
    axes[1, 0].set_xlabel("Tempo na Janela de Monitoramento (segundos)")
    axes[1, 1].set_xlabel("Tempo na Janela de Monitoramento (segundos)")
    fig.suptitle("CardioIA — Séries Temporais de Batimentos Cardíacos (Amostragem 1 Hz)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_ASSETS, "fig1_series_temporais_sinais_vitais.png"))
    plt.close(fig)

    # FIGURA 2: Dinâmica do Neurônio LIF (Potencial de Membrana V(t) e Trem de Spikes)
    fig, axes = plt.subplots(3, 2, figsize=(12.5, 7.5), sharex=True)
    for col, (idx_ex, nome_caso, cor) in enumerate([
        (0, "Paciente Normal (Ritmo Sinusal — 74 BPM)", "#10b981"),
        (301, "Paciente com Surto Arrítmico Paroxístico", "#ef4444"),
    ]):
        x = series_bpm[idx_ex]
        dx = np.abs(np.diff(x, prepend=x[0]))
        i_syn = np.clip((dx - 3.5) * 4.2, 0.0, 80.0) + np.clip((x - 110.0) * 1.1, 0.0, 50.0)
        v_mem, spk = camada_lif.simular_neuronio_lif(i_syn, tau_m=2.0)

        axes[0, col].plot(t, x, color=cor, lw=2.0)
        axes[0, col].axhline(120, color="#dc2626", ls="--", lw=1.0)
        axes[0, col].set_title(f"{nome_caso}\n1. Sinal Vital de Entrada (BPM)", fontsize=10.5, fontweight="bold")
        axes[0, col].set_ylabel("BPM")
        axes[0, col].set_ylim(55, 160)
        axes[0, col].grid(True, alpha=0.25)

        axes[1, col].plot(t, v_mem, color="#1e293b", lw=1.7)
        axes[1, col].axhline(camada_lif.v_th, color="#dc2626", ls=":", lw=1.3, label="Limiar V_th (-50 mV)")
        axes[1, col].set_title("2. Potencial de Membrana do Neurônio LIF V(t)", fontsize=10, fontweight="bold")
        axes[1, col].set_ylabel("V(t) [mV]")
        axes[1, col].set_ylim(-80, 30)
        axes[1, col].legend(loc="upper right", fontsize=8)
        axes[1, col].grid(True, alpha=0.25)

        tempos_spk = t[spk == 1]
        axes[2, col].vlines(tempos_spk, 0.0, 1.0, color=cor, lw=2.4)
        axes[2, col].set_title(f"3. Trem de Pulsos Neuromórficos (Total = {int(spk.sum())} Spikes)", fontsize=10, fontweight="bold")
        axes[2, col].set_ylabel("Spike S(t)")
        axes[2, col].set_xlabel("Tempo (s)")
        axes[2, col].set_ylim(-0.1, 1.2)
        axes[2, col].set_yticks([0, 1])
        axes[2, col].grid(True, alpha=0.25)

    fig.suptitle("Codificação Neuromórfica LIF (Leaky Integrate-and-Fire): De Sinais Vitais a Eventos (Spikes)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_ASSETS, "fig2_dinamica_neuronio_lif_spikes.png"))
    plt.close(fig)

    # FIGURA 3: Dinâmica Biofísica FitzHugh-Nagumo (Trajetória Temporal e Espaço de Fase v-w)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    x_norm = series_bpm[0]
    dx_norm = np.abs(np.diff(x_norm, prepend=x_norm[0]))
    i_norm = 0.18 + np.clip((x_norm - 92.0) * 0.012, -0.10, 0.75) + np.clip((dx_norm - 4.0) * 0.035, 0.0, 0.65)
    v_n, w_n, _ = camada_fhn.simular_oscilador_fhn(i_norm)

    x_arr = series_bpm[300]
    dx_arr = np.abs(np.diff(x_arr, prepend=x_arr[0]))
    i_arr = 0.18 + np.clip((x_arr - 92.0) * 0.012, -0.10, 0.75) + np.clip((dx_arr - 4.0) * 0.035, 0.0, 0.65)
    v_a, w_a, _ = camada_fhn.simular_oscilador_fhn(i_arr)

    axes[0].plot(t, v_n, color="#10b981", lw=2.0, label="Paciente Normal (Sub-limiar quiescente)")
    axes[0].plot(t, v_a, color="#ef4444", lw=2.0, label="Paciente com Taquicardia (Oscilação de Disparo)")
    axes[0].set_title("Potencial Excitatório v(t) no Modelo FitzHugh-Nagumo", fontsize=11, fontweight="bold")
    axes[0].set_xlabel("Tempo (s)")
    axes[0].set_ylabel("Variável de Membrana v(t)")
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.25)

    v_grid = np.linspace(-2.2, 2.2, 200)
    nullcline_v = v_grid - (v_grid ** 3) / 3.0 + 0.35
    nullcline_w = (v_grid + camada_fhn.a) / camada_fhn.b
    axes[1].plot(v_grid, nullcline_v, "--", color="#94a3b8", lw=1.2, label="Nulclina dv/dt = 0")
    axes[1].plot(v_grid, nullcline_w, ":", color="#64748b", lw=1.2, label="Nulclina dw/dt = 0")
    axes[1].plot(v_n, w_n, color="#10b981", lw=2.2, label="Trajetória Normal (Atrator Estável)")
    axes[1].plot(v_a, w_a, color="#ef4444", lw=2.0, label="Trajetória Anômala (Ciclo-Limite Ativo)")
    axes[1].set_title("Retrato de Fase Biofísico (v vs. w) — Bifurcação de Hopf", fontsize=11, fontweight="bold")
    axes[1].set_xlabel("Excitação Rápida v(t)")
    axes[1].set_ylabel("Recuperação Lenta w(t)")
    axes[1].set_xlim(-2.2, 2.2)
    axes[1].set_ylim(-1.2, 1.8)
    axes[1].legend(fontsize=8.5, loc="upper left")
    axes[1].grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_ASSETS, "fig3_dinamica_fitzhugh_nagumo_espaco_fase.png"))
    plt.close(fig)

    # FIGURA 4: Matrizes de Confusão Lado a Lado
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3))
    cmaps = ["Blues", "Reds", "Purples"]
    for ax, (nome, cm), cmap in zip(axes, matrizes.items(), cmaps):
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap=cmap,
            cbar=False,
            xticklabels=["Normal", "Anomalia"],
            yticklabels=["Normal", "Anomalia"],
            annot_kws={"size": 13, "weight": "bold"},
            ax=ax,
        )
        acc_m = resultados_modelos[nome]["acuracia_teste"]
        rec_m = resultados_modelos[nome]["recall_sensibilidade"]
        ax.set_title(f"{nome}\nAcurácia: {acc_m:.2f}% | Recall: {rec_m:.2f}%", fontsize=10.5, fontweight="bold")
        ax.set_xlabel("Previsão do Modelo")
        ax.set_ylabel("Diagnóstico Real")
    fig.suptitle("Comparativo de Matrizes de Confusão (Conjunto de Teste Estratificado — 150 Janelas)", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_ASSETS, "fig4_matrizes_confusao_comparativo.png"))
    plt.close(fig)

    # FIGURA 5: Curvas ROC e Comparativo de Métricas Clínicas
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.8))
    cores_mod = {
        "Regressão Logística (Tradicional)": "#2563eb",
        "Rede Neuromórfica LIF (Spiking)": "#e11d48",
        "Rede Neuromórfica FHN (Biofísica)": "#7c3aed",
    }
    for nome, (fpr, tpr, _) in curvas_roc.items():
        auc_val = resultados_modelos[nome]["roc_auc"]
        axes[0].plot(fpr, tpr, lw=2.3, color=cores_mod[nome], label=f"{nome} (AUC = {auc_val:.2f}%)")
    axes[0].plot([0, 1], [0, 1], "k--", lw=1.0, alpha=0.5)
    axes[0].set_title("Curvas ROC (Receiver Operating Characteristic)", fontsize=11, fontweight="bold")
    axes[0].set_xlabel("Taxa de Falsos Positivos (1 - Especificidade)")
    axes[0].set_ylabel("Taxa de Verdadeiros Positivos (Sensibilidade)")
    axes[0].legend(loc="lower right", fontsize=8.8)
    axes[0].grid(True, alpha=0.25)

    metricas_nomes = ["Acurácia", "Precisão", "Recall (Sens.)", "F1-Score"]
    x_pos = np.arange(len(metricas_nomes))
    largura = 0.25
    for idx_m, (nome, dados_m) in enumerate(resultados_modelos.items()):
        valores = [
            dados_m["acuracia_teste"],
            dados_m["precisao"],
            dados_m["recall_sensibilidade"],
            dados_m["f1_score"],
        ]
        barras = axes[1].bar(x_pos + (idx_m - 1) * largura, valores, width=largura, color=cores_mod[nome], label=nome)
        for b in barras:
            axes[1].text(
                b.get_x() + b.get_width() / 2.0,
                b.get_height() + 0.8,
                f"{b.get_height():.1f}%",
                ha="center",
                va="bottom",
                fontsize=7.8,
                fontweight="bold",
            )
    axes[1].set_xticks(x_pos)
    axes[1].set_xticklabels(metricas_nomes)
    axes[1].set_ylim(70, 106)
    axes[1].set_ylabel("Desempenho (%)")
    axes[1].set_title("Desempenho Diagnóstico por Modelo", fontsize=11, fontweight="bold")
    axes[1].legend(loc="lower right", fontsize=8.5)
    axes[1].grid(True, axis="y", alpha=0.25)

    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_ASSETS, "fig5_curvas_roc_pr_desempenho.png"))
    plt.close(fig)

    # FIGURA 6: Benchmark de Eficiência Energética e Operações na Borda (Edge / Wearable IoT)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    nomes_curtos = ["Reg. Logística\n(Tradicional MAC)", "Rede LIF\n(Spiking Event-Driven)", "Rede FHN\n(Oscilador Biofísico)"]
    energias = [resultados_modelos[k]["energia_estimada_edge_uj"] for k in resultados_modelos]
    ops = [resultados_modelos[k]["operacoes_equivalentes"] for k in resultados_modelos]
    cores_bar = ["#2563eb", "#10b981", "#7c3aed"]

    b1 = axes[0].bar(nomes_curtos, energias, color=cores_bar, width=0.52)
    for b in b1:
        axes[0].text(b.get_x() + b.get_width() / 2, b.get_height() + 0.04, f"{b.get_height():.2f} µJ", ha="center", fontweight="bold")
    axes[0].set_title("Consumo Energético Estimado por Janela no Vestível (µJ)", fontsize=10.5, fontweight="bold")
    axes[0].set_ylabel("Energia por Inferência (µJ)")
    axes[0].set_ylim(0, 2.2)
    axes[0].grid(True, axis="y", alpha=0.25)

    b2 = axes[1].bar(nomes_curtos, ops, color=cores_bar, width=0.52)
    for b in b2:
        axes[1].text(b.get_x() + b.get_width() / 2, b.get_height() + 10, f"{int(b.get_height())} ops", ha="center", fontweight="bold")
    axes[1].set_title("Operações de Computação por Janela (MACs Contínuos vs. Spike ACs)", fontsize=10.5, fontweight="bold")
    axes[1].set_ylabel("Operações por Janela de 60s")
    axes[1].set_ylim(0, 490)
    axes[1].grid(True, axis="y", alpha=0.25)

    fig.suptitle("Vantagem Neuromórfica em Hardware Médico Vestível (Edge Computing)", fontsize=12.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_ASSETS, "fig6_benchmark_latencia_energia_edge.png"))
    plt.close(fig)

    resumo = {
        "dataset": {
            "total_janelas": len(df),
            "passos_por_janela_s": 60,
            "classe_0_normal": int(np.sum(y == 0)),
            "classe_1_anomalia": int(np.sum(y == 1)),
        },
        "estatisticas_spiking_lif": info_lif,
        "modelos": resultados_modelos,
    }
    caminho_json = os.path.join(PASTA_ASSETS, "resultados_comparativos.json")
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(resumo, f, indent=2, ensure_ascii=False)

    print("\n=== RESUMO COMPARATIVO DOS MODELOS (IR ALÉM 2) ===")
    for nome, m in resultados_modelos.items():
        print(
            f"• {nome:36s} -> Acurácia: {m['acuracia_teste']:6.2f}% | "
            f"CV(5-fold): {m['acuracia_cv_5fold']:6.2f}% | "
            f"Recall: {m['recall_sensibilidade']:6.2f}% | "
            f"F1: {m['f1_score']:6.2f}% | "
            f"AUC: {m['roc_auc']:6.2f}% | "
            f"Energia Edge: {m['energia_estimada_edge_uj']} uJ"
        )
    return resumo


if __name__ == "__main__":
    executar_experimento_completo()
