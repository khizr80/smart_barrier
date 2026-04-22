#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include <time.h>
#include "secrets.h"

// Variables are now loaded from secrets.h
// const char* ssid = ...;
// const char* password = ...;
// const char* mqtt_server = ...;
// const int mqtt_port = ...;

// --- Hardware Pins ---
const int trigPin = 5;
const int echoPin = 18;
const int servoPin = 13;
const int buzzerPin = 12;

// --- Objects & Variables ---
WiFiClient espClient;
PubSubClient client(espClient);
Servo gateServo;

long duration;
float distance;
unsigned long lastMsg = 0;
String currentStatus = "STATIONARY";
unsigned long lastBuzzerToggle = 0;
bool buzzerState = false;

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
    Serial.println("AI Status Update: " + currentStatus);
  } 
  else if (topicStr == "barrier/control") {
    String cmd = doc["command"] | "";
    if (cmd == "OPEN") gateServo.write(90);
    else if (cmd == "CLOSED") gateServo.write(0);
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "ESP32-Barrier-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("connected");
      client.subscribe("barrier/ai_status");
      client.subscribe("barrier/control");
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
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  
  ESP32PWM::allocateTimer(0);
  gateServo.setPeriodHertz(50);
  gateServo.attach(servoPin, 500, 2400);
  gateServo.write(90); // Open by default

  setup_wifi();
  configTime(0, 0, "pool.ntp.org"); // Sync time for logs
  
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  unsigned long now = millis();
  
  // 1. Measure Distance every 500ms
  if (now - lastMsg > 500) {
    lastMsg = now;
    digitalWrite(trigPin, LOW); delayMicroseconds(2);
    digitalWrite(trigPin, HIGH); delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    duration = pulseIn(echoPin, HIGH);
    distance = duration * 0.034 / 2;
    
    // Publish to MQTT
    StaticJsonDocument<100> outDoc;
    outDoc["distance"] = round(distance * 10) / 10.0;
    outDoc["timestamp"] = now; 
    char buffer[100];
    serializeJson(outDoc, buffer);
    client.publish("barrier/distance", buffer);
  }

  // 2. Actuator Logic
  if (currentStatus == "FAST_APPROACH") {
    gateServo.write(0); // Close
    digitalWrite(buzzerPin, HIGH); // Continuous beep
  } 
  else if (currentStatus == "LINGERING") {
    gateServo.write(0); // Close
    if (now - lastBuzzerToggle > 300) {
      lastBuzzerToggle = now;
      buzzerState = !buzzerState;
      digitalWrite(buzzerPin, buzzerState ? HIGH : LOW);
    }
  } 
  else {
    gateServo.write(90); // Open
    digitalWrite(buzzerPin, LOW);
  }
}
