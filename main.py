import os, random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    CallbackQueryHandler, ConversationHandler, MessageHandler, filters
)

# === STATE CONSTANTS ===
UNIVERSITY, GENDER, AGE = range(3)

# === Data sementara (pakai DB di production) ===
users = {}       # {user_id: {...}}
chat_logs = {}   # {user_id: [(sender, pesan), ...]}

# === Daftar Admin ===
ADMIN_IDS = [7894393728]  # ganti ID admin kamu


# =========================================================
# UTILS
# =========================================================
def save_chat(user_id, sender, message):
    """Simpan riwayat chat max 20 pesan terakhir"""
    if user_id not in chat_logs:
        chat_logs[user_id] = []
    chat_logs[user_id].append((sender, message))
    if len(chat_logs[user_id]) > 20:
        chat_logs[user_id] = chat_logs[user_id][-20:]


# =========================================================
# MENU UTAMA
# =========================================================
async def show_main_menu(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None, chat_id: int = None):
    keyboard = [
        [InlineKeyboardButton("🔍 Find", callback_data="find")],
        [InlineKeyboardButton("💘 Cari Doi", callback_data="cari_doi")],
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")],
        [InlineKeyboardButton("👤 Profil", callback_data="profil")]
    ]
    text = "✅ Kamu sudah diverifikasi!\nPilih tombol untuk memulai percakapan:"

    if update and update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif chat_id and context:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))


# =========================================================
# START
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users:
        users[user_id] = {
            "verified": False, "partner": None,
            "university": None, "gender": None,
            "age": None, "blocked_at": None,
            "searching": False
        }

    if users[user_id]["verified"]:
        if users[user_id]["searching"]:
            await update.message.reply_text("⏳ Kamu sedang mencari partner...\nGunakan /stop untuk membatalkan.")
        elif users[user_id]["partner"]:
            await update.message.reply_text("💬 Kamu sedang dalam percakapan anonim.\nGunakan /stop untuk mengakhiri.")
        else:
            await show_main_menu(update, context)
        return ConversationHandler.END
    else:
        keyboard = [
            [InlineKeyboardButton("UNNES", callback_data="unnes")],
            [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")]
        ]
        await update.message.reply_text(
            "👋 Selamat datang di Anonymous Kampus!\nPilih asal universitas kamu:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return UNIVERSITY


# =========================================================
# REGISTRASI FLOW
# =========================================================
async def handle_university(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    users[user_id]["university"] = "UNNES" if query.data == "unnes" else "Non-UNNES"

    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="male")],
        [InlineKeyboardButton("Perempuan", callback_data="female")]
    ]
    await query.edit_message_text("🚻 Pilih gender kamu:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER


async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    users[user_id]["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"

    await query.edit_message_text("🎂 Masukkan usia kamu (contoh: 21):")
    return AGE


async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    age_text = update.message.text
    if not age_text.isdigit():
        await update.message.reply_text("⚠️ Usia harus berupa angka. Coba lagi:")
        return AGE

    users[user_id]["age"] = int(age_text)
    await update.message.reply_text("📩 Data kamu sudah dikirim ke admin untuk diverifikasi. Tunggu ya!")
    await request_admin_verification(user_id, context)
    return ConversationHandler.END


# =========================================================
# PROFIL COMMAND
# =========================================================
async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("⚠️ Kamu belum terdaftar. Gunakan /start untuk memulai.")
        return

    profil = users[user_id]
    teks = "📝 **Profil Kamu**\n"
    teks += f"🏫 Universitas: {profil['university'] or '-'}\n"
    teks += f"🚻 Gender: {profil['gender'] or '-'}\n"
    teks += f"🎂 Usia: {profil['age'] or '-'}\n"
    teks += f"✅ Status Verifikasi: {'Sudah' if profil['verified'] else 'Belum'}\n\n"
    teks += "🔒 Profil ini **hanya bisa kamu lihat sendiri**.\nIdentitasmu tetap **anonymous**."
    await update.message.reply_text(teks, parse_mode="Markdown")


# =========================================================
# STOP COMMAND
# =========================================================
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users[user_id].get("partner")

    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="❌ Partner keluar dari percakapan.")
        users[partner_id]["partner"] = None
    users[user_id]["partner"] = None
    users[user_id]["searching"] = False
    await update.message.reply_text("❌ Kamu keluar dari percakapan / pencarian partner.")


# =========================================================
# REPORT COMMAND
# =========================================================
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users[user_id].get("partner")

    if not partner_id:
        await update.message.reply_text("⚠️ Kamu tidak sedang dalam percakapan anonim.")
        return

    log_text = "📑 Riwayat Chat Terakhir:\n\n"
    for sender, msg in chat_logs.get(user_id, []):
        prefix = "🟢 Kamu" if sender == "user" else "🔵 Partner"
        log_text += f"{prefix}: {msg}\n"

    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"🚨 LAPORAN USER!\n\nPelapor: {user_id}\nTerlapor: {partner_id}\n\n{log_text}"
        )
    await update.message.reply_text("📩 Laporan sudah dikirim ke admin. Terima kasih!")


