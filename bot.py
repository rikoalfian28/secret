import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Data user di-memory dan persisten
users_file = "users.json"
if os.path.exists(users_file):
    with open(users_file, "r") as f:
        users = json.load(f)
else:
    users = {}  # user_id -> {verified, partner, university, gender, age, blocked_at}

waiting_list = []   # daftar user menunggu pasangan
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

def save_users():
    with open(users_file, "w") as f:
        json.dump(users, f)

def is_verified(user_id):
    u = users.get(str(user_id), {})
    return u.get("verified", False) and not u.get("blocked_at")

# ===== STATES =====
UNIVERSITY, GENDER, UMUR = range(3)
REPORT_REASON = range(1)

# ===== START & VERIFIKASI =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users[user_id] = users.get(user_id, {"verified": False, "partner": None, "university": None, "gender": None, "age": None, "blocked_at": None})
    save_users()
    log_activity(f"User {user_id} memulai bot. Verified: {users[user_id]['verified']}")
    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="unnes")],
        [InlineKeyboardButton("Mahasiswa lain", callback_data="nonunnes")],
        [InlineKeyboardButton("Bukan mahasiswa", callback_data="nonstudent")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang!\nPilih asal universitas/tipe kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UNIVERSITY

async def select_university(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    univ_map = {
        "unnes": "UNNES",
        "nonunnes": "Mahasiswa lain",
        "nonstudent": "Bukan mahasiswa"
    }
    users[user_id]["university"] = univ_map.get(query.data)
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="gender_male")],
        [InlineKeyboardButton("Perempuan", callback_data="gender_female")],
        [InlineKeyboardButton("Lainnya", callback_data="gender_other")]
    ]
    await query.edit_message_text(
        f"Universitas/tipe dipilih: {users[user_id]['university']}\nPilih gender:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GENDER

async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    gender_map = {
        "gender_male": "Laki-laki",
        "gender_female": "Perempuan",
        "gender_other": "Lainnya"
    }
    users[user_id]["gender"] = gender_map.get(query.data)
    keyboard = [[InlineKeyboardButton(str(age), callback_data=f"age_{age}") for age in range(18,26)]]
    await query.edit_message_text(
        f"Gender dipilih: {users[user_id]['gender']}\nPilih umur (18-25):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UMUR

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    umur = int(query.data.split("_")[1])
    users[user_id]["age"] = umur
    save_users()

    # Kirim ke admin untuk verifikasi
    text_admin = (
        f"🔔 Permintaan verifikasi:\n"
        f"Nama: {query.from_user.full_name}\n"
        f"ID: {user_id}\n"
        f"Universitas/tipe: {users[user_id]['university']}\n"
        f"Gender: {users[user_id]['gender']}\n"
        f"Umur: {users[user_id]['age']}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{user_id}")
    ]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=text_admin, reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text("✅ Permintaan verifikasi dikirim ke admin. Tunggu persetujuan.")
    log_activity(f"User {user_id} mengirim permintaan verifikasi")
    return ConversationHandler.END

# ===== ADMIN VERIFIKASI =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = str(query.from_user.id)
    if int(admin_id) not in admins:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return
    await query.answer()
    data = query.data.split('_')
    action, target_id = data[0], data[1]
    if action == "approve":
        users[target_id]["verified"] = True
        save_users()
        await context.bot.send_message(chat_id=int(target_id), text="✅ Anda diverifikasi! Gunakan /find untuk mencari partner.")
        await query.edit_message_text(f"User {target_id} disetujui ✅")
        log_activity(f"Admin {admin_id} menyetujui {target_id}")
    else:
        users[target_id]["verified"] = False
        save_users()
        await context.bot.send_message(chat_id=int(target_id), text="❌ Verifikasi ditolak.")
        await query.edit_message_text(f"User {target_id} ditolak ❌")
        log_activity(f"Admin {admin_id} menolak {target_id}")

# ===== FIND / CARI JODOH / STOP / RELAY =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Harus diverifikasi.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Sudah terhubung partner. Gunakan /stop untuk berhenti.")
        return
    for partner_id in waiting_list:
        if partner_id != user_id and is_verified(partner_id) and not users[partner_id].get("partner"):
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            waiting_list.remove(partner_id)
            save_users()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(chat_id=int(partner_id), text="✅ Partner ditemukan! Mulai chat.")
            log_activity(f"User {user_id} dipasangkan dengan {partner_id}")
            return
    waiting_list.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner...")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        users[partner_id]["partner"] = None
        users[user_id]["partner"] = None
        save_users()
        await update.message.reply_text("✋ Chat dihentikan.")
        await context.bot.send_message(chat_id=int(partner_id), text="✋ Partner menghentikan chat.")
        log_activity(f"User {user_id} berhenti chat dengan {partner_id}")
    else:
        if user_id in waiting_list:
            waiting_list.remove(user_id)
            await update.message.reply_text("✋ Pencarian dibatalkan.")
        else:
            await update.message.reply_text("⚠️ Tidak sedang chat atau mencari partner.")

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.send_message(chat_id=int(partner_id), text=update.message.text)

# ===== REPORT PARTNER =====
async def report_partner_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if not partner_id:
        await update.message.reply_text("⚠️ Tidak ada partner yang sedang chat.")
        return ConversationHandler.END
    context.user_data['report_partner_id'] = partner_id
    await update.message.reply_text(
        "✏️ Tulis alasan laporan partner kamu:",
        reply_markup=ReplyKeyboardMarkup([["Batal"]], one_time_keyboard=True)
    )
    return REPORT_REASON

async def report_partner_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() == "batal":
        await update.message.reply_text("❌ Laporan dibatalkan.")
        return ConversationHandler.END

    reporter_id = str(update.effective_user.id)
    partner_id = context.user_data.get("report_partner_id")

    report_message = (
        f"🚨 Laporan Partner:\n"
        f"Pelapor: {update.effective_user.full_name} (ID: {reporter_id})\n"
        f"User yang dilaporkan: {partner_id}\n"
        f"Alasan: {text}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=report_message)
    await update.message.reply_text("✅ Laporan telah dikirim ke admin.")
    log_activity(f"User {reporter_id} melaporkan partner {partner_id}: {text}")
    return ConversationHandler.END

report_partner_handler = ConversationHandler(
    entry_points=[CommandHandler('laporkan', report_partner_start)],
    states={REPORT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_partner_reason)]},
    fallbacks=[CommandHandler('batal', lambda u,c: ConversationHandler.END)]
)

