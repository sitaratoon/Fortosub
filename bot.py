import time
from datetime import date, datetime
from dotenv import load_dotenv

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ParseMode

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
VERIFY_DELAY = 1
# =========================================

app = Client("SubXChangeBot", API_ID, API_HASH, bot_token=BOT_TOKEN)

mongo = AsyncIOMotorClient(MONGO_DB)
db = mongo["SUB_EXCHANGE"]

users = db.users
channels = db.channels
orders = db.orders

# ================= HELPERS =================

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

# ================= MENUS =================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Earn Credits", callback_data="earn"),
            InlineKeyboardButton("➕ Add Channel", callback_data="add")
        ],
        [
            InlineKeyboardButton("📊 Balance", callback_data="balance"),
            InlineKeyboardButton("🔗 Refer & Earn", callback_data="refer")
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
        [
            InlineKeyboardButton("📦 Ongoing Orders", callback_data="admin_orders_active"),
            InlineKeyboardButton("✅ Completed Orders", callback_data="admin_orders_done")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="menu")
        ]
    ])

# ================= START + REFERRAL =================

@app.on_message(filters.command("start"))
async def start(_, m):
    ref_id = None
    if len(m.command) > 1 and m.command[1].isdigit():
        ref_id = int(m.command[1])

    u = await get_user(m.from_user.id)

    # REFERRAL CREDIT
    if ref_id and ref_id != m.from_user.id and not u.get("ref_credited"):
        ref_user = await users.find_one({"user_id": ref_id})
        if ref_user:
            await users.update_one(
                {"user_id": ref_id},
                {"$inc": {"credits": 2}}
            )
            await users.update_one(
                {"user_id": m.from_user.id},
                {"$set": {"ref_credited": True, "referred_by": ref_id}}
            )
            try:
                await app.send_message(
                    ref_id,
                    f"🎉 Referral Success!\n💰 You earned +2 credits"
                )
            except:
                pass

    await users.update_one(
        {"user_id": m.from_user.id},
        {"$unset": {"step": "", "temp": ""}}
    )

    await m.reply(
        f"👋 Welcome\n💰 Credits: {u['credits']}",
        reply_markup=main_menu()
    )

# ================= BASIC BUTTONS =================

@app.on_callback_query(filters.regex("^menu$"))
async def menu(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"💰 Credits: {u['credits']}",
        reply_markup=main_menu()
    )

@app.on_callback_query(filters.regex("^balance$"))
async def balance(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"📊 Balance\n\n💰 Credits: {u['credits']}",
        reply_markup=back_menu()
    )

@app.on_callback_query(filters.regex("^buy$"))
async def buy(_, cb):
    await cb.message.edit_text(
        "💳 Buy Credits\n\nContact admin to buy credits.",
        reply_markup=back_menu()
    )

@app.on_callback_query(filters.regex("^help$"))
async def help_btn(_, cb):
    await cb.message.edit_text(
        "ℹ️ Help\n\n"
        "• Join channel → Verify\n"
        "• 2 credits = 1 subscriber\n"
        "• Bot must be admin in channel",
        reply_markup=back_menu()
    )

@app.on_callback_query(filters.regex("^refer$"))
async def refer(_, cb):
    me = await app.get_me()
    link = f"https://t.me/{me.username}?start={cb.from_user.id}"

    await cb.message.edit_text(
        "🔗 **Refer & Earn**\n\n"
        "Invite friends using this link 👇\n"
        "🎁 Get **2 credits per referral**\n\n"
        f"{link}",
        reply_markup=back_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

# ================= EARN SYSTEM =================

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

    # CHECK BOT ADMIN
    try:
        bot_member = await app.get_chat_member(ch["channel_id"], "me")
        if not bot_member.privileges:
            raise Exception
    except:
        await channels.update_one(
            {"_id": ch["_id"]},
            {"$set": {"status": "inactive"}}
        )
        order = await orders.find_one({"channel_id": str(ch["_id"]), "status": "active"})
        if order:
            completed = order.get("completed", 0)
            refund = max(order["credits_used"] - completed * 2, 0)
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "cancelled"}}
            )
            if refund > 0:
                await users.update_one(
                    {"user_id": order["user_id"]},
                    {"$inc": {"credits": refund}}
                )
        return await earn(_, cb)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"last_join_time": int(time.time())}}
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
        [
            InlineKeyboardButton("✅ Verify Join", callback_data=f"check_{ch['_id']}"),
            InlineKeyboardButton("➡️ Next Channel", callback_data="earn")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"Join channel & wait {VERIFY_DELAY}s then verify\n\n📢 {ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    if oid in u["joined"]:
        return await cb.answer("Already verified", show_alert=True)

    if int(time.time()) - u["last_join_time"] < VERIFY_DELAY:
        return await cb.answer("Please wait before verify", show_alert=True)

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Channel expired", show_alert=True)

    try:
        await app.get_chat_member(ch["channel_id"], cb.from_user.id)
    except UserNotParticipant:
        return await cb.answer("Join channel first", show_alert=True)

    # CREDIT USER
    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$inc": {"credits": JOIN_REWARD, "daily": 1}, "$push": {"joined": oid}}
    )

    order = await orders.find_one({"channel_id": oid, "status": "active"})
    if order:
        done = order.get("completed", 0) + 1
        if done >= order["subscribers"]:
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "completed", "completed": done}}
            )
            await channels.update_one(
                {"_id": ObjectId(oid)},
                {"$set": {"status": "inactive"}}
            )
            await app.send_message(
                order["user_id"],
                f"🎉 ORDER COMPLETED!\n📢 {order['title']}"
            )
        else:
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"completed": done}}
            )

    await cb.message.edit_text(
        "✅ Verified! +2 Credits",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Join Next Channel", callback_data="earn")],
            [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
        ])
    )

