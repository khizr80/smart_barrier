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

# --- INITIALIZATION ---
# Load environment variables from .env file (GEMINI_API_KEY, MQTT_BROKER, etc.)
load_dotenv()

# --- GEMINI AI CONFIGURATION ---
# Get API Key from environment or fallback to placeholder
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
genai.configure(api_key=GEMINI_API_KEY)
# Using Gemini 1.5 Flash for fast, efficient pattern recognition
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# --- DATABASE CONFIGURATION (SQLite) ---
# Alert history is stored in a local SQLite file 'alerts.db'
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./alerts.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Session factory and Base class for SQLAlchemy models
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Model for historical alerts
class AlertHistory(Base):
    __tablename__ = "alert_history"
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, index=True)      # e.g., FAST_APPROACH, LINGERING
    distance = Column(Integer)               # Distance in cm when alert triggered
    ai_engine = Column(String, default="local") # Which AI made the decision
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create the table if it doesn't exist
Base.metadata.create_all(bind=engine)

# --- FASTAPI WEB SERVER SETUP ---
app = FastAPI(title="Smart Barrier Backend")

# Enable CORS so the React frontend (likely on port 5173) can talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GLOBAL STATE & AI LOGIC ---
history = []                # Stores the last 6 distance readings
MAX_HISTORY = 6             # Window size (approx 3 seconds of data)
DANGER_THRESHOLD = 60       # Distance (cm) below which alerts are active
ai_mode = "local"           # Default engine: "local" (rule-based) or "gemini" (LLM)

# Possible classification states
class Status:
    STATIONARY = "STATIONARY"
    APPROACHING = "APPROACHING"
    LINGERING = "LINGERING"
    MOVING_AWAY = "MOVING_AWAY"
    FAST_APPROACH = "FAST_APPROACH"

VALID_STATUSES = {Status.STATIONARY, Status.APPROACHING, Status.LINGERING, Status.MOVING_AWAY, Status.FAST_APPROACH}
current_ai_status = Status.STATIONARY

# ── LOCAL AI: Rule-Based Logic ────────────────────────────────────────────────
def analyze_local():
    """
    Analyzes movement patterns using a sliding window algorithm.
    Calculates the 'average difference' (velocity) over the last 6 readings.
    """
    if len(history) < 2:
        return None

    recent = history[-1]['distance']
    
    # Calculate differences between consecutive points
    diffs = [history[i]['distance'] - history[i-1]['distance'] for i in range(1, len(history))]
    avg_diff = sum(diffs) / len(diffs) if diffs else 0

    status = Status.STATIONARY

    # Threshold Logic:
    if avg_diff < -10:
        status = Status.FAST_APPROACH # Rapidly moving closer
    elif avg_diff < -1:
        status = Status.APPROACHING   # Normally moving closer
    elif avg_diff > 2:
        status = Status.MOVING_AWAY    # Moving further away
    else:
        # If speed is near zero but object is close, it might be lingering
        if recent < DANGER_THRESHOLD and len(history) == MAX_HISTORY:
            max_dist = max(h['distance'] for h in history)
            min_dist = min(h['distance'] for h in history)
            # Total variation < 10cm over 3 seconds means 'still'
            if max_dist - min_dist < 10:
                status = Status.LINGERING

    return status

# ── GEMINI AI: LLM Logic ──────────────────────────────────────────────────────
def analyze_gemini():
    """
    Sends the distance history array to Google Gemini.
    Asks the LLM to classify movement based on the provided patterns.
    """
    if len(history) < 2:
        return None

    readings = [h['distance'] for h in history]
    # Prompt instructs the AI on the exact labels and thresholds to use
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
            # Fallback to local if Gemini gives an invalid label
            print(f"[Gemini] Unexpected label: '{label}', falling back to local.")
            return analyze_local()
    except Exception as e:
        # Fallback to local if API is down or quota exceeded
        print(f"[Gemini] API error: {e}. Falling back to local.")
        return analyze_local()

# ── DISPATCHER: Coordination ──────────────────────────────────────────────────
def analyze_history():
    """Triggers the active AI engine and broadcasts results via MQTT."""
    global current_ai_status

    # Choose engine based on user preference
    if ai_mode == "gemini":
        status = analyze_gemini()
    else:
        status = analyze_local()

    if status is None:
        return

    # Only publish if the state actually changed (de-bouncing)
    if status != current_ai_status:
        current_ai_status = status
        # Notify the Frontend and ESP32 of the new status
        mqtt_client.publish("barrier/ai_status", json.dumps({
            "status": current_ai_status,
            "engine": ai_mode
        }))

        # If it's a critical alert, save it to the database for historical logs
        if status in [Status.FAST_APPROACH, Status.LINGERING]:
            recent = history[-1]['distance']
            db = SessionLocal()
            db.add(AlertHistory(status=status, distance=int(recent), ai_engine=ai_mode))
            db.commit()
            db.close()

# --- MQTT COMMUNICATION SETUP ---
BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
PORT = int(os.getenv("MQTT_PORT", "1883"))

def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to MQTT Broker")
    # Subscribe to all relevant topics
    client.subscribe("barrier/distance")      # Raw sensor data
    client.subscribe("barrier/config")        # Configuration changes (e.g. threshold)
    client.subscribe("barrier/control/mode")  # Auto/Manual toggle
    client.subscribe("barrier/ai_mode")       # Engine toggle (Local/Gemini)

def on_message(client, userdata, msg):
    """Main MQTT message handler (The "Brain" loop)"""
    global DANGER_THRESHOLD, ai_mode
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())

        # Scenario: New distance reading from ESP32
        if topic == "barrier/distance":
            history.append(payload)
            # Keep sliding window at MAX_HISTORY
            if len(history) > MAX_HISTORY:
                history.pop(0)
            # Run AI analysis on every new reading
            analyze_history()

        # Scenario: User moved the slider on the dashboard
        elif topic == "barrier/config":
            if "danger_threshold" in payload:
                DANGER_THRESHOLD = int(payload["danger_threshold"])
                print(f"[Config] Updated DANGER_THRESHOLD to {DANGER_THRESHOLD} cm")
                # Acknowledge back to UI so the slider stays in place
                mqtt_client.publish("barrier/config/ack", json.dumps({"danger_threshold": DANGER_THRESHOLD}))

        # Scenario: User switched between Local and Gemini AI
        elif topic == "barrier/ai_mode":
            new_mode = payload.get("mode", "local").lower()
            if new_mode in ("local", "gemini"):
                ai_mode = new_mode
                print(f"[Config] AI mode switched to: {ai_mode.upper()}")
                # Acknowledge back to UI
                mqtt_client.publish("barrier/ai_mode/ack", json.dumps({"active_mode": ai_mode}))

    except Exception as e:
        print(f"Error processing MQTT message: {e}")

# Initialize Paho MQTT Client
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "backend_ai_primary")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# FastAPI Lifecycle events for MQTT loop management
@app.on_event("startup")
async def startup_event():
    mqtt_client.connect(BROKER, PORT, 60)
    mqtt_client.loop_start()

@app.on_event("shutdown")
def shutdown_event():
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

# --- REST API ENDPOINTS ---

@app.get("/api/alerts")
def get_alerts(limit: int = 20):
    """Returns the most recent critical alerts from the database."""
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
    """Simple endpoint to verify the backend is running."""
    return {"message": "Sentinel Barrier Backend is Active", "version": "1.1"}

@app.get("/api/status")
def get_status():
    """Returns current system configuration and AI status."""
    return {
        "current_status": current_ai_status, 
        "ai_mode": ai_mode,
        "danger_threshold": DANGER_THRESHOLD
    }
