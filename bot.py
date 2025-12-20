import os
from dotenv import load_dotenv
from datetime import date, datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()  # ⭐ VERY IMPORTANT

# ================= CONFIG =================
API_ID = int(os.getenv("18946488"))
API_HASH = os.getenv("c163d4e28e63196c3806cf3b9b2885de")
BOT_TOKEN = os.getenv("8410298290:AAGPdfUv3nwkzkdKZFoFoAweB_T8JVf2o_o")
MONGO_DB = os.getenv("mongodb+srv://acxanime01:acxanime01@cluster0.alxqtrc.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

ADMIN_IDS = [6692613520]   # <-- ADMIN TELEGRAM IDs
JOIN_REWARD = 2           # 2 credits = 1 subscriber
DAILY_JOIN_LIMIT = 20
# =========================================

app = Client("SubExchangeBot", API_ID, API_HASH, bot_token=BOT_TOKEN)

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

def main_menu(credits):
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
    u = await get_user(m.from_user.id)
    await m.reply(
        f"👋 Welcome {m.from_user.first_name}\n\n💰 Credits: {u['credits']}",
        reply_markup=main_menu(u["credits"])
    )

@app.on_callback_query(filters.regex("^menu$"))
async def menu(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"💰 Credits: {u['credits']}",
        reply_markup=main_menu(u["credits"])
    )

# ================= EARN =================

@app.on_callback_query(filters.regex("^earn$"))
async def earn(_, cb):
    u = await get_user(cb.from_user.id)

    if u["daily"] >= DAILY_JOIN_LIMIT:
        return await cb.answer("❌ Daily join limit reached", show_alert=True)

    ch = await channels.find_one({
        "owner_id": {"$ne": cb.from_user.id},
        "status": "active",
        "completed": {"$lt": "needed"}
    })

    if not ch:
        return await cb.answer("No active orders right now", show_alert=True)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
        [InlineKeyboardButton("✅ Check Join", callback_data=f"check_{ch['channel_id']}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"Join this channel to earn +2 credits\n\n📢 {ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    cid = int(cb.data.split("_")[1])
    u = await get_user(cb.from_user.id)

    if cid in u["joined"]:
        return await cb.answer("Already joined", show_alert=True)

    try:
        await app.get_chat_member(cid, cb.from_user.id)
    except UserNotParticipant:
        return await cb.answer("❌ Join channel first", show_alert=True)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {
            "$inc": {"credits": JOIN_REWARD, "daily": 1},
            "$push": {"joined": cid}
        }
    )

    ch = await channels.find_one({"channel_id": cid})
    new_done = ch["completed"] + 1
    status = "completed" if new_done >= ch["needed"] else "active"

    await channels.update_one(
        {"channel_id": cid},
        {"$set": {"completed": new_done, "status": status}}
    )

    await orders.update_one(
        {"channel_id": cid},
        {"$set": {"completed": new_done, "status": status}}
    )

    if status == "completed":
        await app.send_message(
            ch["owner_id"],
            f"🎉 Order Completed!\n\n📢 {ch['title']}\n👥 {ch['needed']} subscribers added"
        )

    await cb.message.edit_text("✅ Verified! +2 Credits", reply_markup=back_menu())

# ================= ADD CHANNEL (NEW ORDER) =================

@app.on_callback_query(filters.regex("^add$"))
async def add(_, cb):
    await cb.message.edit_text(
        "Send your channel @username OR invite link",
        reply_markup=back_menu()
    )
    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"step": "channel"}}
    )

