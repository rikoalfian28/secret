import os
import json
import logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")

# ===== PERSISTEN DATA =====
DATA_FILE = "users.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_data()
waiting_list = []
admins = [ADMIN_ID]

# ===== LOGGING =====
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/activity.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log_activity(message: str):
    print(message)
    logging.info(message)

def is_verified(user_id):
    u = users.get(str(user_id), {})
    return u.get("verified", False) and not u.get("blocked_at")

# ===== STATES =====
UNIVERSITY, GENDER, UMUR, REPORT_REASON = range(4)

# ===== START & VERIFIKASI =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {
            "verified": False, "partner": None, "university": None,
            "gender": None, "age": None, "blocked_at": None, "name": update.effective_user.full_name
        }
        save_data()
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
    user_id = str(query.from_user.id)
    await query.answer()
    users[user_id]["university"] = "UNNES" if query.data == "unnes" else "Non-UNNES"
    save_data()
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="gender_male")],
        [InlineKeyboardButton("Perempuan", callback_data="gender_female")],
        [InlineKeyboardButton("Lainnya", callback_data="gender_other")]
    ]
    await query.edit_message_text(
        f"Universitas: {users[user_id]['university']}\nPilih gender kamu:",
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
    users[user_id]["gender"] = gender_map.get(query.data, "Lainnya")
    save_data()
    keyboard = [[InlineKeyboardButton(str(age), callback_data=f"age_{age}") for age in range(18, 26)]]
    await query.edit_message_text(
        f"Gender: {users[user_id]['gender']}\nSekarang pilih umur kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UMUR

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    await query.answer()
    umur = int(query.data.split("_")[1])
    users[user_id]["age"] = umur
    save_data()

    text_admin = (
        f"🔔 Permintaan verifikasi:\n"
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
    await query.edit_message_text("✅ Permintaan verifikasi dikirim ke admin. Tunggu persetujuan.")
    log_activity(f"User {user_id} minta verifikasi.")
    return ConversationHandler.END

# ===== ADMIN =====
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if len(context.args) != 1:
        await update.message.reply_text("❗ Gunakan: /registeradmin <kode_rahasia>")
        return
    code = context.args[0]
    if code == SECRET_ADMIN_CODE:
        if user_id not in admins:
            admins.append(user_id)
            await update.message.reply_text("✅ Anda kini admin!")
            log_activity(f"User {user_id} menjadi admin.")
        else:
            await update.message.reply_text("⚠️ Sudah admin.")
    else:
        await update.message.reply_text("❌ Kode salah.")

async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = str(query.from_user.id)
    if admin_id not in admins:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return
    await query.answer()
    action, target_id = query.data.split("_")
    target = users.get(target_id)
    if not target:
        await query.edit_message_text("⚠️ User tidak ditemukan.")
        return
    if action == "approve":
        target["verified"] = True
        await context.bot.send_message(chat_id=int(target_id), text="✅ Anda telah diverifikasi! Gunakan /find untuk mencari partner.")
        await query.edit_message_text(f"User {target_id} disetujui ✅")
        log_activity(f"Admin {admin_id} menyetujui {target_id}")
    else:
        target["verified"] = False
        await context.bot.send_message(chat_id=int(target_id), text="❌ Verifikasi ditolak.")
        await query.edit_message_text(f"User {target_id} ditolak ❌")
        log_activity(f"Admin {admin_id} menolak {target_id}")
    save_data()

# ===== FIND & STOP =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Anda belum diverifikasi.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Anda sudah terhubung. Gunakan /stop untuk berhenti.")
        return
    for partner_id in waiting_list:
        if partner_id != user_id and is_verified(partner_id) and not users[partner_id].get("partner"):
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            waiting_list.remove(partner_id)
            save_data()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(chat_id=int(partner_id), text="✅ Partner ditemukan! Mulai chat.")
            return
    waiting_list.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner lain...")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        users[user_id]["partner"] = None
        users[partner_id]["partner"] = None
        save_data()
        await update.message.reply_text("✋ Chat dihentikan.")
        await context.bot.send_message(chat_id=int(partner_id), text="✋ Partner menghentikan chat.")
    elif user_id in waiting_list:
        waiting_list.remove(user_id)
        await update.message.reply_text("❌ Pencarian partner dibatalkan.")
    else:
        await update.message.reply_text("⚠️ Tidak sedang chat atau mencari partner.")

# ===== RELAY PESAN =====
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.send_message(chat_id=int(partner_id), text=update.message.text)

# ===== LIST USER =====
async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in admins:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    text = "📋 Daftar User:\n\n"
    for uid, info in users.items():
        text += f"• {info['name']} ({uid}) - {'✅' if info.get('verified') else '❌'}\n"
    await update.message.reply_text(text)

# ===== BROADCAST =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in admins:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    msg = " ".join(context.args)
    count = 0
    for uid, info in users.items():
        if is_verified(uid):
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📢 Broadcast:\n\n{msg}")
                count += 1
            except: pass
    await update.message.reply_text(f"✅ Broadcast dikirim ke {count} user.")

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    reason = " ".join(context.args)
    if not reason:
        await update.message.reply_text("Gunakan: /report <alasan>")
        return
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 Laporan dari {users[user_id]['name']} ({user_id}): {reason}")
    await update.message.reply_text("✅ Laporan dikirim ke admin.")

# ===== HANDLER =====
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        UNIVERSITY: [CallbackQueryHandler(select_university, pattern="^(unnes|nonunnes)$")],
        GENDER: [CallbackQueryHandler(select_gender, pattern="^gender_")],
        UMUR: [CallbackQueryHandler(select_age, pattern="^age_")]
    },
    fallbacks=[]
)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(admin_verify, pattern="^(approve|reject)_"))
app.add_handler(CommandHandler("registeradmin", register_admin))
app.add_handler(CommandHandler("find", find_partner))
app.add_handler(CommandHandler("stop", stop_chat))
app.add_handler(CommandHandler("listuser", list_user))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("report", report))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

# ===== RAILWAY SAFE LOOP =====
if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")

    import asyncio

    async def main():
        await app.initialize()
        await app.start()
        print("✅ Bot siap menerima update...")
        await app.updater.start_polling()
        await app.updater.idle()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(main())
        else:
            loop.run_until_complete(main())
    except RuntimeError:
        asyncio.run(main())
