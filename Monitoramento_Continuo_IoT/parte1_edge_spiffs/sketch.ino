/**
 * ============================================================================
 * FIAP - Faculdade de Informática e Administração Paulista
 * Projeto CardioIA - Fase 3: Monitoramento Contínuo (IoT na Saúde Digital)
 * Grupo: Data Health Solutions
 *
 * PARTE 1 – Armazenamento e Processamento Local (Edge Computing)
 * ============================================================================
 * Descrição:
 * Firmware para ESP32 (Wokwi / Hardware Real) simulando um dispositivo vestível
 * de monitoramento cardiológico contínuo com processamento na borda (Edge),
 * detecção local de anomalias e resiliência offline com SPIFFS + Buffer Circular.
 *
 * Sensores integrados (3 sensores distintos + chave de conectividade):
 *   1. DHT22 (GPIO 15)         -> Temperatura corporal/superficial (°C) e Umidade (%)
 *   2. Potenciômetro (GPIO 34) + Botão de Pulso (GPIO 4) -> Batimentos Cardíacos (BPM)
 *   3. MPU6050 I2C (GPIO 21/22)-> Acelerômetro/Giroscópio (Movimento, Queda e Imobilidade)
 *   4. Slide Switch (GPIO 18)  -> Simulação física da variável booleana (wifiConectado)
 *
 * Estratégia de Resiliência Offline (Modelo de Negócio CardioIA):
 *   - Partição Flash SPIFFS (/leituras_offline.csv): Limite de negócio de 10.000
 *     amostras (~640 KB de 1,5 MB disponíveis, ~64 bytes/amostra), garantindo
 *     13,8 horas de autonomia offline a 1 leitura/5s.
 *   - Buffer Circular em RAM (Espelho para Simulador Wokwi): Janela circular FIFO
 *     com preservação prioritária de alertas clínicos (Taquicardia, Bradicardia,
 *     Febre, Hipotermia e Ausência de Movimento).
 *   - Ao reconectar (wifiConectado == true): Descarrega todo o histórico acumulado
 *     para a nuvem via Serial.println (JSON/CSV) e remove o arquivo local SPIFFS.
 * ============================================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <FS.h>
#include <SPIFFS.h>
#include <DHTesp.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

// ============================================================================
// 1. DEFINIÇÃO DE PINOS DO HARDWARE (ESP32 WOKWI)
// ============================================================================
#define PIN_DHT22         15   // Sensor obrigatório de Temperatura e Umidade (DHT22)
#define PIN_POT_BPM       34   // Sensor analógico para simulação contínua de BPM
#define PIN_BTN_PULSO     4    // Botão de pressão para simular pulsos cardíacos manuais
#define PIN_SW_WIFI       18   // Chave deslizante para controlar booleana wifiConectado
#define PIN_LED_WIFI      2    // LED Azul/Verde: aceso = Online | apagado = Offline
#define PIN_LED_ALERTA    5    // LED Vermelho: aceso = Alerta Clínico detectado na Borda
#define PIN_I2C_SDA       21   // Barramento I2C SDA (MPU6050)
#define PIN_I2C_SCL       22   // Barramento I2C SCL (MPU6050)

// ============================================================================
// 2. CONSTANTES DO MODELO DE NEGÓCIO E LIMITES CLÍNICOS (EDGE COMPUTING)
// ============================================================================
const char* PACIENTE_ID          = "PAC-001";
const char* PACIENTE_NOME        = "Ana Beatriz Souza"; // Paciente de Alto Risco (Fase 2)
const char* ARQUIVO_SPIFFS       = "/leituras_offline.csv";

// Intervalo de coleta periódica (3 segundos na simulação para fácil visualização;
// 5 segundos em produção)
const unsigned long INTERVALO_COLETA_MS = 3000;

// Estratégia de armazenamento limitado (Resiliência Offline):
// Em produção no chip ESP32 real: até 10.000 amostras no SPIFFS (~640 KB).
// No buffer circular em RAM (e limite de demonstração no simulador): 120 amostras.
const size_t LIMITE_AMOSTRAS_NEGOCIO_FLASH = 10000;
const size_t CAPACIDADE_BUFFER_RAM         = 120;

// Limiares Clínicos de Alerta na Borda (Protocolo CardioIA)
const int   LIMITE_TAQUICARDIA_BPM = 120;  // Acima de 120 bpm -> Taquicardia
const int   LIMITE_BRADICARDIA_BPM = 50;   // Abaixo de 50 bpm  -> Bradicardia
const float LIMITE_FEBRE_C         = 38.0; // Acima de 38.0 °C -> Febre / Hipertermia
const float LIMITE_HIPOTERMIA_C    = 35.0; // Abaixo de 35.0 °C-> Hipotermia
const float LIMITE_IMOBILIDADE_G   = 0.08; // Variação < 0.08g por vários ciclos -> Sem movimento
const int   CICLOS_PARA_IMOBILIDADE = 4;   // Ciclos consecutivos sem variação de movimento

// ============================================================================
// 3. ESTRUTURAS DE DADOS E VARIÁVEIS GLOBAIS
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
  char          descricao_alerta[48];
};

// Instâncias dos sensores
DHTesp           sensorDHT;
Adafruit_MPU6050 sensorMPU;
bool             mpuDisponivel = false;

// Variável booleana obrigatória de simulação de conectividade Wi-Fi
bool wifiConectado         = true;
bool wifiConectadoAnterior = true;
bool modoControleSerial    = false; // Permite forçar online/offline via comando Serial

// Buffer Circular em RAM (garante funcionamento 100% resiliente mesmo se o SPIFFS
// do simulador web for volátil) + contadores de auditoria
AmostraVital bufferOfflineRAM[CAPACIDADE_BUFFER_RAM];
size_t       indiceEscritaRAM        = 0;
size_t       totalAmostrasPendentes  = 0;
size_t       totalAmostrasSobrescritas = 0;
uint32_t     contadorSequenciaGlobal = 0;
bool         spiffsMontado           = false;

// Variáveis auxiliares para leitura do botão de pulso e detecção de movimento
volatile unsigned long contadorCliquesBotao = 0;
unsigned long          ultimoCliqueMs       = 0;
unsigned long          janelaPulsoInicioMs  = 0;
int                    bpmIncrementoBotao   = 0;
float                  ultimaAceleracaoG    = 1.0;
int                    ciclosSemMovimento   = 0;
unsigned long          ultimaColetaMs       = 0;

// Interrupção de hardware (ISR) para capturar cliques no botão de pulso cardíaco
void IRAM_ATTR isrBotaoPulso() {
  unsigned long agora = millis();
  // Debounce de 120ms (suporta até ~500 bpm teóricos sem ruído mecânico)
  if (agora - ultimoCliqueMs > 120) {
    contadorCliquesBotao++;
    ultimoCliqueMs = agora;
  }
}

// ============================================================================
// 4. FUNÇÕES DE ARMAZENAMENTO LOCAL (SPIFFS + BUFFER CIRCULAR)
// ============================================================================

/**
 * Inicializa o sistema de arquivos SPIFFS na memória Flash do ESP32.
 */
