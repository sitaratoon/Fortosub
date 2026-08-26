from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from database import users, get_user

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

@Client.on_message(filters.command("start"))
async def start(app, m):
    ref_id = None
    if len(m.command) > 1 and m.command[1].isdigit():
        ref_id = int(m.command[1])

    u = await get_user(m.from_user.id)

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
                    "🎉 Referral Success!\n💰 You earned +2 credits"
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

@Client.on_callback_query(filters.regex("^menu$"))
async def menu(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"💰 Credits: {u['credits']}",
        reply_markup=main_menu()
    )

@Client.on_callback_query(filters.regex("^balance$"))
async def balance(_, cb):
    u = await get_user(cb.from_user.id)
    await cb.message.edit_text(
        f"📊 Balance\n\n💰 Credits: {u['credits']}",
        reply_markup=back_menu()
    )

@Client.on_callback_query(filters.regex("^buy$"))
async def buy(_, cb):
    await cb.message.edit_text(
        "💳 Buy Credits\n\nContact admin to buy credits.",
        reply_markup=back_menu()
    )

@Client.on_callback_query(filters.regex("^help$"))
async def help_btn(_, cb):
    await cb.message.edit_text(
        "ℹ️ Help\n\n"
        "• Join channel → Verify\n"
        "• 2 credits = 1 subscriber\n"
        "• Bot must be admin in channel",
        reply_markup=back_menu()
    )

@Client.on_callback_query(filters.regex("^refer$"))
async def refer(app, cb):
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
