"""
הלוגיקה המרכזית של בוט ריקון מוח
מכיל את כל ה-handlers והפקודות
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

from config import (
    TELEGRAM_BOT_TOKEN,
    MESSAGES,
    BOT_STATES,
    CATEGORIES,
    TOPICS,
    THOUGHT_STATUS,
    TIMEZONE,
    WEEKLY_REVIEW_ENABLED,
    WEEKLY_REVIEW_FRIDAY_HOUR,
    WEEKLY_REVIEW_FRIDAY_MINUTE,
    WEEKLY_REVIEW_SUNDAY_HOUR,
    WEEKLY_REVIEW_SUNDAY_MINUTE,
    WEEKLY_REVIEW_REPROMPT_COOLDOWN_HOURS,
)
from database import db
from nlp_analyzer import nlp

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BrainDumpBot:
    """
    מחלקה ראשית לניהול הבוט
    """
    
    def __init__(self):
        """אתחול הבוט"""
        self.application = None
        # מילון למעקב אחר מצב המשתמשים
        self.user_states = {}
        # אחסון זמני של מחשבות במצב dump
        self.dump_sessions = {}
        # סשנים עבור ארכוב מרובה (בחירה מרובה)
        self.bulk_archive_sessions = {}
        # סשן סקירה שבועית לכל משתמש
        self.review_sessions: dict[int, dict] = {}
        self.scheduler: AsyncIOScheduler | None = None
    
    async def setup(self, use_updater: bool = False):
        """
        הגדרת הבוט והתחברות לשירותים.

        Args:
            use_updater (bool): האם לאפשר יצירת Updater (נדרש עבור מצב polling).
        """
        if not TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN לא מוגדר - לא ניתן להפעיל את הבוט")

        # התחברות ל-DB
        connected = await db.connect()
        if not connected:
            logger.error("❌ אתחול הבוט הופסק - חיבור ל-MongoDB נכשל")
            raise RuntimeError("MongoDB connection failed - aborting bot setup")
        
        # יצירת application
        builder = Application.builder().token(TELEGRAM_BOT_TOKEN)

        # ב-PTB v20 הייתה מתודת updater() לבקרת ה-Updater; ב-v21 הוסרה.
        if not use_updater:
            try:
                builder.updater(None)  # v20.x
            except AttributeError:
                # v21+: אין Updater בבילדר; מצב webhook לא דורש כלום כאן
                pass

        self.application = builder.build()
        
        # רישום handlers
        self._register_handlers()
        self.application.add_error_handler(self.error_handler)

        mode = "Webhook mode (Updater disabled)" if not use_updater else "Polling mode (Updater enabled)"
        logger.info("✅ הבוט הוגדר בהצלחה (%s)", mode)
    
    def _register_handlers(self):
        """
        רישום כל ה-handlers של הבוט
        """
        app = self.application
        
        # פקודות בסיסיות
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        
        # פקודות ניהול מחשבות
        app.add_handler(CommandHandler("dump", self.dump_command))
        app.add_handler(CommandHandler("done", self.done_command))
        
        # פקודות שליפה וחיפוש
        app.add_handler(CommandHandler("list", self.list_command))
        app.add_handler(CommandHandler("topics", self.list_command))
        app.add_handler(CommandHandler("today", self.today_command))
        app.add_handler(CommandHandler("week", self.week_command))
        app.add_handler(CommandHandler("archive", self.archive_command))
        app.add_handler(CommandHandler("search", self.search_command))
        # סקירה שבועית - ידני
        app.add_handler(CommandHandler("weekly_review", self.weekly_review_command))
        app.add_handler(CommandHandler("review", self.weekly_review_command))
        
        # פקודות נוספות
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CommandHandler("export", self.export_command))
        app.add_handler(CommandHandler("clear", self.clear_command))
        
        # Callback queries (כפתורים)
        app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # הודעות טקסט רגילות
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text
        ))
        
        logger.info("✅ כל ה-handlers נרשמו")

    def start_schedulers(self):
        """הפעלת מתזמנים (APScheduler) לטריגרים אוטומטיים"""
        if not WEEKLY_REVIEW_ENABLED:
            logger.info("⏸️ Weekly review scheduling disabled via config")
            return
        if self.scheduler:
            # למניעת אתחול כפול
            if not self.scheduler.running:
                self.scheduler.start()
            return

        tz = ZoneInfo(TIMEZONE)
        self.scheduler = AsyncIOScheduler(timezone=tz)

        # שישי 16:00
        fri_trigger = CronTrigger(day_of_week='fri', hour=WEEKLY_REVIEW_FRIDAY_HOUR, minute=WEEKLY_REVIEW_FRIDAY_MINUTE, timezone=tz)
        self.scheduler.add_job(self._scheduled_weekly_review_prompt, fri_trigger, id="weekly_review_fri")

        # ראשון 08:00
        sun_trigger = CronTrigger(day_of_week='sun', hour=WEEKLY_REVIEW_SUNDAY_HOUR, minute=WEEKLY_REVIEW_SUNDAY_MINUTE, timezone=tz)
        self.scheduler.add_job(self._scheduled_weekly_review_prompt, sun_trigger, id="weekly_review_sun")

        self.scheduler.start()
        logger.info("⏰ APScheduler התחיל - סקירה שבועית תישלח אוטומטית")

    async def _scheduled_weekly_review_prompt(self):
        """שליחת הודעת פתיחה של סקירה שבועית לכל המשתמשים הפעילים"""
        try:
            user_ids = await db.list_all_user_ids()
        except Exception:
            logger.exception("❌ כשל בשליפת משתמשים לטריגר סקירה")
            return

        if not user_ids:
            logger.info("ℹ️ אין משתמשים לשלוח להם סקירה שבועית")
            return

        tz = ZoneInfo(TIMEZONE)
        now = datetime.now(tz=tz)
        sent = 0
        for uid in user_ids:
            try:
                # מניעת כפילויות: אם נשלחה תזכורת לאחרונה (חלון cooldown), דלג
                user = await self._get_user_doc(uid)
                last_prompt = None
                if user:
                    last_prompt = (((user.get("settings") or {}).get("weekly_review") or {}).get("last_prompted_at"))
                if last_prompt:
                    if last_prompt.tzinfo is None:
                        last_prompt = last_prompt.replace(tzinfo=ZoneInfo("UTC"))
                    hours_since = (now - last_prompt.astimezone(tz)).total_seconds() / 3600.0
                    if hours_since < WEEKLY_REVIEW_REPROMPT_COOLDOWN_HOURS:
                        continue

                keyboard = [
                    [InlineKeyboardButton("בוא נתחיל! 🚀", callback_data="review_start")],
                    [InlineKeyboardButton("אולי מאוחר יותר ⏰", callback_data="review_later")],
                ]
                text = (
                    "🗓️ *שבוע חדש מתחיל!*\n\n"
                    "מוכנים לסקירה קצרה של המחשבות מהשבוע האחרון?\n"
                    "נעבור ונחליט מה להשאיר ומה לארכב."
                )
                await self.application.bot.send_message(
                    chat_id=uid,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                await db.set_weekly_review_prompted(uid)
                sent += 1
            except Exception:
                logger.exception("❌ כשל בשליחת תזכורת סקירה למשתמש %s", uid)
        logger.info("📣 נשלחו %d תזכורות סקירה שבועית", sent)

    async def _get_user_doc(self, user_id: int) -> dict:
        try:
            return await db.users_collection.find_one({"user_id": user_id})
        except Exception:
            return {}
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /start - הודעת פתיחה
        """
        user = update.effective_user
        
        # יצירה/שליפת משתמש ב-DB
        user_data = {
            "username": user.username,
            "first_name": user.first_name
        }
        await db.get_or_create_user(user.id, user_data)
        
        # שליחת הודעת ברוכים הבאים
        await update.message.reply_text(
            MESSAGES["welcome"],
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"👤 משתמש {user.id} (@{user.username}) התחיל שימוש בבוט")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /help - עזרה
        """
        await update.message.reply_text(
            MESSAGES["help_text"],
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def dump_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /dump - כניסה למצב "שפוך הכול"
        """
        user_id = update.effective_user.id
        
        # הפעלת מצב dump
        self.user_states[user_id] = BOT_STATES["DUMP_MODE"]
        self.dump_sessions[user_id] = []
        
        await update.message.reply_text(
            MESSAGES["dump_mode_start"],
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"🌬️ משתמש {user_id} נכנס למצב dump")
    
    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /done - סיום מצב dump וסיכום
        """
        user_id = update.effective_user.id
        
        # בדיקה אם המשתמש במצב dump
        if self.user_states.get(user_id) != BOT_STATES["DUMP_MODE"]:
            await update.message.reply_text(
                "לא הייתם במצב 'שפוך הכול'.\nהשתמשו ב-/dump כדי להתחיל."
            )
            return
        
        # שליחת הודעת עיבוד
        await update.message.reply_text(MESSAGES["dump_mode_end"])
        
        # שליפת המחשבות מהסשן
        thoughts = self.dump_sessions.get(user_id, [])
        
        if not thoughts:
            await update.message.reply_text(MESSAGES["empty_dump"])
            # איפוס מצב
            self.user_states[user_id] = BOT_STATES["NORMAL"]
            del self.dump_sessions[user_id]
            return
        
        # ניתוח ושמירת כל המחשבות
        saved_count = 0
        category_summary = {}
        
        for thought_text in thoughts:
            # ניתוח NLP
            analysis = nlp.analyze(thought_text)
            
            # שמירה ב-DB
            await db.save_thought(
                user_id=user_id,
                raw_text=thought_text,
                nlp_analysis=analysis
            )
            
            saved_count += 1
            
            # ספירה לסיכום
            category = analysis["category"]
            category_summary[category] = category_summary.get(category, 0) + 1
        
        # עדכון סטטיסטיקות משתמש
        await db.update_user_stats(user_id)
        
        # בניית הודעת סיכום
        summary_text = self._build_dump_summary(saved_count, category_summary)
        
        await update.message.reply_text(
            summary_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # איפוס מצב
        self.user_states[user_id] = BOT_STATES["NORMAL"]
        del self.dump_sessions[user_id]
        
        logger.info(f"✅ משתמש {user_id} סיים סשן dump - {saved_count} מחשבות נשמרו")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        טיפול בהודעות טקסט רגילות
        """
        user_id = update.effective_user.id
        text = update.message.text
        
        # בדיקה אם המשתמש במצב dump
        if self.user_states.get(user_id) == BOT_STATES["DUMP_MODE"]:
            # הוספת המחשבה לסשן
            self.dump_sessions[user_id].append(text)
            
            # תגובה שקטה (סימן V)
            await update.message.reply_text(MESSAGES["dump_mode_active"])
            return
        
        # מצב רגיל - ניתוח ושמירה מיידית
        # ניתוח NLP
        analysis = nlp.analyze(text)
        
        # שמירה ב-DB
        try:
            thought_id = await db.save_thought(
                user_id=user_id,
                raw_text=text,
                nlp_analysis=analysis
            )
            await db.update_user_stats(user_id)
        except Exception:
            logger.exception("❌ שגיאה בשמירת מחשבה עבור משתמש %s", user_id)
            await update.message.reply_text(
                "😔 נתקלתי בשגיאה בזמן השמירה. נסו שוב בעוד רגע."
            )
            return
        
        # הודעת תגובה עם הניתוח
        summary = nlp.format_analysis_summary(analysis, text)
        
        response_text = f"✅ *נשמר!*\n\n{summary}"
        
        # כפתורים למשימות נוספות
        keyboard = [
            [
                InlineKeyboardButton("🔍 חיפוש דומים", callback_data=f"similar_{thought_id}"),
                InlineKeyboardButton("📋 רשימת הכל", callback_data="show_all")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            response_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        logger.info(f"💭 מחשבה נשמרה למשתמש {user_id}: {analysis['category']}")
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /list או /topics - הצגת סיכום קטגוריות ונושאים
        """
        user_id = update.effective_user.id
        
        # שליפת סיכומים
        category_summary = await db.get_category_summary(user_id)
        topic_summary = await db.get_topic_summary(user_id)
        
        if not category_summary and not topic_summary:
            await update.message.reply_text(
                "עדיין אין לך מחשבות שמורות.\nתתחיל/י לשתף! 💭"
            )
            return
        
        # בניית הודעה
        lines = ["📊 *סיכום המחשבות שלך:*\n"]
        
        # קטגוריות
        if category_summary:
            lines.append("*📁 קטגוריות:*")
            for category, count in sorted(
                category_summary.items(),
                key=lambda x: x[1],
                reverse=True
            ):
                emoji = nlp.get_category_emoji(category)
                lines.append(f"  {emoji} {category}: {count}")
            lines.append("")
        
        # נושאים
        if topic_summary:
            lines.append("*🏷️ נושאים:*")
            for topic, count in sorted(
                topic_summary.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]:  # רק 5 הראשונים
                emoji = nlp.get_topic_emoji(topic)
                lines.append(f"  {emoji} {topic}: {count}")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /today - מה נרשם היום
        """
        user_id = update.effective_user.id
        
        thoughts = await db.get_thoughts_by_date_range(user_id, days_back=1)
        
        if not thoughts:
            await update.message.reply_text("לא נרשמו מחשבות היום. 🤔")
            return
        
        # בניית הודעה
        lines = [f"📅 *היום רשמת {len(thoughts)} מחשבות:*\n"]
        
        for i, thought in enumerate(thoughts[:10], 1):  # מקסימום 10
            text = (thought.get("raw_text") or "").strip()
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            # קיצור טקסט ארוך
            if len(text) > 50:
                text = text[:47] + "..."
            
            safe_text = self._escape_markdown(text)
            lines.append(f"{i}. {emoji} {safe_text}")
        
        if len(thoughts) > 10:
            lines.append(f"\n_ועוד {len(thoughts) - 10} מחשבות..._")
        
        # כפתורים לבחירת פריטים לארכוב/מחיקה
        keyboard = [
            [
                InlineKeyboardButton("✅ בחר פריטים לארכוב", callback_data="bulk_today_start"),
                InlineKeyboardButton("🗑️ מחק פריטים", callback_data="bulk_today_delete_start"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def week_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /week - מה נרשם השבוע
        """
        user_id = update.effective_user.id
        
        thoughts = await db.get_thoughts_by_date_range(user_id, days_back=7)
        
        if not thoughts:
            await update.message.reply_text("לא נרשמו מחשבות השבוע. 🤔")
            return
        
        # בניית הודעה בפורמט זהה ל-/today
        lines = [f"📆 *השבוע רשמת {len(thoughts)} מחשבות:*\n"]
        
        for i, thought in enumerate(thoughts[:10], 1):  # מקסימום 10
            text = (thought.get("raw_text") or "").strip()
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            if len(text) > 50:
                text = text[:47] + "..."
            
            safe_text = self._escape_markdown(text)
            lines.append(f"{i}. {emoji} {safe_text}")
        
        if len(thoughts) > 10:
            lines.append(f"\n_ועוד {len(thoughts) - 10} מחשבות..._")
        
        # כפתורים לבחירת פריטים לארכוב/מחיקה
        keyboard = [
            [
                InlineKeyboardButton("✅ בחר פריטים לארכוב", callback_data="bulk_week_start"),
                InlineKeyboardButton("🗑️ מחק פריטים", callback_data="bulk_week_delete_start"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def archive_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /archive - הצגת מחשבות בארכיון
        """
        user_id = update.effective_user.id
        thoughts = await db.get_user_thoughts(user_id, limit=10, status=THOUGHT_STATUS["ARCHIVED"])
        
        if not thoughts:
            await update.message.reply_text("אין פריטים בארכיון כרגע.")
            return
        
        lines = ["📦 *המחשבות בארכיון:*\n"]
        for i, thought in enumerate(thoughts, 1):
            text = (thought.get("raw_text") or "").strip()
            if len(text) > 50:
                text = text[:47] + "..."
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            safe_text = self._escape_markdown(text)
            lines.append(f"{i}. {emoji} {safe_text}")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
        )
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /search - חיפוש מחשבות
        """
        user_id = update.effective_user.id
        
        # קבלת מונח החיפוש
        if not context.args:
            await update.message.reply_text(
                "שימוש: /search <מילת חיפוש>\nלדוגמה: /search עבודה"
            )
            return
        
        search_term = " ".join(context.args).strip()
        escaped_search_term = self._escape_markdown(search_term)
        
        # חיפוש
        results = await db.search_thoughts(user_id, search_term)
        
        if not results:
            await update.message.reply_text(
                f"לא נמצאו תוצאות עבור '{search_term}' 🔍"
            )
            return
        
        # בניית הודעה
        lines = [f"🔍 *נמצאו {len(results)} תוצאות עבור '{escaped_search_term}':*\n"]
        
        for i, thought in enumerate(results[:8], 1):
            text = (thought.get("raw_text") or "").strip()
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            if len(text) > 60:
                text = text[:57] + "..."
            
            safe_text = self._escape_markdown(text)
            lines.append(f"{i}. {emoji} {safe_text}")
        
        if len(results) > 8:
            lines.append(f"\n_ועוד {len(results) - 8} תוצאות..._")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
        )

    async def weekly_review_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /weekly_review או /review - התחלת סקירה שבועית ידנית
        """
        user_id = update.effective_user.id

        thoughts = await db.get_thoughts_by_date_range(user_id, days_back=7)
        if not thoughts:
            await update.message.reply_text(
                "לא נמצאו מחשבות מהשבוע האחרון.\nהמשך לכתוב ונדבר שבוע הבא! 😊"
            )
            return

        # שמירת סשן סקירה בסיסי (רשימת מזהים וסדר)
        items = []
        for t in thoughts:
            items.append({
                "id": str(t.get("_id")),
                "text": (t.get("raw_text") or "").strip(),
                "created_at": t.get("created_at"),
                "category": t.get("nlp_analysis", {}).get("category", "")
            })

        self.review_sessions[user_id] = {
            "items": items,
            "index": 0,
            "kept": 0,
            "archived": 0,
        }

        keyboard = [
            [InlineKeyboardButton("בוא נתחיל! 🚀", callback_data="review_start")],
            [InlineKeyboardButton("אולי מאוחר יותר ⏰", callback_data="review_later")],
        ]
        await update.message.reply_text(
            f"🗓️ *שבוע חדש מתחיל!*\n\n"
            f"השבוע שעבר רשמת *{len(items)}* מחשבות.\n"
            f"בוא/י נעבור עליהן ונבחר מה להשאיר לשבוע הבא.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /stats - סטטיסטיקות אישיות
        """
        user_id = update.effective_user.id
        
        stats = await db.get_user_stats(user_id)
        
        if not stats or stats.get("total_thoughts", 0) == 0:
            await update.message.reply_text(
                "עדיין אין סטטיסטיקות.\nתתחיל/י לשתף מחשבות! 💭"
            )
            return
        
        # בניית הודעה
        total = stats["total_thoughts"]
        joined = stats["joined_at"].strftime("%d/%m/%Y")
        
        lines = [
            "📈 *הסטטיסטיקות שלך:*\n",
            f"💭 סה״כ מחשבות: *{total}*",
            f"📅 חבר/ה מאז: {joined}\n"
        ]
        
        # הקטגוריה הפופולרית ביותר
        if stats.get("categories"):
            top_category = max(stats["categories"].items(), key=lambda x: x[1])
            emoji = nlp.get_category_emoji(top_category[0])
            lines.append(
                f"🏆 הכי הרבה: {emoji} {top_category[0]} ({top_category[1]})"
            )
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def export_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /export - ייצוא מחשבות (בסיסי)
        """
        await update.message.reply_text(
            "🚧 הפיצ'ר של ייצוא עדיין בפיתוח!\n"
            "בקרוב תוכלו לייצא את כל המחשבות ל-TXT/CSV 📄"
        )
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        פקודת /clear - מחיקת כל המחשבות (עם אישור)
        """
        keyboard = [
            [
                InlineKeyboardButton("✅ כן, מחק הכל", callback_data="confirm_clear"),
                InlineKeyboardButton("❌ ביטול", callback_data="cancel_clear")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ *אזהרה!*\n\n"
            "פעולה זו תמחק את *כל* המחשבות שלך.\n"
            "האם אתה בטוח?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        טיפול בלחיצות על כפתורים
        """
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "show_all":
            # הצגת כל המחשבות
            await self._show_recent_thoughts(query, user_id)
        
        # ===== ארכוב מרובה - זרימה 4 =====
        elif data == "bulk_today_start":
            # אתחול סשן לבחירה מרובה עבור מחשבות היום (ארכוב)
            await self._start_bulk_archive_session(query, user_id, days_back=1)
        elif data == "bulk_week_start":
            # אתחול סשן לבחירה מרובה עבור מחשבות השבוע (ארכוב)
            await self._start_bulk_archive_session(query, user_id, days_back=7)
        elif data == "bulk_today_delete_start":
            # אתחול סשן לבחירה מרובה עבור מחשבות היום (מחיקה)
            await self._start_bulk_delete_session(query, user_id, days_back=1)
        elif data == "bulk_week_delete_start":
            # אתחול סשן לבחירה מרובה עבור מחשבות השבוע (מחיקה)
            await self._start_bulk_delete_session(query, user_id, days_back=7)
        
        elif data.startswith("bulk_tog_"):
            # החלפת מצב בחירה למחשבה לפי מזהה
            thought_id = data.replace("bulk_tog_", "")
            await self._toggle_bulk_selection(query, user_id, thought_id)
        
        elif data == "bulk_apply":
            # ביצוע ארכוב לפריטים שנבחרו
            await self._apply_bulk_archive(query, user_id)
        elif data == "bulk_delete_apply":
            # ביצוע מחיקה לפריטים שנבחרו
            await self._apply_bulk_delete(query, user_id)
        
        elif data == "bulk_cancel":
            # ביטול הסשן
            self.bulk_archive_sessions.pop(user_id, None)
            await query.edit_message_text("✅ בוטל.")
        
        elif data == "confirm_clear":
            # מחיקה מאושרת
            count = await db.delete_all_user_thoughts(user_id)
            await query.edit_message_text(
                f"🗑️ נמחקו {count} מחשבות.\n"
                "תתחיל/י מחדש מתי שתרצה! 🌱"
            )
        
        elif data == "cancel_clear":
            await query.edit_message_text("✅ בוטל. המחשבות נשארות.")
        
        elif data.startswith("similar_"):
            await query.edit_message_text("🚧 חיפוש דומים בפיתוח...")

        # ===== סקירה שבועית - זרימה =====
        elif data == "review_later":
            await query.edit_message_text("⏰ אין בעיה, נזכיר בהמשך.")
        elif data == "review_start":
            await self._review_show_current(query, user_id)
        elif data.startswith("review_keep_"):
            # שמירה: לא משנים סטטוס
            await self._review_handle_decision(query, user_id, action="keep", thought_id=data.replace("review_keep_", ""))
        elif data.startswith("review_archive_"):
            await self._review_handle_decision(query, user_id, action="archive", thought_id=data.replace("review_archive_", ""))
        elif data == "review_skip":
            await self._review_handle_decision(query, user_id, action="skip")
        elif data == "review_finish":
            await self._review_finish(query, user_id)

    async def _start_bulk_archive_session(self, query, user_id: int, days_back: int = 1):
        """
        אתחול סשן לבחירה מרובה של מחשבות לארכוב
        """
        # שליפת מחשבות לפי טווח ימים (פעילות)
        thoughts = await db.get_thoughts_by_date_range(user_id, days_back=days_back)
        if not thoughts:
            await query.edit_message_text("לא נרשמו מחשבות היום. 🤔")
            return
        
        # בניית רשימת מחשבות לסשן
        session_thoughts = []
        preselected_ids = set()
        for t in thoughts[:20]:  # מגבילים ל-20 לרוחב הודעה
            tid = str(t.get("_id"))
            text = t.get("raw_text", "").strip()
            category = t.get("nlp_analysis", {}).get("category", "הרהורים")
            if len(text) > 60:
                text = text[:57] + "..."
            session_thoughts.append({"id": tid, "text": text, "category": category})
            # ברירת מחדל: לבחור פריטי "משימות"
            if category == "משימות":
                preselected_ids.add(tid)
        
        # שמירת סשן
        self.bulk_archive_sessions[user_id] = {
            "thoughts": session_thoughts,
            "selected": preselected_ids,
            "mode": "archive",
        }
        
        # הצגה ראשונית
        text = self._build_bulk_archive_message(session_thoughts, preselected_ids)
        keyboard = self._build_bulk_selection_keyboard(session_thoughts, preselected_ids, mode="archive")
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    async def _start_bulk_delete_session(self, query, user_id: int, days_back: int = 1):
        """
        אתחול סשן לבחירה מרובה של מחשבות למחיקה
        """
        thoughts = await db.get_thoughts_by_date_range(user_id, days_back=days_back)
        if not thoughts:
            await query.edit_message_text("לא נרשמו מחשבות רלוונטיות. 🤔")
            return
        
        session_thoughts = []
        preselected_ids = set()
        for t in thoughts[:20]:
            tid = str(t.get("_id"))
            text = t.get("raw_text", "").strip()
            category = t.get("nlp_analysis", {}).get("category", "הרהורים")
            if len(text) > 60:
                text = text[:57] + "..."
            session_thoughts.append({"id": tid, "text": text, "category": category})
            if category == "משימות":
                preselected_ids.add(tid)
        
        self.bulk_archive_sessions[user_id] = {
            "thoughts": session_thoughts,
            "selected": preselected_ids,
            "mode": "delete",
        }
        
        text = self._build_bulk_archive_message(session_thoughts, preselected_ids)
        keyboard = self._build_bulk_selection_keyboard(session_thoughts, preselected_ids, mode="delete")
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    def _build_bulk_archive_message(self, thoughts: list[dict], selected: set[str]) -> str:
        """
        בניית טקסט ההודעה לבחירה מרובה עם תיבות סימון
        """
        lines = ["בחר/י מחשבות לארכוב:\n"]
        for item in thoughts:
            mark = "☑️" if item["id"] in selected else "☐"
            emoji = nlp.get_category_emoji(item.get("category", ""))
            display_text = self._escape_markdown(item.get("text", ""))
            lines.append(f"{mark} {emoji} {display_text}")
        return "\n".join(lines)

    def _build_bulk_selection_keyboard(self, thoughts: list[dict], selected: set[str], mode: str) -> InlineKeyboardMarkup:
        """
        בניית מקלדת כפתורי בחירה + פעולות בהתאם למצב (ארכוב/מחיקה)
        """
        rows = []
        for item in thoughts:
            mark = "☑️" if item["id"] in selected else "☐"
            label = item["text"]
            if len(label) > 28:
                label = label[:25] + "..."
            rows.append([
                InlineKeyboardButton(f"{mark} {label}", callback_data=f"bulk_tog_{item['id']}")
            ])
        
        apply_count = len(selected)
        if mode == "delete":
            apply_btn = InlineKeyboardButton(f"🗑️ מחק נבחרים ({apply_count})", callback_data="bulk_delete_apply")
        else:
            apply_btn = InlineKeyboardButton(f"📦 ארכב נבחרים ({apply_count})", callback_data="bulk_apply")
        rows.append([apply_btn, InlineKeyboardButton("❌ ביטול", callback_data="bulk_cancel")])
        return InlineKeyboardMarkup(rows)

    async def _toggle_bulk_selection(self, query, user_id: int, thought_id: str):
        """
        החלפת מצב בחירה של מחשבה בסשן הפעיל
        """
        session = self.bulk_archive_sessions.get(user_id)
        if not session:
            await query.answer("אין סשן פעיל")
            return
        
        selected: set[str] = session["selected"]
        if thought_id in selected:
            selected.remove(thought_id)
        else:
            selected.add(thought_id)
        
        # רענון התצוגה
        thoughts = session["thoughts"]
        text = self._build_bulk_archive_message(thoughts, selected)
        keyboard = self._build_bulk_selection_keyboard(thoughts, selected, mode=session.get("mode", "archive"))
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    async def _apply_bulk_action(self, query, user_id: int, action: str):
        """
        מבצע פעולה מרובה (ארכוב/מחיקה) עבור הבחירות בסשן
        """
        session = self.bulk_archive_sessions.get(user_id)
        if not session:
            await query.answer("אין סשן פעיל")
            return
        
        selected_ids = list(session.get("selected", []))
        if not selected_ids:
            await query.answer("לא נבחרו פריטים")
            return
        
        if action == "delete":
            count = await db.delete_thoughts_bulk(user_id, selected_ids)
        else:
            count = await db.archive_thoughts_bulk(user_id, selected_ids)
        await db.update_user_stats(user_id)
        
        # ניקוי סשן
        self.bulk_archive_sessions.pop(user_id, None)
        
        if action == "delete":
            await query.edit_message_text(f"🗑️ *{count}* מחשבות נמחקו!", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.edit_message_text(f"✅ *{count}* מחשבות הועברו לארכיון!", parse_mode=ParseMode.MARKDOWN)

    async def _apply_bulk_archive(self, query, user_id: int):
        await self._apply_bulk_action(query, user_id, action="archive")

    async def _apply_bulk_delete(self, query, user_id: int):
        await self._apply_bulk_action(query, user_id, action="delete")
    
    async def _show_recent_thoughts(self, query, user_id: int):
        """
        הצגת מחשבות אחרונות
        """
        thoughts = await db.get_user_thoughts(user_id, limit=10)
        
        if not thoughts:
            await query.edit_message_text("אין מחשבות להצגה.")
            return
        
        lines = ["📝 *המחשבות האחרונות:*\n"]
        
        for i, thought in enumerate(thoughts, 1):
            text = (thought.get("raw_text") or "").strip()
            if len(text) > 40:
                text = text[:37] + "..."
            
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            safe_text = self._escape_markdown(text)
            lines.append(f"{i}. {emoji} {safe_text}")
        
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
        )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """
        טיפול בשגיאות גלובליות של הבוט
        """
        logger.exception("❌ שגיאה לא מטופלת בבוט", exc_info=context.error)

        message = getattr(update, "effective_message", None) if update else None
        if message:
            try:
                await message.reply_text(
                    "😬 קרתה שגיאה זמנית. נסו שוב מאוחר יותר."
                )
            except Exception:
                logger.exception("❌ כשל בשליחת הודעת שגיאה למשתמש")
    
    def _build_dump_summary(self, count: int, category_summary: dict) -> str:
        """
        בניית הודעת סיכום לסשן dump
        """
        lines = [
            "✅ *סיימתי לעבד!*\n",
            f"💾 נשמרו {count} מחשבות\n",
            "*פילוח לפי קטגוריות:*"
        ]
        
        for category, num in sorted(
            category_summary.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            emoji = nlp.get_category_emoji(category)
            lines.append(f"  {emoji} {category}: {num}")
        
        return "\n".join(lines)

    def _escape_markdown(self, text: str) -> str:
        """
        איסוף טקסט של משתמשים לפני שליחה במצב Markdown
        """
        if not text:
            return ""
        return escape_markdown(text, version=1)

    # ===== Weekly Review helpers =====
    async def _review_show_current(self, query, user_id: int):
        session = self.review_sessions.get(user_id)
        if not session or not session.get("items"):
            await query.edit_message_text("אין מחשבות לסקירה כרגע.")
            return

        idx = session.get("index", 0)
        items = session["items"]
        if idx >= len(items):
            await self._review_finish(query, user_id)
            return

        item = items[idx]
        text = item.get("text", "")
        if len(text) > 140:
            text = text[:137] + "..."
        safe_text = self._escape_markdown(text)

        created_at = item.get("created_at")
        ago_str = ""
        if isinstance(created_at, datetime):
            # חישוב זמן שחלף
            now = datetime.now(tz=ZoneInfo(TIMEZONE))
            created_naive = created_at
            # created_at מה-DB לרוב naive ב-UTC
            if created_naive.tzinfo is None:
                created_naive = created_naive.replace(tzinfo=ZoneInfo("UTC"))
            delta = now - created_naive.astimezone(ZoneInfo(TIMEZONE))
            days = delta.days
            if days <= 0:
                ago_str = "נרשם: היום"
            elif days == 1:
                ago_str = "נרשם: אתמול"
            else:
                ago_str = f"נרשם: לפני {days} ימים"

        emoji = nlp.get_category_emoji(item.get("category", ""))

        lines = [
            f"{emoji} *סקירה שבועית*",
            "",
            safe_text,
        ]
        if ago_str:
            lines.append(ago_str)

        keyboard = [
            [
                InlineKeyboardButton("השאר ✅", callback_data=f"review_keep_{item['id']}"),
                InlineKeyboardButton("ארכב 📦", callback_data=f"review_archive_{item['id']}")
            ],
            [
                InlineKeyboardButton("דלג ➡️", callback_data="review_skip"),
                InlineKeyboardButton("סיים עכשיו", callback_data="review_finish"),
            ],
        ]

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _review_handle_decision(self, query, user_id: int, action: str, thought_id: str | None = None):
        session = self.review_sessions.get(user_id)
        if not session:
            await query.answer("אין סקירה פעילה")
            return
        idx = session.get("index", 0)
        items = session.get("items", [])
        if idx >= len(items):
            await self._review_finish(query, user_id)
            return

        current = items[idx]
        # ודא התאמה מזהה כאשר מדובר בפעולה ספציפית
        if thought_id and current.get("id") != thought_id:
            # אם לא תואם, מציגים הנוכחי ללא שינוי
            await self._review_show_current(query, user_id)
            return

        if action == "archive":
            await db.update_thought_status(current["id"], THOUGHT_STATUS["ARCHIVED"])
            session["archived"] = session.get("archived", 0) + 1
        elif action == "keep":
            session["kept"] = session.get("kept", 0) + 1
        # skip לא משנה מונים

        # מעבר לפריט הבא
        session["index"] = idx + 1

        if session["index"] >= len(items):
            await self._review_finish(query, user_id)
        else:
            await self._review_show_current(query, user_id)

    async def _review_finish(self, query, user_id: int):
        session = self.review_sessions.pop(user_id, None)
        if not session:
            await query.edit_message_text("✅ סקירה הושלמה!")
            return

        kept = session.get("kept", 0)
        archived = session.get("archived", 0)
        total = kept + archived + (len(session.get("items", [])) - session.get("index", 0))

        lines = [
            "✅ *סקירה הושלמה!*\n",
            "📊 התוצאות:",
            f"• נשארו: {kept}",
            f"• ארכבו: {archived}",
            "",
            "💡 המחשבות שארכבת זמינות דרך /archive או /search",
            "מוכן/ה לשבוע חדש! 🚀",
        ]

        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
        )


# יצירת אובייקט גלובלי
bot = BrainDumpBot()
