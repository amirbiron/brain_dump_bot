"""
נקודת הכניסה הראשית לבוט ריקון מוח
מגדיר webhook ו-Flask server עבור Render
"""

import asyncio
import logging
from flask import Flask, request
from telegram import Update
import os

from config import PORT, RENDER_EXTERNAL_URL, DEBUG_MODE
from bot import bot

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG if DEBUG_MODE else logging.INFO
)
logger = logging.getLogger(__name__)

# יצירת Flask app
app = Flask(__name__)


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


@app.route(f'/{os.getenv("TELEGRAM_BOT_TOKEN")}', methods=['POST'])
async def webhook():
    """
    Webhook endpoint לקבלת עדכונים מטלגרם
    """
    try:
        # קבלת הנתונים מטלגרם
        json_data = request.get_json(force=True)
        
        # יצירת Update object
        update = Update.de_json(json_data, bot.application.bot)
        
        # עיבוד העדכון
        await bot.application.process_update(update)
        
        return {"status": "ok"}, 200
        
    except Exception as e:
        logger.error(f"❌ שגיאה בעיבוד webhook: {e}")
        return {"status": "error", "message": str(e)}, 500


async def setup_webhook():
    """
    הגדרת webhook עם טלגרם
    """
    try:
        # אתחול הבוט
        await bot.setup()
        
        # הגדרת ה-webhook URL
        webhook_url = f"{RENDER_EXTERNAL_URL}/{os.getenv('TELEGRAM_BOT_TOKEN')}"
        
        # מחיקת webhook קיים (במקרה שיש)
        await bot.application.bot.delete_webhook(drop_pending_updates=True)
        
        logger.info("🗑️ Webhook קיים נמחק")
        
        # הגדרת webhook חדש
        await bot.application.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
        
        logger.info(f"✅ Webhook הוגדר בהצלחה: {webhook_url}")
        
        # אתחול הבוט (צריך לקרוא initialize פעם אחת)
        await bot.application.initialize()
        await bot.application.start()
        
        logger.info("🤖 הבוט פעיל ומוכן לעבודה!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ שגיאה בהגדרת webhook: {e}")
        return False


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
        # Render mode - הרצה עם webhook
        logger.info("🚀 מתחיל בוט במצב Render (webhook)")
        
        # הגדרת webhook (async)
        # נריץ את זה בלולאת אירועים חדשה
        asyncio.run(setup_webhook())
        
        # הרצת Flask server
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
