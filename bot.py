import os
import json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ===== KONFIGURASI DASAR =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

users = {}
waiting = []


# ====== UTILITAS ======
def save_users():
    with open("users.json", "w") as f:
        json.dump(users, f, indent=2)


def load_users():
    global users
    if os.path.exists("users.json"):
        with open("users.json") as f:
            users.update(json.load(f))


# ====== START ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users.setdefault(user_id, {
        "verified": False,
        "gender": None,
        "age": None,
        "status": None,
        "partner": None
    })
    save_users()
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="gender_male"),
         InlineKeyboardButton("Perempuan", callback_data="gender_female")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang di Bot Anonymous Kampus!\n"
        "Silakan pilih gender kamu untuk mulai verifikasi:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====== GENDER ======
async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    users[user_id]["gender"] = "Laki-laki" if "male" in query.data else "Perempuan"
    save_users()

    ages = [
        [InlineKeyboardButton(str(a), callback_data=f"age_{a}") for a in range(18, 23)],
        [InlineKeyboardButton(str(a), callback_data=f"age_{a}") for a in range(23, 26)]
    ]
    await query.edit_message_text("🎂 Pilih umur kamu:", reply_markup=InlineKeyboardMarkup(ages))


# ====== UMUR ======
async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    users[user_id]["age"] = int(query.data.split("_")[1])
    save_users()

    keyboard = [
        [InlineKeyboardButton("Mahasiswa UNNES", callback_data="status_unnes")],
        [InlineKeyboardButton("Mahasiswa Lain", callback_data="status_other")],
        [InlineKeyboardButton("Bukan Mahasiswa", callback_data="status_non")]
    ]
    await query.edit_message_text(
        "🎓 Pilih status kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ====== STATUS ======
async def select_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    status_map = {
        "status_unnes": "Mahasiswa UNNES",
        "status_other": "Mahasiswa Lain",
        "status_non": "Bukan Mahasiswa"
    }
    users[user_id]["status"] = status_map[query.data]
    save_users()

    await query.edit_message_text("✅ Data kamu dikirim ke admin untuk verifikasi.")
    text = (
        f"🔔 Permintaan Verifikasi Baru\n"
        f"👤 {query.from_user.full_name}\n"
        f"🆔 {user_id}\n"
        f"Gender: {users[user_id]['gender']}\n"
        f"Umur: {users[user_id]['age']}\n"
        f"Status: {users[user_id]['status']}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Verifikasi", callback_data=f"approve_{user_id}")]
        ])
    )


# ====== VERIFIKASI ADMIN ======
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if admin_id != ADMIN_ID:
        await query.answer("🚫 Anda bukan admin.", show_alert=True)
        return

    target_id = query.data.split("_")[1]
    users[target_id]["verified"] = True
    save_users()

    await query.edit_message_text(f"✅ User {target_id} telah diverifikasi.")
    await context.bot.send_message(
        chat_id=target_id,
        text="✅ Kamu telah diverifikasi oleh admin! Sekarang kamu bisa gunakan /find"
    )


# ====== FIND ======
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not users.get(user_id, {}).get("verified"):
        await update.message.reply_text("⚠️ Kamu harus diverifikasi oleh admin dulu.")
        return

    if user_id in waiting:
        await update.message.reply_text("⌛ Kamu sedang menunggu partner.")
        return

    for pid in waiting:
        if users[pid]["verified"] and not users[pid].get("partner"):
            users[user_id]["partner"] = pid
            users[pid]["partner"] = user_id
            waiting.remove(pid)
            save_users()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(pid, "✅ Partner ditemukan! Mulai chat.")
            return

    waiting.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner lain...")


# ====== STOP ======
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner = users.get(user_id, {}).get("partner")

    if partner:
        users[user_id]["partner"] = None
        users[partner]["partner"] = None
        save_users()
        await context.bot.send_message(partner, "✋ Partner menghentikan chat.")
        await update.message.reply_text("✋ Kamu menghentikan chat.")
    elif user_id in waiting:
        waiting.remove(user_id)
        await update.message.reply_text("❌ Kamu berhenti mencari partner.")
    else:
        await update.message.reply_text("⚠️ Tidak sedang dalam chat atau mencari partner.")


# ====== ADMIN PANEL ======
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Hanya admin yang bisa mengakses menu ini.")
        return
    keyboard = [
        [InlineKeyboardButton("📋 Belum Diverifikasi", callback_data="panel_unverified")],
        [InlineKeyboardButton("👥 Daftar User", callback_data="panel_users")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="panel_broadcast")]
    ]
    await update.message.reply_text("🔧 Panel Admin", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("🚫 Bukan admin.", show_alert=True)
        return

    if query.data == "panel_unverified":
        unverified = [u for u in users if not users[u]["verified"]]
        if not unverified:
            await query.edit_message_text("✅ Tidak ada user yang menunggu verifikasi.")
            return
        text = "📋 Daftar user belum diverifikasi:\n\n"
        for uid in unverified:
            data = users[uid]
            text += f"🆔 {uid} | {data['gender']} | {data['age']} | {data['status']}\n"
        await query.edit_message_text(text)

    elif query.data == "panel_users":
        text = "👥 Daftar semua user:\n\n"
        for uid, data in users.items():
            verif = "✅" if data["verified"] else "❌"
            text += f"{verif} {uid} | {data['gender']} | {data['age']} | {data['status']}\n"
        await query.edit_message_text(text)

    elif query.data == "panel_broadcast":
        context.user_data["broadcast_mode"] = True
        await query.edit_message_text("📢 Silakan kirim pesan broadcast yang ingin disebar ke semua user.")


# ====== BROADCAST & CHAT ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get("broadcast_mode") and user_id == ADMIN_ID:
        text = update.message.text
        sent = 0
        for uid in users:
            try:
                await context.bot.send_message(uid, f"📢 {text}")
                sent += 1
            except:
                pass
        context.user_data["broadcast_mode"] = False
        await update.message.reply_text(f"✅ Broadcast terkirim ke {sent} user.")
    else:
        uid = str(user_id)
        partner = users.get(uid, {}).get("partner")
        if partner:
            await context.bot.send_message(partner, f"💬 {update.message.text}")


# ====== MAIN (Versi Async - FIX untuk Railway) ======
async def main():
    load_users()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(select_gender, pattern="^gender_"))
    app.add_handler(CallbackQueryHandler(select_age, pattern="^age_"))
    app.add_handler(CallbackQueryHandler(select_status, pattern="^status_"))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(admin_menu_handler, pattern="^panel_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot Anonymous Kampus aktif...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