void inicializarSPIFFS() {
  Serial.println(F("------------------------------------------------------------"));
  Serial.println(F("[EDGE-STORAGE] Inicializando sistema de arquivos SPIFFS..."));
  if (SPIFFS.begin(true)) {
    spiffsMontado = true;
    size_t totalBytes = SPIFFS.totalBytes();
    size_t usedBytes  = SPIFFS.usedBytes();
    Serial.printf("[EDGE-STORAGE] SPIFFS montado com sucesso! Total: %u bytes | Usado: %u bytes\n",
                  (unsigned int)totalBytes, (unsigned int)usedBytes);
    Serial.printf("[EDGE-STORAGE] Politica de Negocio CardioIA: Limite Flash = %u amostras (~640 KB) | Buffer RAM = %u amostras\n",
                  (unsigned int)LIMITE_AMOSTRAS_NEGOCIO_FLASH, (unsigned int)CAPACIDADE_BUFFER_RAM);
  } else {
    spiffsMontado = false;
    Serial.println(F("[EDGE-STORAGE] Aviso: SPIFFS indisponivel no simulador atual. Operando com Buffer Circular em RAM + Monitor Serial."));
  }
  Serial.println(F("------------------------------------------------------------"));
}

/**
 * Armazena uma leitura localmente no arquivo CSV do SPIFFS e no Buffer Circular.
 * Caso o limite de armazenamento seja atingido durante um período longo offline,
 * aplica a estratégia FIFO preservando eventos críticos.
 */
