import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")

users = {}
waiting_list = []
admins = [ADMIN_ID]

# ===== LOGGING =====
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/activity.log",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_activity(message: str):
    print(message)
    logging.info(message)

def is_verified(user_id):
    return users.get(user_id, {}).get("verified", False)

# ===== COMMAND: /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = users.get(user_id, {"verified": False, "gender": None, "partner": None})
    log_activity(f"User {user_id} memulai bot. Verified: {users[user_id]['verified']}")

    await update.message.reply_text(
        "👋 Selamat datang di *Anonymous Kampus*\n\n"
        "Untuk menggunakan bot ini, Anda harus diverifikasi oleh admin terlebih dahulu.\n"
        "Kirim perintah /find setelah disetujui.",
        parse_mode="Markdown"
    )

    text = (
        f"🔔 Permintaan verifikasi baru:\n"
        f"Nama: {update.effective_user.full_name}\n"
        f"User ID: {user_id}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{user_id}")
    ]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== COMMAND: /registeradmin =====
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❗ Gunakan format: /registeradmin <kode_rahasia>")
        return

    code = context.args[0]
    if code == SECRET_ADMIN_CODE:
        if user_id not in admins:
            admins.append(user_id)
            await update.message.reply_text("✅ Anda telah terdaftar sebagai admin!")
            log_activity(f"User {user_id} menjadi admin menggunakan kode rahasia.")
        else:
            await update.message.reply_text("⚠️ Anda sudah terdaftar sebagai admin.")
    else:
        await update.message.reply_text("❌ Kode rahasia salah.")
        log_activity(f"User {user_id} gagal menjadi admin - kode salah.")

# ===== CALLBACK ADMIN: VERIFIKASI =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in admins:
        await query.answer("🚫 Anda bukan admin.", show_alert=True)
        return

    await query.answer()
    data = query.data.split('_')
    action, target_id = data[0], int(data[1])

    if action == 'approve':
        users[target_id]["verified"] = True
        log_activity(f"Admin {user_id} menyetujui user {target_id}")
        await context.bot.send_message(chat_id=target_id, text="✅ Anda telah diverifikasi oleh admin! Gunakan /find untuk mencari teman chat.")
        await query.edit_message_text(f"User {target_id} telah disetujui ✅")
    else:
        log_activity(f"Admin {user_id} menolak user {target_id}")
        await context.bot.send_message(chat_id=target_id, text="❌ Permintaan verifikasi Anda ditolak oleh admin.")
        await query.edit_message_text(f"User {target_id} ditolak ❌")

# ===== COMMAND: /find =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Anda belum diverifikasi oleh admin.")
        return

    if user_id in waiting_list:
        await update.message.reply_text("⏳ Anda sudah dalam antrian, harap tunggu...")
        return

    if waiting_list:
        partner_id = waiting_list.pop(0)
        users[user_id]['partner'] = partner_id
        users[partner_id]['partner'] = user_id
        log_activity(f"User {user_id} terhubung dengan {partner_id}")
        await context.bot.send_message(chat_id=user_id, text="🎉 Anda terhubung dengan seseorang! Kirim pesan sekarang.")
        await context.bot.send_message(chat_id=partner_id, text="🎉 Anda terhubung dengan seseorang! Kirim pesan sekarang.")
    else:
        waiting_list.append(user_id)
        await update.message.reply_text("🔎 Menunggu pasangan...")
        log_activity(f"User {user_id} menunggu pasangan.")

# ===== COMMAND: /stop =====
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get('partner')
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="🚫 Pasangan Anda telah meninggalkan obrolan.")
        log_activity(f"User {user_id} mengakhiri obrolan dengan {partner_id}")
        users[partner_id]['partner'] = None
        users[user_id]['partner'] = None
        await update.message.reply_text("Anda telah keluar dari obrolan.")
    else:
        await update.message.reply_text("Anda tidak sedang dalam obrolan.")

# ===== COMMAND: /lihatlog =====
async def lihat_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("🚫 Anda bukan admin.")
        return

    try:
        with open("logs/activity.log", "r") as f:
            log_content = f.readlines()[-15:]
        await update.message.reply_text("📜 Log Aktivitas Terakhir:\n" + "".join(log_content))
    except FileNotFoundError:
        await update.message.reply_text("❌ Belum ada log aktivitas.")

# ===== RELAY PESAN =====
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get('partner')
    if partner_id:
        log_activity(f"Pesan dari {user_id} ke {partner_id}: {update.message.text}")
        await context.bot.send_message(chat_id=partner_id, text=update.message.text)
    else:
        await update.message.reply_text("❗ Anda belum terhubung dengan siapa pun.")

# ===== MAIN =====
app = ApplicationBuilder().token(TOKEN).build()

# Tambahkan semua handler
app.add_handler(CommandHandler('start', start))
app.add_handler(CommandHandler('registeradmin', register_admin))
app.add_handler(CommandHandler('find', find_partner))
app.add_handler(CommandHandler('stop', stop_chat))
app.add_handler(CommandHandler('lihatlog', lihat_log))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))
app.add_handler(CallbackQueryHandler(admin_verify))

if __name__ == '__main__':
    print("🚀 Bot Anonymous Kampus sedang berjalan...")
    log_activity("Bot dimulai pada " + str(datetime.now()))
    app.run_polling()
