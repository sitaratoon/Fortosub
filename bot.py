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

def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Ongoing Orders", callback_data="admin_orders_active"),
            InlineKeyboardButton("✅ Completed Orders", callback_data="admin_orders_done")
        ],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

# ================= START =================

@app.on_message(filters.command("start"))
async def start(_, m):
    await users.update_one(
        {"user_id": m.from_user.id},
        {"$unset": {"step": "", "awaiting": "", "awaiting_time": "", "temp_channel": ""}}
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

# ================= USER BUTTONS =================

@app.on_callback_query(filters.regex("^balance$"))
async def balance(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"📊 Balance\n\n💰 Credits: {u['credits']}",
        reply_markup=back_menu()
    )

@app.on_callback_query(filters.regex("^help$"))
async def help_btn(_, cb):
    await cb.message.edit_text(
        "ℹ️ Help\n\n"
        "• Join channels to earn credits\n"
        "• 1 Join = 2 Credits\n"
        "• Minimum order = 50 credits\n"
        "• 2 Credits = 1 Subscriber",
        reply_markup=back_menu()
    )

@app.on_callback_query(filters.regex("^buy$"))
async def buy(_, cb):
    await cb.message.edit_text(
        "💳 Buy Credits (Info)\n\n"
        "50 Credits = ₹50\n"
        "100 Credits = ₹90\n"
        "250 Credits = ₹200\n\n"
        "Payment system coming soon.",
        reply_markup=back_menu()
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

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
        [InlineKeyboardButton("✅ Check Join", callback_data=f"check_{ch['_id']}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"Join to earn +2 credits\n\n📢 {ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Expired", show_alert=True)

    try:
        if ch.get("channel_id"):
            await app.get_chat_member(ch["channel_id"], cb.from_user.id)
    except UserNotParticipant:
        return await cb.answer("Join first", show_alert=True)
    except:
        pass

    if oid in u["joined"]:
        return await cb.answer("Already verified", show_alert=True)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$inc": {"credits": JOIN_REWARD, "daily": 1},
         "$push": {"joined": oid}}
    )

    # ORDER PROGRESS
    order = await orders.find_one({"channel_id": oid, "status": "active"})
    if order:
        done = order.get("completed", 0) + 1
        if done >= order["subscribers"]:
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "completed", "completed": done}}
            )
            await app.send_message(
                order["user_id"],
                f"🎉 Order Completed!\n\n📢 {order['title']}"
            )
        else:
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"completed": done}}
            )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Join Next Channel", callback_data="earn")],
        [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
    ])

    await cb.message.edit_text("✅ Verified! +2 Credits", reply_markup=kb)

# ================= ADD CHANNEL =================

@app.on_callback_query(filters.regex("^add$"))
async def add(_, cb):
    u = await get_user(cb.from_user.id)
    if u["credits"] < MIN_ORDER_CREDITS:
        return await cb.answer("Minimum 50 credits required", show_alert=True)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"step": "channel", "awaiting_time": int(time.time())}}
    )

    await cb.message.edit_text(
        "Send channel @username or invite link\n(1 minute)",
        reply_markup=back_menu()
    )

@app.on_message(filters.private & filters.text & ~filters.regex("^/"))
async def steps(_, m):
    u = await get_user(m.from_user.id)
    text = m.text.strip()

    if u.get("step") == "channel":
        chat = None
        if "t.me/+" in text:
            title, link, cid = "Private Channel", text, None
        else:
            try:
                chat = await app.get_chat(text)
            except:
                return await m.reply("Invalid channel")
            title, link, cid = chat.title, f"https://t.me/{chat.username}", chat.id

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {"step": "credits", "temp": {
                "title": title, "link": link, "channel_id": cid
            }}}
        )

        return await m.reply("Enter credits to use (min 50)")

    if u.get("step") == "credits":
        if not text.isdigit():
            return await m.reply("Numbers only")

        credits = int(text)
        if credits < MIN_ORDER_CREDITS or credits > u["credits"]:
            return await m.reply("Invalid credits")

        subs = credits // 2
        ch = u["temp"]

        res = await channels.insert_one({
            "owner_id": m.from_user.id,
            "title": ch["title"],
            "link": ch["link"],
            "channel_id": ch["channel_id"],
            "status": "active"
        })

        await orders.insert_one({
            "user_id": m.from_user.id,
            "channel_id": str(res.inserted_id),
            "title": ch["title"],
            "credits_used": credits,
            "subscribers": subs,
            "completed": 0,
            "status": "active",
            "date": str(datetime.now())
        })

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$inc": {"credits": -credits},
             "$unset": {"step": "", "temp": ""}}
        )

        for admin in ADMIN_IDS:
            await app.send_message(
                admin,
                f"🔔 New Order\nUser: {m.from_user.id}\nCredits: {credits}"
            )

        await m.reply("✅ Order placed", reply_markup=back_menu())

# ================= ADMIN =================

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 Admin Panel", reply_markup=admin_menu())

@app.on_callback_query(filters.regex("^admin_stats$") & filters.user(ADMIN_IDS))
async def admin_stats(_, cb):
    await cb.message.edit_text(
        f"Users: {await users.count_documents({})}\n"
        f"Orders: {await orders.count_documents({})}",
        reply_markup=admin_menu()
    )

@app.on_callback_query(filters.regex("^admin_orders_active$") & filters.user(ADMIN_IDS))
async def admin_orders_active(_, cb):
    text = "📦 Ongoing Orders\n\n"
    async for o in orders.find({"status": "active"}):
        text += f"{o['_id']} | {o['title']}\n"
    await cb.message.edit_text(text or "No active orders", reply_markup=admin_menu())

@app.on_callback_query(filters.regex("^admin_orders_done$") & filters.user(ADMIN_IDS))
async def admin_orders_done(_, cb):
    text = "✅ Completed Orders\n\n"
    async for o in orders.find({"status": "completed"}):
        text += f"{o['_id']} | {o['title']}\n"
    await cb.message.edit_text(text or "No completed orders", reply_markup=admin_menu())

# ===== ADMIN COMMANDS =====

@app.on_message(filters.command("cancelorder") & filters.user(ADMIN_IDS))
async def cancel_order(_, m):
    _, oid = m.text.split()
    await orders.update_one({"_id": ObjectId(oid)}, {"$set": {"status": "cancelled"}})
    await m.reply("Order cancelled")

@app.on_message(filters.command("refund") & filters.user(ADMIN_IDS))
async def refund(_, m):
    _, oid = m.text.split()
    order = await orders.find_one({"_id": ObjectId(oid)})
    if not order:
        return await m.reply("Order not found")

    await orders.update_one({"_id": order["_id"]}, {"$set": {"status": "refunded"}})
    await users.update_one(
        {"user_id": order["user_id"]},
        {"$inc": {"credits": order.get("credits_used", 0)}}
    )
    await m.reply("Refund done")

@app.on_message(filters.command("resetcredit") & filters.user(ADMIN_IDS))
async def resetcredit(_, m):
    _, uid = m.text.split()
    await users.update_one({"user_id": int(uid)}, {"$set": {"credits": 0}})
    await m.reply("Credits reset")

# ================= RUN =================

print("🤖 Bot is running...")
app.run()
