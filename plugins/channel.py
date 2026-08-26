from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import users, channels, orders, get_user
from config import MIN_ORDER_CREDITS

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
    ])

@Client.on_callback_query(filters.regex("^add$"))
async def add(_, cb):
    u = await get_user(cb.from_user.id)
    if u["credits"] < MIN_ORDER_CREDITS:
        return await cb.answer("Minimum 50 credits required", show_alert=True)

    await users.update_one({"user_id": cb.from_user.id}, {"$set": {"step": "channel"}})
    await cb.message.edit_text(
        "Send channel @username OR private channel ID\nBot must be ADMIN",
        reply_markup=back_menu()
    )

@Client.on_message(filters.private & filters.text & ~filters.regex("^/"))
async def steps(app, m):
    u = await get_user(m.from_user.id)
    text = m.text.strip()

    if u.get("step") == "channel":
        try:
            if text.startswith("@"):
                chat = await app.get_chat(text)
                link = f"https://t.me/{text.lstrip('@')}"

            elif "t.me/" in text:
                chat = await app.get_chat(text)
                link = text

            else:
                chat = await app.get_chat(int(text))
                link = await app.export_chat_invite_link(chat.id)

            bot_member = await app.get_chat_member(chat.id, "me")
            if not bot_member.privileges:
                raise Exception

        except:
            return await m.reply("❌ Channel add failed\nBot must be ADMIN")

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {
                "step": "credits",
                "temp": {
                    "title": chat.title,
                    "link": link,
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
