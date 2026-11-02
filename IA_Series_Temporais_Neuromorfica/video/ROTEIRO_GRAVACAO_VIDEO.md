# Roteiro de Apresentação em Vídeo (Até 4 Minutos) — Ir Além 2: IA em Séries Temporais de Saúde

- **Projeto:** CardioIA Conectada — Fase 3 (FIAP)
- **Grupo:** Data Health Solutions
- **Duração Estimada:** ~2 min 45 seg (Limite máximo do enunciado: 4 minutos)
- **Vídeo MP4 pré-renderizado disponível nesta pasta:** [`apresentacao_ir_alem2_neuromorfica.mp4`](apresentacao_ir_alem2_neuromorfica.mp4)

> **Como publicar no YouTube:**
> 1. Faça upload do arquivo `apresentacao_ir_alem2_neuromorfica.mp4` (ou grave sua tela seguindo o roteiro abaixo) em [https://studio.youtube.com](https://studio.youtube.com).
> 2. Na etapa **Visibilidade**, selecione **Não listado** (*Unlisted*).
> 3. Copie o link gerado pelo YouTube e atualize o hiperlink na seção `🎥 Demonstração em Vídeo` do `README.md`.

---

## Estrutura Minuto a Minuto da Apresentação

### Slide 1 — Introdução e Problema Clínico (00:00 – 00:30)
- **Visual na tela:** Capa do projeto CardioIA / Notebook `analise_series_temporais_neuromorfica.ipynb` e Figura 1 (`fig1_series_temporais_sinais_vitais.png`).
- **Fala sugerida:**
  > *"Olá! Somos o grupo Data Health Solutions da FIAP e apresentamos os resultados do desafio Ir Além 2 da Fase 3 do projeto CardioIA. Nosso objetivo foi aplicar técnicas de Inteligência Artificial em séries temporais de sinais vitais — especificamente 600 janelas de 60 segundos de batimentos cardíacos e temperatura corporal capturados pelo nosso dispositivo vestível IoT — comparando um classificador tradicional de Regressão Logística com duas arquiteturas de Redes Neuromórficas: o modelo Leaky Integrate-and-Fire (LIF) e o modelo biofísico de FitzHugh-Nagumo (FHN)."*

### Slide 2 — Codificação Neuromórfica LIF e Pulsos (Spikes) (00:30 – 01:15)
- **Visual na tela:** Figura 2 (`fig2_dinamica_neuronio_lif_spikes.png`).
- **Fala sugerida:**
  > *"Enquanto a Regressão Logística tradicional extrai estatísticas estáticas da janela inteira (como média e desvio-padrão), a rede neuromórfica LIF funciona de maneira orientada a eventos, imitando neurônios biológicos. O potencial de membrana V(t) integra a corrente sináptica com vazamento e permanece em silêncio durante quase 90% do tempo. Somente quando ocorre uma transição abrupta — como um surto de taquicardia paroxística ou ectopia — o potencial cruza o limiar de -50 milivolts e emite um trem de pulsos binários (spikes)."*

### Slide 3 — Modelo Biofísico FitzHugh-Nagumo (FHN) (01:15 – 01:45)
- **Visual na tela:** Figura 3 (`fig3_dinamica_fitzhugh_nagumo_espaco_fase.png`).
- **Fala sugerida:**
  > *"Também implementamos o modelo de FitzHugh-Nagumo, uma redução bidimensional das equações de Hodgkin-Huxley. No retrato de fase entre a variável rápida de excitação v(t) e a variável lenta de recuperação w(t), observamos que pacientes em ritmo sinusal normal permanecem presos a um ponto de equilíbrio quiescente, enquanto crises taquicárdicas empurram o sistema através de uma bifurcação de Hopf para um ciclo-limite de disparos periódicos."*

### Slide 4 — Comparação de Desempenho Diagnóstico (01:45 – 02:15)
- **Visual na tela:** Figura 4 (`fig4_matrizes_confusao_comparativo.png`) e Figura 5 (`fig5_curvas_roc_pr_desempenho.png`).
- **Fala sugerida:**
  > *"Nos resultados experimentais com validação estratificada, a Regressão Logística obteve 97,33% de acurácia no teste e 96,50% na validação cruzada de 5 dobras. Porém, a Rede Neuromórfica LIF superou o modelo tradicional na validação cruzada de 5 dobras (alcançando 97,17%), na Precisão diagnóstica (98,57%, com apenas 1 falso positivo em 75 pacientes normais) e na área sob a curva ROC (99,75% contra 99,54%). Já o modelo FHN atingiu 89,17% na validação cruzada e 95,66% de ROC-AUC."*

### Slide 5 — Análise Crítica: Eficiência Energética em Wearables Edge (02:15 – 02:45)
- **Visual na tela:** Figura 6 (`fig6_benchmark_latencia_energia_edge.png`) e Tabela Síntese.
- **Fala sugerida:**
  > *"A grande vantagem crítica da arquitetura neuromórfica LIF aparece quando olhamos para o hardware vestível na borda, como o ESP32 da Parte 1: por operar orientada a eventos com 89,6% de esparsidade temporal, a rede LIF reduz as operações computacionais de 420 multiplicações em ponto flutuante para apenas 85 acumulações de spikes, derrubando o consumo energético estimado de 1,85 microjoules para 0,24 microjoules por inferência — uma economia de 87% de bateria sem abrir mão da precisão clínica. Muito obrigado!"*
