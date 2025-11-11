# 🧠 בוט ריקון מוח (Brain Dump Bot)

בוט טלגרם חכם שעוזר לך לארגן מחשבות, רעיונות ומשימות בצורה אוטומטית.  
המוח השני שלך - מקום בטוח לשפוך כל מה שעובר לך בראש! 💭

## ✨ תכונות עיקריות

### 🎯 ליבת הפונקציונליות
- **ריקון מוח חופשי**: פשוט תכתוב מה שבא לך, הבוט יסווג אוטומטית
- **מצב "שפוך הכול"**: אפשרות לכתוב בזרימה ללא הפרעות
- **סיווג חכם**: זיהוי אוטומטי של קטגוריות ונושאים בעברית
- **חיפוש מתקדם**: מציאת מחשבות לפי מילות מפתח, תאריכים וקטגוריות
- **סטטיסטיקות**: מעקב אחרי הדפוסים שלך

### 🏷️ קטגוריות שהבוט מזהה
- ✅ **משימות** - דברים שצריך לעשות
- 💡 **רעיונות** - מחשבות יצירתיות
- 💭 **רגשות** - תחושות ומצבי רוח
- 🎯 **מטרות** - שאיפות ארוכות טווח
- 🤔 **הרהורים** - מחשבות עמוקות ושאלות

### 🗂️ נושאים שהבוט מזהה
💼 עבודה | 🏠 בית | 💰 כסף | 🏥 בריאות | 👨‍👩‍👧‍👦 משפחה | 👥 חברים | 📚 לימודים | 🛒 קניות

---

## 📋 דרישות מקדימות