# =========================================================
# ADMIN VERIFIKASI
# =========================================================
async def request_admin_verification(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    u = users[user_id]
    text = (
        f"🔔 Permintaan verifikasi baru!\n\n"
        f"👤 User ID: {user_id}\n"
        f"🏫 Universitas: {u['university']}\n"
        f"🚻 Gender: {u['gender']}\n"
        f"🎂 Usia: {u['age']}\n\n✅ Approve atau ❌ Reject?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
    ]
    for admin_id in ADMIN_IDS:
        await context.bot.send_message(admin_id, text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    action, user_id = query.data.split("_"); user_id = int(user_id)

    if action == "approve":
        users[user_id]["verified"] = True
        await query.edit_message_text(f"✅ User {user_id} diverifikasi.")
        await context.bot.send_message(user_id, "🎉 Profil kamu sudah diverifikasi!")
        await show_main_menu(context=context, chat_id=user_id)

    elif action == "reject":
        users[user_id]["verified"] = False
        await query.edit_message_text(f"❌ User {user_id} ditolak.")
        await context.bot.send_message(user_id, "⚠️ Verifikasi kamu ditolak. Silakan coba lagi.")


# =========================================================
# BUTTON HANDLER (MENU)
# =========================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id

    if query.data in ["find", "cari_doi"]:
        if users[user_id]["partner"]:
            await query.edit_message_text("⚠️ Kamu sedang dalam percakapan. Gunakan /stop untuk keluar.")
            return
        if users[user_id]["searching"]:
            await query.edit_message_text("⏳ Kamu sudah mencari partner. Gunakan /stop untuk membatalkan.")
            return

        # cari partner random
        candidates = [uid for uid, u in users.items() if u["searching"] and uid != user_id]
        if candidates:
            partner_id = random.choice(candidates)
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            users[user_id]["searching"] = False
            users[partner_id]["searching"] = False
            await context.bot.send_message(user_id, "💬 Partner ditemukan! Sekarang kamu bisa ngobrol anonim.")
            await context.bot.send_message(partner_id, "💬 Partner ditemukan! Sekarang kamu bisa ngobrol anonim.")
        else:
            users[user_id]["searching"] = True
            await query.edit_message_text("🔍 Sedang mencari partner...")

    elif query.data == "ubah_profil":
        users[user_id].update({"verified": False, "university": None, "gender": None, "age": None})
        keyboard = [
            [InlineKeyboardButton("UNNES", callback_data="unnes")],
            [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")]
        ]
        await query.edit_message_text("✏️ Ubah profil kamu.\nPilih asal universitas:", reply_markup=InlineKeyboardMarkup(keyboard))
        return UNIVERSITY

    elif query.data == "profil":
        await profil(update, context)


# =========================================================
# RELAY CHAT
# =========================================================
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")

    if partner_id:
        msg = update.message.text
        save_chat(user_id, "user", msg)
        save_chat(partner_id, "partner", msg)
        await context.bot.send_message(partner_id, msg)
    else:
        await update.message.reply_text("⚠️ Kamu tidak sedang dalam percakapan anonim.")


# =========================================================
# MAIN
# =========================================================
def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("❌ BOT_TOKEN tidak ditemukan. Set di Railway Variables.")

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            UNIVERSITY: [CallbackQueryHandler(handle_university, pattern="^(unnes|nonunnes)$")],
            GENDER: [CallbackQueryHandler(handle_gender, pattern="^(male|female)$")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
