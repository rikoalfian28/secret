import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)
import calendar

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")

users = {}          # user_id -> {verified, partner, university, gender, age, blocked_at}
waiting_list = []   # daftar user menunggu pasangan
admins = [ADMIN_ID] # daftar admin

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
    u = users.get(user_id, {})
    return u.get("verified", False) and not u.get("blocked_at")

# ===== STATES =====
UNIVERSITY, GENDER, UMUR = range(3)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users[user_id] = users.get(user_id, {"verified": False, "partner": None, "university": None, "gender": None, "age": None, "blocked_at": None})
    log_activity(f"User {user_id} memulai bot. Verified: {users[user_id]['verified']}")

    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="unnes")],
        [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang di Anonymous Kampus!\n"
        "Sebelum mulai, pilih asal universitas kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UNIVERSITY

# ===== PILIH UNIVERSITAS =====
async def select_university(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    users[user_id]["university"] = "UNNES" if query.data == "unnes" else "Non-UNNES"

    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="gender_male")],
        [InlineKeyboardButton("Perempuan", callback_data="gender_female")],
        [InlineKeyboardButton("Lainnya", callback_data="gender_other")]
    ]
    await query.edit_message_text(
        f"Universitas dipilih: {users[user_id]['university']}\nSekarang pilih gender kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GENDER

# ===== PILIH GENDER =====
async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    gender_map = {
        "gender_male": "Laki-laki",
        "gender_female": "Perempuan",
        "gender_other": "Lainnya"
    }
    users[user_id]["gender"] = gender_map.get(query.data, "Lainnya")

    keyboard = [[InlineKeyboardButton(str(age), callback_data=f"age_{age}") for age in range(18,26)]]
    await query.edit_message_text(
        f"Gender dipilih: {users[user_id]['gender']}\nSekarang pilih umur kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UMUR

# ===== PILIH UMUR =====
async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    umur = int(query.data.split("_")[1])
    if umur < 18 or umur > 25:
        await query.edit_message_text("⚠️ Maaf, umur yang diperbolehkan adalah 18 sampai 25 tahun.")
        return ConversationHandler.END

    users[user_id]["age"] = umur

    # Kirim request ke admin
    text_admin = (
        f"🔔 Permintaan verifikasi baru:\n"
        f"Nama: {query.from_user.full_name}\n"
        f"User ID: {user_id}\n"
        f"Universitas: {users[user_id]['university']}\n"
        f"Gender: {users[user_id]['gender']}\n"
        f"Umur: {users[user_id]['age']}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{user_id}")
    ]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=text_admin, reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text("✅ Permintaan verifikasi telah dikirim ke admin. Tunggu persetujuan.")
    log_activity(f"User {user_id} mengirim permintaan verifikasi (Universitas: {users[user_id]['university']}, Gender: {users[user_id]['gender']}, Umur: {umur})")
    return ConversationHandler.END

# ===== REGISTER ADMIN =====
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❗ Gunakan format: /registeradmin <kode_rahasia>")
        return
    code = context.args[0]
    if code == SECRET_ADMIN_CODE:
        if user_id not in admins:
            admins.append(user_id)
            await update.message.reply_text("✅ Anda terdaftar sebagai admin!")
            log_activity(f"User {user_id} menjadi admin.")
        else:
            await update.message.reply_text("⚠️ Anda sudah admin.")
    else:
        await update.message.reply_text("❌ Kode salah.")

# ===== CALLBACK ADMIN: APPROVE / REJECT =====
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
        await context.bot.send_message(chat_id=target_id, text="✅ Anda telah diverifikasi! Gunakan /find untuk mencari partner.")
        await query.edit_message_text(f"User {target_id} disetujui ✅")
    else:
        log_activity(f"Admin {user_id} menolak user {target_id}")
        await context.bot.send_message(chat_id=target_id, text="❌ Permintaan verifikasi ditolak.")
        await query.edit_message_text(f"User {target_id} ditolak ❌")

# ===== BLOCK / UNBLOCK =====
async def block_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id
    if admin_id not in admins:
        await query.answer("🚫 Anda bukan admin.", show_alert=True)
        return
    await query.answer()
    target_id = int(query.data.split("_")[1])
    users[target_id]["blocked_at"] = datetime.now()
    users[target_id]["verified"] = False
    partner_id = users.get(target_id, {}).get('partner')
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="🚫 Partner Anda telah diblokir oleh admin.")
        users[partner_id]['partner'] = None
    try:
        await context.bot.send_message(chat_id=target_id, text="⚠️ Akun Anda telah diblokir oleh admin. Hanya admin yang bisa membuka blokir.")
    except:
        pass
    keyboard = [[InlineKeyboardButton("✅ Unblock", callback_data=f"unblock_{target_id}")]]
    await context.bot.send_message(chat_id=admin_id, text=f"User {target_id} diblokir.", reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text(f"⚠️ User {target_id} telah diblokir oleh admin.")
    log_activity(f"Admin {admin_id} memblokir user {target_id}")

async def unblock_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id
    if admin_id not in admins:
        await query.answer("🚫 Anda bukan admin.", show_alert=True)
        return
    await query.answer()
    target_id = int(query.data.split("_")[1])
    if target_id not in users or not users[target_id].get("blocked_at"):
        await query.edit_message_text("⚠️ User tidak sedang diblokir.")
        return
    users[target_id]["blocked_at"] = None
    log_activity(f"Admin {admin_id} membuka blokir user {target_id}")
    try:
        await context.bot.send_message(chat_id=target_id, text="✅ Admin telah membuka blokir akun Anda. Anda bisa menggunakan bot kembali.")
    except:
        pass
    await query.edit_message_text(f"✅ User {target_id} telah dibuka blokir oleh admin.")

# ===== FIND PARTNER =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Anda harus diverifikasi sebelum mencari partner.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Anda sudah terhubung dengan partner. Gunakan /stop untuk berhenti.")
        return
    # Cek waiting list
    for partner_id in waiting_list:
        if partner_id != user_id and is_verified(partner_id) and not users[partner_id].get("partner"):
            # Pasangkan
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            waiting_list.remove(partner_id)
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat sekarang.")
            await context.bot.send_message(chat_id=partner_id, text="✅ Partner ditemukan! Mulai chat sekarang.")
            log_activity(f"User {user_id} dipasangkan dengan {partner_id}")
            return
    # Tambah ke waiting list
    waiting_list.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner...")
    log_activity(f"User {user_id} menunggu partner")

# ===== CARI JODOH (malam minggu 18-23) =====
async def cari_jodoh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Anda harus diverifikasi sebelum mencari jodoh.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Anda sudah terhubung dengan partner. Gunakan /stop untuk berhenti.")
        return
    now = datetime.now()
    if now.weekday() != 5 or now.hour < 18 or now.hour > 23:  # Sabtu malam 18-23
        await update.message.reply_text("⚠️ Fitur cari jodoh hanya bisa digunakan Sabtu malam (18-23).")
        return
    # Cari partner lawan jenis
    for partner_id, info in users.items():
        if partner_id != user_id and is_verified(partner_id) and not info.get("partner") and info.get("gender") != users[user_id]["gender"]:
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            await update.message.reply_text("✅ Partner jodoh ditemukan! Mulai chat sekarang.")
            await context.bot.send_message(chat_id=partner_id, text="✅ Partner jodoh ditemukan! Mulai chat sekarang.")
            log_activity(f"User {user_id} dipasangkan dengan {partner_id} (cari_jodoh)")
            return
    await update.message.reply_text("⌛ Menunggu partner lawan jenis...")
    waiting_list.append(user_id)
    log_activity(f"User {user_id} menunggu partner lawan jenis")

# ===== STOP CHAT =====
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        users[partner_id]["partner"] = None
        users[user_id]["partner"] = None
        await update.message.reply_text("✋ Anda berhenti chat.")
        await context.bot.send_message(chat_id=partner_id, text="✋ Partner menghentikan chat.")
        log_activity(f"User {user_id} berhenti chat dengan {partner_id}")
    else:
        await update.message.reply_text("⚠️ Anda tidak sedang chat dengan partner.")

# ===== RELAY PESAN =====
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text=update.message.text)

