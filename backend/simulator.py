import time
import json
import random
import paho.mqtt.client as mqtt
from datetime import datetime

BROKER = "broker.emqx.io"
PORT = 1883
TOPIC_DISTANCE = "barrier/distance"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "simulator_esp32_123")
client.connect(BROKER, PORT, 60)
client.loop_start()

distance = 150 # Start far away

def publish_distance(dist):
    payload = {
        "distance": round(dist, 1),
        "timestamp": datetime.utcnow().isoformat()
    }
    client.publish(TOPIC_DISTANCE, json.dumps(payload))
    print(f"Published: {payload}")
    time.sleep(0.5)

print("Starting ESP32 Simulator...")

try:
    while True:
        # 1. STATIONARY (far)
        print("--- Mode: STATIONARY (Far) ---")
        for _ in range(6):
            distance += random.uniform(-1, 1)
            publish_distance(distance)

        # 2. APPROACHING (normal)
        print("--- Mode: APPROACHING ---")
        for _ in range(10):
            distance -= random.uniform(2, 5) # decrease 2-5 cm per tick
            publish_distance(distance)

        # 3. LINGERING
        print("--- Mode: LINGERING ---")
        for _ in range(15):
            distance += random.uniform(-1, 1)
            publish_distance(distance)

        # 4. MOVING AWAY
        print("--- Mode: MOVING AWAY ---")
        for _ in range(8):
            distance += random.uniform(5, 8)
            publish_distance(distance)

        # 5. FAST APPROACH
        print("--- Mode: FAST APPROACH ---")
        for _ in range(5):
            distance -= random.uniform(15, 20)
            publish_distance(distance)
            
        print("--- Resetting for next cycle ---")
        distance = 150
        publish_distance(distance)
        time.sleep(2)

except KeyboardInterrupt:
    print("Stopping.")
    client.loop_stop()
    client.disconnect()
