"""
AEGIS Flask Server — Process 2 of 2.

Serves:
  • GET  /                           → Dashboard
  • GET  /api/alerts                 → All alerts
  • GET  /api/alerts/<id>/messages   → Chat history for an alert
  • GET  /api/users                  → All users with contact info
  • PATCH /api/alerts/<id>/status    → Escalate/resolve + sends feedback poll
  • POST /api/broadcast              → Translate + TTS + send to users
  • POST /api/send_message           → Direct message to specific user
"""
import io
import asyncio
import logging
from flask import Flask, jsonify, request, render_template
from backend.config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG, TELEGRAM_BOT_TOKEN
from backend import db
from backend.llm_gateway import translate_text
from backend.tts_gateway import synthesize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("aegis.app")

app = Flask(
    __name__,
    template_folder="../frontend",
    static_folder="../static",
)


@app.route("/")
def dashboard():
    return render_template("index-integrated.html")


@app.route("/api/alerts")
def api_alerts():
    alerts = db.get_all_alerts()
    # Enrich alerts with user contact info
    user_cache = {}
    for alert in alerts:
        cid = alert["chat_id"]
        if cid not in user_cache:
            user_cache[cid] = db.get_user(cid) or {}
        u = user_cache[cid]
        alert["user_name"] = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or f"User {cid}"
        alert["user_username"] = u.get("username", "")
        alert["user_phone"] = u.get("phone_number", "")
    return jsonify(alerts)


@app.route("/api/alerts/<int:alert_id>/messages")
def api_alert_messages(alert_id: int):
    messages = db.get_messages_for_alert(alert_id)
    return jsonify(messages)


@app.route("/api/alerts/<int:alert_id>/logs")
def api_alert_logs(alert_id: int):
    logs = db.get_alert_logs(alert_id)
    return jsonify(logs)


@app.route("/api/users")
def api_users():
    users = db.get_all_users()
    return jsonify(users)


@app.route("/api/alerts/<int:alert_id>/status", methods=["PATCH"])
def api_update_alert_status(alert_id: int):
    """Update alert status. On resolve, sends a feedback poll to the user."""
    data = request.get_json(force=True)
    new_status = data.get("status", "").strip()
    new_severity = data.get("severity")

    if new_status not in ("active", "escalated", "resolved"):
        return jsonify({"error": "Invalid status. Use: active, escalated, resolved."}), 400

    alert = db.get_alert_by_id(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found."}), 404

    if new_severity is not None:
        new_severity = max(1, min(5, int(new_severity)))

    db.update_alert_status(alert_id, new_status, new_severity)
    logger.info("Alert #%d status → %s (severity=%s)", alert_id, new_status, new_severity)

    # ── Send feedback poll on resolution ──────────────────────────────────
    if new_status == "resolved":
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _send_feedback_poll(alert["chat_id"], alert_id)
            )
            loop.close()
            logger.info("Feedback poll sent for alert #%d", alert_id)
        except Exception as e:
            logger.error("Feedback poll failed for alert #%d: %s", alert_id, e)

    return jsonify({"ok": True, "alert_id": alert_id, "status": new_status})


@app.route("/api/alerts/<int:alert_id>/verify", methods=["POST"])
def api_alert_verify(alert_id: int):
    """Manually re-trigger the AI verification agent for an alert."""
    alert = db.get_alert_by_id(alert_id)
    if not alert:
        return jsonify({"error": "Alert not found."}), 404

    # Run in background
    from backend.agent import verify_incident
    import threading
    threading.Thread(
        target=verify_incident,
        args=(alert_id, alert.get("incident_type", "unknown"), alert.get("location_name", "")),
        kwargs={"lat": alert.get("lat"), "lng": alert.get("lng")},
        daemon=True,
    ).start()

    return jsonify({"ok": True, "message": "Verification agent dispatched."})


async def _send_feedback_poll(chat_id: int, alert_id: int) -> None:
    """Send a Telegram poll asking if the user received support."""
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # Import the poll-to-alert mapping from bot module
    # Since bot runs in a separate process, we store the mapping via a file-based approach
    # For hackathon simplicity, we send a regular message as well
    poll_msg = await bot.send_poll(
        chat_id=chat_id,
        question=f"🛡️ AEGIS Feedback — Alert #{alert_id}\nHave you received emergency support?",
        options=["✅ Yes, I received help", "❌ No, I did not receive help"],
        is_anonymous=False,
    )

    # Store poll_id → alert_id mapping in the bot process via a shared file
    import json, os
    poll_map_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "_poll_map.json")
    poll_map = {}
    if os.path.exists(poll_map_file):
        try:
            with open(poll_map_file, "r") as f:
                poll_map = json.load(f)
        except Exception:
            pass
    poll_map[poll_msg.poll.id] = alert_id
    with open(poll_map_file, "w") as f:
        json.dump(poll_map, f)

    # Also send a text notification
    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ *Your emergency alert #{alert_id} has been resolved.*\n\n"
             "Please respond to the poll above to help us improve our service.",
        parse_mode="Markdown",
    )


