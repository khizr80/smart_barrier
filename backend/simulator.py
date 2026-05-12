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
        # --- MODE 1: STATIONARY (Idle) ---
        # Logic: Small fluctuations between -1 and +1 cm.
        # Result: Backend avg_diff will be near 0. Classification -> STATIONARY.
        print("--- Mode: STATIONARY (Far) ---")
        for _ in range(6):
            distance += random.uniform(-1, 1)
            publish_distance(distance)

        # --- MODE 2: APPROACHING (Normal) ---
        # Logic: Decreasing distance by 2-5 cm every 0.5s.
        # Threshold: Backend triggers APPROACHING if avg_diff is < -1 cm.
        print("--- Mode: APPROACHING ---")
        for _ in range(10):
            distance -= random.uniform(2, 5) # decrease 2-5 cm per tick
            publish_distance(distance)

        # --- MODE 3: LINGERING (Danger Zone) ---
        # Logic: Staying still (fluctuation -1 to +1) while distance is likely < 60cm.
        # Threshold: Backend triggers LINGERING if distance < 60 and max_diff < 10.
        print("--- Mode: LINGERING ---")
        for _ in range(15):
            distance += random.uniform(-1, 1)
            publish_distance(distance)

        # --- MODE 4: MOVING AWAY ---
        # Logic: Increasing distance by 5-8 cm every 0.5s.
        # Threshold: Backend triggers MOVING_AWAY if avg_diff is > 2 cm.
        print("--- Mode: MOVING AWAY ---")
        for _ in range(8):
            distance += random.uniform(5, 8)
            publish_distance(distance)

        # --- MODE 5: FAST APPROACH (Emergency/Speeding) ---
        # Logic: Decreasing distance very quickly (15-20 cm per 0.5s).
        # Threshold: Backend triggers FAST_APPROACH if avg_diff is < -10 cm.
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
