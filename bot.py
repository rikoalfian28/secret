import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ConversationHandler, ContextTypes
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
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
BROADCAST = range(1)
BLOCK_USER = range(1)

# ===== START & VERIFIKASI =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        users[user_id] = {"verified": False, "partner": None, "university": None, "gender": None, "age": None, "blocked_at": None}
    log_activity(f"User {user_id} memulai bot. Verified: {users[user_id]['verified']}")
    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="unnes")],
        [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang di Anonymous Kampus!\nPilih asal universitas kamu:",
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
    users[user_id]["age"] = umur

    # Kirim permintaan verifikasi ke admin
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

# ===== ADMIN VERIFIKASI =====
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
        await context.bot.send_message(chat_id=target_id, text="✅ Anda diverifikasi!")
        await query.edit_message_text(f"User {target_id} disetujui ✅")
        log_activity(f"Admin {user_id} menyetujui user {target_id}")
    else:
        users[target_id]["verified"] = False
        await context.bot.send_message(chat_id=target_id, text="❌ Verifikasi ditolak.")
        await query.edit_message_text(f"User {target_id} ditolak ❌")
        log_activity(f"Admin {user_id} menolak user {target_id}")

# ===== FIND PARTNER =====
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

    if user_id not in waiting_list:
        waiting_list.append(user_id)

    online_count = sum(
        1 for uid, info in users.items()
        if uid != user_id and (uid in waiting_list or info.get("partner"))
    )
    await update.message.reply_text(f"⌛ Menunggu partner...\n📶 Saat ini ada {online_count} user aktif atau menunggu.")

# ===== STOP CHAT =====
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        users[partner_id]["partner"] = None
        users[user_id]["partner"] = None
        if user_id in waiting_list: waiting_list.remove(user_id)
        await update.message.reply_text("✋ Anda berhenti chat.")
        await context.bot.send_message(chat_id=partner_id, text="✋ Partner menghentikan chat.")
        log_activity(f"User {user_id} berhenti chat dengan {partner_id}")
    else:
        if user_id in waiting_list: waiting_list.remove(user_id)
        await update.message.reply_text("⚠️ Tidak sedang chat, berhenti menunggu.")

# ===== RELAY CHAT =====
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.send_message(chat_id=partner_id, text=update.message.text)

# ===== PANEL ADMIN =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("🚫 Bukan admin")
        return
    keyboard = [
        [InlineKeyboardButton("📶 User Online", callback_data="admin_online")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 Block/Unblock User", callback_data="admin_block")]
    ]
    await update.message.reply_text("⚙️ Panel Admin:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    if query.data == "admin_online":
        online_count = sum(1 for uid, info in users.items() if uid in waiting_list or info.get("partner"))
        await query.edit_message_text(f"📶 User aktif atau menunggu: {online_count}")
    elif query.data == "admin_broadcast":
        await query.edit_message_text("Kirim pesan untuk broadcast:")
        return BROADCAST
    elif query.data == "admin_block":
        await query.edit_message_text("Kirim user_id untuk blokir/unblock:")
        return BLOCK_USER

async def admin_broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    for uid, info in users.items():
        if not info.get("blocked_at"):
            await context.bot.send_message(chat_id=uid, text=f"📢 Broadcast Admin:\n{message}")
    await update.message.reply_text("✅ Broadcast terkirim ke semua user.")
    return ConversationHandler.END

async def admin_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        if target_id in users:
            if users[target_id].get("blocked_at"):
                users[target_id]["blocked_at"] = None
                await update.message.reply_text(f"✅ User {target_id} di-unblock")
            else:
                users[target_id]["blocked_at"] = datetime.now()
                await update.message.reply_text(f"🚫 User {target_id} diblokir")
        else:
            await update.message.reply_text("❌ User tidak ditemukan")
    except:
        await update.message.reply_text("❌ Masukkan user_id yang valid")
    return ConversationHandler.END

# ===== START BOT =====
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_verif = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            UNIVERSITY: [CallbackQueryHandler(select_university)],
            GENDER: [CallbackQueryHandler(select_gender)],
            UMUR: [CallbackQueryHandler(select_age)]
        },
        fallbacks=[]
    )

    conv_admin = ConversationHandler(
        entry_points=[CommandHandler("panel", admin_panel)],
        states={
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_msg)],
            BLOCK_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_block_user)]
        },
        fallbacks=[]
    )

    app.add_handler(conv_verif)
    app.add_handler(conv_admin)
    app.add_handler(CallbackQueryHandler(admin_verify, pattern="^(approve|reject)_"))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_"))
    app.add_handler(CommandHandler("find", find_partner))
    app.add_handler(CommandHandler("stop", stop_chat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

    log_activity("🚀 Bot Anonymous Kampus berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