# ===== REPORT USER =====
async def report_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❗ Gunakan format: /report <user_id>")
        return
    target_id = int(context.args[0])
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 User {user_id} melaporkan user {target_id}")
    await update.message.reply_text("✅ Laporan telah dikirim ke admin.")

# ===== CONVERSATION HANDLER =====
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        UNIVERSITY: [CallbackQueryHandler(select_university, pattern='^(unnes|nonunnes)$')],
        GENDER: [CallbackQueryHandler(select_gender, pattern='^gender_')],
        UMUR: [CallbackQueryHandler(select_age, pattern='^age_')]
    },
    fallbacks=[]
)

# ===== APP =====
app = ApplicationBuilder().token(TOKEN).build()

# ===== HANDLER =====
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(admin_verify, pattern='^(approve|reject)_'))
app.add_handler(CallbackQueryHandler(block_user_callback, pattern='^block_'))
app.add_handler(CallbackQueryHandler(unblock_user_callback, pattern='^unblock_'))
app.add_handler(CommandHandler('registeradmin', register_admin))
app.add_handler(CommandHandler('find', find_partner))
app.add_handler(CommandHandler('cari_jodoh', cari_jodoh))
app.add_handler(CommandHandler('stop', stop_chat))
app.add_handler(CommandHandler('report', report_user))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

if __name__ == '__main__':
    print("🚀 Bot Anonymous Kampus berjalan...")
    log_activity("Bot dimulai: " + str(datetime.now()))
    app.run_polling()
