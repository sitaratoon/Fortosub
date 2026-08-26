import time
from datetime import date
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB

mongo = AsyncIOMotorClient(MONGO_DB)
db = mongo["SUB_EXCHANGE"]

users = db.users
channels = db.channels
orders = db.orders

async def get_user(uid: int):
    today = str(date.today())
    user = await users.find_one({"user_id": uid})

    if not user:
        user = {
            "user_id": uid,
            "credits": 0,
            "daily": 0,
            "date": today,
            "joined": [],
            "last_join_time": 0,
            "ref_credited": False
        }
        await users.insert_one(user)

    if user["date"] != today:
        await users.update_one(
            {"user_id": uid},
            {"$set": {"daily": 0, "date": today}}
        )
        user["daily"] = 0

    return user
  
