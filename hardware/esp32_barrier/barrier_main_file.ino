// ============================================================
//  SMART PROXIMITY-BASED AUTOMATIC BARRIER SYSTEM
//  ESP32 Main Sketch — Final Integrated Version
// ============================================================

#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// ── 🔧 CONFIGURATION ─────────────────────────────────────────
const char* WIFI_SSID      = "YOUR_WIFI_NAME";     // Change this
const char* WIFI_PASSWORD  = "YOUR_WIFI_PASSWORD"; // Change this
const char* MQTT_BROKER    = "broker.emqx.io";
const int   MQTT_PORT      = 1883;
const char* MQTT_CLIENT_ID = "esp32-sentinel-barrier";

// Toggle between real sensor and internal simulation
#define SIMULATION_MODE false 
// ─────────────────────────────────────────────────────────────

// ── 📍 PIN DEFINITIONS ───────────────────────────────────────
#define TRIG_PIN    5
#define ECHO_PIN    18
#define SERVO_PIN   13
#define BUZZER_PIN  12
// ─────────────────────────────────────────────────────────────

// ── MQTT TOPICS ──────────────────────────────────────────────
#define TOPIC_DISTANCE   "barrier/distance"
#define TOPIC_AI_STATUS  "barrier/ai_status"
#define TOPIC_CONTROL    "barrier/control"
// ─────────────────────────────────────────────────────────────

WiFiClient espClient;
PubSubClient mqttClient(espClient);
Servo barrierServo;

// ── STATE VARIABLES ──────────────────────────────────────────
String currentAIStatus = "STATIONARY";
unsigned long lastSensorRead = 0;
unsigned long lastBuzzerToggle = 0;
bool buzzerState = false;
int buzzerMode = 0; // 0=off, 1=medium (lingering), 2=fast (danger)

// Simulation variables
float simDist = 150.0;
int simPhase = 0;
int simStep = 0;

// ── FUNCTIONS ────────────────────────────────────────────────

void connectWiFi() {
  Serial.print("\nConnecting to WiFi: " + String(WIFI_SSID));
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[OK] WiFi Connected. IP: " + WiFi.localIP().toString());
}

void onMQTTMessage(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<200> doc;
  deserializeJson(doc, payload, length);
  
  String topicStr = String(topic);
  
  // 1. Handle AI status updates from backend
  if (topicStr == TOPIC_AI_STATUS) {
    currentAIStatus = doc["status"] | "STATIONARY";
    Serial.println("[AI] New Status: " + currentAIStatus);
    
    // Update Buzzer and Servo based on AI decision
    if (currentAIStatus == "FAST_APPROACH") {
      barrierServo.write(0); // Close
      buzzerMode = 2;        // Fast alert
    } 
    else if (currentAIStatus == "LINGERING") {
      barrierServo.write(0); // Close
      buzzerMode = 1;        // Warning alert
    } 
    else {
      barrierServo.write(90); // Open
      buzzerMode = 0;         // Silent
    }
  }
  
  // 2. Handle Manual Controls from Dashboard
  if (topicStr == TOPIC_CONTROL) {
    String cmd = doc["command"] | "";
    if (cmd == "OPEN") barrierServo.write(90);
    else if (cmd == "CLOSED") barrierServo.write(0);
  }
}

void reconnectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("connected");
      mqttClient.subscribe(TOPIC_AI_STATUS);
      mqttClient.subscribe(TOPIC_CONTROL);
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" try again in 5s");
      delay(5000);
    }
  }
}

float readRealDistance() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return 400.0; // Out of range
  return (duration * 0.0343) / 2.0;
}

float readSimulatedDistance() {
  if (simPhase == 0) { // Stationary
    simDist += random(-10, 11) / 10.0;
    if (++simStep > 10) { simPhase = 1; simStep = 0; }
  } else if (simPhase == 1) { // Approach
    simDist -= random(20, 51) / 10.0;
    if (simDist < 40) { simPhase = 2; simStep = 0; }
  } else if (simPhase == 2) { // Linger
    simDist += random(-5, 6) / 10.0;
    if (++simStep > 15) { simPhase = 3; simStep = 0; }
  } else { // Reset
    simDist = 150.0; simPhase = 0;
  }
  return simDist;
}

void handleBuzzer() {
  if (buzzerMode == 0) {
    digitalWrite(BUZZER_PIN, LOW);
    return;
  }
  unsigned long interval = (buzzerMode == 2) ? 100 : 300;
  if (millis() - lastBuzzerToggle > interval) {
    lastBuzzerToggle = millis();
    buzzerState = !buzzerState;
    digitalWrite(BUZZER_PIN, buzzerState ? HIGH : LOW);
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  ESP32PWM::allocateTimer(0);
  barrierServo.setPeriodHertz(50);
  barrierServo.attach(SERVO_PIN, 500, 2400);
  barrierServo.write(90); // Default Open

  connectWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(onMQTTMessage);
}

void loop() {
  if (!mqttClient.connected()) reconnectMQTT();
  mqttClient.loop();
  
  handleBuzzer();

  unsigned long now = millis();
  if (now - lastSensorRead > 500) {
    lastSensorRead = now;
    
    float distance = SIMULATION_MODE ? readSimulatedDistance() : readRealDistance();
    
    StaticJsonDocument<100> doc;
    doc["distance"] = round(distance * 10) / 10.0;
    doc["timestamp"] = now;
    char buffer[100];
    serializeJson(doc, buffer);
    mqttClient.publish(TOPIC_DISTANCE, buffer);
    
    Serial.printf("Dist: %.1f cm | Mode: %s\n", distance, SIMULATION_MODE ? "SIM" : "REAL");
  }
}
