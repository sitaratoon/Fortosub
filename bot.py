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
            "joined": []
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
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

# ================= START =================

@app.on_message(filters.command("start"))
async def start(_, m):
    await users.update_one(
        {"user_id": m.from_user.id},
        {"$unset": {
            "step": "", "awaiting": "", "awaiting_time": "",
            "temp_id": "", "temp_link": "", "title": ""
        }}
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

# ================= BALANCE =================

@app.on_callback_query(filters.regex("^balance$"))
async def balance(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"📊 **Your Balance**\n\n💰 Credits: {u['credits']}",
        reply_markup=back_menu()
    )

# ================= HELP =================

@app.on_callback_query(filters.regex("^help$"))
async def help_btn(_, cb):
    await cb.message.edit_text(
        "ℹ️ **How it works**\n\n"
        "• Join channels to earn credits\n"
        "• 1 Join = 2 Credits\n"
        "• 2 Credits = 1 Subscriber\n"
        "• Add your channel using credits",
        reply_markup=back_menu()
    )

# ================= EARN (FIXED) =================

@app.on_callback_query(filters.regex("^earn$"))
async def earn(_, cb):
    u = await get_user(cb.from_user.id)

    if u["daily"] >= DAILY_JOIN_LIMIT:
        return await cb.answer("❌ Daily limit reached", show_alert=True)

    ch = await channels.find_one({"status": "active"})
    if not ch:
        return await cb.answer("No channels available", show_alert=True)

    # prevent repeat join credit
    if str(ch["_id"]) in u.get("joined", []):
        return await cb.answer("Already joined this channel", show_alert=True)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
        [InlineKeyboardButton("✅ Check Join", callback_data=f"check_{ch['_id']}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"📢 Join this channel to earn +2 credits\n\n{ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Order expired", show_alert=True)

    try:
        # For public channels bot must be admin
        if ch.get("channel_id"):
            await app.get_chat_member(ch["channel_id"], cb.from_user.id)
    except UserNotParticipant:
        return await cb.answer("❌ Join channel first", show_alert=True)
    except:
        pass  # private invite links can't be verified; allow once

    if oid in u.get("joined", []):
        return await cb.answer("Already verified", show_alert=True)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {
            "$inc": {"credits": JOIN_REWARD, "daily": 1},
            "$push": {"joined": oid}
        }
    )

    await cb.message.edit_text(
        "✅ Verified!\n💰 +2 Credits added",
        reply_markup=back_menu()
    )

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
        "📢 Send channel @username OR invite link\n⏱️ You have 1 minute",
        reply_markup=back_menu()
    )

@app.on_message(filters.private & filters.text & ~filters.regex("^/"))
async def steps(_, m):
    u = await get_user(m.from_user.id)
    text = m.text.strip()
    now = int(time.time())

    if u.get("step") == "channel" and u.get("awaiting"):
        if now - u.get("awaiting_time", 0) > 60:
            await users.update_one(
                {"user_id": m.from_user.id},
                {"$unset": {"step": "", "awaiting": "", "awaiting_time": ""}}
            )
            return await m.reply("❌ Time expired. Click ➕ Add Channel again.")

        # private invite
        if "t.me/+" in text or "joinchat" in text:
            title = "Private Channel"
            link = text
            channel_id = None
        else:
            try:
                chat = await app.get_chat(text)
            except:
                return await m.reply("❌ Invalid channel link or username")
            title = chat.title
            link = f"https://t.me/{chat.username}"
            channel_id = chat.id

        await channels.insert_one({
            "owner_id": m.from_user.id,
            "title": title,
            "link": link,
            "channel_id": channel_id,
            "status": "active"
        })

        await orders.insert_one({
            "user_id": m.from_user.id,
            "title": title,
            "status": "active",
            "date": str(datetime.now())
        })

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$unset": {"step": "", "awaiting": "", "awaiting_time": ""}}
        )

        for admin in ADMIN_IDS:
            await app.send_message(
                admin,
                f"🔔 New Order\nUser: {m.from_user.id}\nChannel: {title}"
            )

        await m.reply("✅ Order added successfully", reply_markup=back_menu())

# ================= USER ORDER HISTORY =================

@app.on_callback_query(filters.regex("^history$"))
async def history(_, cb):
    text = "🧾 **Your Orders**\n\n"
    found = False
    async for o in orders.find({"user_id": cb.from_user.id}):
        found = True
        text += f"📢 {o['title']} | {o['status']}\n"
    if not found:
        text += "No orders"
    await cb.message.edit_text(text, reply_markup=back_menu())

# ================= ADMIN =================

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 Admin Panel", reply_markup=admin_menu())

@app.on_callback_query(filters.regex("^admin_stats$") & filters.user(ADMIN_IDS))
async def admin_stats(_, cb):
    await cb.message.edit_text(
        f"📊 Stats\n"
        f"👤 Users: {await users.count_documents({})}\n"
        f"📢 Orders: {await orders.count_documents({})}",
        reply_markup=admin_menu()
    )

@app.on_callback_query(filters.regex("^admin_orders$") & filters.user(ADMIN_IDS))
async def admin_orders(_, cb):
    text = "🧾 Active Orders\n\n"
    found = False
    async for o in orders.find({"status": "active"}):
        found = True
        text += f"👤 {o['user_id']}\n📢 {o['title']}\n\n"
    if not found:
        text = "No active orders"
    await cb.message.edit_text(text, reply_markup=admin_menu())

@app.on_message(filters.command("userorders") & filters.user(ADMIN_IDS))
async def user_orders(_, m):
    _, uid = m.text.split()
    uid = int(uid)
    text = f"🧾 Orders of {uid}\n\n"
    found = False
    async for o in orders.find({"user_id": uid}):
        found = True
        text += f"📢 {o['title']} | {o['status']}\n"
    if not found:
        text += "No orders"
    await m.reply(text)

@app.on_message(filters.command("cancelorder") & filters.user(ADMIN_IDS))
async def cancel_order(_, m):
    _, uid = m.text.split()
    uid = int(uid)
    await orders.update_many(
        {"user_id": uid, "status": "active"},
        {"$set": {"status": "cancelled"}}
    )
    await m.reply("❌ Orders cancelled")

@app.on_message(filters.command("addcredit") & filters.user(ADMIN_IDS))
async def addcredit(_, m):
    _, uid, amt = m.text.split()
    await users.update_one(
        {"user_id": int(uid)},
        {"$inc": {"credits": int(amt)}},
        upsert=True
    )
    await m.reply("✅ Credits added")

# ================= RUN =================

print("🤖 Bot is running...")
app.run()
