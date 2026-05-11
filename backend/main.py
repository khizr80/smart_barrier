import json
import os
import asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import paho.mqtt.client as mqtt
import google.generativeai as genai
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# --- Gemini API Setup ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# --- DB Setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./alerts.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AlertHistory(Base):
    __tablename__ = "alert_history"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, index=True)
    distance = Column(Integer)
    ai_engine = Column(String, default="local")
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- FastAPI Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- State & AI Logic ---
history = []
MAX_HISTORY = 6  # keep last 6 readings (last 3 seconds if 0.5s per reading)
DANGER_THRESHOLD = 60
ai_mode = "local"  # "local" or "gemini"

class Status:
    STATIONARY = "STATIONARY"
    APPROACHING = "APPROACHING"
    LINGERING = "LINGERING"
    MOVING_AWAY = "MOVING_AWAY"
    FAST_APPROACH = "FAST_APPROACH"

VALID_STATUSES = {Status.STATIONARY, Status.APPROACHING, Status.LINGERING, Status.MOVING_AWAY, Status.FAST_APPROACH}
current_ai_status = Status.STATIONARY

# ── LOCAL (Rule-Based) AI ─────────────────────────────────────────────────────
def analyze_local():
    """Original rule-based sliding-window algorithm."""
    if len(history) < 2:
        return None

    recent = history[-1]['distance']
    diffs = [history[i]['distance'] - history[i-1]['distance'] for i in range(1, len(history))]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0

    status = Status.STATIONARY

    if avg_diff < -10:
        status = Status.FAST_APPROACH
    elif avg_diff < -1:
        status = Status.APPROACHING
    elif avg_diff > 2:
        status = Status.MOVING_AWAY
    else:
        if recent < DANGER_THRESHOLD and len(history) == MAX_HISTORY:
            max_dist = max(h['distance'] for h in history)
            min_dist = min(h['distance'] for h in history)
            if max_dist - min_dist < 10:
                status = Status.LINGERING

    return status

# ── GEMINI AI ─────────────────────────────────────────────────────────────────
def analyze_gemini():
    """Send the distance history to Gemini and ask it to classify the movement."""
    if len(history) < 2:
        return None

    readings = [h['distance'] for h in history]
    prompt = f"""You are an AI monitoring a proximity sensor on an automatic barrier system.
You are given the last {len(readings)} distance readings (in cm) taken at 0.5-second intervals.
Readings (oldest → newest): {readings}
Danger zone threshold: {DANGER_THRESHOLD} cm

Based ONLY on these readings, classify the movement into exactly ONE of these labels:
- STATIONARY   (object not moving significantly, at any distance)
- APPROACHING  (object moving closer at a normal pace)
- FAST_APPROACH (object moving closer very rapidly)
- MOVING_AWAY  (object moving further away)
- LINGERING    (object staying very close to the sensor for a prolonged time, within the danger threshold)

Respond with ONLY the single label and nothing else. No punctuation, no explanation."""

    try:
        response = gemini_model.generate_content(prompt)
        label = response.text.strip().upper()
        if label in VALID_STATUSES:
            return label
        else:
            print(f"[Gemini] Unexpected label: '{label}', falling back to local.")
            return analyze_local()
    except Exception as e:
        print(f"[Gemini] API error: {e}. Falling back to local.")
        return analyze_local()

# ── Dispatcher ────────────────────────────────────────────────────────────────
def analyze_history():
    global current_ai_status

    if ai_mode == "gemini":
        status = analyze_gemini()
    else:
        status = analyze_local()

    if status is None:
        return

    if status != current_ai_status:
        current_ai_status = status
        mqtt_client.publish("barrier/ai_status", json.dumps({
            "status": current_ai_status,
            "engine": ai_mode
        }))

        if status in [Status.FAST_APPROACH, Status.LINGERING]:
            recent = history[-1]['distance']
            db = SessionLocal()
            db.add(AlertHistory(status=status, distance=int(recent), ai_engine=ai_mode))
            db.commit()
            db.close()

# --- MQTT Setup ---
BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
PORT = int(os.getenv("MQTT_PORT", "1883"))

def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to MQTT")
    client.subscribe("barrier/distance")
    client.subscribe("barrier/config")
    client.subscribe("barrier/control/mode")
    client.subscribe("barrier/ai_mode")

def on_message(client, userdata, msg):
    global DANGER_THRESHOLD, ai_mode
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())

        if topic == "barrier/distance":
            history.append(payload)
            if len(history) > MAX_HISTORY:
                history.pop(0)
            analyze_history()

        elif topic == "barrier/config":
            if "danger_threshold" in payload:
                DANGER_THRESHOLD = int(payload["danger_threshold"])
                print(f"[Config] Updated DANGER_THRESHOLD to {DANGER_THRESHOLD} cm")

        elif topic == "barrier/ai_mode":
            new_mode = payload.get("mode", "local").lower()
            if new_mode in ("local", "gemini"):
                ai_mode = new_mode
                print(f"[Config] AI mode switched to: {ai_mode.upper()}")
                # Acknowledge the switch back to the dashboard
                mqtt_client.publish("barrier/ai_mode/ack", json.dumps({"active_mode": ai_mode}))

    except Exception as e:
        print(f"Error processing message: {e}")

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "backend_ai_123")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

@app.on_event("startup")
async def startup_event():
    mqtt_client.connect(BROKER, PORT, 60)
    mqtt_client.loop_start()

@app.on_event("shutdown")
def shutdown_event():
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

# --- API Endpoints ---
@app.get("/api/alerts")
def get_alerts(limit: int = 20):
    db = SessionLocal()
    alerts = db.query(AlertHistory).order_by(AlertHistory.timestamp.desc()).limit(limit).all()
    db.close()
    return [
        {
            "id": a.id,
            "status": a.status,
            "distance": a.distance,
            "ai_engine": a.ai_engine,
            "timestamp": a.timestamp.isoformat()
        }
        for a in alerts
    ]

@app.get("/")
def health_check():
    return {"message": "backend works"}

@app.get("/api/status")
def get_status():
    return {"current_status": current_ai_status, "ai_mode": ai_mode}
