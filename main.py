"""
נקודת הכניסה הראשית לבוט ריקון מוח
מגדיר webhook ו-Flask server עבור Render
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from typing import Optional

from flask import Flask, request
from telegram import Update

from config import DEBUG_MODE, PORT, RENDER_EXTERNAL_URL, TELEGRAM_BOT_TOKEN
from bot import bot

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG if DEBUG_MODE else logging.INFO
)
logger = logging.getLogger(__name__)

# יצירת Flask app
app = Flask(__name__)

# ===== לולאת אירועים ייעודית לבוט (דרוש עבור Webhook) =====
_bot_loop: Optional[asyncio.AbstractEventLoop] = None
_bot_loop_thread: Optional[threading.Thread] = None
_bot_loop_ready = threading.Event()
_bot_initialized = threading.Event()
_bot_init_lock = threading.Lock()


def _start_bot_loop() -> None:
    """
    מפעיל לולאת אירועים ייעודית שמעבדת את כל העדכונים מהבוט.
    """
    global _bot_loop, _bot_loop_thread

    if _bot_loop_thread and _bot_loop_thread.is_alive():
        return

    _bot_loop = asyncio.new_event_loop()
    _bot_loop_ready.clear()

    def _run_loop():
        asyncio.set_event_loop(_bot_loop)
        _bot_loop_ready.set()
        logger.debug("🔁 לולאת האירועים של הבוט הופעלה")
        _bot_loop.run_forever()

    _bot_loop_thread = threading.Thread(
        target=_run_loop,
        name="brain-dump-bot-loop",
        daemon=True
    )
    _bot_loop_thread.start()
    _bot_loop_ready.wait()
    logger.debug("✅ לולאת האירועים של הבוט מוכנה")


def _run_on_bot_loop(coro: Coroutine) -> concurrent.futures.Future:
    """
    מריץ coroutine על לולאת האירועים הייעודית של הבוט.
    """
    if not _bot_loop:
        raise RuntimeError("לולאת האירועים של הבוט לא הופעלה")
    return asyncio.run_coroutine_threadsafe(coro, _bot_loop)


@app.route('/')
def index():
    """
    נקודת קצה בסיסית לבדיקת בריאות השרת
    """
    return {
        "status": "running",
        "bot": "Brain Dump Bot",
        "version": "1.0.0"
    }, 200


@app.route('/health')
def health():
    """
    Health check endpoint עבור Render
    """
    return {"status": "healthy"}, 200


WEBHOOK_PATH = f"/{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else "/webhook"
if not TELEGRAM_BOT_TOKEN:
    logger.warning("⚠️ TELEGRAM_BOT_TOKEN לא מוגדר - משתמשים במסלול webhook ברירת מחדל '/webhook'")


@app.route(WEBHOOK_PATH, methods=['POST'])
async def webhook():
    """
    Webhook endpoint לקבלת עדכונים מטלגרם
    """
    try:
        json_data = request.get_json(force=True)

        init_ok = await ensure_bot_initialized()
        if not init_ok:
            logger.error("❌ הבוט לא אותחל - לא ניתן לעבד את העדכון")
            return {"status": "error", "message": "bot initialization failed"}, 503

        update = Update.de_json(json_data, bot.application.bot)
        process_future = _run_on_bot_loop(bot.application.process_update(update))
        await asyncio.wrap_future(process_future)

        return {"status": "ok"}, 200

    except Exception as e:
        logger.exception("❌ שגיאה בעיבוד webhook: %s", e)
        return {"status": "error", "message": str(e)}, 500


async def setup_webhook() -> bool:
    """
    הגדרת webhook עם טלגרם
    """
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN לא מוגדר - לא ניתן להגדיר webhook")
    if not RENDER_EXTERNAL_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL לא מוגדר - נדרש URL חיצוני עבור webhook")

    # יצירת URL אמין (ללא סלאשים כפולים)
    webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{TELEGRAM_BOT_TOKEN}"

    try:
        await bot.setup()

        # ניקוי webhook קיים
        await bot.application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("🗑️ Webhook קיים נמחק")

        # הגדרת webhook חדש
        await bot.application.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
        logger.info(f"✅ Webhook הוגדר בהצלחה: {webhook_url}")

        # אתחול והפעלת ה-Application
        await bot.application.initialize()
        await bot.application.start()
        logger.info("🤖 הבוט פעיל ומוכן לעבודה!")

        return True

    except Exception as e:
        logger.exception("❌ שגיאה בהגדרת webhook: %s", e)
        raise


async def ensure_bot_initialized() -> bool:
    """
    מבטיח שהבוט אותחל ורץ על לולאת אירועים נפרדת.
    """
    if _bot_initialized.is_set():
        return True

    with _bot_init_lock:
        if _bot_initialized.is_set():
            return True

        logger.debug("🚀 מתחיל אתחול ראשוני של הבוט (Webhook mode)")
        _start_bot_loop()
        future = _run_on_bot_loop(setup_webhook())

    try:
        result = await asyncio.wrap_future(future)
    except Exception:
        logger.exception("❌ כשל באתחול הבוט (Webhook mode)")
        return False

    if result:
        _bot_initialized.set()
    return result


def run_polling():
    """
    הרצה במצב polling (לפיתוח מקומי)
    שימושי רק לבדיקות - לא עובד ב-Render
    """

    async def main():
        await bot.setup()

        # הפעלת polling
        await bot.application.initialize()
        await bot.application.start()
        await bot.application.updater.start_polling()

        logger.info("🤖 הבוט רץ במצב polling (פיתוח מקומי)")

        # המתנה אינסופית
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 עצירת הבוט...")
            await bot.application.stop()
            await bot.application.shutdown()

    asyncio.run(main())


def main():
    """
    פונקציית main - מחליטה איך להריץ את הבוט
    """
    if not RENDER_EXTERNAL_URL:
        logger.warning(
            "⚠️ RENDER_EXTERNAL_URL לא מוגדר!\n"
            "נדרש כדי להריץ את הבוט ב-Render.\n"
            "מריץ במצב polling לפיתוח מקומי..."
        )
        run_polling()
    else:
        logger.info("🚀 מתחיל בוט במצב Render (webhook)")

        init_ok = asyncio.run(ensure_bot_initialized())
        if not init_ok:
            raise RuntimeError("Failed to initialize bot for webhook mode")

        logger.info(f"🌐 Flask server מתחיל על פורט {PORT}")
        app.run(
            host='0.0.0.0',
            port=PORT,
            debug=DEBUG_MODE
        )


if RENDER_EXTERNAL_URL and TELEGRAM_BOT_TOKEN:
    try:
        asyncio.run(ensure_bot_initialized())
    except Exception:
        logger.exception("⚠️ אתחול מוקדם של הבוט נכשל - יבוצע ניסיון נוסף בבקשה הראשונה")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("👋 הבוט נעצר")
    except Exception as e:
        logger.error(f"❌ שגיאה קריטית: {e}")
        raise
