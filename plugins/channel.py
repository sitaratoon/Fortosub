from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import users, channels, orders, get_user
from config import MIN_ORDER_CREDITS

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
    ])

def channel_type_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Public Link (@username)", callback_data="type_public"),
            InlineKeyboardButton("📩 Private (Auto Request Link)", callback_data="type_request")
        ],
        [InlineKeyboardButton("⬅️ Back Menu", callback_data="menu")]
    ])

@Client.on_callback_query(filters.regex("^add$"))
async def add(_, cb):
    u = await get_user(cb.from_user.id)
    if u["credits"] < MIN_ORDER_CREDITS:
        return await cb.answer("Minimum 50 credits required", show_alert=True)

    await cb.message.edit_text(
        "📢 **Select Channel Type**\n\nAap kis tarah ka channel add karna chahte hain?",
        reply_markup=channel_type_menu()
    )

@Client.on_callback_query(filters.regex("^type_"))
async def set_type(_, cb):
    ch_type = cb.data.split("_")[1]  # 'public' or 'request'
    
    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"step": "channel", "temp_type": ch_type}}
    )
    
    if ch_type == "public":
        msg = "Send Public `@username` OR Channel ID (`-100xxxx`)\n\n⚠️ Bot channel mein ADMIN hona chahiye!"
    else:
        msg = "Send Channel ID (e.g. `-1004334967403`)\n\n⚠️ Bot channel mein **Invite Users via Link** & **Approve Join Requests** permission ke sath ADMIN hona chahiye!\n\n*(Bot khud request link generate kar lega)*"

    await cb.message.edit_text(msg, reply_markup=back_menu())

@Client.on_message(filters.private & filters.text & ~filters.regex("^/"))
async def steps(app, m):
    u = await get_user(m.from_user.id)
    text = m.text.strip()

    if u.get("step") == "channel":
        ch_type = u.get("temp_type", "public")
        
        try:
            if ch_type == "public":
                if text.startswith("@"):
                    chat = await app.get_chat(text)
                    link = f"https://t.me/{text.lstrip('@')}"
                elif "t.me/" in text and "+" not in text:
                    chat = await app.get_chat(text)
                    link = text
                else:
                    chat_id = int(text)
                    chat = await app.get_chat(chat_id)
                    link = await app.export_chat_invite_link(chat.id)
            else:
                # 📩 Private Request Link Auto Generation
                try:
                    chat_id = int(text)
                except ValueError:
                    return await m.reply("❌ Private Request Channel ke liye sirf Channel ID (`-100...`) bhejien!")

                chat = await app.get_chat(chat_id)
                
                # Bot creates Join Request link automatically
                invite_link_obj = await app.create_chat_invite_link(
                    chat_id=chat.id,
                    creates_join_request=True
                )
                link = invite_link_obj.invite_link

            # Check Bot Admin Rights
            bot_member = await app.get_chat_member(chat.id, "me")
            if not bot_member.privileges:
                return await m.reply("❌ Bot channel mein ADMIN nahi hai!")

        except Exception as e:
            return await m.reply(
                "❌ Channel Add Failed!\n\n"
                "Check karein:\n"
                "1. Bot Channel mein Admin ho.\n"
                "2. Bot ke paas 'Invite Users via Link' permission ho.\n"
                "3. Channel ID Sahi ho (e.g. `-100...`)."
            )

        await users.update_one(
            {"user_id": m.from_user.id},
            {"$set": {
                "step": "credits",
                "temp": {
                    "title": chat.title,
                    "link": link,
                    "channel_id": chat.id,
                    "type": ch_type
                }
            }}
        )
        return await m.reply(f"✅ Channel Verified: **{chat.title}**\n\nEnter credits to use (min 50)")

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
            "type": ch.get("type", "public"),
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
            {"$inc": {"credits": -credits}, "$unset": {"step": "", "temp": "", "temp_type": ""}}
        )

        await m.reply(f"✅ Order placed successfully!\n\nGenerated Link: {ch['link']}", reply_markup=back_menu())
