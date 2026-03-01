"""
AEGIS Telegram Bot — Process 1 of 2.

Features:
  • Consolidated alerts: one active alert per user with chat history
  • Deduplication: identical messages within the same alert are skipped
  • Contact capture: extracts name/username from Telegram profile,
    requests phone number via contact share keyboard
  • Feedback polls: handles poll answers from resolution feedback
"""
import logging
import threading
from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, PollAnswerHandler, filters,
)
from backend.config import TELEGRAM_BOT_TOKEN
from backend import db
from backend.llm_gateway import extract_incident
from backend.agent import verify_incident

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("aegis.bot")

# Maps poll_id → alert_id so we can link feedback answers
_poll_to_alert: dict[str, int] = {}


def _extract_user_info(update: Update) -> dict:
    """Extract Telegram profile info from any update."""
    user = update.effective_user
    if not user:
        return {}
    return {
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "username": user.username or "",
    }


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    info = _extract_user_info(update)

    db.upsert_user(
        chat_id,
        first_name=info.get("first_name", ""),
        last_name=info.get("last_name", ""),
        username=info.get("username", ""),
    )

    # Request phone number via contact share button
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Share Phone Number", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )

    await update.message.reply_text(
        "🛡️ *AEGIS — Emergency Intelligence System*\n\n"
        "Send me a message describing your emergency in *any language*.\n"
        "Then share your 📍 *location* so responders can find you.\n\n"
        "Please also share your phone number below so we can reach you in emergencies.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared contact information."""
    chat_id = update.effective_chat.id
    contact = update.message.contact

    if contact:
        phone = contact.phone_number or ""
        db.update_user_phone(chat_id, phone)
        logger.info("Phone number captured for %d: %s", chat_id, phone)
        await update.message.reply_text(
            f"✅ Phone number saved: {phone}\n\n"
            "You can now describe your emergency or share your 📍 location.",
            reply_markup=ReplyKeyboardRemove(),
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming distress text with deduplication."""
    chat_id = update.effective_chat.id
    raw_text = update.message.text

    if not raw_text or len(raw_text.strip()) < 3:
        return

    logger.info("Received text from %d: %s", chat_id, raw_text[:80])

    # Capture user info on every message (in case /start was skipped)
    info = _extract_user_info(update)

    # ── Step 1: Mistral extraction ───────────────────────────────────────
    data = extract_incident(raw_text)

    detected_lang = data.get("detected_language", "Unknown")
    incident_type = data.get("incident_type", "unknown")
    severity = data.get("severity", 1)
    severity_label = data.get("severity_label", "INFO")
    summary_en = data.get("translated_summary_en", "")
    summary_local = data.get("translated_summary_local", "")
    people_count = data.get("people_count", "unknown")
    trapped = data.get("trapped", False)
    needs = ", ".join(data.get("needs", []))

    # ── Step 2: Persist user ─────────────────────────────────────────────
    db.upsert_user(
        chat_id, language=detected_lang,
        first_name=info.get("first_name", ""),
        last_name=info.get("last_name", ""),
        username=info.get("username", ""),
    )

    # ── Step 3: Consolidate into single active alert ─────────────────────
    existing_alert = db.get_active_alert_for_user(chat_id)

    if existing_alert:
        alert_id = existing_alert["id"]

        # Dedup: skip if exact same text already recorded
        if db.is_duplicate_message(alert_id, raw_text):
            logger.info("Duplicate message skipped for alert #%d", alert_id)
            return

        db.append_message_to_alert(
            alert_id=alert_id, chat_id=chat_id, raw_text=raw_text,
            incident_type=incident_type, severity=severity,
            severity_label=severity_label, summary_en=summary_en,
            summary_local=summary_local, detected_language=detected_lang,
            people_count=people_count, trapped=trapped, needs=needs,
        )
        logger.info("Message appended to alert #%d", alert_id)
    else:
        alert_id = db.create_alert_with_message(
            chat_id=chat_id, raw_text=raw_text,
            incident_type=incident_type, severity=severity,
            severity_label=severity_label, summary_en=summary_en,
            summary_local=summary_local, detected_language=detected_lang,
            people_count=people_count, trapped=trapped, needs=needs,
        )
        logger.info("New alert #%d created (type=%s, severity=%d)", alert_id, incident_type, severity)

    # ── Step 4: Background verification ──────────────────────────────────
    location_text = data.get("location_text", "")
    alert = db.get_alert_by_id(alert_id)
    threading.Thread(
        target=verify_incident,
        args=(alert_id, incident_type, location_text),
        kwargs={"lat": alert.get("lat"), "lng": alert.get("lng")} if alert else {},
        daemon=True,
    ).start()

    # ── Step 5: Acknowledge ──────────────────────────────────────────────
    if existing_alert:
        ack = f"📝 Message added to your active alert #{alert_id}. Responders notified."
    else:
        ack_messages = {
            "German": "✅ Notfall registriert (#{id}). Bitte teilen Sie Ihren 📍 Standort.",
            "French": "✅ Urgence enregistrée (#{id}). Veuillez partager votre 📍 position.",
            "Spanish": "✅ Emergencia registrada (#{id}). Por favor comparta su 📍 ubicación.",
            "Italian": "✅ Emergenza registrata (#{id}). Condividi la tua 📍 posizione.",
            "Portuguese": "✅ Emergência registrada (#{id}). Compartilhe sua 📍 localização.",
            "Polish": "✅ Zgłoszenie zarejestrowane (#{id}). Proszę udostępnić 📍 lokalizację.",
            "Hindi": "✅ आपातकाल दर्ज हुआ (#{id})। कृपया अपना 📍 स्थान साझा करें।",
        }
        default_ack = "✅ Emergency registered (#{id}). Please share your 📍 location so responders can find you."
        ack = ack_messages.get(detected_lang, default_ack).replace("{id}", str(alert_id))

    await update.message.reply_text(ack)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Attach GPS to the user's active alert, then re-verify."""
    chat_id = update.effective_chat.id
    loc = update.message.location
    if not loc:
        return

    lat, lng = loc.latitude, loc.longitude
    logger.info("GPS from %d: %.5f, %.5f", chat_id, lat, lng)

    alert_id = db.update_latest_alert_location(chat_id, lat, lng)
    if alert_id:
        alert = db.get_alert_by_id(alert_id)
        if alert:
            threading.Thread(
                target=verify_incident,
                args=(alert_id, alert.get("incident_type", "unknown"), ""),
                kwargs={"lat": lat, "lng": lng},
                daemon=True,
            ).start()
        await update.message.reply_text(
            f"📍 Location attached to alert #{alert_id}. Responders can now see you."
        )
    else:
        await update.message.reply_text(
            "📍 Location received. Describe your emergency first, then share location."
        )


# ── Feedback poll handler ────────────────────────────────────────────────────

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user's response to the resolution feedback poll."""
    answer = update.poll_answer
    if not answer:
        return

    poll_id = answer.poll_id

    # Look up alert_id from shared poll map file (written by Flask process)
    import json, os
    poll_map_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_poll_map.json")
    alert_id = _poll_to_alert.get(poll_id)

    if not alert_id and os.path.exists(poll_map_file):
        try:
            with open(poll_map_file, "r") as f:
                poll_map = json.load(f)
            alert_id = poll_map.get(poll_id)
            # Clean up used mapping
            if poll_id in poll_map:
                del poll_map[poll_id]
                with open(poll_map_file, "w") as f:
                    json.dump(poll_map, f)
        except Exception as e:
            logger.warning("Failed to read poll map: %s", e)

    if not alert_id:
        logger.warning("Unknown poll_id: %s", poll_id)
        return

    # option_ids: [0] = Yes, [1] = No
    option_ids = answer.option_ids
    if 0 in option_ids:
        feedback = "yes_received_support"
        logger.info("Alert #%d feedback: YES, received support", alert_id)
    else:
        feedback = "no_support_received"
        logger.info("Alert #%d feedback: NO support received", alert_id)

    db.update_alert_feedback(alert_id, feedback)
    _poll_to_alert.pop(poll_id, None)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    db.init_db()
    logger.info("AEGIS Bot starting... (polling mode)")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
