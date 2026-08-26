import time
from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

from database import users, channels, orders, get_user
from config import DAILY_JOIN_LIMIT, VERIFY_DELAY, JOIN_REWARD

@Client.on_callback_query(filters.regex("^earn$"))
async def earn(app, cb):
    u = await get_user(cb.from_user.id)

    if u["daily"] >= DAILY_JOIN_LIMIT:
        return await cb.answer("Daily limit reached", show_alert=True)

    # 🔁 STEP 1: CHECK OLD JOINED CHANNELS
    for jid in u.get("joined", []):
        ch_old = await channels.find_one({
            "_id": ObjectId(jid),
            "status": "active"
        })
        if not ch_old:
            continue

        try:
            await app.get_chat_member(ch_old["channel_id"], cb.from_user.id)

        except UserNotParticipant:
            await users.update_one(
                {"user_id": cb.from_user.id},
                {"$set": {"last_join_time": int(time.time())}}
            )

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 Re-Join Channel", url=ch_old["link"])],
                [InlineKeyboardButton("✅ Verify Again", callback_data=f"check_{jid}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
            ])

            return await cb.message.edit_text(
                f"⚠️ Aapne channel leave kar diya hai\n\n"
                f"📢 {ch_old['title']}\n\n"
                f"Pehle is channel ko dubara join karo 👇",
                reply_markup=kb
            )

        except (ValueError, KeyError):
            await channels.update_one(
                {"_id": ObjectId(jid)},
                {"$set": {"status": "inactive"}}
            )
            continue

    # 🔁 STEP 2: GIVE NEW CHANNEL
    ch = await channels.find_one({
        "status": "active",
        "_id": {"$nin": [ObjectId(x) for x in u.get("joined", [])]}
    })

    if not ch:
        return await cb.answer("No channels available", show_alert=True)

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
        return await earn(app, cb)

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

@Client.on_callback_query(filters.regex("^check_"))
async def check_join(app, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    if oid in u.get("joined", []):
        return await cb.answer("Is channel ka credit pehle hi mil chuka hai ✅", show_alert=True)

    if int(time.time()) - u["last_join_time"] < VERIFY_DELAY:
        return await cb.answer("Thoda wait karo fir verify karo", show_alert=True)

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Channel expire ho chuka hai", show_alert=True)

    try:
        await app.get_chat_member(ch["channel_id"], cb.from_user.id)
    except UserNotParticipant:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Join Channel", url=ch["link"])],
            [InlineKeyboardButton("✅ Verify Join", callback_data=f"check_{oid}")]
        ])
        return await cb.message.edit_text(
            "❌ Aap channel join nahi ho\n\nPehle join karo fir verify karo 👇",
            reply_markup=kb
        )

    await users.update_one(
        {"user_id": cb.from_user.id},
        {
            "$inc": {"credits": JOIN_REWARD, "daily": 1},
            "$push": {"joined": oid}
        }
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
        "✅ Join verified!\n💰 +2 Credits",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Next Channel", callback_data="earn")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu")]
        ])
    )
  
