# Smart Barrier – Deployment & Testing Guide

## Overview
This document explains how to **deploy** the Smart Barrier system and how to **test** it locally using the provided ESP32 simulator.

---

## 1. Project Structure
```
smart_barrier/
├─ backend/          # FastAPI server, MQTT handling, AI logic
│   ├─ main.py
│   ├─ simulator.py   # MQTT distance simulator (ESP32‑like)
│   ├─ .env.example
│   └─ requirements.txt
├─ frontend/         # React + Vite dashboard
│   ├─ src/
│   ├─ vite.config.js
│   └─ package.json
├─ hardware/         # Arduino/ESP32 firmware (optional)
└─ README.md         # High‑level project description
```

---

## 2. Local Development (quick start)
### Prerequisites
- **Python 3.9+**
- **Node 18+** and **npm**
- **Git**
- An internet connection (MQTT broker `broker.emqx.io` is public)

### Backend
```bash
cd backend
# 1️⃣ Create a virtual environment
python -m venv venv
# 2️⃣ Activate it (Windows)
venv\Scripts\activate
# 3️⃣ Install dependencies
pip install -r requirements.txt
# 4️⃣ Set environment variables – copy the example file
cp .env.example .env   # edit .env and add your Gemini API key
# 5️⃣ Run the server (hot‑reload)
uvicorn main:app --reload
```
The API will be reachable at `http://127.0.0.1:8000`.

### ESP32 Simulator (already provided)
```bash
# In a second terminal, with the same venv activated:
python simulator.py
```
The simulator publishes distance readings to `barrier/distance` every 0.5 s.

### Frontend
```bash
cd ../frontend
npm install            # first time only
npm run dev            # Vite dev server → http://localhost:5173
```
The dashboard connects to the MQTT broker over WebSockets (`wss://broker.emqx.io:8084/mqtt`).

---

## 3. Deploying the Backend to Render (free tier)
Render offers a **static‑IP, always‑on** environment suitable for MQTT clients.
1. **Create a GitHub repo** (push the current `smart_barrier` folder).
2. Sign‑up at <https://render.com> and **Create a New Web Service**.
3. **Connect** the repo and select **Python** as the runtime.
4. **Build Command**:
   ```bash
   pip install -r backend/requirements.txt
   ```
5. **Start Command** (Render runs the command in the repo root, so we prefix the path):
   ```bash
   uvicorn backend/main:app --host 0.0.0.0 --port $PORT
   ```
6. **Environment Variables** – add the following in Render’s dashboard:
   - `GEMINI_API_KEY` – your Google Gemini key
   - `MQTT_BROKER` – `broker.emqx.io`
   - `MQTT_PORT` – `1883`
   - `DATABASE_URL` – leave default (`sqlite:///./alerts.db`) **or** set a PostgreSQL URL if you add a Render Postgres instance.
7. Click **Create Web Service**. Render will build and launch the API.
8. Note the generated URL, e.g. `https://smart-barrier-backend.onrender.com`.

### Updating Frontend to Use Remote Backend
In `frontend/src/App.jsx` replace the hard‑coded API base:
```js
const API_BASE = "http://localhost:8000"; // change to
const API_BASE = "https://<your‑render‑url>";
```
Re‑build the frontend (see section 4).

---

## 4. Deploying the Frontend to Vercel (free tier)
1. **Install Vercel CLI** (optional) or use the Vercel web UI.
2. In the repository root, run:
   ```bash
   cd frontend
   npm install
   npm run build   # creates a production bundle in dist/
   ```
3. Push the `frontend` folder to GitHub (or connect the existing repo).
4. In Vercel, **Create a New Project**, select the repo, and set the **Root Directory** to `frontend`.
5. Vercel automatically detects a Vite project. No additional build steps are needed – it will run `npm run build`.
6. After deployment, Vercel provides a live URL, e.g. `https://smart-barrier.vercel.app`.

---

## 5. Full‑System Test (after deployment)
1. **Backend** – confirm the health endpoint:
   ```bash
   curl https://<render‑url>/api/status
   ```
2. **Frontend** – open the Vercel URL in a browser. You should see the dashboard.
3. **Simulator** – still run locally (or on any machine) with the same MQTT broker. The dashboard will receive live data from the simulator.
4. **Switch AI Engine** – use the toggle in the top‑right corner; if you have a Gemini key the backend will call the Gemini API, otherwise it falls back to the local rule‑based engine.
5. **Adjust Danger Threshold** – slide the control; the backend will respect the new threshold instantly.

---

## 6. Optional: Deploying a Real ESP32
If you have the hardware, flash `hardware/esp32_barrier/esp32_barrier.ino` via the Arduino IDE. Make sure `secrets.h` contains your Wi‑Fi SSID and password. The ESP32 will connect to the public MQTT broker and publish to `barrier/distance` just like the simulator.

---

## 7. Frequently Asked Questions
| Question | Answer |
|---|---|
| **Do I need a paid Render plan for the SQLite DB?** | No. The free tier provides a persistent file system, which works with SQLite. For larger scale you can switch to a Render Postgres instance and set `DATABASE_URL` accordingly. |
| **Can I run the backend on Vercel instead of Render?** | Vercel’s serverless functions have a maximum execution time (≈10 s) and do not maintain a persistent MQTT client, so they are unsuitable for this use case. |
| **What if the public MQTT broker is blocked?** | You can spin up a small Mosquitto container on Render (free tier) and point `MQTT_BROKER`/`MQTT_PORT` to it. |
| **Do I need to rebuild the frontend after changing API URL?** | Yes – the API URL is compiled into the bundle. Run `npm run build` again before redeploying to Vercel. |

---

## 8. Quick Reference – Environment Variables
| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(none)* | Your Google Gemini API key – required for Gemini AI mode |
| `MQTT_BROKER` | `broker.emqx.io` | Hostname of the MQTT broker |
| `MQTT_PORT` | `1883` | TCP port for MQTT (use `8084` for WebSocket if you want a secure WS endpoint) |
| `DATABASE_URL` | `sqlite:///./alerts.db` | SQLAlchemy connection string – can be PostgreSQL for production |
| `AI_MODE` | `local` | Default AI engine (`local` or `gemini`) |

---

## 9. Gotchas & Tips
- **CORS** – the backend already allows `*`. If you lock it down, add the Vercel domain to `allow_origins`.
- **WebSocket MQTT** – Vercel’s dev server runs on `http://localhost:5173`; the frontend connects to `wss://broker.emqx.io:8084/mqtt`. No extra configuration needed.
- **SQLite persistence on Render** – files in the `/` root are persisted between restarts. Do not write to `/tmp`.
- **Logging** – backend prints to stdout; Render captures logs automatically. Use the Render dashboard to view them.

---

## 10. License & Contributing
This project is released under the MIT License. Feel free to fork, open issues, or submit pull requests.

---

*Happy hacking! 🚀*