void armazenarLeituraOffline(const AmostraVital& amostra) {
  // 1. Gravação no Buffer Circular em RAM (com política de limite de amostras)
  if (totalAmostrasPendentes >= CAPACIDADE_BUFFER_RAM) {
    // Procura a amostra mais antiga que NÃO seja um alerta crítico para sobrescrever
    size_t indiceSubstituicao = indiceEscritaRAM;
    for (size_t i = 0; i < CAPACIDADE_BUFFER_RAM; i++) {
      size_t idx = (indiceEscritaRAM + i) % CAPACIDADE_BUFFER_RAM;
      if (!bufferOfflineRAM[idx].alerta_critico) {
        indiceSubstituicao = idx;
        break;
      }
    }
    bufferOfflineRAM[indiceSubstituicao] = amostra;
    indiceEscritaRAM = (indiceSubstituicao + 1) % CAPACIDADE_BUFFER_RAM;
    totalAmostrasSobrescritas++;
    Serial.printf("[EDGE-RESILIENCIA] Limite do buffer atingido (%u amostras). Aplicada politica FIFO com retencao de risco (sobrescritas: %u).\n",
                  (unsigned int)CAPACIDADE_BUFFER_RAM, (unsigned int)totalAmostrasSobrescritas);
  } else {
    bufferOfflineRAM[indiceEscritaRAM] = amostra;
    indiceEscritaRAM = (indiceEscritaRAM + 1) % CAPACIDADE_BUFFER_RAM;
    totalAmostrasPendentes++;
  }

  // 2. Gravação física no arquivo CSV do SPIFFS (se montado e abaixo do teto de negócio)
  if (spiffsMontado && totalAmostrasPendentes <= LIMITE_AMOSTRAS_NEGOCIO_FLASH) {
    bool escreverCabecalho = !SPIFFS.exists(ARQUIVO_SPIFFS);
    File arquivo = SPIFFS.open(ARQUIVO_SPIFFS, FILE_APPEND);
    if (arquivo) {
      if (escreverCabecalho) {
        arquivo.println("seq,timestamp_ms,paciente_id,temperatura_c,umidade_pct,bpm,aceleracao_g,movimento,alerta,detalhe_alerta");
      }
      arquivo.printf("%u,%lu,%s,%.1f,%.1f,%d,%.2f,%s,%s,%s\n",
                     amostra.sequencia,
                     amostra.timestamp_ms,
                     PACIENTE_ID,
                     amostra.temperatura_c,
                     amostra.umidade_pct,
                     amostra.batimentos_bpm,
                     amostra.aceleracao_g,
                     amostra.em_movimento ? "SIM" : "NAO",
                     amostra.alerta_critico ? "CRITICO" : "NORMAL",
                     amostra.descricao_alerta);
      arquivo.close();
    }
  }

  Serial.printf("[OFFLINE -> SPIFFS] Amostra #%u gravada localmente (%u/%u no buffer) | Temp: %.1f C | Umid: %.1f%% | BPM: %d | Mov: %s | Status: %s\n",
                amostra.sequencia,
                (unsigned int)totalAmostrasPendentes,
                (unsigned int)CAPACIDADE_BUFFER_RAM,
                amostra.temperatura_c,
                amostra.umidade_pct,
                amostra.batimentos_bpm,
                amostra.em_movimento ? "ATIVO" : "PARADO",
                amostra.descricao_alerta);
}

