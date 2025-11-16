"""
נקודת הכניסה הראשית לבוט ריקון מוח
מגדיר webhook ו-Flask server עבור Render
"""

import asyncio
import concurrent.futures
import logging
import threading
import time
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


@app.before_request
def _initialize_bot_before_request() -> None:
    """
    מבטיחים שהבוט יאותחל לאחר יצירת ה-worker של Gunicorn ולפני עיבוד בקשות.
    """
    if _bot_initialized.is_set():
        return
    if not (RENDER_EXTERNAL_URL and TELEGRAM_BOT_TOKEN):
        return

    try:
        ensure_bot_initialized_sync()
    except Exception:
        logger.exception("⚠️ אתחול הבוט נכשל בבקשה הראשונה - ניסיון נוסף יבוצע בבקשה הבאה")

# ===== לולאת אירועים ייעודית לבוט (דרוש עבור Webhook) =====
_bot_loop: Optional[asyncio.AbstractEventLoop] = None
_bot_loop_thread: Optional[threading.Thread] = None
_bot_loop_ready = threading.Event()
_bot_initialized = threading.Event()
_bot_init_lock = threading.Lock()
_bot_init_future: Optional[concurrent.futures.Future] = None
# מגבלת זמן רכה - משמשת להתרעות בלבד, לא לעצירת העיבוד
_PROCESS_UPDATE_TIMEOUT_SECONDS = 8.0


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


def _consume_processed_update_future(
    future: concurrent.futures.Future,
    update_id: int,
    started_at: float
) -> tuple[bool, bool, float]:
    """
    מטפל בתוצאת future של עיבוד עדכון ומחזיר מידע על הצלחתו.

    Returns:
        (succeeded, cancelled, duration_seconds)
    """
    duration = time.perf_counter() - started_at

    if future.cancelled():
        logger.warning("⚠️ עיבוד עדכון %s בוטל לאחר %.2fs", update_id, duration)
        return False, True, duration

    try:
        future.result()
    except Exception:
        logger.exception("❌ שגיאה בעיבוד עדכון %s (משך %.2fs)", update_id, duration)
        return False, False, duration

    if duration >= _PROCESS_UPDATE_TIMEOUT_SECONDS:
        logger.warning("⌛ עדכון %s הושלם לאחר %.2fs (איטי מהרגיל)", update_id, duration)
    else:
        logger.debug("✅ עדכון %s הושלם ב-%.2fs", update_id, duration)

    return True, False, duration


def _on_init_future_done(future: concurrent.futures.Future) -> None:
    """
    Callback שמופעל בסיום אתחול הבוט.
    """
    global _bot_init_future

    try:
        result = future.result()
    except Exception:
        logger.exception("❌ כשל באתחול הבוט (future callback)")
        with _bot_init_lock:
            if _bot_init_future is future:
                _bot_init_future = None
        return

    if result:
        _bot_initialized.set()
    else:
        logger.error("⚠️ אתחול הבוט החזיר False")

    with _bot_init_lock:
        if _bot_init_future is future:
            _bot_init_future = None


