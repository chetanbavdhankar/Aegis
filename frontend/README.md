# AEGIS — Frontend Dashboard

This folder contains all HTML-based dashboard interfaces for the **AEGIS Crisis Intelligence Platform**. Each file is a self-contained, single-page application (HTML + CSS + JS) that connects to the Flask backend and renders real-time emergency alerts on an interactive map.

---

## Files Overview

| File | Title | Theme | Backend Integration | Status |
|------|-------|-------|---------------------|--------|
| `index.html` | AEGIS — Crisis Intelligence | Minimal black / monochrome | ✅ Live (`/api/alerts`) | **Primary** |
| `myversion.html` | AEGIS OS // Tactical Crisis Terminal | Dark OS / military terminal | Mock data | Design prototype |
| `mynewversion.html` | AEGIS // Crisis Management Platform | Dark glass / modern | Mock data | Design prototype |
| `index-cyberpunk.html` | AEGIS Crisis Intelligence Terminal | Cyberpunk / neon teal | Mock data | Design prototype |
| `cyberpunkversion.html` | AEGIS Crisis Intelligence Terminal | Cyberpunk / neon amber | Mock data | Design prototype |

---

## Primary Dashboard: `index.html`

The production-ready interface. It connects to the Flask API and renders live data.

### Features
- **Live alert feed** — polls `GET /api/alerts` every 5 seconds
- **Leaflet.js map** — plots incident pins colored by severity (Critical / Warning / Safe)
- **Alert triage panel** — sidebar listing incoming alerts with timestamps, location, and severity
- **Broadcast input** — field to send a response message back to victims via the backend
- **Chart.js trend chart** — rolling 24-hour alert volume visualization
- **Stars background** — subtle animated star field for ambient UI

### API Endpoints Consumed
```
GET  http://localhost:8000/api/alerts          → Fetch all active alerts
POST http://localhost:8000/api/alerts          → Submit a new broadcast/response
```

> **Note:** The port is currently hardcoded to `localhost:8000`. When deploying via Flask (`python -m backend.app`), ensure the Flask server runs on port `8000`, or update the fetch URLs in `index.html` accordingly. The canonical Flask template lives at `../templates/index.html` — that file is what Flask actually serves; `frontend/index.html` is the standalone/dev version.

### Dependencies (CDN)
```html
<!-- Map -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link  rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">

<!-- Charts -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<!-- Fonts -->
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans...&family=Space+Grotesk...">
```

No npm or build step required — open in any browser with an internet connection.

---

## Design Prototypes

All prototype files are fully functional standalone HTML dashboards using **mock/simulated alert data**. They were created during the UI design phase to explore different visual identities for AEGIS.

### `myversion.html` — Tactical OS Terminal
- Boot sequence animation on load
- Military-grade dark OS aesthetic with scanlines and CRT effects
- Sidebar alert feed with color-coded severity chips
- Trend chart for alert volumes
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
- Real-time statistics bar

### `cyberpunkversion.html` — Cyberpunk Neon (Amber/Orange)
- Warm amber cyberpunk color scheme
- Boot scan overlay animation
- Notification system with slide-in alerts
- Compact system-status sidebar
- Alert severity bar breakdown

---

## Relationship to `templates/index.html`

Flask serves its HTML from the `templates/` directory (not this `frontend/` folder). Here is how they relate:

```
Aegis/
├── templates/
│   └── index.html     ← Flask serves this via Jinja2 routing (production)
└── frontend/
    ├── index.html     ← Standalone dev copy; same dashboard, no Jinja2 needed
    ├── myversion.html
    ├── mynewversion.html
    ├── index-cyberpunk.html
    └── cyberpunkversion.html
```

To update the live dashboard, edit `templates/index.html`. The `frontend/index.html` copy is useful for local development and iteration without running the full Flask server.

---

## Running the Dashboard Standalone

To preview `index.html` without the Flask backend running:

1. Open `index.html` directly in your browser, **or** serve it with a local HTTP server to avoid CORS issues:

```bash
# Python one-liner
python -m http.server 3000

# Then open: http://localhost:3000/index.html
```

2. The dashboard will gracefully show an empty map and alert feed until the Flask API (`localhost:8000`) is reachable.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Map | Leaflet.js 1.9.4 + CARTO dark tile layer |
| Charts | Chart.js (CDN) |
| Fonts | Google Fonts — Instrument Sans, Space Grotesk, JetBrains Mono |
| Styling | Vanilla CSS (CSS custom properties / variables) |
| Scripting | Vanilla JavaScript (no framework) |
| Build | None — zero-build, single HTML file per dashboard |

---

## Contributing

1. Fork the repo and create a feature branch.
2. Make your changes to the appropriate dashboard file.
3. If updating the production dashboard, apply the same change in both `frontend/index.html` **and** `templates/index.html`.
4. Open a pull request with a screenshot or screen recording of the change.

---

*Part of the [AEGIS](../README.md) — AI Emergency Guidance & Intelligence System.*
