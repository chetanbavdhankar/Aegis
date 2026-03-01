"""
AEGIS TTS Gateway — Responder-selected voice synthesis dispatch.

Supported modes:
  - "elevenlabs"  → ElevenLabs multilingual v2
  - "text_only"   → No TTS, returns None (saves API credits)

The responder explicitly chooses the output mode from the dashboard UI.
No automatic fallback chain — the human controls the tool selection.
"""
import io
import logging
from elevenlabs import ElevenLabs
from backend.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL

logger = logging.getLogger("aegis.tts")


def synthesize(text: str, output_mode: str = "text_only") -> bytes | None:
    """
    Generate audio bytes based on the selected output_mode.

    Args:
        text: The text to synthesize (already translated to target language).
        output_mode: One of "elevenlabs", "text_only".

    Returns:
        bytes of MP3 audio, or None if text_only or on failure.
    """
    mode = output_mode.lower().strip()

    if mode == "text_only":
        logger.info("TTS mode: text_only — skipping audio generation.")
        return None

    if mode == "elevenlabs":
        return _elevenlabs_tts(text)

    logger.warning("Unknown TTS mode '%s' — falling back to text_only.", mode)
    return None


def _elevenlabs_tts(text: str) -> bytes | None:
    """Generate audio via ElevenLabs API. Returns MP3 bytes or None on failure."""
    if not ELEVENLABS_API_KEY:
        logger.error("ELEVENLABS_API_KEY not set — cannot generate audio.")
        return None

    try:
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        # generate() returns an iterator of audio chunks
        audio_iterator = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=text,
            model_id=ELEVENLABS_MODEL,
            output_format="mp3_44100_128",
        )

        # Collect all chunks into a single bytes buffer
        buffer = io.BytesIO()
        for chunk in audio_iterator:
            buffer.write(chunk)

        audio_bytes = buffer.getvalue()
        logger.info("ElevenLabs TTS OK: %d bytes generated.", len(audio_bytes))
        return audio_bytes

    except Exception as e:
        logger.error("ElevenLabs TTS error: %s", e)
        return None
