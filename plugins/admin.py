from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

from database import users, channels, orders
from config import ADMIN_IDS

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

@Client.on_message(filters.command("admin") & filters.user(ADMIN_IDS))
async def admin(_, m):
    await m.reply("👑 Admin Panel", reply_markup=admin_menu())

@Client.on_message(filters.command("addcredit") & filters.user(ADMIN_IDS))
async def addcredit(app, m):
    try:
        _, uid, amount = m.text.split()
        uid = int(uid)
        amount = int(amount)
    except:
        return await m.reply("Usage:\n/addcredit <user_id> <credits>")

    if amount <= 0:
        return await m.reply("Credits must be > 0")

    if not await users.find_one({"user_id": uid}):
        return await m.reply("User not found")

    await users.update_one(
        {"user_id": uid},
        {"$inc": {"credits": amount}}
    )

    try:
        await app.send_message(
            uid,
            f"💳 Credits Added\n➕ {amount} credits added by admin"
        )
    except:
        pass

    await m.reply(f"✅ Added {amount} credits to {uid}")

@Client.on_message(filters.command("cancelorder") & filters.user(ADMIN_IDS))
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

@Client.on_callback_query(filters.regex("^admin_orders_active$") & filters.user(ADMIN_IDS))
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

@Client.on_callback_query(filters.regex("^admin_orders_done$") & filters.user(ADMIN_IDS))
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
