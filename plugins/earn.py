import time
from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest, ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid

from database import users, channels, orders, get_user, db
from config import DAILY_JOIN_LIMIT, VERIFY_DELAY, JOIN_REWARD

# Live user status track karne ke liye collection
fs_status_col = db["fsub_user_status"]

# 📩 1. CAPTURE JOIN REQUEST (Pending Request Track karega)
@Client.on_chat_join_request()
async def handle_join_request(client: Client, join_request: ChatJoinRequest):
    user_id = join_request.from_user.id
    channel_id = join_request.chat.id
    
    ch = await channels.find_one({"channel_id": channel_id, "status": "active"})
    if not ch:
        return
        
    try:
        await fs_status_col.update_one(
            {"user_id": user_id, "channel_id": channel_id},
            {"$set": {"status": "request_submitted", "ch_id": str(ch["_id"])}},
            upsert=True
        )
    except Exception as e:
        print(f"Join request error: {e}")

# 🔄 2. CAPTURE MEMBER UPDATE (Join / Leave Track karega)
@Client.on_chat_member_updated()
async def handle_member_update(client: Client, chat_member_updated: ChatMemberUpdated):
    if not chat_member_updated.from_user:
        return

    user_id = chat_member_updated.from_user.id
    channel_id = chat_member_updated.chat.id
    
    ch = await channels.find_one({"channel_id": channel_id, "status": "active"})
    if not ch:
        return
    
    old_status = chat_member_updated.old_chat_member.status if chat_member_updated.old_chat_member else None
    new_status = chat_member_updated.new_chat_member.status if chat_member_updated.new_chat_member else None
    
    active_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
    
    try:
        if new_status in active_statuses and (old_status is None or old_status not in active_statuses):
            await fs_status_col.update_one(
                {"user_id": user_id, "channel_id": channel_id},
                {"$set": {"status": "joined", "ch_id": str(ch["_id"])}},
                upsert=True
            )
        elif old_status in active_statuses and (new_status is None or new_status not in active_statuses):
            await fs_status_col.update_one(
                {"user_id": user_id, "channel_id": channel_id},
                {"$set": {"status": "left", "ch_id": str(ch["_id"])}},
                upsert=True
            )
    except Exception as e:
        print(f"Member update error: {e}")

# 💰 3. EARN HANDLER
@Client.on_callback_query(filters.regex("^earn$"))
async def earn(app, cb):
    u = await get_user(cb.from_user.id)

    if u.get("daily", 0) >= DAILY_JOIN_LIMIT:
        return await cb.answer("Daily limit reached", show_alert=True)

    # 🔁 STEP 1: CHECK OLD JOINED CHANNELS (Leave Detect)
    for jid in u.get("joined", []):
        if not ObjectId.is_valid(jid):
            continue
        
        ch_old = await channels.find_one({"_id": ObjectId(jid), "status": "active"})
        if not ch_old:
            continue

        # Check DB status first for pending requests
        status_rec = await fs_status_col.find_one({"user_id": cb.from_user.id, "channel_id": ch_old["channel_id"]})
        if status_rec and status_rec.get("status") in ["request_submitted", "joined"]:
            continue

        # Fallback Pyrogram Check
        try:
            await app.get_chat_member(ch_old["channel_id"], cb.from_user.id)
        except UserNotParticipant:
            await users.update_one(
                {"user_id": cb.from_user.id},
                {"$set": {"last_join_time": int(time.time())}}
            )

            btn_label = "📩 Re-Request Channel" if ch_old.get("type") == "request" else "🔔 Re-Join Channel"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(btn_label, url=ch_old["link"])],
                [InlineKeyboardButton("✅ Verify Again", callback_data=f"check_{jid}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
            ])

            return await cb.message.edit_text(
                f"⚠️ Aapne channel leave kar diya hai\n\n📢 {ch_old['title']}\n\nPehle is channel ko dubara join/request karo 👇",
                reply_markup=kb
            )
        except Exception:
            continue

    # 🔁 STEP 2: FETCH NEW ACTIVE CHANNEL
    joined_object_ids = [ObjectId(x) for x in u.get("joined", []) if ObjectId.is_valid(x)]
    
    ch = await channels.find_one({
        "status": "active",
        "owner_id": {"$ne": cb.from_user.id},
        "_id": {"$nin": joined_object_ids}
    })

    if not ch:
        return await cb.answer("Filhal koi naya channel available nahi hai!", show_alert=True)

    await users.update_one(
        {"user_id": cb.from_user.id},
        {"$set": {"last_join_time": int(time.time())}}
    )

    btn_text = "📩 Request Join" if ch.get("type") == "request" else "🔔 Join Channel"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_text, url=ch["link"])],
        [
            InlineKeyboardButton("✅ Verify Join", callback_data=f"check_{ch['_id']}"),
            InlineKeyboardButton("➡️ Next Channel", callback_data="earn")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")]
    ])

    await cb.message.edit_text(
        f"Join/Request channel & wait {VERIFY_DELAY}s then verify\n\n📢 **{ch['title']}**",
        reply_markup=kb
    )