/**
 * Envia uma amostra diretamente para a nuvem (simulada via Serial.println JSON).
 */
void enviarAmostraParaNuvem(const AmostraVital& amostra, const char* origemEnvio) {
  Serial.printf("[NUVEM-SYNC | %s] {\"paciente_id\":\"%s\",\"paciente\":\"%s\",\"seq\":%u,\"timestamp_ms\":%lu,"
                "\"temperatura_c\":%.1f,\"umidade_pct\":%.1f,\"bpm\":%d,\"aceleracao_g\":%.2f,"
                "\"em_movimento\":%s,\"alerta_critico\":%s,\"diagnostico_borda\":\"%s\"}\n",
                origemEnvio,
                PACIENTE_ID,
                PACIENTE_NOME,
                amostra.sequencia,
                amostra.timestamp_ms,
                amostra.temperatura_c,
                amostra.umidade_pct,
                amostra.batimentos_bpm,
                amostra.aceleracao_g,
                amostra.em_movimento ? "true" : "false",
                amostra.alerta_critico ? "true" : "false",
                amostra.descricao_alerta);
}

/**
 * Sincroniza todos os dados armazenados offline assim que a conectividade Wi-Fi
 * é restabelecida e apaga o arquivo local no SPIFFS.
 */
void sincronizarDadosOfflineComNuvem() {
  if (totalAmostrasPendentes == 0 && (!spiffsMontado || !SPIFFS.exists(ARQUIVO_SPIFFS))) {
    return;
  }

  Serial.println(F("\n============================================================"));
  Serial.println(F("[RECONEXAO WI-FI DETECTADA] Iniciando sincronizacao de resiliencia offline..."));
  Serial.printf("[SYNC] Total de amostras retidas na borda (Edge): %u amostras\n",
                (unsigned int)totalAmostrasPendentes);

  // 1. Se o arquivo existir no SPIFFS, lê e exibe o conteúdo bruto do arquivo CSV
  if (spiffsMontado && SPIFFS.exists(ARQUIVO_SPIFFS)) {
    File arquivo = SPIFFS.open(ARQUIVO_SPIFFS, FILE_READ);
    if (arquivo) {
      Serial.println(F("[SPIFFS-READ] Lendo arquivo local /leituras_offline.csv:"));
      while (arquivo.available()) {
        String linha = arquivo.readStringUntil('\n');
        linha.trim();
        if (linha.length() > 0) {
          Serial.println("  [CSV] " + linha);
        }
      }
      arquivo.close();
    }
  }

  // 2. Transmite cada amostra estruturada em JSON para a nuvem via Serial.println
  size_t indiceInicial = (totalAmostrasPendentes < CAPACIDADE_BUFFER_RAM)
                         ? 0
                         : indiceEscritaRAM;

  for (size_t i = 0; i < totalAmostrasPendentes; i++) {
    size_t idx = (indiceInicial + i) % CAPACIDADE_BUFFER_RAM;
    enviarAmostraParaNuvem(bufferOfflineRAM[idx], "RESILIENCIA_OFFLINE");
  }

  // 3. Apaga o arquivo local no SPIFFS e limpa os ponteiros do buffer
  if (spiffsMontado && SPIFFS.exists(ARQUIVO_SPIFFS)) {
    if (SPIFFS.remove(ARQUIVO_SPIFFS)) {
      Serial.println(F("[SPIFFS-CLEAN] Arquivo local /leituras_offline.csv removido com sucesso apos sincronizacao!"));
    } else {
      Serial.println(F("[SPIFFS-CLEAN] Erro ao remover arquivo local /leituras_offline.csv."));
    }
  }

  indiceEscritaRAM          = 0;
  totalAmostrasPendentes    = 0;
  totalAmostrasSobrescritas = 0;

  Serial.println(F("[SYNC-CONCLUIDO] Todos os dados offline foram sincronizados com a nuvem!"));
  Serial.println(F("============================================================\n"));
}