- Python 3.9 ומעלה
- חשבון MongoDB (חינם ב-[MongoDB Atlas](https://www.mongodb.com/cloud/atlas))
- בוט טלגרם (יצירה דרך [@BotFather](https://t.me/botfather))
- חשבון Render (חינם ב-[Render](https://render.com))

---

## 🚀 התקנה מהירה

### שלב 1: הורדת הקוד
```bash
git clone <repository-url>
cd brain-dump-bot
```

### שלב 2: יצירת סביבת עבודה
```bash
python -m venv venv

# הפעלה ב-Windows
venv\Scripts\activate

# הפעלה ב-Mac/Linux
source venv/bin/activate
```

### שלב 3: התקנת תלויות
```bash
pip install -r requirements.txt
```

### שלב 4: הגדרת משתני סביבה

צור קובץ `.env` (העתק מ-`.env.example`):

```bash
cp .env.example .env
```

ערוך את הקובץ `.env` והוסף את הערכים שלך:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# MongoDB Configuration
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
MONGODB_DB_NAME=brain_dump_bot

# Render Configuration (רק לייצור)
PORT=10000
RENDER_EXTERNAL_URL=https://your-app-name.onrender.com

# Bot Configuration
ADMIN_USER_ID=your_telegram_user_id
DEBUG=False
```

---

## 🔧 קבלת הנתונים הנדרשים

### 1️⃣ יצירת בוט טלגרם

1. פתח שיחה עם [@BotFather](https://t.me/botfather) בטלגרם
2. שלח את הפקודה: `/newbot`
3. עקוב אחרי ההוראות ובחר שם לבוט
4. שמור את ה-**TOKEN** שתקבל
5. הדבק אותו ב-`.env` תחת `TELEGRAM_BOT_TOKEN`

### 2️⃣ הקמת MongoDB

#### דרך MongoDB Atlas (מומלץ - חינם):

1. היכנס ל-[MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. צור Cluster חדש (בחר בתכנית החינמית)
3. צור משתמש DB עם סיסמה
4. הוסף את כתובת ה-IP שלך לרשימת ההיתרים (או `0.0.0.0/0` לגישה מכל מקום)
5. לחץ על "Connect" → "Connect your application"
6. העתק את ה-Connection String
7. החלף את `<password>` בסיסמה שיצרת
8. הדבק ב-`.env` תחת `MONGODB_URI`

דוגמה:
```
mongodb+srv://myuser:mypassword123@cluster0.abc123.mongodb.net/
```

### 3️⃣ מציאת ה-User ID שלך בטלגרם

1. פתח שיחה עם [@userinfobot](https://t.me/userinfobot)
2. הבוט ישלח לך את ה-ID שלך
3. הדבק אותו ב-`.env` תחת `ADMIN_USER_ID`

---

## 💻 הרצה מקומית (פיתוח)

### בדיקה מהירה:
```bash
python main.py
```

הבוט ירוץ במצב **polling** (מתאים לפיתוח מקומי).

### בדיקה שהכל עובד:
1. פתח את הבוט בטלגרם
2. שלח `/start`
3. אמור להגיע הודעת ברוכים הבאים 🎉

---

## ☁️ פריסה ל-Render (ייצור)

### שלב 1: יצירת Git Repository

```bash
git init
git add .
git commit -m "Initial commit - Brain Dump Bot"
```

העלה ל-GitHub/GitLab (יצר repository חדש ועקוב אחר ההוראות).

### שלב 2: יצירת Web Service ב-Render

1. היכנס ל-[Render Dashboard](https://dashboard.render.com/)
2. לחץ על **"New +"** → **"Web Service"**
3. חבר את ה-repository שלך
4. הגדרות:
   - **Name**: `brain-dump-bot` (או כל שם שתרצה)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 main:app`

### שלב 3: הגדרת Environment Variables

ב-Render, לחץ על "Environment" והוסף את המשתנים הבאים:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | הטוקן של הבוט שלך |
| `MONGODB_URI` | Connection string של MongoDB |
| `MONGODB_DB_NAME` | `brain_dump_bot` |
| `RENDER_EXTERNAL_URL` | `https://your-app-name.onrender.com` |
| `ADMIN_USER_ID` | ה-ID של המשתמש שלך |
| `PORT` | `10000` (אוטומטי) |

**⚠️ חשוב**: ה-`RENDER_EXTERNAL_URL` צריך להיות ה-URL המלא של האפליקציה שלך ב-Render.

### שלב 4: Deploy

לחץ על **"Create Web Service"**.  
Render יתחיל לבנות ולהעלות את הבוט. זה לוקח כ-2-3 דקות.

### שלב 5: בדיקה

1. אחרי שהפריסה הצליחה, Render ייתן לך URL
2. בדוק את הלוג שהבוט עלה בהצלחה
3. פתח את הבוט בטלגרם ושלח `/start`
4. אמור לעבוד! 🎊

---

## 📱 שימוש בבוט

### פקודות בסיסיות

```
/start - הודעת פתיחה
/help - מדריך שימוש מלא
```

### מצב רגיל
פשוט תשלח הודעה והבוט ינתח ויסווג אותה אוטומטית:

```
"צריך לקנות מתנה ליומולדת של אמא"
→ הבוט יסווג: ✅ משימות, 👨‍👩‍👧‍👦 משפחה
```

### מצב "שפוך הכול"
```
/dump - התחלת מצב שפיכה
[כתוב כמה שיותר מחשבות...]
/done - סיום וקבלת סיכום
```

### חיפוש ושליפה
```
/list - סיכום כל הקטגוריות והנושאים
/today - מה רשמת היום
/week - מה רשמת השבוע
/search <מילה> - חיפוש חופשי
```

### סטטיסטיקות וניהול
```
/stats - הסטטיסטיקות שלך
/export - ייצוא לקובץ (בפיתוח)
/clear - מחיקת כל המידע
```

---

## 🏗️ ארכיטקטורה

```
brain-dump-bot/
│
├── main.py              # נקודת כניסה + webhook
├── bot.py               # לוגיקה מרכזית + handlers
├── database.py          # ניהול MongoDB
├── nlp_analyzer.py      # מנוע NLP לניתוח טקסט
├── config.py            # הגדרות וקטגוריות
│
├── requirements.txt     # תלויות Python
├── Procfile            # הגדרות Render
├── .env.example        # תבנית משתני סביבה
├── .gitignore          # קבצים להתעלמות
└── README.md           # המדריך הזה
```

### זרימת עבודה:

1. **משתמש שולח הודעה** → Telegram
2. **Webhook מקבל** → main.py (Flask)
3. **Handler מעבד** → bot.py
4. **NLP מנתח** → nlp_analyzer.py
5. **שמירה ב-DB** → database.py (MongoDB)
6. **תגובה למשתמש** → Telegram

---

## 🔍 פתרון בעיות נפוצות

### הבוט לא עונה

**בדוק:**
1. ה-TOKEN תקין ב-`.env`
2. MongoDB מחובר (בדוק את הלוגים)
3. ב-Render: ה-webhook הוגדר נכון
4. לוקלי: הבוט רץ במצב polling

**פתרון מהיר:**
```bash
# הרץ מקומית ובדוק את השגיאות
python main.py
```

### שגיאות MongoDB

**בעיות נפוצות:**
- Username/Password שגויים
- IP לא מורשה ב-MongoDB Atlas
- Connection String לא מעודכן

**פתרון:**
1. היכנס ל-MongoDB Atlas
2. בדוק את Network Access → הוסף `0.0.0.0/0`
3. בדוק Database Access → ודא שהמשתמש קיים

### Webhook לא עובד ב-Render

**בדוק:**
1. `RENDER_EXTERNAL_URL` מוגדר נכון (עם https://)
2. הלוגים ב-Render מראים "Webhook הוגדר בהצלחה"
3. ה-Health check עובר (`/health`)

**פתרון:**
```bash
# בדוק בלוג של Render אם יש שגיאות
# לפעמים צריך Restart ידני
```

### הבוט לא מזהה עברית נכון

זה לא אמור לקרות! הקוד אופטימלי לעברית.

**אם בכל זאת:**
1. ודא ש-UTF-8 encoding בכל הקבצים
2. בדוק שה-triggers ב-`config.py` בעברית

---

## 🛠️ פיתוח והרחבות

### הוספת קטגוריה חדשה

ערוך את `config.py` → `CATEGORIES`:

```python
CATEGORIES = {
    "הקטגוריה שלי": {
        "emoji": "🚀",
        "description": "תיאור",
        "triggers": ["מילה1", "מילה2", "מילה3"]
    },
    # ... שאר הקטגוריות
}
```

### הוספת נושא חדש

ערוך את `config.py` → `TOPICS`:

```python
TOPICS = {
    "הנושא שלי": {
        "emoji": "🎨",
        "keywords": ["מילת_מפתח1", "מילת_מפתח2"]
    },
    # ... שאר הנושאים
}
```

### הוספת פקודה חדשה

ב-`bot.py`:

```python
async def my_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודה חדשה שלי"""
    await update.message.reply_text("תגובה!")

# ואז ב-_register_handlers:
app.add_handler(CommandHandler("mycommand", self.my_command))
```

---

## 🤝 תרומה לפרויקט

רוצה לתרום? מעולה! 🎉

1. עשה Fork לפרויקט
2. צור branch חדש (`git checkout -b feature/amazing-feature`)
3. Commit השינויים (`git commit -m 'Add amazing feature'`)
4. Push ל-branch (`git push origin feature/amazing-feature`)
5. פתח Pull Request

---

## 📝 רישיון

פרויקט זה הוא קוד פתוח תחת רישיון MIT.

---

## 💬 תמיכה ויצירת קשר

- **בעיות?** פתח [Issue](../../issues) ב-GitHub
- **שאלות?** צור איתי קשר דרך Telegram

---

## 🎯 רעיונות לעתיד

- [ ] ייצוא ל-PDF/Google Docs
- [ ] אינטגרציה עם Todoist
- [ ] גרפים ויזואליים של מצב הרוח
- [ ] תזכורות אוטומטיות למשימות
- [ ] ניתוח רגש מתקדם יותר (ML)
- [ ] תמיכה בשפות נוספות

---

<div align="center">

**נוצר עם ❤️ בעברית**

אם הבוט עזר לך - תן כוכב ⭐ לפרויקט!

</div>
