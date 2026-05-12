# Project Execution & Documentation Guide

This guide contains everything you need to run the **Smart Sentinel Barrier** project, configure it for different environments, and switch between AI processing modes.

---

## 🚀 Commands to Run the Project

### 1. Backend (Python/FastAPI)
The backend handles MQTT communication, AI processing (Local/Gemini), and the Alert History API.

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment (if not already done)
python -m venv venv

# Activate virtual environment
# On Windows:cked
.\venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the backend
uvicorn main:app --reload
```

### 2. Frontend (React/Vite)
The dashboard provides real-time monitoring and manual control.

```powershell
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```
for sumilator cd backend .\venv\Scripts\activate
then python simulator.py

### 3. Hardware (ESP32)
1. Open `hardware/esp32_barrier/esp32_barrier.ino` in the Arduino IDE.
2. Install required libraries: `PubSubClient`, `ESP32Servo`, `ArduinoJson`.
3. Configure `secrets.h` with your WiFi and MQTT details.
4. Select **ESP32 Dev Module** and click **Upload**.

---

## 🔧 Configuration & Switching Environments

### A. Switch Backend (Local vs Deployed)
The frontend connects to the backend using an environment variable.

1.  **Local Backend**: By default, it connects to `http://localhost:8000`.
2.  **Deployed Backend**: 
    - Create or edit `frontend/.env`.
    - Add the following line:
      ```env
      VITE_API_URL=https://your-deployed-backend-url.vercel.app
      ```
    - Restart the frontend dev server.

### B. Switch AI Processing (Local vs Gemini)
You can switch the AI engine "on the fly" without restarting anything.

1.  **Via Dashboard**:
    - Use the **Local AI** and **Gemini AI** toggle buttons in the header of the Sentinel Barrier dashboard.
2.  **Persistent Default**:
    - Open `backend/main.py`.
    - Change line 56: `ai_mode = "gemini"` or `ai_mode = "local"`.
3.  **Via MQTT**:
    - Publish to `barrier/ai_mode`: `{"mode": "gemini"}` or `{"mode": "local"}`.

---

## 📘 Project Documentation

### System Architecture
1.  **ESP32**: Measures distance every 500ms using an Ultrasonic sensor and publishes to MQTT.
2.  **MQTT Broker**: Acts as the central communication hub (`broker.emqx.io`).
3.  **Backend (FastAPI)**: 
    - Subscribes to distance data.
    - Runs a **Sliding Window** analysis (Local) or sends data to **Google Gemini** for classification.
    - Publishes classification updates back to MQTT.
    - Stores critical alerts in a SQLite database.
4.  **Frontend (React)**: 
    - Visualizes distance data using Recharts.
    - Displays AI status and historical alerts.
    - Sends manual control commands to the barrier.

### AI Classification Modes
-   **Local AI**: Uses a mathematical algorithm to calculate the `avg_diff` of distance readings. Very fast and requires no internet/API calls.
-   **Gemini AI**: Uses the `gemini-1.5-flash` model to analyze patterns in the last 6 readings. More robust to noise and can "understand" complex movement patterns.

### MQTT Topic Reference
| Topic | Description | Payload Example |
|---|---|---|
| `barrier/distance` | Live distance from ESP32 | `{"distance": 45.2, "timestamp": 123456}` |
| `barrier/ai_status` | Current classification | `{"status": "APPROACHING", "engine": "gemini"}` |
| `barrier/ai_mode` | Command to switch engine | `{"mode": "gemini"}` |
| `barrier/control` | Manual gate command | `{"command": "OPEN"}` |
| `barrier/config` | Change settings | `{"danger_threshold": 80}` |

---

## 🛠️ Requirements
-   **Python 3.9+**
-   **Node.js 18+**
-   **Arduino IDE** (with ESP32 board support)
-   **Gemini API Key** (Set in `backend/.env`)