// ============================================================================
// 5. LEITURA DOS SENSORES E PROCESSAMENTO NA BORDA (EDGE ANALYTICS)
// ============================================================================

/**
 * Atualiza o estado da variável booleana wifiConectado a partir da chave física
 * no circuito Wokwi (GPIO 18) ou de comandos digitados no Monitor Serial.
 */
void atualizarEstadoConectividade() {
  // Verifica comandos via Monitor Serial ("offline", "online", "auto")
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();
    comando.toLowerCase();
    if (comando == "offline" || comando == "0") {
      modoControleSerial = true;
      wifiConectado = false;
      Serial.println(F("[COMANDO SERIAL] Conectividade Wi-Fi alterada manualmente para: OFFLINE (false)"));
    } else if (comando == "online" || comando == "1") {
      modoControleSerial = true;
      wifiConectado = true;
      Serial.println(F("[COMANDO SERIAL] Conectividade Wi-Fi alterada manualmente para: ONLINE (true)"));
    } else if (comando == "auto") {
      modoControleSerial = false;
      Serial.println(F("[COMANDO SERIAL] Conectividade controlada pela chave fisica GPIO 18."));
    }
  }

  // Se não estiver travado por comando serial, lê a chave deslizante (Slide Switch)
  if (!modoControleSerial) {
    wifiConectado = (digitalRead(PIN_SW_WIFI) == HIGH);
  }

  // Atualiza LED de status Wi-Fi
  digitalWrite(PIN_LED_WIFI, wifiConectado ? HIGH : LOW);

  // Detecta mudança de estado (Transição Offline <-> Online)
  if (wifiConectado != wifiConectadoAnterior) {
    if (wifiConectado) {
      Serial.println(F("\n>>> [STATUS REDE] Wi-Fi CONECTADO (wifiConectado = true) <<<"));
      sincronizarDadosOfflineComNuvem();
    } else {
      Serial.println(F("\n>>> [STATUS REDE] Wi-Fi DESCONECTADO (wifiConectado = false) - Ativando Resiliencia Offline (Edge) <<<"));
    }
    wifiConectadoAnterior = wifiConectado;
  }
}

/**
 * Realiza a leitura dos 3 sensores (DHT22, Potenciômetro/Botão de BPM e MPU6050)
 * e executa a inferência de risco local (Edge Computing).
 */