@app.on_message(filters.private & filters.text)
async def steps(_, m):
    u = await get_user(m.from_user.id)

    if u.get("step") == "channel":
        chat = await app.get_chat(m.text)
        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {
                "step": "credits",
                "temp": chat.id,
                "title": chat.title,
                "link": m.text if "http" in m.text else f"https://t.me/{chat.username}"
            }}
        )
        return await m.reply("How many credits you want to use?")

    if u.get("step") == "credits":
        credits = int(m.text)

        if credits < 2 or u["credits"] < credits:
            return await m.reply("❌ Invalid or insufficient credits")

        subs = credits // 2

        await channels.insert_one({
            "channel_id": u["temp"],
            "title": u["title"],
            "link": u["link"],
            "owner_id": m.from_user.id,
            "needed": subs,
            "completed": 0,
            "status": "active"
        })

        await orders.insert_one({
            "user_id": m.from_user.id,
            "channel_id": u["temp"],
            "title": u["title"],
            "needed": subs,
            "completed": 0,
            "credits": credits,
            "status": "active",
            "date": str(datetime.now())
        })

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$inc": {"credits": -credits},
             "$unset": {"step": "", "temp": "", "title": "", "link": ""}}
        )

        # 🔔 ADMIN NEW ORDER NOTIFICATION
        for admin in ADMIN_IDS:
            await app.send_message(
                admin,
                f"🔔 **New Order Received**\n\n"
                f"👤 User ID: {m.from_user.id}\n"
                f"📢 Channel: {u['title']}\n"
                f"👥 Subscribers: {subs}\n"
                f"💰 Credits Used: {credits}"
            )

        await m.reply(
            f"✅ Order Started Successfully\n\n"
            f"👥 Subscribers: {subs}\n"
            f"💰 Credits Used: {credits}",
            reply_markup=back_menu()
        )

# ================= ORDER HISTORY =================

@app.on_callback_query(filters.regex("^history$"))
async def history(_, cb):
    text = "🧾 **Your Orders**\n\n"
    found = False

    async for o in orders.find({"user_id": cb.from_user.id}):
        found = True
        text += (
            f"📢 {o['title']}\n"
            f"👥 {o['completed']}/{o['needed']}\n"
            f"📌 {o['status']}\n\n"
        )

    if not found:
        text += "No orders found."

    await cb.message.edit_text(text, reply_markup=back_menu())

# ================= BUY CREDITS =================

@app.on_callback_query(filters.regex("^buy$"))
async def buy(_, cb):
    await cb.message.edit_text(
        "💳 **Buy Credits**\n\n"
        "100 Credits = ₹50\n"
        "250 Credits = ₹120\n"
        "500 Credits = ₹200\n\n"
        "UPI: yourupi@upi\n\n"
        "Pay & send screenshot here",
        reply_markup=back_menu()
    )
    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"step": "payment"}}
    )

@app.on_message(filters.private & filters.photo)
async def payment(_, m):
    u = await get_user(m.from_user.id)
    if u.get("step") != "payment":
        return

    await payments.insert_one({
        "user_id": m.from_user.id,
        "status": "pending"
    })

    for admin in ADMIN_IDS:
        await m.forward(admin)

    await m.reply("✅ Payment sent for admin approval")
    await users.update_one(
        {"user_id": m.from_user.id},
        {"$unset": {"step": ""}}
    )

# ================= ADMIN PANEL =================

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 **Admin Dashboard**", reply_markup=admin_menu())

@app.on_callback_query(filters.regex("^admin_stats$") & filters.user(ADMIN_IDS))
async def admin_stats(_, cb):
    await cb.message.edit_text(
        f"📊 **Bot Stats**\n\n"
        f"👤 Users: {await users.count_documents({})}\n"
        f"📢 Active Orders: {await orders.count_documents({'status':'active'})}\n"
        f"✅ Completed Orders: {await orders.count_documents({'status':'completed'})}\n"
        f"💳 Pending Payments: {await payments.count_documents({'status':'pending'})}",
        reply_markup=admin_menu()
    )

@app.on_message(filters.command("approve") & filters.user(ADMIN_IDS))
async def approve(_, m):
    _, uid, credits = m.text.split()
    await users.update_one(
        {"user_id": int(uid)},
        {"$inc": {"credits": int(credits)}}
    )
    await app.send_message(int(uid), f"✅ {credits} credits added to your account")

# ================= RUN =================

print("🤖 Bot is running...")
app.run()
