import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    return users.get(user_id, {}).get("verified", False)

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

    # Pilih gender
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

    # Tombol umur 18-25
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

# ===== FIND PARTNER =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Anda belum diverifikasi admin.")
        return

    if user_id in waiting_list:
        await update.message.reply_text("⏳ Anda sudah dalam antrian, harap tunggu...")
        return

    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Anda sudah terhubung dengan partner.")
        return

    partner_id = None
    for uid in waiting_list:
        if uid != user_id:
            partner_id = uid
            waiting_list.remove(uid)
            break

    if partner_id:
        users[user_id]['partner'] = partner_id
        users[partner_id]['partner'] = user_id
        await context.bot.send_message(chat_id=user_id, text="🎉 Terhubung dengan seseorang! Kirim pesan sekarang.")
        await context.bot.send_message(chat_id=partner_id, text="🎉 Terhubung dengan seseorang! Kirim pesan sekarang.")
        log_activity(f"User {user_id} terhubung dengan {partner_id} (/find)")
    else:
        waiting_list.append(user_id)
        await update.message.reply_text("🔎 Menunggu partner...")

# ===== CARI JODOH (malam minggu lawan jenis) =====
async def cari_jodoh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Anda belum diverifikasi admin.")
        return

    now = datetime.now()
    weekday = now.weekday()  # 5=Sabtu,6=Minggu
    hour = now.hour

    if not (weekday in [5,6] and 18 <= hour <= 23):
        await update.message.reply_text("❌ Fitur 'cari jodoh' hanya tersedia malam minggu 18-23.")
        return

    from_gender = users[user_id].get("gender", "Lainnya")

    if user_id in waiting_list:
        await update.message.reply_text("⏳ Anda sudah dalam antrian, harap tunggu...")
        return

    partner_id = None
    for uid in waiting_list:
        if uid == user_id:
            continue
        partner_gender = users[uid].get("gender","Lainnya")
        if partner_gender != from_gender:
            partner_id = uid
            waiting_list.remove(uid)
            break

    if partner_id:
        users[user_id]['partner'] = partner_id
        users[partner_id]['partner'] = user_id
        await context.bot.send_message(chat_id=user_id, text="💖 Terhubung dengan lawan jenis! Kirim pesan sekarang.")
        await context.bot.send_message(chat_id=partner_id, text="💖 Terhubung dengan lawan jenis! Kirim pesan sekarang.")
        log_activity(f"User {user_id} terhubung dengan {partner_id} (/cari_jodoh)")
    else:
        waiting_list.append(user_id)
        await update.message.reply_text("🔎 Menunggu lawan jenis...")

# ===== STOP CHAT =====
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get('partner')
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="🚫 Pasangan meninggalkan obrolan.")
        users[partner_id]['partner'] = None
        users[user_id]['partner'] = None
        await update.message.reply_text("Anda keluar dari obrolan.")
        log_activity(f"User {user_id} keluar dari chat dengan {partner_id}")
    else:
        await update.message.reply_text("Anda tidak sedang chat dengan siapa pun.")

# ===== RELAY MESSAGE =====
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get('partner')
    if partner_id:
        log_activity(f"Pesan {user_id} → {partner_id}: {update.message.text}")
        await context.bot.send_message(chat_id=partner_id, text=update.message.text)
    else:
        await update.message.reply_text("⚠️ Belum terhubung dengan siapa pun.")

# ===== REPORT USER =====
async def report_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("❗ Gunakan format: /report <alasan>")
        return

    alasan = " ".join(context.args)
    partner_id = users.get(user_id, {}).get('partner')

    report_text = f"🚨 Laporan baru:\n" \
                  f"Dari User ID: {user_id}\n" \
                  f"Nama: {update.effective_user.full_name}\n" \
                  f"Partner ID: {partner_id}\n" \
                  f"Alasan: {alasan}"

    keyboard = [
        [InlineKeyboardButton("🚫 Block User", callback_data=f"block_{user_id}")]
    ]

    for admin in admins:
        await context.bot.send_message(chat_id=admin, text=report_text, reply_markup=InlineKeyboardMarkup(keyboard))

    await update.message.reply_text("✅ Laporan berhasil dikirim ke admin. Terima kasih telah melaporkan.")
    log_activity(f"User {user_id} melaporkan partner {partner_id}: {alasan}")

# ===== CALLBACK BLOCK USER =====
async def block_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id
    if admin_id not in admins:
        await query.answer("🚫 Anda bukan admin.", show_alert=True)
        return

    await query.answer()
    target_id = int(query.data.split("_")[1])

    # Reset user & simpan waktu blokir
    users[target_id] = {
        "verified": False,
        "partner": None,
        "university": None,
        "gender": None,
        "age": None,
        "blocked_at": datetime.now()
    }
    if target_id in waiting_list:
        waiting_list.remove(target_id)

    # Beri tahu partner jika sedang chat
    partner_id = users.get(target_id, {}).get('partner')
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text="🚫 Partner Anda telah diblokir oleh admin.")
        users[partner_id]['partner'] = None

    # Pemberitahuan ke user yang diblokir
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="⚠️ Akun Anda telah diblokir oleh admin selama 30 hari karena pelanggaran/penyalahgunaan bot.\n"
                 "Setelah 30 hari, akun Anda akan otomatis dibuka."
        )
    except:
        pass

    await query.edit_message_text(f"⚠️ User {target_id} telah diblokir oleh admin selama 30 hari.")
    log_activity(f"Admin {admin_id} memblokir user {target_id} selama 30 hari")

# ===== JOB UNBLOCK OTOMATIS 30 HARI =====
async def unblock_users(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    for user_id, data in list(users.items()):
        blocked_at = data.get("blocked_at")
        if blocked_at and now - blocked_at >= timedelta(days=30):
            users[user_id]["blocked_at"] = None
            log_activity(f"User {user_id} otomatis dibuka blokir setelah 30 hari")
            try:
                await context.bot.send_message(chat_id=user_id, text="✅ Akun Anda telah dibuka blokir. Anda bisa menggunakan bot kembali.")
            except:
                pass

# ===== MAIN =====
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        UNIVERSITY: [CallbackQueryHandler(select_university, pattern='^(unnes|nonunnes)$')],
        GENDER: [CallbackQueryHandler(select_gender, pattern='^gender_')],
        UMUR: [CallbackQueryHandler(select_age, pattern='^age_')]
    },
    fallbacks=[]
)

app = ApplicationBuilder().token(TOKEN).build()

# Tambahkan job queue untuk unblock otomatis
job_queue = app.job_queue
job_queue.run_repeating(unblock_users, interval=24*60*60, first=10)  # cek setiap 24 jam

# ===== HANDLER =====
app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(admin_verify, pattern='^(approve|reject)_'))
app.add_handler(CallbackQueryHandler(block_user_callback, pattern='^block_'))
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