@app.route("/api/broadcast", methods=["POST"])
def api_broadcast():
    data = request.get_json(force=True)
    message_text = data.get("message", "").strip()
    output_mode = data.get("output_mode", "text_only")
    target_chat_ids = data.get("chat_ids", [])

    if not message_text:
        return jsonify({"error": "Message text is required."}), 400

    if target_chat_ids == "all" or not target_chat_ids:
        users = db.get_all_users()
    else:
        cids = [int(c) for c in target_chat_ids] if isinstance(target_chat_ids, list) else [int(target_chat_ids)]
        users = [{"chat_id": cid, "language": db.get_user_language(cid)} for cid in cids]

    if not users:
        return jsonify({"error": "No users to broadcast to."}), 404

    results = []
    loop = asyncio.new_event_loop()

    for user in users:
        chat_id = user["chat_id"]
        user_lang = user.get("language", "Unknown")

        translated = translate_text(message_text, user_lang) if user_lang and user_lang != "Unknown" else message_text

        try:
            audio_bytes = synthesize(translated, output_mode)
            loop.run_until_complete(_send_telegram_message(chat_id, translated, audio_bytes))
            results.append({"chat_id": chat_id, "status": "sent", "language": user_lang})
            
            # Find an active alert for this user to attach the log to
            active_alert = db.get_active_alert_for_user(chat_id)
            if active_alert:
                db.log_alert_action(
                    active_alert["id"], 
                    "broadcast_sent", 
                    f"Mode: {output_mode}, Msg: {translated[:100]}", 
                    "dashboard"
                )
        except Exception as e:
            logger.error("Broadcast failed for %d: %s", chat_id, e)
            results.append({"chat_id": chat_id, "status": "failed", "error": str(e)})

    loop.close()
    return jsonify({"broadcast_results": results})


@app.route("/api/send_message", methods=["POST"])
def api_send_message():
    data = request.get_json(force=True)
    chat_id = data.get("chat_id")
    message_text = data.get("message", "").strip()
    output_mode = data.get("output_mode", "text_only")

    if not chat_id or not message_text:
        return jsonify({"error": "chat_id and message are required."}), 400

    chat_id = int(chat_id)
    user_lang = db.get_user_language(chat_id)
    translated = translate_text(message_text, user_lang) if user_lang and user_lang != "Unknown" else message_text

    try:
        audio_bytes = synthesize(translated, output_mode)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_send_telegram_message(chat_id, translated, audio_bytes))
        loop.close()
        
        # Log to the user's active/recent alert if possible
        active_alert = db.get_active_alert_for_user(chat_id)
        if active_alert:
            db.log_alert_action(
                active_alert["id"], 
                "direct_message_sent", 
                f"Mode: {output_mode}, Msg: {translated[:100]}", 
                "dashboard"
            )
            
        return jsonify({"ok": True, "chat_id": chat_id, "language": user_lang})
    except Exception as e:
        logger.error("Direct message failed for %d: %s", chat_id, e)
        return jsonify({"error": str(e)}), 500


async def _send_telegram_message(chat_id: int, text: str, audio_bytes: bytes | None = None) -> None:
    from telegram import Bot
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=chat_id,
        text=f"📢 *AEGIS Emergency Alert*\n\n{text}",
        parse_mode="Markdown",
    )
    if audio_bytes:
        await bot.send_voice(chat_id=chat_id, voice=io.BytesIO(audio_bytes), caption="🔊 Voice alert")


def main() -> None:
    import os
    import time
    import webbrowser
    import urllib.request
    from threading import Thread

    db.init_db()
    logger.info("AEGIS Dashboard starting on %s:%d", FLASK_HOST, FLASK_PORT)
    
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        url = f"http://{'127.0.0.1' if FLASK_HOST == '0.0.0.0' else FLASK_HOST}:{FLASK_PORT}/"
        
        def _open_browser():
            for _ in range(15):
                try:
                    res = urllib.request.urlopen(url)
                    if res.getcode() == 200:
                        webbrowser.open(url)
                        break
                except Exception:
                    time.sleep(1)

        Thread(target=_open_browser, daemon=True).start()
        
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)


if __name__ == "__main__":
    main()
