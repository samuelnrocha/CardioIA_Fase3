# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href="https://www.fiap.com.br/"><img src="Monitoramento_Continuo_IoT/assets/logo-fiap.png" alt="FIAP - Faculdade de Informática e Administração Paulista" border="0" width=40% height=40%></a>
</p>

<br>

# CardioIA Conectada — Ecossistema de Cardiologia Inteligente, IoT e IA em Saúde Digital

## Grupo: Data Health Solutions

## 👨‍🎓 Integrantes:
- <a href="https://www.linkedin.com/in/gabriel-oliveira-b6353a16b/">Gabriel Oliveira dos Santos</a> — RM567166
- <a href="https://www.linkedin.com/in/arthur-bruttel-7171b8381">Arthur Bruttel Nascimento</a> — RM568484
- <a href="https://www.linkedin.com/in/jonviotti/">Jonatan Viotti Rodrigues da Silva</a> — RM566787
- <a href="https://www.linkedin.com/in/eusamuelrocha/">Samuel Nicolas Oliveira Rocha</a> — RM568552

## 👩‍🏫 Professores:
### Tutor(a)
- <a href="https://www.linkedin.com/in/leonardoorabona/">Leonardo Ruiz Orabona</a>
### Coordenador(a)
- <a href="https://www.linkedin.com/company/inova-fusca">André Godoi Chiovato</a>

---

## 🧭 Índice Geral da Fase 3 — Monitoramento Contínuo: IoT na Saúde

Nesta **Fase 3**, o projeto **CardioIA** evolui para um sistema completo de monitoramento contínuo vestível (*wearable*), cobrindo **Edge Computing (ESP32 + SPIFFS)**, **Fog/Cloud Computing (MQTT HiveMQ + Node-RED & Grafana)**, **Automação RPA com API REST e E-mail (Ir Além 1)** e **Inteligência Artificial em Séries Temporais de Saúde com Redes Neuromórficas LIF e FitzHugh-Nagumo (Ir Além 2)**.

