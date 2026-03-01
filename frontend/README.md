# AEGIS — Frontend Dashboard

This folder contains all HTML-based dashboard interfaces for the **AEGIS Crisis Intelligence Platform**. Each file is a self-contained, single-page application (HTML + CSS + JS) that can connect to the Flask backend and render real-time emergency alerts on an interactive Leaflet.js map.

---

## Files Overview

| File | Title | Theme | Backend Integration | Status |
|------|-------|-------|---------------------|--------|
| `index.html` | AEGIS — Crisis Intelligence | Minimal black / monochrome | ✅ Live (`/api/alerts`, `/api/broadcast`) | **Primary** |
| `myversion.html` | AEGIS OS // Tactical Crisis Terminal | Dark OS / military terminal | Mock data | Design prototype |
| `mynewversion.html` | AEGIS // Crisis Management Platform | Dark glass / modern | Mock data | Design prototype |
| `index-cyberpunk.html` | AEGIS Crisis Intelligence Terminal | Cyberpunk / neon teal | Mock data | Design prototype |
| `cyberpunkversion.html` | AEGIS Crisis Intelligence Terminal | Cyberpunk / neon amber | Mock data | Design prototype |

---

## Primary Dashboard: `index.html`

The production-ready interface. Connects to the Flask backend and renders live data.

### Features
- **Live alert feed** — polls `GET /api/alerts` on load and after each submission
- **Leaflet.js map** — plots incident pins colored by severity (Critical / Warning / Safe)
- **Alert triage panel** — sidebar listing incoming alerts with timestamps, location, and severity
- **Emergency report input** — submit new alerts directly from the dashboard
- **Chart.js trend chart** — rolling alert volume visualization
- **Stars background** — subtle animated star field for ambient UI

### API Endpoints Consumed

The dashboard communicates with the Flask server (`backend/app.py`). The full API surface is:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/alerts` | Fetch all active alerts (with enriched user info) |
| `GET` | `/api/alerts/<id>/messages` | Fetch chat message history for an alert |
| `GET` | `/api/alerts/<id>/logs` | Fetch audit log for an alert |
| `GET` | `/api/users` | Fetch all registered users with contact info |
| `PATCH` | `/api/alerts/<id>/status` | Update alert status (`active` / `escalated` / `resolved`) |
| `POST` | `/api/broadcast` | Translate + TTS + broadcast to all (or selected) users |
| `POST` | `/api/send_message` | Send a direct message to a specific user |

> ⚠️ **Port note:** `index.html` currently has the API base URL hardcoded to `http://localhost:8000`. The Flask server default port (set in `backend/config.py` and `.env`) is **`5000`**. If running locally with defaults, update the two `fetch(...)` calls in `index.html` to point to `http://localhost:5000`, or set `FLASK_PORT=8000` in your `.env`.

### Dependencies (CDN — no build step required)

```html
<!-- Map -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

<!-- Charts -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<!-- Fonts -->
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
```

---

## Design Prototypes

All prototype files are fully functional standalone HTML dashboards using **mock/simulated alert data**. They were created during the UI design phase to explore different visual identities for AEGIS. None require a running backend.

### `myversion.html` — Tactical OS Terminal
- Boot sequence animation on load with scrolling log output
- Military-grade dark OS aesthetic with scanlines and CRT effects
- Sidebar alert feed with color-coded severity chips
- Chart.js trend chart for alert volumes
- Real-time clock

### `mynewversion.html` — Modern Glass UI
- Clean dark-glass panel layout
- Alert feed with smooth entry animations
- Chart.js trend visualization
- Toast notification system for incoming alerts
- Real-time clock

### `index-cyberpunk.html` — Cyberpunk Neon (Teal)
- High-contrast teal-on-dark cyberpunk palette
- Alert severity progress bars (Critical / Warning / Safe)
- Live trend chart
- Emergency broadcast input panel
- Verified alert counter and real-time statistics bar

### `cyberpunkversion.html` — Cyberpunk Neon (Amber/Orange)
- Warm amber/orange cyberpunk color scheme
- Boot scan overlay animation on load
- Slide-in notification system
- Compact system-status sidebar
- Alert severity breakdown bar

---

## Relationship to `templates/index.html`

Flask serves HTML from the `templates/` directory (not this `frontend/` folder). Here is how they relate:

```
Aegis/
├── templates/
│   └── index.html     ← Flask serves this at GET / (Jinja2, production)
└── frontend/
    ├── index.html     ← Standalone dev copy; same dashboard logic, no Jinja2
    ├── myversion.html
    ├── mynewversion.html
    ├── index-cyberpunk.html
    └── cyberpunkversion.html
```

To update the live production dashboard, edit `templates/index.html`. The `frontend/index.html` copy is useful for local development and iteration without running the full Flask server.

---

## Running the Dashboard Standalone

To preview any file without the Flask backend:

```bash
# Serve locally to avoid CORS issues
python -m http.server 3000
# Then open: http://localhost:3000/frontend/index.html
```

The dashboard will show an empty map and alert feed until `backend/app.py` is reachable on its configured port.

To run the full stack, see the [root README](../README.md#setup-instructions).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Map | Leaflet.js 1.9.4 + CARTO dark tile layer |
| Charts | Chart.js (CDN) |
| Fonts | Google Fonts — Instrument Sans, Space Grotesk, JetBrains Mono |
| Styling | Vanilla CSS with CSS custom properties |
| Scripting | Vanilla JavaScript (no framework, no build step) |

---

## Contributing

1. Fork the repo and create a feature branch.
2. Make your changes to the appropriate dashboard file.
3. If updating the production dashboard, apply the same change in both `frontend/index.html` **and** `templates/index.html`.
4. Open a pull request with a screenshot or screen recording of the change.

---

*Part of [AEGIS](../README.md) — AI Emergency Guidance & Intelligence System.*
