"""
מודול ניהול מסד הנתונים - MongoDB
מטפל בכל האינטראקציות עם מונגו DB
"""

from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import logging
from config import (
    MONGODB_URI, 
    MONGODB_DB_NAME, 
    THOUGHT_STATUS,
    CATEGORIES,
    TOPICS
)

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class Database:
    """
    מחלקה לניהול כל פעולות הדאטהבייס
    """
    
    def __init__(self):
        """אתחול החיבור למונגו"""
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.thoughts_collection = None
        self.users_collection = None
    
    async def connect(self):
        """
        יצירת חיבור למונגו DB
        """
        try:
            self.client = AsyncIOMotorClient(MONGODB_URI)
            self.db = self.client[MONGODB_DB_NAME]
            self.thoughts_collection = self.db.thoughts
            self.users_collection = self.db.users
            
            # יצירת אינדקסים
            await self._create_indexes()
            
            logger.info("✅ התחברות למונגו DB הצליחה")
            return True
            
        except Exception as e:
            logger.error(f"❌ שגיאה בהתחברות למונגו: {e}")
            return False
    
    async def _create_indexes(self):
        """
        יצירת אינדקסים לביצועים מיטביים
        """
        try:
            # אינדקס על user_id ותאריך (לשליפות מהירות)
            await self.thoughts_collection.create_index([
                ("user_id", 1),
                ("created_at", -1)
            ])
            
            # אינדקס טקסט לחיפוש (Full Text Search)
            await self.thoughts_collection.create_index([
                ("raw_text", "text")
            ])
            
            # אינדקס על קטגוריות
            await self.thoughts_collection.create_index([
                ("nlp_analysis.category", 1)
            ])
            
            # אינדקס על סטטוס
            await self.thoughts_collection.create_index([
                ("status", 1)
            ])
            
            logger.info("✅ אינדקסים נוצרו בהצלחה")
            
        except Exception as e:
            logger.error(f"⚠️ שגיאה ביצירת אינדקסים: {e}")
    
    async def close(self):
        """
        סגירת החיבור למונגו
        """
        if self.client:
            self.client.close()
            logger.info("🔌 חיבור למונגו נסגר")
    
    # ===== פעולות על מחשבות (Thoughts) =====
    
    async def save_thought(
        self,
        user_id: int,
        raw_text: str,
        nlp_analysis: Dict[str, Any],
        metadata: Optional[Dict] = None
    ) -> str:
        """
        שמירת מחשבה חדשה
        
        Args:
            user_id: מזהה המשתמש
            raw_text: הטקסט המקורי
            nlp_analysis: תוצאות ניתוח NLP
            metadata: מידע נוסף (אופציונלי)
        
        Returns:
            מזהה המחשבה שנשמרה
        """
        try:
            thought = {
                "user_id": user_id,
                "raw_text": raw_text,
                "created_at": datetime.utcnow(),
                "nlp_analysis": nlp_analysis,
                "status": THOUGHT_STATUS["ACTIVE"],
                "metadata": metadata or {}
            }
            
            result = await self.thoughts_collection.insert_one(thought)
            logger.info(f"💾 מחשבה נשמרה: {result.inserted_id}")
            
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"❌ שגיאה בשמירת מחשבה: {e}")
            raise
    
    async def get_user_thoughts(
        self,
        user_id: int,
        limit: int = 50,
        skip: int = 0,
        category: Optional[str] = None,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        שליפת מחשבות של משתמש עם אפשרויות סינון
        
        Args:
            user_id: מזהה המשתמש
            limit: מקסימום תוצאות
            skip: דילוג על תוצאות (לעימוד)
            category: סינון לפי קטגוריה
            topic: סינון לפי נושא
            status: סינון לפי סטטוס
            from_date: מתאריך
            to_date: עד תאריך
        
        Returns:
            רשימת מחשבות
        """
        try:
            # בניית query
            query = {"user_id": user_id}
            
            if category:
                query["nlp_analysis.category"] = category
            
            if topic:
                query["nlp_analysis.topics"] = topic
            
            if status:
                query["status"] = status
            else:
                # ברירת מחדל - רק מחשבות פעילות
                query["status"] = THOUGHT_STATUS["ACTIVE"]
            
            # סינון תאריכים
            if from_date or to_date:
                query["created_at"] = {}
                if from_date:
                    query["created_at"]["$gte"] = from_date
                if to_date:
                    query["created_at"]["$lte"] = to_date
            
            # שליפה
            cursor = self.thoughts_collection.find(query).sort(
                "created_at", -1
            ).skip(skip).limit(limit)
            
            thoughts = await cursor.to_list(length=limit)
            
            logger.info(f"📥 נשלפו {len(thoughts)} מחשבות למשתמש {user_id}")
            
            return thoughts
            
        except Exception as e:
            logger.error(f"❌ שגיאה בשליפת מחשבות: {e}")
            return []
    
    async def search_thoughts(
        self,
        user_id: int,
        search_term: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        חיפוש טקסט חופשי במחשבות
        
        Args:
            user_id: מזהה המשתמש
            search_term: מונח החיפוש
            limit: מקסימום תוצאות
        
        Returns:
            רשימת מחשבות מתאימות
        """
        try:
            # חיפוש עם MongoDB text search
            query = {
                "user_id": user_id,
                "status": THOUGHT_STATUS["ACTIVE"],
                "$text": {"$search": search_term}
            }
            
            cursor = self.thoughts_collection.find(
                query,
                {"score": {"$meta": "textScore"}}
            ).sort(
                [("score", {"$meta": "textScore"})]
            ).limit(limit)
            
            results = await cursor.to_list(length=limit)
            
            logger.info(f"🔍 נמצאו {len(results)} תוצאות עבור '{search_term}'")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ שגיאה בחיפוש: {e}")
            return []
    
    async def get_thoughts_by_date_range(
        self,
        user_id: int,
        days_back: int = 1
    ) -> List[Dict]:
        """
        שליפת מחשבות מטווח זמן אחורה
        
        Args:
            user_id: מזהה המשתמש
            days_back: כמה ימים אחורה
        
        Returns:
            רשימת מחשבות
        """
        from_date = datetime.utcnow() - timedelta(days=days_back)
        
        return await self.get_user_thoughts(
            user_id=user_id,
            from_date=from_date,
            limit=100
        )
    
    async def get_category_summary(self, user_id: int) -> Dict[str, int]:
        """
        סיכום כמות מחשבות לפי קטגוריות
        
        Args:
            user_id: מזהה המשתמש
        
        Returns:
            מילון: {קטגוריה: כמות}
        """
        try:
            pipeline = [
                {
                    "$match": {
                        "user_id": user_id,
                        "status": THOUGHT_STATUS["ACTIVE"]
                    }
                },
                {
                    "$group": {
                        "_id": "$nlp_analysis.category",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            results = await self.thoughts_collection.aggregate(pipeline).to_list(None)
            
            summary = {item["_id"]: item["count"] for item in results if item["_id"]}
            
            logger.info(f"📊 סיכום קטגוריות למשתמש {user_id}: {summary}")
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ שגיאה בסיכום קטגוריות: {e}")
            return {}
    
    async def get_topic_summary(self, user_id: int) -> Dict[str, int]:
        """
        סיכום כמות מחשבות לפי נושאים
        
        Args:
            user_id: מזהה המשתמש
        
        Returns:
            מילון: {נושא: כמות}
        """
        try:
            pipeline = [
                {
                    "$match": {
                        "user_id": user_id,
                        "status": THOUGHT_STATUS["ACTIVE"]
                    }
                },
                {"$unwind": "$nlp_analysis.topics"},
                {
                    "$group": {
                        "_id": "$nlp_analysis.topics",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"count": -1}}
            ]
            
            results = await self.thoughts_collection.aggregate(pipeline).to_list(None)
            
            summary = {item["_id"]: item["count"] for item in results if item["_id"]}
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ שגיאה בסיכום נושאים: {e}")
            return {}
    
    async def update_thought_status(
        self,
        thought_id: str,
        new_status: str
    ) -> bool:
        """
        עדכון סטטוס של מחשבה
        
        Args:
            thought_id: מזהה המחשבה
            new_status: הסטטוס החדש
        
        Returns:
            האם העדכון הצליח
        """
        try:
            from bson import ObjectId
            
            result = await self.thoughts_collection.update_one(
                {"_id": ObjectId(thought_id)},
                {"$set": {"status": new_status}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"❌ שגיאה בעדכון סטטוס: {e}")
            return False
    
    async def delete_all_user_thoughts(self, user_id: int) -> int:
        """
        מחיקה מוחלטת של כל מחשבות המשתמש
        
        Args:
            user_id: מזהה המשתמש
        
        Returns:
            כמות המחשבות שנמחקו
        """
        try:
            result = await self.thoughts_collection.delete_many(
                {"user_id": user_id}
            )
            
            logger.warning(f"🗑️ נמחקו {result.deleted_count} מחשבות למשתמש {user_id}")
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"❌ שגיאה במחיקת מחשבות: {e}")
            return 0
    
    # ===== פעולות על משתמשים =====
    
    async def get_or_create_user(self, user_id: int, user_data: Dict) -> Dict:
        """
        שליפה או יצירת משתמש
        
        Args:
            user_id: מזהה טלגרם
            user_data: מידע על המשתמש
        
        Returns:
            מסמך המשתמש
        """
        try:
            user = await self.users_collection.find_one({"user_id": user_id})
            
            if not user:
                # יצירת משתמש חדש
                user = {
                    "user_id": user_id,
                    "username": user_data.get("username"),
                    "first_name": user_data.get("first_name"),
                    "joined_at": datetime.utcnow(),
                    "settings": {
                        "dump_mode": False,
                        "notifications": True
                    },
                    "stats": {
                        "total_thoughts": 0,
                        "last_activity": datetime.utcnow()
                    }
                }
                
                await self.users_collection.insert_one(user)
                logger.info(f"👤 משתמש חדש נוצר: {user_id}")
            
            return user
            
        except Exception as e:
            logger.error(f"❌ שגיאה בניהול משתמש: {e}")
            return {}
    
    async def update_user_stats(self, user_id: int):
        """
        עדכון סטטיסטיקות משתמש
        
        Args:
            user_id: מזהה המשתמש
        """
        try:
            # ספירת מחשבות
            total_thoughts = await self.thoughts_collection.count_documents({
                "user_id": user_id,
                "status": THOUGHT_STATUS["ACTIVE"]
            })
            
            # עדכון
            await self.users_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "stats.total_thoughts": total_thoughts,
                        "stats.last_activity": datetime.utcnow()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"❌ שגיאה בעדכון סטטיסטיקות: {e}")
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """
        שליפת סטטיסטיקות משתמש מפורטות
        
        Args:
            user_id: מזהה המשתמש
        
        Returns:
            מילון עם סטטיסטיקות
        """
        try:
            user = await self.users_collection.find_one({"user_id": user_id})
            
            if not user:
                return {}
            
            # סיכומים
            category_summary = await self.get_category_summary(user_id)
            topic_summary = await self.get_topic_summary(user_id)
            
            stats = {
                "total_thoughts": user.get("stats", {}).get("total_thoughts", 0),
                "joined_at": user.get("joined_at"),
                "last_activity": user.get("stats", {}).get("last_activity"),
                "categories": category_summary,
                "topics": topic_summary
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ שגיאה בשליפת סטטיסטיקות: {e}")
            return {}


# יצירת אובייקט גלובלי
db = Database()
