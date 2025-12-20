import os
import time
from datetime import date, datetime
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

# ================= CONFIG =================
API_ID = 18946488
API_HASH = "c163d4e28e63196c3806cf3b9b2885de"
BOT_TOKEN = "8410298290:AAGPdfUv3nwkzkdKZFoFoAweB_T8JVf2o_o"
MONGO_DB = "mongodb+srv://acxanime01:acxanime01@cluster0.alxqtrc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

ADMIN_IDS = [6692613520]   # <-- ADMIN TELEGRAM IDs
JOIN_REWARD = 2           # 2 credits = 1 subscriber
DAILY_JOIN_LIMIT = 20
# =========================================

app = Client("SubXChangeBot", API_ID, API_HASH, bot_token=BOT_TOKEN)

mongo = AsyncIOMotorClient(MONGO_DB)
db = mongo["SUB_EXCHANGE"]

users = db.users
channels = db.channels
orders = db.orders
payments = db.payments

# ================= HELPERS =================

async def get_user(uid):
    today = str(date.today())
    user = await users.find_one({"user_id": uid})

    if not user:
        user = {
            "user_id": uid,
            "credits": 0,
            "joined": [],
            "daily": 0,
            "date": today
        }
        await users.insert_one(user)

    if user["date"] != today:
        await users.update_one(
            {"user_id": uid},
            {"$set": {"daily": 0, "date": today}}
        )
        user["daily"] = 0

    return user

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Earn Credits", callback_data="earn"),
            InlineKeyboardButton("➕ Add Channel", callback_data="add")
        ],
        [
            InlineKeyboardButton("📊 Balance", callback_data="balance"),
            InlineKeyboardButton("🧾 Order History", callback_data="history")
        ],
        [
            InlineKeyboardButton("💳 Buy Credits", callback_data="buy"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help")
        ]
    ])

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🧾 Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("💳 Payments", callback_data="admin_payments")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

# ================= START =================

@app.on_message(filters.command("start"))
async def start(_, m):
    await users.update_one(
        {"user_id": m.from_user.id},
        {"$unset": {"step": "", "awaiting": "", "awaiting_time": "",
                    "temp_id": "", "temp_link": "", "title": ""}}
    )
    u = await get_user(m.from_user.id)
    await m.reply(
        f"👋 Welcome {m.from_user.first_name}\n💰 Credits: {u['credits']}",
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
        return await cb.answer("❌ Daily limit reached", show_alert=True)

    ch = await channels.find_one({
        "owner_id": {"$ne": cb.from_user.id},
        "status": "active"
    })

    if not ch:
        return await cb.answer("No active orders", show_alert=True)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
        [InlineKeyboardButton("✅ Check Join", callback_data=f"check_{ch['_id']}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"Join channel to earn +2 credits\n\n📢 {ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    order = await channels.find_one({"_id": oid})
    if not order:
        return await cb.answer("Order expired", show_alert=True)

    try:
        await app.get_chat_member(order["channel_id"], cb.from_user.id)
    except:
        return await cb.answer("❌ Join first", show_alert=True)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$inc": {"credits": JOIN_REWARD, "daily": 1}}
    )

    done = order["completed"] + 1
    status = "completed" if done >= order["needed"] else "active"

    await channels.update_one(
        {"_id": oid},
        {"$set": {"completed": done, "status": status}}
    )

    if status == "completed":
        await app.send_message(
            order["owner_id"],
            f"🎉 Order Completed\n📢 {order['title']}\n👥 {order['needed']} subscribers"
        )

    await cb.message.edit_text("✅ Verified! +2 Credits", reply_markup=back_menu())

# ================= ADD CHANNEL =================

@app.on_callback_query(filters.regex("^add$"))
async def add(_, cb):
    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {
            "step": "channel",
            "awaiting": True,
            "awaiting_time": int(time.time())
        }}
    )

    await cb.message.edit_text(
        "📢 **Send your channel @username OR invite link**\n\n⏱️ You have 1 minute",
        reply_markup=back_menu()
    )

# ================= STEPS =================

@app.on_message(filters.private & filters.text & ~filters.command)
async def steps(_, m):
    u = await get_user(m.from_user.id)
    text = m.text.strip()
    now = int(time.time())

    # WAITING FOR CHANNEL
    if u.get("step") == "channel" and u.get("awaiting"):

        if now - u.get("awaiting_time", 0) > 60:
            await users.update_one(
                {"user_id": m.from_user.id},
                {"$unset": {"step": "", "awaiting": "", "awaiting_time": ""}}
            )
            return await m.reply(
                "❌ Time expired\nPlease click ➕ Add Channel again",
                reply_markup=back_menu()
            )

        # PRIVATE INVITE LINK
        if "t.me/+" in text or "joinchat" in text:
            await users.update_one(
                {"user_id": m.from_user.id},
                {"$set": {
                    "step": "credits",
                    "temp_link": text,
                    "title": "Private Channel"
                },
                 "$unset": {"awaiting": "", "awaiting_time": ""}}
            )
            return await m.reply("How many credits you want to use?")

        # PUBLIC CHANNEL
        try:
            chat = await app.get_chat(text)
        except:
            return await m.reply("❌ Invalid channel link or username")

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {
                "step": "credits",
                "temp_id": chat.id,
                "temp_link": f"https://t.me/{chat.username}",
                "title": chat.title
            },
             "$unset": {"awaiting": "", "awaiting_time": ""}}
        )
        return await m.reply("How many credits you want to use?")

    # CREDIT INPUT
    if u.get("step") == "credits":
        if not text.isdigit():
            return await m.reply("❌ Send numbers only")

        credits = int(text)
        if credits < 2 or u["credits"] < credits:
            return await m.reply("❌ Invalid or insufficient credits")

        subs = credits // 2

        await channels.insert_one({
            "channel_id": u.get("temp_id"),
            "title": u["title"],
            "link": u["temp_link"],
            "owner_id": m.from_user.id,
            "needed": subs,
            "completed": 0,
            "status": "active"
        })

        await orders.insert_one({
            "user_id": m.from_user.id,
            "title": u["title"],
            "needed": subs,
            "credits": credits,
            "status": "active",
            "date": str(datetime.now())
        })

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$inc": {"credits": -credits},
             "$unset": {"step": "", "temp_id": "", "temp_link": "", "title": ""}}
        )

        for admin in ADMIN_IDS:
            await app.send_message(
                admin,
                f"🔔 New Order\nUser: {m.from_user.id}\nChannel: {u['title']}\nSubs: {subs}"
            )

        await m.reply(
            f"✅ Order Started\n👥 Subscribers: {subs}\n💰 Credits Used: {credits}",
            reply_markup=back_menu()
        )

# ================= ADMIN =================

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 Admin Dashboard", reply_markup=admin_menu())

@app.on_callback_query(filters.regex("^admin_stats$") & filters.user(ADMIN_IDS))
async def admin_stats(_, cb):
    await cb.message.edit_text(
        f"📊 Stats\n\n"
        f"👤 Users: {await users.count_documents({})}\n"
        f"📢 Active Orders: {await channels.count_documents({'status':'active'})}\n"
        f"💳 Pending Payments: {await payments.count_documents({'status':'pending'})}",
        reply_markup=admin_menu()
    )

# ================= RUN =================

print("🤖 Bot is running...")
app.run()
