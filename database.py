import time
from datetime import date
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB

mongo = AsyncIOMotorClient(MONGO_DB)
db = mongo["SUB_EXCHANGE"]

# Collections
users = db.users
channels = db.channels
orders = db.orders
fs_status_col = db["fsub_user_status"]  # Status tracking collection

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
            "pending_requests": [],
            "last_join_time": 0,
            "ref_credited": False
        }
        await users.insert_one(user)

    # Daily resets
    if user.get("date") != today:
        await users.update_one(
            {"user_id": uid},
            {"$set": {"daily": 0, "date": today}}
        )
        user["daily"] = 0

    # Ensure missing keys exist in existing old user documents
    if "pending_requests" not in user:
        await users.update_one(
            {"user_id": uid},
            {"$set": {"pending_requests": []}}
        )
        user["pending_requests"] = []

    return user
    
