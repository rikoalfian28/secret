import os
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
REPORT_REASON = range(1)

# ===== START & VERIFIKASI =====
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
        "Pilih asal universitas kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UNIVERSITY

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

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    umur = int(query.data.split("_")[1])
    if umur < 18 or umur > 25:
        await query.edit_message_text("⚠️ Umur harus antara 18 sampai 25 tahun.")
        return ConversationHandler.END
    users[user_id]["age"] = umur
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
    log_activity(f"User {user_id} mengirim permintaan verifikasi")
    return ConversationHandler.END

# ===== REGISTER ADMIN =====
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❗ Gunakan: /registeradmin <kode_rahasia>")
        return
    code = context.args[0]
    if code == SECRET_ADMIN_CODE:
        if user_id not in admins:
            admins.append(user_id)
            await update.message.reply_text("✅ Terdaftar sebagai admin!")
            log_activity(f"User {user_id} menjadi admin")
        else:
            await update.message.reply_text("⚠️ Anda sudah admin.")
    else:
        await update.message.reply_text("❌ Kode salah.")

# ===== ADMIN APPROVE/REJECT =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in admins:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return
    await query.answer()
    data = query.data.split('_')
    action, target_id = data[0], int(data[1])
    if action == 'approve':
        users[target_id]["verified"] = True
        log_activity(f"Admin {user_id} menyetujui user {target_id}")
        await context.bot.send_message(chat_id=target_id, text="✅ Anda diverifikasi! Gunakan /find untuk mencari partner.")
        await query.edit_message_text(f"User {target_id} disetujui ✅")
    else:
        users[target_id]["verified"] = False
        await context.bot.send_message(chat_id=target_id, text="❌ Verifikasi ditolak.")
        await query.edit_message_text(f"User {target_id} ditolak ❌")
        log_activity(f"Admin {user_id} menolak user {target_id}")

# ===== BLOCK / UNBLOCK =====
async def block_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id
    if admin_id not in admins:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return
    await query.answer()
    target_id = int(query.data.split("_")[1])
    users[target_id]["blocked_at"] = datetime.now()
    users[target_id]["verified"] = False
    partner_id = users.get(target_id, {}).get('partner')
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="🚫 Partner Anda diblokir admin.")
        users[partner_id]['partner'] = None
    try:
        await context.bot.send_message(chat_id=target_id, text="⚠️ Anda diblokir admin. Hanya admin bisa membuka blokir.")
    except: pass
    keyboard = [[InlineKeyboardButton("✅ Unblock", callback_data=f"unblock_{target_id}")]]
    await context.bot.send_message(chat_id=admin_id, text=f"User {target_id} diblokir.", reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text(f"⚠️ User {target_id} diblokir oleh admin")
    log_activity(f"Admin {admin_id} memblokir user {target_id}")

async def unblock_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id
    if admin_id not in admins:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return
    await query.answer()
    target_id = int(query.data.split("_")[1])
    if target_id not in users or not users[target_id].get("blocked_at"):
        await query.edit_message_text("⚠️ User tidak diblokir.")
        return
    users[target_id]["blocked_at"] = None
    log_activity(f"Admin {admin_id} membuka blokir user {target_id}")
    try:
        await context.bot.send_message(chat_id=target_id, text="✅ Admin membuka blokir akun Anda.")
    except: pass
    await query.edit_message_text(f"✅ User {target_id} dibuka blokir oleh admin")

# ===== FIND / CARI JODOH / STOP / RELAY =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(chat_id=partner_id, text="✅ Partner ditemukan! Mulai chat.")
            log_activity(f"User {user_id} dipasangkan dengan {partner_id}")
            return
    waiting_list.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner...")

async def cari_jodoh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Harus diverifikasi.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Sudah terhubung partner. Gunakan /stop.")
        return
    now = datetime.now()
    weekday, hour = now.weekday(), now.hour
    # aktif Sabtu 18:00 -> Senin 00:00
    is_sabtu_malam = (weekday == 5 and hour >= 18)
    is_minggu = (weekday == 6)
    is_senin_dini = (weekday == 0 and hour == 0)
    if not (is_sabtu_malam or is_minggu or is_senin_dini):
        await update.message.reply_text("⚠️ Cari jodoh hanya Sabtu 18:00 sampai Senin 00:00.")
        return
    for partner_id, info in users.items():
        if partner_id != user_id and is_verified(partner_id) and not info.get("partner") and info.get("gender") != users[user_id]["gender"]:
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            await update.message.reply_text("✅ Partner jodoh ditemukan!")
            await context.bot.send_message(chat_id=partner_id, text="✅ Partner jodoh ditemukan!")
            log_activity(f"User {user_id} dipasangkan dengan {partner_id} (cari_jodoh)")
            return
    waiting_list.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner lawan jenis...")

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
        await update.message.reply_text("⚠️ Tidak sedang chat dengan partner.")

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text=update.message.text)

