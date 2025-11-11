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
from datetime import datetime, timedelta
import logging

from config import (
    TELEGRAM_BOT_TOKEN,
    MESSAGES,
    BOT_STATES,
    CATEGORIES,
    TOPICS
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
    
    async def setup(self):
        """
        הגדרת הבוט והתחברות לשירותים
        """
        # התחברות ל-DB
        await db.connect()
        
        # יצירת application
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # רישום handlers
        self._register_handlers()
        
        logger.info("✅ הבוט הוגדר בהצלחה")
    
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
        app.add_handler(CommandHandler("search", self.search_command))
        
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
        thought_id = await db.save_thought(
            user_id=user_id,
            raw_text=text,
            nlp_analysis=analysis
        )
        
        # עדכון סטטיסטיקות
        await db.update_user_stats(user_id)
        
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
            text = thought["raw_text"]
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            # קיצור טקסט ארוך
            if len(text) > 50:
                text = text[:47] + "..."
            
            lines.append(f"{i}. {emoji} {text}")
        
        if len(thoughts) > 10:
            lines.append(f"\n_ועוד {len(thoughts) - 10} מחשבות..._")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
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
        
        # ניתוח לפי ימים
        days_data = {}
        for thought in thoughts:
            date = thought["created_at"].strftime("%Y-%m-%d")
            days_data[date] = days_data.get(date, 0) + 1
        
        # בניית הודעה
        lines = [f"📆 *השבוע רשמת {len(thoughts)} מחשבות:*\n"]
        
        for date, count in sorted(days_data.items(), reverse=True):
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            day_name = date_obj.strftime("%A")
            lines.append(f"• {day_name}: {count} מחשבות")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
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
        
        search_term = " ".join(context.args)
        
        # חיפוש
        results = await db.search_thoughts(user_id, search_term)
        
        if not results:
            await update.message.reply_text(
                f"לא נמצאו תוצאות עבור '{search_term}' 🔍"
            )
            return
        
        # בניית הודעה
        lines = [f"🔍 *נמצאו {len(results)} תוצאות עבור '{search_term}':*\n"]
        
        for i, thought in enumerate(results[:8], 1):
            text = thought["raw_text"]
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            if len(text) > 60:
                text = text[:57] + "..."
            
            lines.append(f"{i}. {emoji} {text}")
        
        if len(results) > 8:
            lines.append(f"\n_ועוד {len(results) - 8} תוצאות..._")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
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
            text = thought["raw_text"]
            if len(text) > 40:
                text = text[:37] + "..."
            
            category = thought["nlp_analysis"]["category"]
            emoji = nlp.get_category_emoji(category)
            
            lines.append(f"{i}. {emoji} {text}")
        
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN
        )
    
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


# יצירת אובייקט גלובלי
bot = BrainDumpBot()