AmostraVital coletarEProcessarSinaisVitais() {
  AmostraVital amostra;
  contadorSequenciaGlobal++;
  amostra.timestamp_ms = millis();
  amostra.sequencia    = contadorSequenciaGlobal;

  // 1. Leitura do Sensor Obrigatório DHT22 (Temperatura e Umidade)
  TempAndHumidity dadosDHT = sensorDHT.getTempAndHumidity();
  if (isnan(dadosDHT.temperature) || isnan(dadosDHT.humidity)) {
    amostra.temperatura_c = 36.6;
    amostra.umidade_pct   = 55.0;
  } else {
    amostra.temperatura_c = dadosDHT.temperature;
    amostra.umidade_pct   = dadosDHT.humidity;
  }

  // 2. Leitura do Sensor de Batimentos Cardíacos (Potenciômetro + Botão de Pulso)
  int leituraADC = analogRead(PIN_POT_BPM);
  // Mapeia o potenciômetro (0..4095) para faixa fisiológica (40..175 BPM)
  int bpmBasePotenciometro = map(leituraADC, 0, 4095, 40, 175);

  // Calcula bônus de BPM caso o usuário tenha pressionado o botão de pulso no último ciclo
  noInterrupts();
  unsigned long cliquesRecentes = contadorCliquesBotao;
  contadorCliquesBotao = 0;
  interrupts();

  if (cliquesRecentes > 0) {
    // Cada clique no botão adiciona estímulo cardíaco (ou simula frequência por cliques)
    bpmIncrementoBotao = min(80, bpmIncrementoBotao + (int)(cliquesRecentes * 12));
  } else {
    // Decaimento suave quando o botão não é pressionado
    bpmIncrementoBotao = max(0, bpmIncrementoBotao - 6);
  }
  amostra.batimentos_bpm = constrain(bpmBasePotenciometro + bpmIncrementoBotao, 35, 220);

  // 3. Leitura do Acelerômetro MPU6050 (Movimento / Atividade Física / Imobilidade)
  if (mpuDisponivel) {
    sensors_event_t a, g, tempMpu;
    sensorMPU.getEvent(&a, &g, &tempMpu);
    // Magnitude do vetor de aceleração em unidades de gravidade (g = 9.80665 m/s^2)
    float mag = sqrt(a.acceleration.x * a.acceleration.x +
                     a.acceleration.y * a.acceleration.y +
                     a.acceleration.z * a.acceleration.z) / 9.80665f;
    amostra.aceleracao_g = mag;
  } else {
    // Fallback caso o barramento I2C não responda
    amostra.aceleracao_g = 1.00f + (cliquesRecentes > 0 ? 0.35f : 0.01f);
  }

  float deltaAccel = fabs(amostra.aceleracao_g - ultimaAceleracaoG);
  ultimaAceleracaoG = amostra.aceleracao_g;

  if (deltaAccel < LIMITE_IMOBILIDADE_G && cliquesRecentes == 0) {
    ciclosSemMovimento++;
  } else {
    ciclosSemMovimento = 0;
  }
  amostra.em_movimento = (ciclosSemMovimento < CICLOS_PARA_IMOBILIDADE);

  // 4. Processamento Local na Borda (Edge Triage & Detecção de Risco)
  amostra.alerta_critico = false;
  strncpy(amostra.descricao_alerta, "SINAIS_ESTAVEIS", sizeof(amostra.descricao_alerta));

  bool taquicardia = (amostra.batimentos_bpm > LIMITE_TAQUICARDIA_BPM);
  bool bradicardia = (amostra.batimentos_bpm < LIMITE_BRADICARDIA_BPM);
  bool febre       = (amostra.temperatura_c > LIMITE_FEBRE_C);
  bool hipotermia  = (amostra.temperatura_c < LIMITE_HIPOTERMIA_C);
  bool imobilidade = (!amostra.em_movimento);

  if (taquicardia && febre) {
    amostra.alerta_critico = true;
    strncpy(amostra.descricao_alerta, "ALERTA_COMBINADO_TAQUICARDIA_E_FEBRE", sizeof(amostra.descricao_alerta));
  } else if (taquicardia) {
    amostra.alerta_critico = true;
    strncpy(amostra.descricao_alerta, "ALERTA_TAQUICARDIA_BPM_ALTO", sizeof(amostra.descricao_alerta));
  } else if (bradicardia) {
    amostra.alerta_critico = true;
    strncpy(amostra.descricao_alerta, "ALERTA_BRADICARDIA_BPM_BAIXO", sizeof(amostra.descricao_alerta));
  } else if (febre) {
    amostra.alerta_critico = true;
    strncpy(amostra.descricao_alerta, "ALERTA_FEBRE_HIPERTERMIA", sizeof(amostra.descricao_alerta));
  } else if (hipotermia) {
    amostra.alerta_critico = true;
    strncpy(amostra.descricao_alerta, "ALERTA_HIPOTERMIA", sizeof(amostra.descricao_alerta));
  } else if (imobilidade && (amostra.batimentos_bpm > 105 || amostra.batimentos_bpm < 55)) {
    amostra.alerta_critico = true;
    strncpy(amostra.descricao_alerta, "ALERTA_IMOBILIDADE_RISCO_SINCOPE", sizeof(amostra.descricao_alerta));
  }

  // Aciona imediatamente o LED de Alerta na Borda (independe de nuvem/Wi-Fi!)
  digitalWrite(PIN_LED_ALERTA, amostra.alerta_critico ? HIGH : LOW);

  return amostra;
}