| Módulo da Fase 3 | Pasta no Repositório | Principais Entregáveis |
| :--- | :--- | :--- |
| **Parte 1 — Armazenamento e Processamento Local (Edge Computing & SPIFFS)** | [`Monitoramento_Continuo_IoT/`](Monitoramento_Continuo_IoT/) | • **Código C++ comentado & Wokwi:** [`parte1_edge_spiffs/sketch.ino`](Monitoramento_Continuo_IoT/parte1_edge_spiffs/sketch.ino) e [`diagram.json`](Monitoramento_Continuo_IoT/parte1_edge_spiffs/diagram.json)<br>• **Evidência Monitor Serial:** [`saida_serial_exemplo.txt`](Monitoramento_Continuo_IoT/parte1_edge_spiffs/saida_serial_exemplo.txt)<br>• **Relatório Parte 1 (MD/PDF):** [`Relatorio_Parte1_Edge_Computing_Resiliencia.md`](Monitoramento_Continuo_IoT/relatorios/Relatorio_Parte1_Edge_Computing_Resiliencia.md) / [`.pdf`](Monitoramento_Continuo_IoT/relatorios/Relatorio_Parte1_Edge_Computing_Resiliencia.pdf) |
| **Parte 2 — Transmissão para Nuvem (MQTT) e Visualização (Node-RED / Grafana)** | [`Monitoramento_Continuo_IoT/`](Monitoramento_Continuo_IoT/) | • **Código ESP32 MQTT + Resiliência:** [`parte2_mqtt_cloud/sketch.ino`](Monitoramento_Continuo_IoT/parte2_mqtt_cloud/sketch.ino) e [`simulador_esp32_mqtt.py`](Monitoramento_Continuo_IoT/parte2_mqtt_cloud/simulador_esp32_mqtt.py)<br>• **Export Dashboard Node-RED:** [`flows_nodered.json`](Monitoramento_Continuo_IoT/dashboard_nodered/flows_nodered.json) e [`grafana_dashboard.json`](Monitoramento_Continuo_IoT/dashboard_nodered/grafana_dashboard.json)<br>• **Prints da Aplicação:** [`assets/`](Monitoramento_Continuo_IoT/assets/)<br>• **Relatório Parte 2 (MD/PDF):** [`Relatorio_Parte2_MQTT_Fog_Cloud_Dashboard.md`](Monitoramento_Continuo_IoT/relatorios/Relatorio_Parte2_MQTT_Fog_Cloud_Dashboard.md) / [`.pdf`](Monitoramento_Continuo_IoT/relatorios/Relatorio_Parte2_MQTT_Fog_Cloud_Dashboard.pdf) |
| **Ir Além 1 — Comunicação Automatizada com REST e E-mail (RPA)** | [`Automacao_REST_Alertas_RPA/`](Automacao_REST_Alertas_RPA/) | • **Cliente REST (`POST`/`GET`):** [`src/cliente_rest.py`](Automacao_REST_Alertas_RPA/src/cliente_rest.py)<br>• **Servidor API REST FastAPI:** [`src/servidor_api.py`](Automacao_REST_Alertas_RPA/src/servidor_api.py)<br>• **Motor de Risco Clínico:** [`src/motor_risco.py`](Automacao_REST_Alertas_RPA/src/motor_risco.py)<br>• **Automação RPA de E-mail:** [`src/automacao_email_rpa.py`](Automacao_REST_Alertas_RPA/src/automacao_email_rpa.py)<br>• **Relatório Ir Além 1 (MD/PDF):** [`Relatorio_IrAlem1_Comunicacao_REST_Automacao_Email.md`](Automacao_REST_Alertas_RPA/relatorios/Relatorio_IrAlem1_Comunicacao_REST_Automacao_Email.md) / [`.pdf`](Automacao_REST_Alertas_RPA/relatorios/Relatorio_IrAlem1_Comunicacao_REST_Automacao_Email.pdf) |
| **Ir Além 2 — Inteligência Artificial em Séries Temporais de Saúde (LIF & FHN)** | [`IA_Series_Temporais_Neuromorfica/`](IA_Series_Temporais_Neuromorfica/) | • **Notebook Python Comentado:** [`analise_series_temporais_neuromorfica.ipynb`](IA_Series_Temporais_Neuromorfica/analise_series_temporais_neuromorfica.ipynb)<br>• **Código dos Modelos (LR vs. LIF vs. FHN):** [`src/modelos_neuromorficos_vs_tradicional.py`](IA_Series_Temporais_Neuromorfica/src/modelos_neuromorficos_vs_tradicional.py)<br>• **Relatório Comparativo (MD/PDF):** [`Relatorio_Comparativo_IrAlem2_Tradicional_vs_Neuromorfico.md`](IA_Series_Temporais_Neuromorfica/relatorios/Relatorio_Comparativo_IrAlem2_Tradicional_vs_Neuromorfico.md) / [`.pdf`](IA_Series_Temporais_Neuromorfica/relatorios/Relatorio_Comparativo_IrAlem2_Tradicional_vs_Neuromorfico.pdf)<br>• **Vídeo Apresentação (Até 4 min):** [`video/apresentacao_ir_alem2_neuromorfica.mp4`](IA_Series_Temporais_Neuromorfica/video/apresentacao_ir_alem2_neuromorfica.mp4) |

---

## 🗂️ Módulos da Fase 2 (Histórico do Projeto)

Os módulos anteriores da **Fase 2** encontram-se no repositório [CardioIA (Fase 2)](https://github.com/jonviotti/CardioIA):
- **[`Estetoscopio_Digital/`](https://github.com/jonviotti/CardioIA/tree/main/Estetoscopio_Digital):** Fase 2 (Parte 1) — Motor de extração de sintomas em linguagem natural e inferência diagnóstica baseada em mapa de conhecimento.
- **[`Classificador_de_Texto/`](https://github.com/jonviotti/CardioIA/tree/main/Classificador_de_Texto):** Fase 2 (Parte 2) — Classificador de triagem clínica com TF-IDF e Regressão Logística.
- **[`data-health-solutions-cardioia-portal/`](https://github.com/jonviotti/CardioIA/tree/main/data-health-solutions-cardioia-portal):** Fase 2 (Ir Além 1) — Portal web em React + Vite para gestão de pacientes e agendamentos.

---

## 📋 Licença

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/agodoi/template">MODELO GIT FIAP</a> por <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">Fiap</a> está licenciado sobre <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
