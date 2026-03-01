"""
AEGIS LLM Gateway — Single wrapper for all Mistral AI calls.

Routes:
  1. extract_incident()  — JSON-mode structured extraction from raw distress text.
  2. translate_text()    — Translate text to a target language for reverse alerts.

Model-agnostic: swap MISTRAL_MODEL in config to change providers via LiteLLM later.
"""
import json
import logging
from mistralai import Mistral
from backend.config import MISTRAL_API_KEY, MISTRAL_MODEL, RESPONDER_LANGUAGE

logger = logging.getLogger("aegis.llm")

# ── Mistral client (lazy singleton) ─────────────────────────────────────────
_client: Mistral | None = None


def _get_client() -> Mistral:
    global _client
    if _client is None:
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY is not set in .env")
        _client = Mistral(api_key=MISTRAL_API_KEY)
    return _client


# ── System prompt for structured extraction ──────────────────────────────────
_EXTRACTION_SYSTEM_PROMPT = f"""You are AEGIS, an AI emergency triage system.
You receive raw distress messages from citizens in ANY language.

Your job: extract structured emergency data as JSON. Be precise.

Required JSON schema (respond with ONLY this JSON, no markdown):
{{
  "detected_language": "<ISO language name (e.g. English, French, Spanish, Hindi). MUST NOT BE 'Unknown' if words are present in text. THIS IS CRITICAL.>",
  "incident_type": "<flood|earthquake|fire|storm|medical|infrastructure|security|other>",
  "severity": <integer 1-5, where 5=life-threatening>,
  "severity_label": "<INFO|LOW|MODERATE|HIGH|CRITICAL>",
  "location_text": "<any location info mentioned in the text>",
  "people_count": "<number or description if mentioned, else 'unknown'>",
  "trapped": <true|false>,
  "needs": ["<rescue>", "<medical>", "<evacuation>", "<shelter>", "<supplies>"],
  "translated_summary_local": "<1-2 sentence summary in {RESPONDER_LANGUAGE}>",
  "translated_summary_en": "<1-2 sentence summary in English>"
}}

Severity guide:
  1 = INFO (general question, no emergency)
  2 = LOW (minor inconvenience)
  3 = MODERATE (property damage risk, no immediate danger to life)
  4 = HIGH (people at risk, situation escalating)
  5 = CRITICAL (people trapped, injured, immediate danger to life)

If the message is not an emergency at all, still extract with severity=1.
Always respond with valid JSON only. No explanations outside JSON."""


def extract_incident(raw_text: str) -> dict:
    """
    Send raw distress text to Mistral JSON mode.
    Returns parsed dict with structured incident data.
    Falls back to a safe default dict on any failure.
    """
    client = _get_client()

    try:
        response = client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,  # deterministic extraction
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        logger.info("Extraction OK: type=%s severity=%s", data.get("incident_type"), data.get("severity"))
        return data

    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s — raw: %s", e, content[:200] if 'content' in dir() else "N/A")
    except Exception as e:
        logger.error("Mistral extraction error: %s", e)

    # ── Safe fallback ────────────────────────────────────────────────────────
    return {
        "detected_language": "Unknown",
        "incident_type": "unknown",
        "severity": 1,
        "severity_label": "INFO",
        "location_text": "",
        "people_count": "unknown",
        "trapped": False,
        "needs": [],
        "translated_summary_local": raw_text,
        "translated_summary_en": raw_text,
    }


def translate_text(text: str, target_language: str) -> str:
    """
    Translate text to the target language via Mistral.
    Returns translated text, or the original on failure.
    """
    client = _get_client()

    try:
        response = client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. "
                        f"Translate the following text to {target_language}. "
                        f"Output ONLY the translation, nothing else. "
                        f"Preserve urgency and tone."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
        translated = response.choices[0].message.content.strip()
        logger.info("Translation OK → %s (%d chars)", target_language, len(translated))
        return translated

    except Exception as e:
        logger.error("Translation error: %s", e)
        return text  # fail-safe: return original text