# ================= ADD CHANNEL =================

@app.on_callback_query(filters.regex("^add$"))
async def add(_, cb):
    u = await get_user(cb.from_user.id)
    if u["credits"] < MIN_ORDER_CREDITS:
        return await cb.answer("Minimum 50 credits required", show_alert=True)

    await users.update_one({"user_id": cb.from_user.id}, {"$set": {"step": "channel"}})
    await cb.message.edit_text(
        "Send channel @username / ID / invite link\nBot must be admin",
        reply_markup=back_menu()
    )

@app.on_message(filters.private & filters.text & ~filters.regex("^/"))
async def steps(_, m):
    u = await get_user(m.from_user.id)
    text = m.text.strip()

    if u.get("step") == "channel":
        try:
            chat = await app.get_chat(text)
            bot_member = await app.get_chat_member(chat.id, "me")
            if not bot_member.privileges:
                raise Exception
        except:
            return await m.reply("❌ Bot must be admin in channel")

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {
                "step": "credits",
                "temp": {
                    "title": chat.title,
                    "link": text if "t.me/" in text else f"https://t.me/{chat.username}",
                    "channel_id": chat.id
                }
            }}
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
            {"$inc": {"credits": -credits}, "$unset": {"step": "", "temp": ""}}
        )

        await m.reply("✅ Order placed", reply_markup=back_menu())

# ================= ADMIN =================

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 Admin Panel", reply_markup=admin_menu())

@app.on_message(filters.command("cancelorder") & filters.user(ADMIN_IDS))
async def cancelorder(_, m):
    try:
        _, oid = m.text.split()
        oid = ObjectId(oid)
    except:
        return await m.reply("Usage: /cancelorder <order_id>")

    order = await orders.find_one({"_id": oid})
    if not order or order["status"] != "active":
        return await m.reply("Order not active")

    completed = order.get("completed", 0)
    refund = max(order["credits_used"] - completed * 2, 0)

    await orders.update_one({"_id": oid}, {"$set": {"status": "cancelled"}})
    await channels.update_one(
        {"_id": ObjectId(order["channel_id"])},
        {"$set": {"status": "inactive"}}
    )

    if refund > 0:
        await users.update_one(
            {"user_id": order["user_id"]},
            {"$inc": {"credits": refund}}
        )

    await m.reply(f"✅ Order cancelled\n💳 Refunded: {refund}")

@app.on_message(filters.command("addcredit") & filters.user(ADMIN_IDS))
async def addcredit(_, m):
    try:
        _, uid, amount = m.text.split()
        uid = int(uid)
        amount = int(amount)
    except:
        return await m.reply(
            "❌ Usage:\n/addcredit <user_id> <credits>\n\nExample:\n/addcredit 123456789 50"
        )

    if amount <= 0:
        return await m.reply("❌ Credit amount must be greater than 0")

    user = await users.find_one({"user_id": uid})
    if not user:
        return await m.reply("❌ User not found")

    await users.update_one(
        {"user_id": uid},
        {"$inc": {"credits": amount}}
    )

    # Notify user
    try:
        await app.send_message(
            uid,
            f"💳 Credits Added\n\n"
            f"➕ {amount} credits added to your account\n"
            f"👑 Added by admin"
        )
    except:
        pass

    await m.reply(f"✅ Successfully added {amount} credits to user {uid}")

@app.on_callback_query(filters.regex("^admin_orders_active$") & filters.user(ADMIN_IDS))
async def admin_orders_active(_, cb):
    text = "📦 **ONGOING ORDERS**\n\n"
    found = False

    async for o in orders.find({"status": "active"}):
        found = True
        text += (
            f"🆔 `{o['_id']}`\n"
            f"📢 {o['title']}\n"
            f"👥 {o.get('completed',0)}/{o['subscribers']}\n"
            f"──────────────\n"
        )

    await cb.message.edit_text(
        text if found else "No active orders",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^admin_orders_done$") & filters.user(ADMIN_IDS))
async def admin_orders_done(_, cb):
    text = "✅ **COMPLETED ORDERS**\n\n"
    found = False

    async for o in orders.find({"status": "completed"}):
        found = True
        text += (
            f"🆔 `{o['_id']}`\n"
            f"📢 {o['title']}\n"
            f"👥 {o['subscribers']}\n"
            f"──────────────\n"
        )

    await cb.message.edit_text(
        text if found else "No completed orders",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.MARKDOWN
    )

# ================= RUN =================

print("🤖 Bot is running...")
app.run()
