"""
מודול NLP לניתוח מחשבות
מזהה קטגוריות, נושאים ומילות מפתח בטקסט עברי
"""

from typing import Dict, List, Set
import re
import logging
from config import CATEGORIES, TOPICS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NLPAnalyzer:
    """
    מחלקה לניתוח טקסט וזיהוי קטגוריות/נושאים
    """
    
    def __init__(self):
        """אתחול המנתח"""
        self.categories = CATEGORIES
        self.topics = TOPICS
        
        # בניית מילונים לחיפוש מהיר
        self._build_lookup_tables()
    
    def _build_lookup_tables(self):
        """
        בניית טבלאות lookup לביצועים טובים יותר
        """
        # המרת כל הטריגרים לאותיות קטנות
        self.category_triggers = {}
        for category, data in self.categories.items():
            self.category_triggers[category] = [
                trigger.lower() for trigger in data["triggers"]
            ]
        
        # המרת כל keywords לאותיות קטנות
        self.topic_keywords = {}
        for topic, data in self.topics.items():
            self.topic_keywords[topic] = [
                keyword.lower() for keyword in data["keywords"]
            ]
    
    def analyze(self, text: str) -> Dict:
        """
        ניתוח מלא של טקסט
        
        Args:
            text: הטקסט לניתוח
        
        Returns:
            מילון עם תוצאות הניתוח:
            {
                "category": str,
                "topics": List[str],
                "keywords": List[str],
                "sentiment": str,
                "confidence": float
            }
        """
        if not text or not text.strip():
            return self._empty_analysis()
        
        # נירמול הטקסט
        normalized_text = self._normalize_text(text)
        
        # זיהוי קטגוריה
        category, category_confidence = self._detect_category(normalized_text)
        
        # זיהוי נושאים
        topics = self._detect_topics(normalized_text)
        
        # חילוץ מילות מפתח
        keywords = self._extract_keywords(normalized_text)
        
        # ניתוח רגש בסיסי
        sentiment = self._basic_sentiment_analysis(normalized_text)
        
        analysis = {
            "category": category,
            "topics": topics,
            "keywords": keywords,
            "sentiment": sentiment,
            "confidence": category_confidence
        }
        
        logger.info(f"📊 ניתוח הושלם: קטגוריה={category}, נושאים={topics}")
        
        return analysis
    
    def _normalize_text(self, text: str) -> str:
        """
        נירמול טקסט - הסרת רווחים מיותרים, המרה לאותיות קטנות
        
        Args:
            text: טקסט מקורי
        
        Returns:
            טקסט מנורמל
        """
        # הסרת רווחים מיותרים
        text = re.sub(r'\s+', ' ', text)
        
        # המרה לאותיות קטנות
        text = text.lower().strip()
        
        return text
    
    def _detect_category(self, text: str) -> tuple[str, float]:
        """
        זיהוי הקטגוריה המתאימה ביותר
        
        Args:
            text: טקסט מנורמל
        
        Returns:
            (שם_קטגוריה, רמת_ביטחון)
        """
        category_scores = {}
        
        # חישוב ציון לכל קטגוריה
        for category, triggers in self.category_triggers.items():
            score = 0
            matches = []
            
            for trigger in triggers:
                # חיפוש המילה/ביטוי בטקסט
                if self._word_in_text(trigger, text):
                    score += 1
                    matches.append(trigger)
            
            if score > 0:
                category_scores[category] = {
                    "score": score,
                    "matches": matches
                }
        
        # אם לא נמצאה קטגוריה - ברירת מחדל
        if not category_scores:
            return "הרהורים", 0.3
        
        # מציאת הקטגוריה עם הציון הגבוה ביותר
        best_category = max(
            category_scores.items(),
            key=lambda x: x[1]["score"]
        )
        
        category_name = best_category[0]
        score = best_category[1]["score"]
        
        # חישוב confidence (0-1)
        # ככל שיותר טריגרים - ביטחון גבוה יותר
        confidence = min(score / 3.0, 1.0)  # מקסימום 1.0
        
        logger.debug(f"🎯 קטגוריה: {category_name} (ציון: {score}, ביטחון: {confidence:.2f})")
        
        return category_name, confidence
    
    def _detect_topics(self, text: str) -> List[str]:
        """
        זיהוי נושאים רלוונטיים
        
        Args:
            text: טקסט מנורמל
        
        Returns:
            רשימת נושאים
        """
        detected_topics = []
        
        for topic, keywords in self.topic_keywords.items():
            for keyword in keywords:
                if self._word_in_text(keyword, text):
                    detected_topics.append(topic)
                    break  # מספיק match אחד לכל נושא
        
        # מיון לפי סדר חשיבות (לפי הגדרה ב-config)
        detected_topics = sorted(
            detected_topics,
            key=lambda t: list(self.topics.keys()).index(t)
        )
        
        logger.debug(f"🏷️ נושאים שזוהו: {detected_topics}")
        
        return detected_topics
    
    def _extract_keywords(self, text: str, max_keywords: int = 5) -> List[str]:
        """
        חילוץ מילות מפתח מהטקסט
        
        Args:
            text: טקסט מנורמל
            max_keywords: מקסימום מילות מפתח
        
        Returns:
            רשימת מילות מפתח
        """
        # הסרת מילות עצירה נפוצות בעברית
        stop_words = {
            'את', 'של', 'על', 'אל', 'עם', 'כל', 'לא', 'זה', 'היה',
            'או', 'אם', 'כי', 'מה', 'יש', 'רק', 'גם', 'אני', 'הוא',
            'היא', 'אתה', 'הם', 'לי', 'אבל', 'כן', 'לו', 'יותר',
            'עוד', 'פה', 'שם', 'אז', 'כמו', 'בין', 'פעם', 'אחד',
            'שני', 'כמה', 'אחרי', 'לפני', 'תמיד', 'עכשיו', 'פתאום'
        }
        
        # פיצול למילים
        words = re.findall(r'\b\w+\b', text)
        
        # סינון מילות עצירה ומילים קצרות
        keywords = [
            word for word in words
            if word not in stop_words and len(word) > 2
        ]
        
        # הסרת כפילויות תוך שמירה על סדר
        seen = set()
        unique_keywords = []
        for word in keywords:
            if word not in seen:
                seen.add(word)
                unique_keywords.append(word)
        
        # החזרת מקסימום X מילות מפתח
        return unique_keywords[:max_keywords]
    
    def _basic_sentiment_analysis(self, text: str) -> str:
        """
        ניתוח רגש בסיסי
        
        Args:
            text: טקסט מנורמל
        
        Returns:
            'positive', 'negative', 'neutral'
        """
        # מילים חיוביות
        positive_words = [
            'שמח', 'טוב', 'נהדר', 'מצוין', 'כיף', 'אוהב', 'אהבתי',
            'מעולה', 'מדהים', 'יפה', 'נחמד', 'כייף', 'גאה', 'אלוף',
            'הצלחה', 'מצליח', 'בעד'
        ]
        
        # מילים שליליות
        negative_words = [
            'עצוב', 'רע', 'נורא', 'קשה', 'כואב', 'מפחיד', 'חרדה',
            'לחץ', 'מתח', 'עייף', 'כעס', 'כועס', 'מתסכל', 'בעיה',
            'אין לי כוח', 'נמאס', 'דאגה', 'דואג', 'פחד'
        ]
        
        positive_count = sum(
            1 for word in positive_words
            if self._word_in_text(word, text)
        )
        
        negative_count = sum(
            1 for word in negative_words
            if self._word_in_text(word, text)
        )
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    def _word_in_text(self, word: str, text: str) -> bool:
        """
        בדיקה אם מילה קיימת בטקסט (כמילה שלמה)
        
        Args:
            word: המילה לחיפוש
            text: הטקסט לחיפוש בו
        
        Returns:
            True אם המילה נמצאת
        """
        # חיפוש כמילה שלמה (עם גבולות מילה)
        pattern = r'\b' + re.escape(word) + r'\b'
        return bool(re.search(pattern, text))
    
    def _empty_analysis(self) -> Dict:
        """
        תוצאת ניתוח ריקה
        
        Returns:
            מילון עם ערכי ברירת מחדל
        """
        return {
            "category": "הרהורים",
            "topics": [],
            "keywords": [],
            "sentiment": "neutral",
            "confidence": 0.0
        }
    
    def batch_analyze(self, texts: List[str]) -> List[Dict]:
        """
        ניתוח של מספר טקסטים בבת אחת
        
        Args:
            texts: רשימת טקסטים
        
        Returns:
            רשימת תוצאות ניתוח
        """
        return [self.analyze(text) for text in texts]
    
    def get_category_emoji(self, category: str) -> str:
        """
        קבלת האימוג'י של קטגוריה
        
        Args:
            category: שם הקטגוריה
        
        Returns:
            האימוג'י
        """
        return self.categories.get(category, {}).get("emoji", "📝")
    
    def get_topic_emoji(self, topic: str) -> str:
        """
        קבלת האימוג'י של נושא
        
        Args:
            topic: שם הנושא
        
        Returns:
            האימוג'י
        """
        return self.topics.get(topic, {}).get("emoji", "🏷️")
    
    def format_analysis_summary(self, analysis: Dict, text: str) -> str:
        """
        יצירת סיכום מפורמט של הניתוח
        
        Args:
            analysis: תוצאות הניתוח
            text: הטקסט המקורי
        
        Returns:
            מחרוזת מפורמטת
        """
        category = analysis.get("category", "הרהורים")
        topics = analysis.get("topics", [])
        keywords = analysis.get("keywords", [])
        confidence = analysis.get("confidence", 0.0)
        
        # אימוג'י קטגוריה
        category_emoji = self.get_category_emoji(category)
        
        summary_lines = [
            f"{category_emoji} *קטגוריה:* {category}",
        ]
        
        # נושאים
        if topics:
            topics_str = ", ".join([
                f"{self.get_topic_emoji(t)} {t}"
                for t in topics
            ])
            summary_lines.append(f"*נושאים:* {topics_str}")
        
        # מילות מפתח
        if keywords:
            keywords_str = ", ".join([f"#{kw}" for kw in keywords[:3]])
            summary_lines.append(f"*תגיות:* {keywords_str}")
        
        # ביטחון (רק אם נמוך)
        if confidence < 0.5:
            summary_lines.append(f"_הערה: לא בטוח לגמרי בסיווג_")
        
        return "\n".join(summary_lines)


# יצירת אובייקט גלובלי
nlp = NLPAnalyzer()
