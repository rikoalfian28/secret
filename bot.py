import os
from telegram import (
    Update, InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    ContextTypes, CallbackQueryHandler,
    ConversationHandler
)

# === State Conversation ===
UNIVERSITY, GENDER, AGE = range(3)

# === Data sementara (bisa diganti DB di production) ===
users = {}

# === Daftar Admin (ubah sesuai Telegram ID admin kamu) ===
ADMIN_IDS = [123456789]

# === Fungsi log sederhana ===
def log_activity(msg):
    print(msg)


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

    if update and update.message:
        await update.message.reply_text(
            "✅ Kamu sudah diverifikasi!\nPilih tombol untuk memulai percakapan:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update and update.callback_query:
        await update.callback_query.edit_message_text(
            "✅ Kamu sudah diverifikasi!\nPilih tombol untuk memulai percakapan:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif chat_id and context:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ Kamu sudah diverifikasi!\nPilih tombol untuk memulai percakapan:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# =========================================================
# START COMMAND
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users:
        users[user_id] = {
            "verified": False,
            "partner": None,
            "university": None,
            "gender": None,
            "age": None,
            "blocked_at": None,
            "searching": False
        }

    if users[user_id]["verified"]:
        if users[user_id]["searching"]:
            await update.message.reply_text(
                "⏳ Kamu sedang mencari partner...\nGunakan /stop untuk membatalkan."
            )
            return
        await show_main_menu(update, context)
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
    if user_id in users and users[user_id]["searching"]:
        users[user_id]["searching"] = False
        await update.message.reply_text("❌ Pencarian partner dibatalkan.")
    else:
        await update.message.reply_text("⚠️ Kamu tidak sedang mencari partner.")


# =========================================================
# ADMIN VERIFIKASI
# =========================================================
async def request_admin_verification(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    user = users[user_id]
    text = (
        f"🔔 Permintaan verifikasi baru!\n\n"
        f"👤 User ID: {user_id}\n"
        f"🏫 Universitas: {user['university']}\n"
        f"🚻 Gender: {user['gender']}\n"
        f"🎂 Usia: {user['age']}\n\n"
        f"✅ Approve atau ❌ Reject?"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]
    ]

    for admin_id in ADMIN_IDS:
        await context.bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action, user_id = data[0], int(data[1])

    if action == "approve":
        users[user_id]["verified"] = True
        await query.edit_message_text(f"✅ User {user_id} berhasil diverifikasi.")
        await context.bot.send_message(
            chat_id=user_id,
            text="🎉 Selamat! Profil kamu sudah diverifikasi oleh admin."
        )
        await show_main_menu(context=context, chat_id=user_id)

    elif action == "reject":
        users[user_id]["verified"] = False
        await query.edit_message_text(f"❌ User {user_id} ditolak verifikasinya.")
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Maaf, verifikasi kamu ditolak oleh admin.\nSilakan coba lagi dengan data yang benar."
        )


# =========================================================
# BUTTON HANDLER
# =========================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data in ["find", "cari_doi"]:
        if users[user_id]["searching"]:
            await query.edit_message_text(
                "⏳ Kamu sedang mencari partner...\nGunakan /stop untuk membatalkan."
            )
        else:
            users[user_id]["searching"] = True
            await query.edit_message_text("🔍 Sedang mencari partner...")

    elif query.data == "ubah_profil":
        users[user_id]["verified"] = False
        users[user_id]["university"] = None
        users[user_id]["gender"] = None
        users[user_id]["age"] = None

        keyboard = [
            [InlineKeyboardButton("UNNES", callback_data="unnes")],
            [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")]
        ]
        await query.edit_message_text(
            "✏️ Mari ubah profil kamu.\nPilih asal universitas:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return UNIVERSITY

    elif query.data == "profil":
        await profil(update, context)


# =========================================================
# SETUP BOT
# =========================================================
def main():
    TOKEN = os.getenv("BOT_TOKEN")  # masukkan ke Railway env
    app = ApplicationBuilder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(CommandHandler("stop", stop))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