# ===== REPORT SEDERHANA =====
async def report_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    report_text = " ".join(context.args)
    if not report_text:
        await update.message.reply_text("❗ Gunakan: /report <pesan>")
        return
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🚨 Laporan dari {update.effective_user.full_name} (ID: {user_id}):\n{report_text}"
    )
    await update.message.reply_text("✅ Laporan telah dikirim ke admin.")
    log_activity(f"User {user_id} melaporkan: {report_text}")

# ===== LAPORKAN PARTNER =====
async def report_partner_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if not partner_id:
        await update.message.reply_text("⚠️ Tidak ada partner yang sedang chat.")
        return ConversationHandler.END
    context.user_data['report_partner_id'] = partner_id
    await update.message.reply_text(
        "✏️ Tulis kesalahan atau alasan laporan partner kamu:",
        reply_markup=ReplyKeyboardMarkup([["Batal"]], one_time_keyboard=True)
    )
    return REPORT_REASON

async def report_partner_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() == "batal":
        await update.message.reply_text("❌ Laporan dibatalkan.")
        return ConversationHandler.END

    reporter_id = update.effective_user.id
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
    states={
        REPORT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_partner_reason)]
    },
    fallbacks=[CommandHandler('batal', lambda u,c: ConversationHandler.END)]
)

# ===== BROADCAST ADMIN =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("🚫 Hanya admin yang dapat mengirim broadcast.")
        return
    if not context.args:
        await update.message.reply_text("❗ Gunakan: /broadcast <pesan>")
        return
    message_text = " ".join(context.args)
    count = 0
    for uid, info in users.items():
        if is_verified(uid) and not info.get("blocked_at"):
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Broadcast dari Admin:\n\n{message_text}")
                count += 1
            except:
                pass
    await update.message.reply_text(f"✅ Pesan broadcast dikirim ke {count} user.")
    log_activity(f"Admin {user_id} broadcast ke {count} user: {message_text}")

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
app.add_handler(report_partner_handler)
app.add_handler(CallbackQueryHandler(admin_verify, pattern='^(approve|reject)_'))
app.add_handler(CallbackQueryHandler(block_user_callback, pattern='^block_'))
app.add_handler(CallbackQueryHandler(unblock_user_callback, pattern='^unblock_'))
app.add_handler(CommandHandler('registeradmin', register_admin))
app.add_handler(CommandHandler('find', find_partner))
app.add_handler(CommandHandler('cari_jodoh', cari_jodoh))
app.add_handler(CommandHandler('stop', stop_chat))
app.add_handler(CommandHandler('report', report_user))
app.add_handler(CommandHandler('broadcast', broadcast))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

if __name__ == '__main__':
    print("🚀 Bot Anonymous Kampus berjalan...")
    log_activity("Bot dimulai: " + str(datetime.now()))
    app.run_polling()
