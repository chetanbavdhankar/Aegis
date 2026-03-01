# 🛡️ AEGIS — AI Emergency Guidance & Intelligence System

> **224 people died in Valencia because the alert came 12 hours too late. AEGIS ensures the next disaster doesn't repeat that failure.**

AEGIS is a crisis intelligence platform that bridges the gap between citizens in distress and local emergency responders — across any language barrier. It captures emergency reports via Telegram, processes them using Mistral AI (structured extraction + agentic web verification), and displays them on a real-time Leaflet.js triage dashboard. Responders can broadcast voice-synthesized alerts back to victims via ElevenLabs in their native language.

---

## Architecture

```
CITIZEN (Telegram)                           RESPONDER (Web Dashboard)
─────────────────                            ────────────────────────

"Hilfe! Wasser steigt!"  ──► bot.py ──────►  🔴 Red pin on live map
  (German, any language)     │                  + Italian summary
                             │                  + Verification flag
                             ▼
                      ┌─────────────┐
                      │  Mistral AI  │        Responder types Italian
                      │  JSON Mode   │        evacuation order
                      └──────┬──────┘              │
                             │                     ▼
                      ┌──────▼──────┐        ┌──────────────┐
                      │  SQLite DB  │◄───────│  app.py      │
                      │  (WAL mode) │        │  Flask server │
                      └──────┬──────┘        └──────┬───────┘
                             │                      │
                      ┌──────▼──────┐        ┌──────▼───────┐
                      │  agent.py   │        │ tts_gateway   │
                      │  web_search │        │ (ElevenLabs)  │
                      │  verify     │        └──────┬───────┘
                      └─────────────┘               │
                                                    ▼
Tourist receives:                          Voice + Text in GERMAN
"Evakuieren Sie über den Hügel..." 🔊     ◄── Telegram Bot API
```

### Two-Process Design

| Process | File | Purpose |
|---------|------|---------|
| **Process 1** | `backend/bot.py` | Telegram polling loop — receives distress messages, extracts via Mistral, saves to DB |
| **Process 2** | `backend/app.py` | Flask HTTP server — serves dashboard, API endpoints, handles broadcasts |

Both processes share the same `aegis.db` file safely via **SQLite WAL mode**.

---

## File Structure

```
Aegis/
├── backend/
│   ├── __init__.py         # Package marker
│   ├── config.py           # Centralized settings (loads .env)
│   ├── db.py               # SQLite init, thread-safe CRUD, WAL mode
│   ├── llm_gateway.py      # Mistral wrapper: extraction + translation
│   ├── agent.py            # Verification agent (web_search tool calling)
│   ├── tts_gateway.py      # TTS dispatch (ElevenLabs / Text-Only)
│   ├── bot.py              # Telegram bot (Process 1)
│   └── app.py              # Flask server (Process 2)
├── frontend/
│   ├── index.html          # Primary dashboard (standalone, API-connected)
│   ├── myversion.html      # Prototype: Tactical OS terminal theme
│   ├── mynewversion.html   # Prototype: Modern glass UI theme
│   ├── index-cyberpunk.html  # Prototype: Cyberpunk neon teal theme
│   ├── cyberpunkversion.html # Prototype: Cyberpunk neon amber theme
│   └── README.md           # Frontend documentation
├── templates/
│   └── index.html          # Flask-served Leaflet.js triage dashboard
├── .env.example            # Template for environment variables
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- Telegram Bot token (from [@BotFather](https://t.me/BotFather))
- Mistral API key ([console.mistral.ai](https://console.mistral.ai))
- ElevenLabs API key (optional, for voice alerts)

### 2. Install Dependencies

```bash
cd Aegis
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 4. Run (Two Terminals)

**Terminal 1 — Telegram Bot:**
```bash
python -m backend.bot
```

**Terminal 2 — Flask Dashboard:**
```bash
python -m backend.app
```

### 5. Access Dashboard

Open `http://localhost:5000` in your browser.

### 6. Deploy with Ngrok (Optional)

```bash
ngrok http 5000
```
Submit the generated HTTPS URL to judges.

---

## Usage

### Sending a Distress Signal
1. Open Telegram, search for your bot
2. Send `/start` to register
3. Send any emergency message in any language
4. Share your 📍 location via Telegram's attachment menu
5. Your alert appears on the dashboard within seconds

### Responding to Alerts
1. Open the dashboard at `http://localhost:5000`
2. Click any alert pin on the map for full details
3. Switch to the **Broadcast** tab
4. Type your message, select output mode (ElevenLabs or Text-Only)
5. Click **Send Broadcast** — all registered users receive the alert in their language

---

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Citizen Interface | Telegram Bot API (`python-telegram-bot` v20+) | Zero install, native GPS, low bandwidth |
| LLM | Mistral Large (JSON mode + tool use) | Structured extraction, multilingual |
| Verification | Mistral Agent + `web_search` tool | Agentic credibility check |
| Voice | ElevenLabs multilingual v2 | Natural multilingual TTS |
| Dashboard | Flask + Leaflet.js + CARTO dark tiles | Premium real-time crisis map |
| Database | SQLite (WAL mode) | Zero setup, file-based |

---

## Key Design Decisions

| Decision | Reasoning |
|----------|-----------|
| **WAL mode + write lock** | Prevents "database is locked" errors in the dual-process architecture |
| **Telegram native GPS** | Never rely on LLM-guessed coordinates — use real lat/lng from device |
| **JSON mode extraction** | Structured output = reliable pipeline, no parsing failures |
| **Explicit TTS mode selection** | Responder controls tool choice — no cascading API fallback chain |
| **Background verification thread** | Agent verification runs asynchronously so user acknowledgment isn't delayed |

---

## Recent Enhancements (March 2026)

*   **Comprehensive Audit Logs:** Implemented `alert_logs` table for tracking the entire lifecycle of an incident across all system actors (Citizen, AI Agent, Dashboard Responder).
*   **Resolution Feedback Loop:** Automatically dispatches a Telegram poll to victims when an alert is marked 'Resolved', closing the loop on support effectiveness and updating the dashboard dynamically.
*   **Contact Information Capture:** `/start` flow now securely requests Telegram profile info + native phone number sharing for emergency out-of-band contact.
*   **Message Deduplication:** Implemented strict DB-level checking (`db.is_duplicate_message`) to prevent UI clutter from duplicate texts caused by network retries or bot restarts.
*   **Targeted Broadcasts:** The dashboard now supports selective messaging to specific victims from the Broadcast panel, translating outbound messages into their native languages.

## Technical Debt Log

| Item | Priority | Notes |
|------|----------|-------|
| Migrate to PostgreSQL + PostGIS | High | Required for production concurrency and geospatial queries |
| Add Celery + Redis task queue | High | LLM/TTS calls block under load; async workers needed |
| GDPR auto-deletion | Medium | PII (GPS, messages, phone numbers) must be purged after retention period |
| Rate limiting | Medium | Protect API budgets from spam |
| Switch to Telegram webhooks | Low | Polling is fine for demo; webhooks better at scale |
