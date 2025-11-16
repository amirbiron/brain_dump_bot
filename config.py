"""
קובץ הגדרות ראשי לבוט ריקון מוח
מכיל את כל ההגדרות, קטגוריות, וטריגרים
"""

import os
from dotenv import load_dotenv
from typing import Optional

# טעינת משתני סביבה
load_dotenv()

# ===== הגדרות Telegram =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# ===== הגדרות MongoDB =====
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "brain_dump_bot")
MONGODB_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT_MS", "5000"))
MONGODB_CONNECT_TIMEOUT_MS = int(os.getenv("MONGODB_CONNECT_TIMEOUT_MS", "5000"))
MONGODB_SOCKET_TIMEOUT_MS = int(os.getenv("MONGODB_SOCKET_TIMEOUT_MS", "10000"))
MONGODB_MAX_POOL_SIZE = int(os.getenv("MONGODB_MAX_POOL_SIZE", "10"))

# ===== הגדרות Render =====
PORT = int(os.getenv("PORT", 10000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

# ===== קטגוריות והגדרות NLP =====

# קטגוריות עיקריות
CATEGORIES = {
    "משימות": {
        "emoji": "✅",
        "description": "דברים שצריך לעשות",
        "triggers": [
            "צריך", "חייב", "לא לשכוח", "להזכיר", "מחר",
            "השבוע", "לעשות", "לקבוע", "לשלם", "לקנות",
            "להתקשר", "לכתוב", "לשלוח", "לסדר"
        ]
    },
    "רעיונות": {
        "emoji": "💡",
        "description": "מחשבות יצירתיות ורעיונות",
        "triggers": [
            "אולי", "בא לי", "חשבתי", "רעיון", "מעניין",
            "כדאי", "אפשר", "נחמד אם", "מה אם", "יהיה מגניב"
        ]
    },
    "רגשות": {
        "emoji": "💭",
        "description": "תחושות ומצבי רוח",
        "triggers": [
            "אין לי כוח", "מרגיש", "מתסכל", "שמח", "עצוב",
            "כועס", "מפחיד", "מלחיץ", "טוב לי", "קשה לי",
            "מתח", "לחץ", "חרדה", "דאגה"
        ]
    },
    "מטרות": {
        "emoji": "🎯",
        "description": "שאיפות ויעדים ארוכי טווח",
        "triggers": [
            "להתחיל", "לשנות", "להשתפר", "ללמוד", "לפתח",
            "מטרה", "יעד", "רוצה", "חולם", "שאיפה",
            "להצליח", "להגיע", "קורס", "ללכת לחדר כושר"
        ]
    },
    "הרהורים": {
        "emoji": "🤔",
        "description": "מחשבות עמוקות ושאלות",
        "triggers": [
            "למה", "מדוע", "איך זה", "תוהה", "מעניין",
            "שאלה", "לא מבין", "זה מוזר", "תמיד", "לעולם"
        ]
    }
}

# נושאים/תגיות
TOPICS = {
    "עבודה": {
        "emoji": "💼",
        "keywords": [
            "עבודה", "משרד", "בוס", "פגישה", "מייל",
            "פרויקט", "לקוח", "מצגת", "דיווח", "ישיבה"
        ]
    },
    "בית": {
        "emoji": "🏠",
        "keywords": [
            "בית", "ניקיון", "תיקון", "ארנונה", "שכירות",
            "חשמל", "מים", "גז", "רהיטים", "מטבח"
        ]
    },
    "כסף": {
        "emoji": "💰",
        "keywords": [
            "כסף", "משכורת", "תשלום", "חשבון", "בנק",
            "חוב", "הלוואה", "חיסכון", "השקעה", "מיסים"
        ]
    },
    "בריאות": {
        "emoji": "🏥",
        "keywords": [
            "רופא", "תור", "בריאות", "כאב", "תרופה",
            "ספורט", "חדר כושר", "ריצה", "דיאטה", "אוכל בריא"
        ]
    },
    "משפחה": {
        "emoji": "👨‍👩‍👧‍👦",
        "keywords": [
            "משפחה", "הורים", "ילדים", "בן זוג", "אח",
            "אחות", "סבא", "סבתא", "יומולדת", "חג"
        ]
    },
    "חברים": {
        "emoji": "👥",
        "keywords": [
            "חבר", "חברה", "מסיבה", "יציאה", "בילוי",
            "מפגש", "שיחה", "קפה", "בירה"
        ]
    },
    "לימודים": {
        "emoji": "📚",
        "keywords": [
            "קורס", "ללמוד", "ספר", "מאמר", "הכשרה",
            "סדנה", "תואר", "לימודים", "שיעור", "מורה"
        ]
    },
    "קניות": {
        "emoji": "🛒",
        "keywords": [
            "לקנות", "לרכוש", "חנות", "סופר", "מתנה",
            "הזמנה", "משלוח", "מוצר", "מבצע"
        ]
    }
}

# ===== הודעות ממשק =====

MESSAGES = {
    "welcome": """
🧠 *ברוכים הבאים לבוט ריקון מוח!*

אני כאן בשביל להיות "המוח השני" שלך - מקום בטוח לשפוך מחשבות, רעיונות, משימות ורגשות.

🌟 *איך זה עובד?*
• פשוט כתבו לי כל מה שעובר לכם בראש
• אני אסווג ואארגן את זה בשבילכם
• תוכלו לחפש, לסנן ולייצא מתי שתרצו

📝 *פקודות עיקריות:*
/dump - מצב "שפוך הכול" (אני רק מאזין)
/done - סיום מצב שפיכה + סיכום
/list - רשימת כל הקטגוריות
/today - מה רשמתם היום
/weekly_review - סקירה שבועית ידנית
/review - קיצור ל-/weekly_review
/search <מילה> - חיפוש חופשי
/export - ייצוא לקובץ
/help - עזרה מלאה

בואו נתחיל! 🚀
""",
    
    "dump_mode_start": """
🌬️ *מצב "שפוך הכול" מופעל!*

אני מאזין לכל מה שיש לך לומר.
רק תכתוב/י בחופשיות, ואני אתעד הכול.

כשתסיימ/י, שלח/י את הפקודה: /done
""",
    
    "dump_mode_active": "✅",  # תגובה שקטה למהלך מצב dump
    
    "dump_mode_end": """
⌛ *מעבד את המחשבות שלך...*

רגע אחד, אני מסכם ומסווג את מה ששיתפת.
""",
    
    "empty_dump": """
😊 לא נרשמו מחשבות במהלך הסשן.

רוצה לנסות שוב? שלח /dump
""",
    
    "help_text": """
🧠 *מדריך שימוש מלא*

*מצבי עבודה:*
1️⃣ *מצב רגיל* - שולחים הודעה, מקבלים ניתוח מיידי
2️⃣ *מצב שפיכה* (/dump) - שולחים כמה הודעות, מסכמים עם /done

*פקודות חיפוש:*
/list או /topics - כל הקטגוריות והנושאים
/topic <שם> - הצגת פריטים מקטגוריה ספציפית
/today - מה נרשם היום
/week - מה נרשם השבוע
/archive - צפייה בפריטים בארכיון
/search <מילה> - חיפוש חופשי בכל המחשבות

*סקירה שבועית:*
/weekly_review או /review - התחלת סקירה שבועית ידנית
⏰ תזמון אוטומטי: שישי 16:00 וראשון 08:00 (Asia/Jerusalem)

*פקודות ניהול:*
/stats - סטטיסטיקה אישית
/export - ייצוא המידע לקובץ
/clear - ניקוי כל המידע (זהירות!)

*טיפים:*
💡 כתבו בחופשיות - הבוט יזהה קטגוריות אוטומטית
💡 השתמשו ב-/dump כשיש הרבה מחשבות
💡 חיפוש עובד גם על מילים חלקיות

שאלות? פשוט כתבו לי! 😊
"""
}

# ===== הגדרות נוספות =====

# מצבי בוט
BOT_STATES = {
    "NORMAL": "normal",
    "DUMP_MODE": "dump_mode"
}

# סטטוסים של מחשבות
THOUGHT_STATUS = {
    "ACTIVE": "active",
    "ARCHIVED": "archived",
    "TASK_CREATED": "task_created",
    "DELETED": "deleted"
}

# הגדרות ייצוא
EXPORT_FORMATS = ["txt", "csv", "json"]
MAX_EXPORT_SIZE = 10000  # מקסימום מחשבות בייצוא

# הגדרות זמן
TIMEZONE = "Asia/Jerusalem"

# לוג
DEBUG_MODE = os.getenv("DEBUG", "False").lower() == "true"

# ===== סקירה שבועית (Weekly Review) =====
# אפשרות להפעיל/לכבות ולשלוט בזמנים דרך משתני סביבה
WEEKLY_REVIEW_ENABLED = os.getenv("WEEKLY_REVIEW_ENABLED", "true").lower() == "true"

# ברירת מחדל: שישי 16:00 וראשון 08:00
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

WEEKLY_REVIEW_FRIDAY_HOUR = _int_env("WEEKLY_REVIEW_FRIDAY_HOUR", 16)
WEEKLY_REVIEW_FRIDAY_MINUTE = _int_env("WEEKLY_REVIEW_FRIDAY_MINUTE", 0)
WEEKLY_REVIEW_SUNDAY_HOUR = _int_env("WEEKLY_REVIEW_SUNDAY_HOUR", 8)
WEEKLY_REVIEW_SUNDAY_MINUTE = _int_env("WEEKLY_REVIEW_SUNDAY_MINUTE", 0)

# חלון מניעת כפילויות (בשעות) בין טריגרים אוטומטיים
WEEKLY_REVIEW_REPROMPT_COOLDOWN_HOURS = _int_env("WEEKLY_REVIEW_REPROMPT_COOLDOWN_HOURS", 36)