# ===== LIST USER =====
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.effective_user.id)
    if user_id not in admins:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    if not users:
        await update.message.reply_text("⚠️ Belum ada user.")
        return
    text = "📋 Daftar User:\n"
    for uid, info in users.items():
        verified = "✅" if info.get("verified") else "❌"
        partner = info.get("partner") or "-"
        blocked = "⚠️" if info.get("blocked_at") else ""
        text += f"ID: {uid} | Verified: {verified} | Partner: {partner} {blocked}\n"
    await update.message.reply_text(text)

# ===== BROADCAST =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.effective_user.id)
    if user_id not in admins:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    if not context.args:
        await update.message.reply_text("❗ Gunakan: /broadcast <pesan>")
        return
    message_text = " ".join(context.args)
    count = 0
    for uid, info in users.items():
        if is_verified(uid) and not info.get("blocked_at"):
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📢 Broadcast dari Admin:\n\n{message_text}")
                count += 1
            except: pass
    await update.message.reply_text(f"✅ Broadcast dikirim ke {count} user.")
    log_activity(f"Admin {user_id} broadcast: {message_text}")

# ===== APP =====
app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        UNIVERSITY: [CallbackQueryHandler(select_university)],
        GENDER: [CallbackQueryHandler(select_gender)],
        UMUR: [CallbackQueryHandler(select_age)]
    },
    fallbacks=[]
)
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(admin_verify, pattern="^(approve|reject)_"))
app.add_handler(CommandHandler("find", find_partner))
app.add_handler(CommandHandler("stop", stop_chat))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))
app.add_handler(report_partner_handler)
app.add_handler(CommandHandler("listuser", list_users))
app.add_handler(CommandHandler("broadcast", broadcast))

# ===== RUN BOT =====
print("🚀 Bot Anonymous Kampus berjalan...")
app.run_polling()
