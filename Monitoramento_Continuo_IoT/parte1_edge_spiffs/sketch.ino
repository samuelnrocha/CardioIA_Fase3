/**
 * ============================================================================
 * FIAP - Faculdade de Informática e Administração Paulista
 * Projeto CardioIA - Fase 3: Monitoramento Contínuo (IoT na Saúde Digital)
 * Grupo: Data Health Solutions
 *
 * PARTE 2 – Transmissão para Nuvem e Visualização (Fog/Cloud Computing + MQTT)
 * Integrado com a Resiliência Offline (Edge Computing + SPIFFS) da Parte 1
 * ============================================================================
 * Descrição:
 * Sistema completo de monitoramento cardiológico contínuo para ESP32 no Wokwi.
 * Captura sinais vitais de 3 sensores (DHT22, Potenciômetro/Botão de Pulso BPM
 * e Acelerômetro MPU6050), processa regras de alerta na borda (Edge), garante
 * resiliência offline via SPIFFS + Buffer Circular quando sem conexão e publica
 * os dados em tempo real na nuvem via protocolo MQTT (Broker HiveMQ).
 *
 * Tópicos MQTT Publicados:
 *   - cardioia/fase3/telemetria  (Payload JSON completo com sinais vitais e alerta)
 *   - cardioia/fase3/alertas     (Payload JSON disparado imediatamente em anomalias)
 *   - cardioia/fase3/bpm         (Valor numérico de batimentos por minuto)
 *   - cardioia/fase3/temperatura (Valor numérico de temperatura em °C)
 *   - cardioia/fase3/umidade     (Valor numérico de umidade em %)
 *   - cardioia/fase3/status      (Status Online/Offline LWT e diagnóstico)
 *
 * Tópico MQTT Subscrito (Comandos Remotos da Equipe Médica / Node-RED):
 *   - cardioia/fase3/comandos    (Permite silenciar alarme ou forçar sincronização)
 * ============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <FS.h>
#include <SPIFFS.h>
#include <DHTesp.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>

// ============================================================================
// 1. CONFIGURAÇÕES DE REDE WI-FI (WOKWI) E BROKER MQTT (HIVEMQ)
// ============================================================================
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const int   WIFI_CHANNEL  = 6;

// Broker MQTT Público de Alta Disponibilidade (HiveMQ)
// Nota: Para cluster privado HiveMQ Cloud TLS (porta 8883), basta substituir
// WiFiClient por WiFiClientSecure e configurar as credenciais do cluster.
const char* MQTT_BROKER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const char* MQTT_USER     = "";
const char* MQTT_PASS     = "";

// Tópicos MQTT da Arquitetura Fog/Cloud CardioIA
const char* TOPICO_TELEMETRIA  = "cardioia/fase3/telemetria";
const char* TOPICO_ALERTAS     = "cardioia/fase3/alertas";
const char* TOPICO_BPM         = "cardioia/fase3/bpm";
const char* TOPICO_TEMPERATURA = "cardioia/fase3/temperatura";
const char* TOPICO_UMIDADE     = "cardioia/fase3/umidade";
const char* TOPICO_STATUS      = "cardioia/fase3/status";
const char* TOPICO_COMANDOS    = "cardioia/fase3/comandos";

// ============================================================================
// 2. DEFINIÇÃO DE PINOS DO HARDWARE (ESP32 WOKWI)
// ============================================================================
#define PIN_DHT22         15   // Sensor obrigatório de Temperatura e Umidade (DHT22)
#define PIN_POT_BPM       34   // Potenciômetro analógico para simulação de BPM
#define PIN_BTN_PULSO     4    // Botão de pressão para simular batimentos manuais
#define PIN_SW_WIFI       18   // Chave deslizante: simula queda/retorno de Wi-Fi
#define PIN_LED_WIFI      2    // LED Verde: Conectado ao Wi-Fi e Broker MQTT
#define PIN_LED_ALERTA    5    // LED Vermelho: Alerta Clínico (>120 bpm, >38°C, etc.)
#define PIN_I2C_SDA       21   // Pino SDA do Acelerômetro MPU6050
#define PIN_I2C_SCL       22   // Pino SCL do Acelerômetro MPU6050

// ============================================================================
// 3. PARÂMETROS CLÍNICOS E MODELO DE NEGÓCIO (RESILIÊNCIA OFFLINE)
// ============================================================================
const char* PACIENTE_ID          = "PAC-001";
const char* PACIENTE_NOME        = "Ana Beatriz Souza";
const char* ARQUIVO_SPIFFS       = "/leituras_offline.csv";

const unsigned long INTERVALO_PUBLICACAO_MS = 3000;
const size_t CAPACIDADE_BUFFER_RAM          = 120;
const size_t LIMITE_AMOSTRAS_NEGOCIO_FLASH  = 10000;

// Limites Clínicos definidos pelo grupo Data Health Solutions
const int   LIMITE_TAQUICARDIA_BPM = 120;  // Alerta se BPM > 120
const int   LIMITE_BRADICARDIA_BPM = 50;   // Alerta se BPM < 50
const float LIMITE_FEBRE_C         = 38.0; // Alerta se Temperatura > 38.0 °C
const float LIMITE_HIPOTERMIA_C    = 35.0; // Alerta se Temperatura < 35.0 °C
const float LIMITE_IMOBILIDADE_G   = 0.08; // Variação mínima de movimento em G
const int   CICLOS_PARA_IMOBILIDADE = 4;

// ============================================================================
// 4. ESTRUTURAS DE DADOS E INSTÂNCIAS GLOBAIS
// ============================================================================
struct AmostraVital {
  unsigned long timestamp_ms;
  uint32_t      sequencia;
  float         temperatura_c;
  float         umidade_pct;
  int           batimentos_bpm;
  float         aceleracao_g;
  bool          em_movimento;
  bool          alerta_critico;
  char          nivel_risco[16];
  char          descricao_alerta[48];
};

WiFiClient       espClient;
PubSubClient     mqttClient(espClient);
DHTesp           sensorDHT;
Adafruit_MPU6050 sensorMPU;

bool             mpuDisponivel           = false;
bool             spiffsMontado           = false;
bool             wifiConectado           = true;  // Variável booleana de simulação Wi-Fi
bool             wifiConectadoAnterior   = true;

AmostraVital     bufferOfflineRAM[CAPACIDADE_BUFFER_RAM];
size_t           indiceEscritaRAM        = 0;
size_t           totalAmostrasPendentes  = 0;
size_t           totalAmostrasSobrescritas = 0;
uint32_t         contadorSequenciaGlobal = 0;

volatile unsigned long contadorCliquesBotao = 0;
unsigned long          ultimoCliqueMs       = 0;
int                    bpmIncrementoBotao   = 0;
float                  ultimaAceleracaoG    = 1.0f;
int                    ciclosSemMovimento   = 0;
unsigned long          ultimaPublicacaoMs   = 0;
unsigned long          ultimaTentativaMqttMs = 0;

// ISR para o botão de pressão de batimentos cardíacos
void IRAM_ATTR isrBotaoPulso() {
  unsigned long agora = millis();
  if (agora - ultimoCliqueMs > 120) {
    contadorCliquesBotao++;
    ultimoCliqueMs = agora;
  }
}

// ============================================================================
// 5. CALLBACK MQTT E GERENCIAMENTO DE CONEXÃO WI-FI / BROKER
// ============================================================================
void callbackMQTT(char* topic, byte* payload, unsigned int length) {
  String mensagem;
  for (unsigned int i = 0; i < length; i++) {
    mensagem += (char)payload[i];
  }
  mensagem.trim();
  Serial.printf("[MQTT-CMD] Mensagem recebida em '%s': %s\n", topic, mensagem.c_str());

  if (mensagem.equalsIgnoreCase("RESET_ALERTA")) {
    digitalWrite(PIN_LED_ALERTA, LOW);
    Serial.println(F("[MQTT-CMD] Alerta visual local reiniciado remotamente pela equipe medica."));
  }
}

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("[WIFI] Conectando a rede '%s'...", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - inicio) < 6000) {
    delay(250);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" Conectado! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(F(" Tempo limite excedido (operando em resiliencia Edge)."));
  }
}

bool conectarMQTT() {
  if (!wifiConectado || WiFi.status() != WL_CONNECTED) return false;
  if (mqttClient.connected()) return true;

  unsigned long agora = millis();
  if (agora - ultimaTentativaMqttMs < 4000) return false;
  ultimaTentativaMqttMs = agora;

  String clientId = "CardioIA-ESP32-" + String(PACIENTE_ID) + "-" + String(random(1000, 9999));
  Serial.printf("[MQTT] Conectando ao broker %s:%d como '%s'...", MQTT_BROKER, MQTT_PORT, clientId.c_str());

  // Configura Last Will and Testament (LWT) para avisar o dashboard em caso de queda abrupta
  bool conectado = false;
  if (strlen(MQTT_USER) > 0) {
    conectado = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS,
                                   TOPICO_STATUS, 1, true, "{\"status\":\"OFFLINE\",\"paciente_id\":\"PAC-001\"}");
  } else {
    conectado = mqttClient.connect(clientId.c_str(),
                                   TOPICO_STATUS, 1, true, "{\"status\":\"OFFLINE\",\"paciente_id\":\"PAC-001\"}");
  }

  if (conectado) {
    Serial.println(F(" Conectado ao HiveMQ!"));
    mqttClient.publish(TOPICO_STATUS, "{\"status\":\"ONLINE\",\"paciente_id\":\"PAC-001\"}", true);
    mqttClient.subscribe(TOPICO_COMANDOS);
    return true;
  } else {
    Serial.printf(" Falha (rc=%d).\n", mqttClient.state());
    return false;
  }
}

// ============================================================================
// 6. ARMAZENAMENTO LOCAL (SPIFFS) E PUBLICAÇÃO MQTT (FOG/CLOUD)
// ============================================================================
void inicializarSPIFFS() {
  if (SPIFFS.begin(true)) {
    spiffsMontado = true;
    Serial.printf("[SPIFFS] Sistema de arquivos pronto (%u bytes totais).\n",
                  (unsigned int)SPIFFS.totalBytes());
  } else {
    spiffsMontado = false;
    Serial.println(F("[SPIFFS] Modo simulador: Buffer Circular em RAM ativo."));
  }
}

void armazenarLeituraOffline(const AmostraVital& amostra) {
  if (totalAmostrasPendentes >= CAPACIDADE_BUFFER_RAM) {
    size_t idxSub = indiceEscritaRAM;
    for (size_t i = 0; i < CAPACIDADE_BUFFER_RAM; i++) {
      size_t idx = (indiceEscritaRAM + i) % CAPACIDADE_BUFFER_RAM;
      if (!bufferOfflineRAM[idx].alerta_critico) {
        idxSub = idx;
        break;
      }
    }
    bufferOfflineRAM[idxSub] = amostra;
    indiceEscritaRAM = (idxSub + 1) % CAPACIDADE_BUFFER_RAM;
    totalAmostrasSobrescritas++;
  } else {
    bufferOfflineRAM[indiceEscritaRAM] = amostra;
    indiceEscritaRAM = (indiceEscritaRAM + 1) % CAPACIDADE_BUFFER_RAM;
    totalAmostrasPendentes++;
  }

  if (spiffsMontado && totalAmostrasPendentes <= LIMITE_AMOSTRAS_NEGOCIO_FLASH) {
    bool novo = !SPIFFS.exists(ARQUIVO_SPIFFS);
    File f = SPIFFS.open(ARQUIVO_SPIFFS, FILE_APPEND);
    if (f) {
      if (novo) {
        f.println("seq,timestamp_ms,paciente_id,temperatura_c,umidade_pct,bpm,aceleracao_g,movimento,risco,alerta");
      }
      f.printf("%u,%lu,%s,%.1f,%.1f,%d,%.2f,%s,%s,%s\n",
               amostra.sequencia, amostra.timestamp_ms, PACIENTE_ID,
               amostra.temperatura_c, amostra.umidade_pct, amostra.batimentos_bpm,
               amostra.aceleracao_g, amostra.em_movimento ? "SIM" : "NAO",
               amostra.nivel_risco, amostra.descricao_alerta);
      f.close();
    }
  }

  Serial.printf("[OFFLINE -> SPIFFS] Amostra #%u salva localmente (%u/%u pendentes) | BPM: %d | Temp: %.1f C | Status: %s\n",
                amostra.sequencia, (unsigned int)totalAmostrasPendentes,
                (unsigned int)CAPACIDADE_BUFFER_RAM, amostra.batimentos_bpm,
                amostra.temperatura_c, amostra.descricao_alerta);
}

bool publicarAmostraMQTT(const AmostraVital& amostra, const char* modoEnvio) {
  StaticJsonDocument<512> doc;
  doc["paciente_id"]       = PACIENTE_ID;
  doc["paciente"]          = PACIENTE_NOME;
  doc["seq"]               = amostra.sequencia;
  doc["timestamp_ms"]      = amostra.timestamp_ms;
  doc["temperatura_c"]     = serialized(String(amostra.temperatura_c, 1));
  doc["umidade_pct"]       = serialized(String(amostra.umidade_pct, 1));
  doc["bpm"]               = amostra.batimentos_bpm;
  doc["aceleracao_g"]      = serialized(String(amostra.aceleracao_g, 2));
  doc["em_movimento"]      = amostra.em_movimento;
  doc["alerta_critico"]    = amostra.alerta_critico;
  doc["nivel_risco"]       = amostra.nivel_risco;
  doc["diagnostico_borda"] = amostra.descricao_alerta;
  doc["origem_envio"]      = modoEnvio;

  char payload[512];
  serializeJson(doc, payload, sizeof(payload));

  // Imprime no Monitor Serial (evidência de envio e auditoria)
  Serial.printf("[MQTT-PUB | %s] Topico: %s -> %s\n", modoEnvio, TOPICO_TELEMETRIA, payload);

  if (mqttClient.connected()) {
    bool ok = mqttClient.publish(TOPICO_TELEMETRIA, payload, false);

    // Publica também nos subtópicos individuais para facilitar widgets diretos
    char bufNum[16];
    snprintf(bufNum, sizeof(bufNum), "%d", amostra.batimentos_bpm);
    mqttClient.publish(TOPICO_BPM, bufNum);

    snprintf(bufNum, sizeof(bufNum), "%.1f", amostra.temperatura_c);
    mqttClient.publish(TOPICO_TEMPERATURA, bufNum);

    snprintf(bufNum, sizeof(bufNum), "%.1f", amostra.umidade_pct);
    mqttClient.publish(TOPICO_UMIDADE, bufNum);

    if (amostra.alerta_critico) {
      mqttClient.publish(TOPICO_ALERTAS, payload, false);
    }
    return ok;
  }
  return false;
}

void sincronizarFilaOfflineMQTT() {
  if (totalAmostrasPendentes == 0) return;

  Serial.println(F("\n============================================================"));
  Serial.printf("[SYNC-MQTT] Conectividade restaurada! Sincronizando %u amostras retidas no SPIFFS/Buffer...\n",
                (unsigned int)totalAmostrasPendentes);

  size_t inicio = (totalAmostrasPendentes < CAPACIDADE_BUFFER_RAM) ? 0 : indiceEscritaRAM;
  for (size_t i = 0; i < totalAmostrasPendentes; i++) {
    size_t idx = (inicio + i) % CAPACIDADE_BUFFER_RAM;
    publicarAmostraMQTT(bufferOfflineRAM[idx], "RESILIENCIA_OFFLINE");
    mqttClient.loop();
    delay(60);
  }

  if (spiffsMontado && SPIFFS.exists(ARQUIVO_SPIFFS)) {
    SPIFFS.remove(ARQUIVO_SPIFFS);
    Serial.println(F("[SPIFFS-CLEAN] Arquivo local /leituras_offline.csv removido apos sincronizacao MQTT."));
  }

  indiceEscritaRAM          = 0;
  totalAmostrasPendentes    = 0;
  totalAmostrasSobrescritas = 0;
  Serial.println(F("[SYNC-MQTT] Sincronizacao concluida com sucesso!"));
  Serial.println(F("============================================================\n"));
}

// ============================================================================
// 7. COLETA DE SENSORES E DETECÇÃO DE ALERTA CLÍNICO
// ============================================================================
AmostraVital lerSensoresEAnalisarRisco() {
  AmostraVital amostra;
  contadorSequenciaGlobal++;
  amostra.timestamp_ms = millis();
  amostra.sequencia    = contadorSequenciaGlobal;

  // 1. Sensor DHT22 (Temperatura e Umidade)
  TempAndHumidity dht = sensorDHT.getTempAndHumidity();
  amostra.temperatura_c = isnan(dht.temperature) ? 36.6f : dht.temperature;
  amostra.umidade_pct   = isnan(dht.humidity)    ? 55.0f : dht.humidity;

  // 2. Sensor de Batimentos Cardíacos (Potenciômetro + Botão de Pressão)
  int adc = analogRead(PIN_POT_BPM);
  int bpmBase = map(adc, 0, 4095, 40, 175);

  noInterrupts();
  unsigned long cliques = contadorCliquesBotao;
  contadorCliquesBotao = 0;
  interrupts();

  if (cliques > 0) {
    bpmIncrementoBotao = min(80, bpmIncrementoBotao + (int)(cliques * 12));
  } else {
    bpmIncrementoBotao = max(0, bpmIncrementoBotao - 6);
  }
  amostra.batimentos_bpm = constrain(bpmBase + bpmIncrementoBotao, 35, 220);

  // 3. Sensor Acelerômetro MPU6050
  if (mpuDisponivel) {
    sensors_event_t a, g, t;
    sensorMPU.getEvent(&a, &g, &t);
    amostra.aceleracao_g = sqrt(a.acceleration.x * a.acceleration.x +
                                a.acceleration.y * a.acceleration.y +
                                a.acceleration.z * a.acceleration.z) / 9.80665f;
  } else {
    amostra.aceleracao_g = 1.00f + (cliques > 0 ? 0.30f : 0.01f);
  }

  float deltaG = fabs(amostra.aceleracao_g - ultimaAceleracaoG);
  ultimaAceleracaoG = amostra.aceleracao_g;
  if (deltaG < LIMITE_IMOBILIDADE_G && cliques == 0) {
    ciclosSemMovimento++;
  } else {
    ciclosSemMovimento = 0;
  }
  amostra.em_movimento = (ciclosSemMovimento < CICLOS_PARA_IMOBILIDADE);

  // 4. Regras de Triagem e Alerta Clínico
  amostra.alerta_critico = false;
  strncpy(amostra.nivel_risco, "BAIXO", sizeof(amostra.nivel_risco));
  strncpy(amostra.descricao_alerta, "SINAIS_ESTAVEIS", sizeof(amostra.descricao_alerta));

  bool taquicardia = (amostra.batimentos_bpm > LIMITE_TAQUICARDIA_BPM);
  bool bradicardia = (amostra.batimentos_bpm < LIMITE_BRADICARDIA_BPM);
  bool febre       = (amostra.temperatura_c > LIMITE_FEBRE_C);
  bool hipotermia  = (amostra.temperatura_c < LIMITE_HIPOTERMIA_C);
  bool imobilidade = (!amostra.em_movimento);

  if (taquicardia && febre) {
    amostra.alerta_critico = true;
    strncpy(amostra.nivel_risco, "CRITICO", sizeof(amostra.nivel_risco));
    strncpy(amostra.descricao_alerta, "ALERTA_COMBINADO_TAQUICARDIA_E_FEBRE", sizeof(amostra.descricao_alerta));
  } else if (taquicardia) {
    amostra.alerta_critico = true;
    strncpy(amostra.nivel_risco, "ALTO", sizeof(amostra.nivel_risco));
    strncpy(amostra.descricao_alerta, "ALERTA_TAQUICARDIA_ACIMA_120BPM", sizeof(amostra.descricao_alerta));
  } else if (bradicardia) {
    amostra.alerta_critico = true;
    strncpy(amostra.nivel_risco, "ALTO", sizeof(amostra.nivel_risco));
    strncpy(amostra.descricao_alerta, "ALERTA_BRADICARDIA_ABAIXO_50BPM", sizeof(amostra.descricao_alerta));
  } else if (febre) {
    amostra.alerta_critico = true;
    strncpy(amostra.nivel_risco, "ALTO", sizeof(amostra.nivel_risco));
    strncpy(amostra.descricao_alerta, "ALERTA_FEBRE_ACIMA_38C", sizeof(amostra.descricao_alerta));
  } else if (hipotermia) {
    amostra.alerta_critico = true;
    strncpy(amostra.nivel_risco, "ALTO", sizeof(amostra.nivel_risco));
    strncpy(amostra.descricao_alerta, "ALERTA_HIPOTERMIA_ABAIXO_35C", sizeof(amostra.descricao_alerta));
  } else if (imobilidade && (amostra.batimentos_bpm > 105 || amostra.batimentos_bpm < 55)) {
    amostra.alerta_critico = true;
    strncpy(amostra.nivel_risco, "ALTO", sizeof(amostra.nivel_risco));
    strncpy(amostra.descricao_alerta, "ALERTA_IMOBILIDADE_COM_ALTERACAO_CARDIACA", sizeof(amostra.descricao_alerta));
  }

  digitalWrite(PIN_LED_ALERTA, amostra.alerta_critico ? HIGH : LOW);
  return amostra;
}

// ============================================================================
// 8. SETUP E LOOP PRINCIPAL
// ============================================================================
void setup() {
  Serial.begin(115200);
  delay(400);

  Serial.println(F("\n============================================================"));
  Serial.println(F("   CARDIOIA - FASE 3 (PARTE 2: FOG/CLOUD MQTT + NODE-RED)   "));
  Serial.println(F("   Grupo: Data Health Solutions - FIAP                      "));
  Serial.println(F("============================================================"));

  pinMode(PIN_BTN_PULSO, INPUT_PULLUP);
  pinMode(PIN_SW_WIFI, INPUT_PULLUP);
  pinMode(PIN_LED_WIFI, OUTPUT);
  pinMode(PIN_LED_ALERTA, OUTPUT);
  analogReadResolution(12);

  attachInterrupt(digitalPinToInterrupt(PIN_BTN_PULSO), isrBotaoPulso, FALLING);

  sensorDHT.setup(PIN_DHT22, DHTesp::DHT22);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  if (sensorMPU.begin()) {
    mpuDisponivel = true;
    sensorMPU.setAccelerometerRange(MPU6050_RANGE_8_G);
    sensorMPU.setGyroRange(MPU6050_RANGE_500_DEG);
    sensorMPU.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }

  inicializarSPIFFS();

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(1024);
  mqttClient.setCallback(callbackMQTT);

  wifiConectado = (digitalRead(PIN_SW_WIFI) == HIGH);
  wifiConectadoAnterior = wifiConectado;
  if (wifiConectado) {
    conectarWiFi();
    conectarMQTT();
  }
}

void loop() {
  // 1. Lê a chave física de simulação de conectividade Wi-Fi (GPIO 18)
  wifiConectado = (digitalRead(PIN_SW_WIFI) == HIGH);

  if (wifiConectado != wifiConectadoAnterior) {
    if (wifiConectado) {
      Serial.println(F("\n>>> [REDE] Chave Wi-Fi ativada (ONLINE) -> Reconectando Wi-Fi e Broker MQTT... <<<"));
      conectarWiFi();
      conectarMQTT();
    } else {
      Serial.println(F("\n>>> [REDE] Chave Wi-Fi desativada (OFFLINE) -> Entrando em modo de resiliencia local (SPIFFS)... <<<"));
      if (mqttClient.connected()) {
        mqttClient.publish(TOPICO_STATUS, "{\"status\":\"OFFLINE_SIMULADO\",\"paciente_id\":\"PAC-001\"}", true);
        mqttClient.disconnect();
      }
    }
    wifiConectadoAnterior = wifiConectado;
  }

  // 2. Mantém loop MQTT ativo se estiver conectado
  bool onlineNaNuvem = false;
  if (wifiConectado) {
    if (WiFi.status() != WL_CONNECTED) {
      conectarWiFi();
    }
    if (WiFi.status() == WL_CONNECTED) {
      onlineNaNuvem = conectarMQTT();
      if (onlineNaNuvem) {
        mqttClient.loop();
      }
    }
  }
  digitalWrite(PIN_LED_WIFI, onlineNaNuvem ? HIGH : LOW);

  // 3. Coleta periódica e envio MQTT (ou gravação offline SPIFFS)
  unsigned long agora = millis();
  if (agora - ultimaPublicacaoMs >= INTERVALO_PUBLICACAO_MS) {
    ultimaPublicacaoMs = agora;

    AmostraVital amostra = lerSensoresEAnalisarRisco();

    if (onlineNaNuvem) {
      if (totalAmostrasPendentes > 0) {
        sincronizarFilaOfflineMQTT();
      }
      publicarAmostraMQTT(amostra, "TEMPO_REAL");
    } else {
      armazenarLeituraOffline(amostra);
    }
  }

  delay(40);
}