// ============================================================================
// 6. SETUP E LOOP PRINCIPAL DO ESP32
// ============================================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println(F("\n============================================================"));
  Serial.println(F("   CARDIOIA - FASE 3 (PARTE 1: EDGE COMPUTING & SPIFFS)     "));
  Serial.println(F("   Grupo: Data Health Solutions - FIAP                      "));
  Serial.println(F("============================================================"));

  // Configuração dos pinos de I/O
  pinMode(PIN_BTN_PULSO, INPUT_PULLUP);
  pinMode(PIN_SW_WIFI, INPUT_PULLUP);
  pinMode(PIN_LED_WIFI, OUTPUT);
  pinMode(PIN_LED_ALERTA, OUTPUT);
  analogReadResolution(12);

  attachInterrupt(digitalPinToInterrupt(PIN_BTN_PULSO), isrBotaoPulso, FALLING);

  // Inicializa Sensor 1: DHT22
  sensorDHT.setup(PIN_DHT22, DHTesp::DHT22);
  Serial.println(F("[SENSOR 1] DHT22 (Temperatura e Umidade) inicializado no GPIO 15."));

  // Inicializa Sensor 2: Potenciômetro + Botão de Pulso Cardíaco
  Serial.println(F("[SENSOR 2] Monitor de Pulso/BPM inicializado no GPIO 34 (ADC) e GPIO 4 (Botao)."));

  // Inicializa Sensor 3: Acelerômetro e Giroscópio MPU6050
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  if (sensorMPU.begin()) {
    mpuDisponivel = true;
    sensorMPU.setAccelerometerRange(MPU6050_RANGE_8_G);
    sensorMPU.setGyroRange(MPU6050_RANGE_500_DEG);
    sensorMPU.setFilterBandwidth(MPU6050_BAND_21_HZ);
    Serial.println(F("[SENSOR 3] Acelerometro MPU6050 inicializado via I2C (GPIO 21/22)."));
  } else {
    mpuDisponivel = false;
    Serial.println(F("[SENSOR 3] MPU6050 em modo emulado (fallback de aceleracao ativo)."));
  }

  // Inicializa armazenamento local SPIFFS
  inicializarSPIFFS();

  // Lê estado inicial da conectividade Wi-Fi
  wifiConectado         = (digitalRead(PIN_SW_WIFI) == HIGH);
  wifiConectadoAnterior = wifiConectado;
  digitalWrite(PIN_LED_WIFI, wifiConectado ? HIGH : LOW);

  Serial.printf("[REDE] Estado inicial de conectividade Wi-Fi (wifiConectado): %s\n",
                wifiConectado ? "ONLINE (true)" : "OFFLINE (false)");
  Serial.println(F("[DICA] Use a chave deslizante (GPIO 18) no Wokwi ou digite 'offline' / 'online' no Monitor Serial.\n"));
}

void loop() {
  // 1. Verifica continuamente a conectividade e executa sincronização se reconectado
  atualizarEstadoConectividade();

  // 2. Coleta periódica dos sensores e processamento na borda (Edge Computing)
  unsigned long agora = millis();
  if (agora - ultimaColetaMs >= INTERVALO_COLETA_MS) {
    ultimaColetaMs = agora;

    AmostraVital amostra = coletarEProcessarSinaisVitais();

    if (wifiConectado) {
      // Se houver dados residuais offline, sincroniza antes de enviar o pacote atual
      if (totalAmostrasPendentes > 0) {
        sincronizarDadosOfflineComNuvem();
      }
      // Envia em tempo real para a nuvem via Serial.println
      enviarAmostraParaNuvem(amostra, "TEMPO_REAL");
    } else {
      // Modo Resiliência Offline: armazena localmente no SPIFFS e Buffer Circular
      armazenarLeituraOffline(amostra);
    }
  }

  delay(50);
}
