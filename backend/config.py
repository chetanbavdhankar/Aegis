"""
AEGIS Configuration — Single source of truth for all settings.
Loads from environment variables via .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# ── API Keys ─────────────────────────────────────────────────────────────────
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# ── Database ─────────────────────────────────────────────────────────────────
DB_PATH = str(ROOT_DIR / "aegis.db")

# ── Mistral Settings ────────────────────────────────────────────────────────
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
MISTRAL_AGENT_MODEL = os.getenv("MISTRAL_AGENT_MODEL", "mistral-large-latest")

# ── ElevenLabs Settings ─────────────────────────────────────────────────────
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # "George" multilingual
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# ── Flask Settings ───────────────────────────────────────────────────────────
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# ── Responder locale (dashboard language) ────────────────────────────────────
RESPONDER_LANGUAGE = os.getenv("RESPONDER_LANGUAGE", "Italian")