def _schedule_bot_initialization() -> Optional[concurrent.futures.Future]:
    """
    דואג שאתחול הבוט יתחיל (אם טרם קרה) ומחזיר future שמייצג את האתחול.
    """
    global _bot_init_future

    if _bot_initialized.is_set():
        return None

    with _bot_init_lock:
        if _bot_initialized.is_set():
            return None

        if _bot_init_future:
            if not _bot_init_future.done():
                return _bot_init_future

            try:
                previous_result = _bot_init_future.result()
            except Exception:
                logger.warning("🔄 ניסיון קודם לאתחול הבוט נכשל - מנסים שוב...")
            else:
                if previous_result:
                    _bot_initialized.set()
                    return None

            _bot_init_future = None

        logger.debug("🚀 מתחיל אתחול ראשוני של הבוט (Webhook mode)")
        _start_bot_loop()
        _bot_init_future = _run_on_bot_loop(setup_webhook())
        _bot_init_future.add_done_callback(_on_init_future_done)
        return _bot_init_future


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
def webhook():
    """
    Webhook endpoint לקבלת עדכונים מטלגרם
    """
    try:
        json_data = request.get_json(force=True)
    except Exception as e:
        logger.exception("❌ שגיאה בעיבוד webhook: %s", e)
        return {"status": "error", "message": str(e)}, 500

    if not ensure_bot_initialized_sync():
        logger.error("❌ הבוט לא אותחל - לא ניתן לעבד את העדכון")
        return {"status": "error", "message": "bot initialization failed"}, 503

    update = Update.de_json(json_data, bot.application.bot)
    update_payload_keys = sorted(k for k in json_data.keys() if k != "update_id")
    logger.debug("📨 התקבל עדכון %s (payload keys=%s)", update.update_id, update_payload_keys)
    started_at = time.perf_counter()

    try:
        process_future = _run_on_bot_loop(bot.application.process_update(update))
    except Exception:
        logger.exception("❌ שגיאה בתזמון עיבוד עדכון %s", update.update_id)
        return {"status": "error", "message": "scheduling failed"}, 500

    if process_future.done():
        succeeded, cancelled, duration = _consume_processed_update_future(
            process_future,
            update.update_id,
            started_at
        )
        if cancelled:
            return {"status": "error", "message": "processing cancelled"}, 500
        if not succeeded:
            return {"status": "error", "message": "processing failed"}, 500
        return {"status": "ok", "processing_time": round(duration, 3)}, 200

    def _on_future_done(fut: concurrent.futures.Future) -> None:
        _consume_processed_update_future(fut, update.update_id, started_at)

    process_future.add_done_callback(_on_future_done)
    logger.debug("⏱️ עדכון %s הועבר לעיבוד אסינכרוני", update.update_id)
    return {"status": "accepted"}, 200


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
        await bot.setup(use_updater=False)

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
        # הפעלת מתזמנים (APScheduler) לאחר התחלת ה-application
        bot.start_schedulers()
        logger.info("🤖 הבוט פעיל ומוכן לעבודה!")

        return True

    except Exception as e:
        logger.exception("❌ שגיאה בהגדרת webhook: %s", e)
        raise


async def ensure_bot_initialized() -> bool:
    """
    מבטיח שהבוט אותחל ורץ על לולאת אירועים נפרדת.
    """
    future = _schedule_bot_initialization()
    if future is None:
        return _bot_initialized.is_set()

    try:
        result = await asyncio.wrap_future(future)
    except Exception:
        logger.exception("❌ כשל באתחול הבוט (Webhook mode)")
        return False
    return result


def ensure_bot_initialized_sync(timeout: float = 30.0) -> bool:
    """
    גרסה סינכרונית של אתחול הבוט עבור הקשרים שאינם אסינכרוניים (כמו WSGI).
    """
    future = _schedule_bot_initialization()
    if future is None:
        return _bot_initialized.wait(timeout=timeout)

    try:
        result = future.result(timeout=timeout)
    except Exception:
        logger.exception("❌ כשל באתחול הבוט (sync)")
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
        await bot.setup(use_updater=True)

        # הפעלת polling
        await bot.application.initialize()
        await bot.application.start()
        await bot.application.updater.start_polling()
        # Scheduler במצב פיתוח
        bot.start_schedulers()

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

        init_ok = ensure_bot_initialized_sync()
        if not init_ok:
            raise RuntimeError("Failed to initialize bot for webhook mode")

        logger.info(f"🌐 Flask server מתחיל על פורט {PORT}")
        app.run(
            host='0.0.0.0',
            port=PORT,
            debug=DEBUG_MODE
        )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("👋 הבוט נעצר")
    except Exception as e:
        logger.error(f"❌ שגיאה קריטית: {e}")
        raise
