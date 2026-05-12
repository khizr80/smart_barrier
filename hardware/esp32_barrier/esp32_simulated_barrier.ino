#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// --- 🔧 CONFIGURATION (Hardcoded - No secrets.h needed) ---
const char* ssid = "YOUR_WIFI_SSID";         // Replace with your WiFi Name
const char* password = "YOUR_WIFI_PASSWORD"; // Replace with your WiFi Password
const char* mqtt_server = "broker.emqx.io";   // MQTT Broker
const int mqtt_port = 1883;                   // MQTT Port

// --- Hardware Pins ---
const int servoPin = 13;
const int buzzerPin = 12;

// --- Objects & Variables ---
WiFiClient espClient;
PubSubClient client(espClient);
Servo gateServo;

float simulatedDistance = 150.0;
unsigned long lastUpdate = 0;
String currentStatus = "STATIONARY";
int simMode = 0; // 0:Stationary, 1:Approach, 2:Linger, 3:Away, 4:Fast
int simStep = 0;

void setup_wifi() {
  delay(10);
  Serial.print("\nConnecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());
}

void callback(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<200> doc;
  deserializeJson(doc, payload, length);
  
  String topicStr = String(topic);
  if (topicStr == "barrier/ai_status") {
    currentStatus = doc["status"] | "STATIONARY";
    Serial.println("AI Decision Received: " + currentStatus);
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "ESP32-Simulator-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("connected");
      client.subscribe("barrier/ai_status");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5s");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(buzzerPin, OUTPUT);
  
  // Servo Setup
  ESP32PWM::allocateTimer(0);
  gateServo.setPeriodHertz(50);
  gateServo.attach(servoPin, 500, 2400);
  gateServo.write(90); // Start Open

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  unsigned long now = millis();

  // --- 1. Simulation Logic (Runs every 500ms) ---
  if (now - lastUpdate > 500) {
    lastUpdate = now;

    if (simMode == 0) { // STATIONARY (Far)
      simulatedDistance += random(-10, 11) / 10.0;
      if (++simStep > 10) { simMode = 1; simStep = 0; }
    } 
    else if (simMode == 1) { // APPROACHING
      simulatedDistance -= random(20, 51) / 10.0;
      if (simulatedDistance < 40) { simMode = 2; simStep = 0; }
    }
    else if (simMode == 2) { // LINGERING
      simulatedDistance += random(-5, 6) / 10.0;
      if (++simStep > 15) { simMode = 3; simStep = 0; }
    }
    else if (simMode == 3) { // MOVING AWAY
      simulatedDistance += random(50, 81) / 10.0;
      if (simulatedDistance > 140) { simMode = 4; simStep = 0; }
    }
    else if (simMode == 4) { // FAST APPROACH
      simulatedDistance -= random(150, 201) / 10.0;
      if (simulatedDistance < 20) { 
        simMode = 0; 
        simStep = 0; 
        simulatedDistance = 150.0; 
      }
    }

    // Publish simulated distance to MQTT
    StaticJsonDocument<100> doc;
    doc["distance"] = round(simulatedDistance * 10) / 10.0;
    doc["timestamp"] = now;
    char buffer[100];
    serializeJson(doc, buffer);
    client.publish("barrier/distance", buffer);
    
    Serial.printf("Published Simulated Dist: %.1f cm | Mode: %d\n", simulatedDistance, simMode);
  }

  // --- 2. Actuator Logic (Reacting to Backend AI) ---
  if (currentStatus == "FAST_APPROACH" || currentStatus == "LINGERING") {
    gateServo.write(0); // Close the barrier
    digitalWrite(buzzerPin, HIGH); // Alarm ON
  } 
  else {
    gateServo.write(90); // Open the barrier
    digitalWrite(buzzerPin, LOW); // Alarm OFF
  }
}