# ✅ 4. VERIFY HANDLER
@Client.on_callback_query(filters.regex("^check_"))
async def check_join(app, cb):
    oid = cb.data.split("_")[1]
    u = await get_user(cb.from_user.id)

    if oid in u.get("joined", []):
        return await cb.answer("Is channel ka credit pehle hi mil chuka hai ✅", show_alert=True)

    if int(time.time()) - u.get("last_join_time", 0) < VERIFY_DELAY:
        return await cb.answer("Thoda wait karo fir verify karo", show_alert=True)

    ch = await channels.find_one({"_id": ObjectId(oid)})
    if not ch:
        return await cb.answer("Channel expire ho chuka hai", show_alert=True)

    is_verified = False

    # Check 1: Live Status in MongoDB (Request or Joined)
    status_rec = await fs_status_col.find_one({"user_id": cb.from_user.id, "channel_id": ch["channel_id"]})
    if status_rec and status_rec.get("status") in ["request_submitted", "joined"]:
        is_verified = True

    # Check 2: Pyrogram API Fallback
    if not is_verified:
        try:
            member_info = await app.get_chat_member(ch["channel_id"], cb.from_user.id)
            if member_info.status not in [ChatMemberStatus.BANNED, ChatMemberStatus.LEFT]:
                is_verified = True
        except Exception:
            pass

    if not is_verified:
        btn_text = "📩 Request Join" if ch.get("type") == "request" else "🔔 Join Channel"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_text, url=ch["link"])],
            [InlineKeyboardButton("✅ Verify Join", callback_data=f"check_{oid}")]
        ])
        return await cb.message.edit_text(
            "❌ **Verification Failed!**\n\n"
            "Aapne abhi tak Channel Join Request nahi bheji hai.\n"
            "Pehle link par click karke request bhejein, fir verify karein 👇",
            reply_markup=kb
        )

    # Add Credit & Save Joined
    await users.update_one(
        {"user_id": cb.from_user.id},
        {
            "$inc": {"credits": JOIN_REWARD, "daily": 1},
            "$push": {"joined": str(oid)}
        }
    )

    # Order Complete Logic
    order = await orders.find_one({"channel_id": str(oid), "status": "active"})
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
            try:
                await app.send_message(
                    order["user_id"],
                    f"🎉 **ORDER COMPLETED!**\n\n📢 Channel: {order['title']}\n👥 Total Subscribers Delivered: {done}"
                )
            except Exception:
                pass
        else:
            await orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"completed": done}}
            )

    await cb.message.edit_text(
        "✅ **Join Verified!**\n💰 **+2 Credits** added to your account.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Next Channel", callback_data="earn")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu")]
        ])
    )
