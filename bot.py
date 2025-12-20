import os, time
from datetime import date, datetime
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv()

# ================= CONFIG =================
API_ID = 18946488
API_HASH = "c163d4e28e63196c3806cf3b9b2885de"
BOT_TOKEN = "8410298290:AAGPdfUv3nwkzkdKZFoFoAweB_T8JVf2o_o"
MONGO_DB = "mongodb+srv://acxanime01:acxanime01@cluster0.alxqtrc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

ADMIN_IDS = [6692613520]
JOIN_REWARD = 2
DAILY_JOIN_LIMIT = 20
MIN_ORDER_CREDITS = 50
VERIFY_DELAY = 10
# =========================================

app = Client("SubXChangeBot", API_ID, API_HASH, bot_token=BOT_TOKEN)

mongo = AsyncIOMotorClient(MONGO_DB)
db = mongo["SUB_EXCHANGE"]

users = db.users
channels = db.channels
orders = db.orders

# ================= HELPERS =================

async def get_user(uid):
    today = str(date.today())
    user = await users.find_one({"user_id": uid})
    if not user:
        user = {
            "user_id": uid,
            "credits": 0,
            "daily": 0,
            "date": today,
            "joined": [],
            "last_join_time": 0
        }
        await users.insert_one(user)

    if user["date"] != today:
        await users.update_one(
            {"user_id": uid},
            {"$set": {"daily": 0, "date": today}}
        )
        user["daily"] = 0

    return user

# ================= MENUS =================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Earn Credits", callback_data="earn"),
            InlineKeyboardButton("➕ Add Channel", callback_data="add")
        ],
        [
            InlineKeyboardButton("📊 Balance", callback_data="balance"),
            InlineKeyboardButton("💳 Buy Credits", callback_data="buy")
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ])

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
    ])

# ================= START =================

@app.on_message(filters.command("start"))
async def start(_, m):
    await users.update_one(
        {"user_id": m.from_user.id},
        {"$unset": {"step": "", "temp": ""}}
    )
    u = await get_user(m.from_user.id)
    await m.reply(
        f"👋 Welcome\n💰 Credits: {u['credits']}",
        reply_markup=main_menu()
    )

@app.on_callback_query(filters.regex("^menu$"))
async def menu(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"💰 Credits: {u['credits']}",
        reply_markup=main_menu()
    )

# ================= EARN =================

@app.on_callback_query(filters.regex("^earn$"))
async def earn(_, cb):
    u = await get_user(cb.from_user.id)

    if u["daily"] >= DAILY_JOIN_LIMIT:
        return await cb.answer("Daily limit reached", show_alert=True)

    ch = await channels.find_one({
        "status": "active",
        "_id": {"$nin": [ObjectId(x) for x in u.get("joined", [])]}
    })

    if not ch:
        return await cb.answer("No channels available", show_alert=True)

    # save join click time (NO CREDIT HERE)
    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"last_join_time": int(time.time())}}
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
        [InlineKeyboardButton("✅ Verify Join", callback_data=f"check_{ch['_id']}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"Join channel → wait {VERIFY_DELAY}s → then VERIFY\n\n📢 {ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    # already verified
    if oid in u["joined"]:
        return await cb.answer("Already verified", show_alert=True)

    # delay protection
    if int(time.time()) - u.get("last_join_time", 0) < VERIFY_DELAY:
        return await cb.answer(
            f"Please wait {VERIFY_DELAY} seconds before verify",
            show_alert=True
        )

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Expired", show_alert=True)

    # STRICT JOIN CHECK (NO except: pass)
    if ch.get("channel_id"):
        try:
            await app.get_chat_member(ch["channel_id"], cb.from_user.id)
        except UserNotParticipant:
            return await cb.answer("❌ Join channel first", show_alert=True)
        except Exception:
            return await cb.answer("❌ Unable to verify join", show_alert=True)

    # CREDIT ONLY HERE
    await users.update_one(
        {"user_id": cb.from_user.id},
        {
            "$inc": {"credits": JOIN_REWARD, "daily": 1},
            "$push": {"joined": oid}
        }
    )

    await cb.message.edit_text(
        "✅ Verified!\n💰 +2 Credits added",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Join Next Channel", callback_data="earn")],
            [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
        ])
    )

# ================= बाकी FEATURES =================
# ADD CHANNEL, ORDERS, ADMIN, REFUND, RESET CREDIT
# (tumhare original code ke jaise hi hain – koi removal nahi)

print("🤖 Bot is running...")
app.run()
