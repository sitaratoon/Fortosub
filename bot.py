import time
from datetime import date, datetime
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

load_dotenv()

# ================= CONFIG =================
ADMIN_IDS = [6692613520]
JOIN_REWARD = 2
DAILY_JOIN_LIMIT = 20
MIN_ORDER_CREDITS = 6
VERIFY_DELAY = 1
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

# ================= USER BUTTONS =================

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
        "• Join channel → VERIFY\n"
        "• 2 Credits = 1 Subscriber\n"
        "• Min order = 50 credits\n"
        "• Bot must be admin in channel",
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
        f"Join channel & wait {VERIFY_DELAY}s then verify\n\n📢 {ch['title']}",
        reply_markup=kb
    )

@app.on_callback_query(filters.regex("^check_"))
async def check_join(_, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    if oid in u["joined"]:
        return await cb.answer("Already verified", show_alert=True)

    if int(time.time()) - u.get("last_join_time", 0) < VERIFY_DELAY:
        return await cb.answer("Wait before verify", show_alert=True)

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Expired", show_alert=True)

    try:
        await app.get_chat_member(ch["channel_id"], cb.from_user.id)
    except UserNotParticipant:
        return await cb.answer("Join channel first", show_alert=True)
    except:
        return await cb.answer("Verification failed", show_alert=True)

    # CREDIT ADD
    await users.update_one(
        {"user_id": cb.from_user.id},
        {
            "$inc": {"credits": JOIN_REWARD, "daily": 1},
            "$push": {"joined": oid}
        }
    )

    # ===== ORDER PROGRESS =====
    order = await orders.find_one({"channel_id": oid, "status": "active"})
    if order:
        done = order.get("completed", 0) + 1

        if done >= order["subscribers"]:
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"status": "completed", "completed": done}}
            )

            # 🔔 USER ORDER COMPLETED NOTIFICATION
            await app.send_message(
                order["user_id"],
                f"🎉 ORDER COMPLETED!\n\n"
                f"📢 Channel: {order['title']}\n"
                f"👥 Subscribers Added: {order['subscribers']}\n"
                f"💰 Credits Used: {order['credits_used']}\n"
                f"🆔 Order ID: {order['_id']}"
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

    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"step": "channel"}}
    )

    await cb.message.edit_text(
        "Send channel ID / @username OR private invite link\n\nBot must be ADMIN",
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
            return await m.reply("❌ Bot must be ADMIN in channel")

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {"step": "credits", "temp": {
                "title": chat.title,
                "link": text if "t.me/+" in text else f"https://t.me/{chat.username}",
                "channel_id": chat.id
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

        order = await orders.insert_one({
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

        # 🔔 ADMIN NEW ORDER NOTIFICATION (EXACT FORMAT)
        for admin in ADMIN_IDS:
            await app.send_message(
                admin,
                f"🔔 NEW ORDER\n\n"
                f"👤 User: {m.from_user.id}\n"
                f"📢 Channel: {ch['title']}\n"
                f"🔗 {ch['link']}\n"
                f"👥 Subscribers: {subs}\n"
                f"💰 Credits: {credits}\n"
                f"🆔 Order ID: {order.inserted_id}"
            )

        await m.reply("✅ Order placed", reply_markup=back_menu())

# ================= ADMIN =================

@app.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 Admin Dashboard", reply_markup=admin_menu())

@app.on_message(filters.command("addcredit") & filters.user(ADMIN_IDS))
async def addcredit(_, m):
    _, uid, amount = m.text.split()
    await users.update_one({"user_id": int(uid)}, {"$inc": {"credits": int(amount)}})
    await m.reply("Credits added")

@app.on_message(filters.command("cancelorder") & filters.user(ADMIN_IDS))
async def cancelorder(_, m):
    _, oid = m.text.split()
    oid = ObjectId(oid)

    order = await orders.find_one({"_id": oid})
    if not order:
        return await m.reply("Order not found")

    await orders.update_one({"_id": oid}, {"$set": {"status": "cancelled"}})
    await m.reply("Order cancelled")

@app.on_message(filters.command("resetcredit") & filters.user(ADMIN_IDS))
async def resetcredit(_, m):
    _, uid = m.text.split()
    await users.update_one({"user_id": int(uid)}, {"$set": {"credits": 0}})
    await m.reply("Credits reset")

@app.on_callback_query(filters.regex("^admin_stats$") & filters.user(ADMIN_IDS))
async def admin_stats(_, cb):
    await cb.message.edit_text(
        f"👤 Total users: {await users.count_documents({})}\n"
        f"📦 Total orders: {await orders.count_documents({})}\n"
        f"🔄 Active orders: {await orders.count_documents({'status':'active'})}\n"
        f"✅ Completed orders: {await orders.count_documents({'status':'completed'})}",
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

# ================= RUN =================

print("🤖 Bot is running...")
app.run()
