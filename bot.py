import os
import json
import logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")

DATA_FILE = "users.json"

# ===== LOGGING =====
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/activity.log",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_activity(msg):
    print(msg)
    logging.info(msg)

# ===== DATA USER =====
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()
waiting_find = []
waiting_jodoh = []
admins = [ADMIN_ID]

def is_verified(uid):
    u = users.get(str(uid), {})
    return u.get("verified") and not u.get("blocked_at")

# ===== STATES =====
UNIV, GENDER, AGE = range(3)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in users:
        users[uid] = {"verified": False, "partner": None, "university": None, "gender": None, "age": None, "blocked_at": None}
        save_users()
    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="unnes")],
        [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang di Anonymous Kampus!\nPilih asal universitas kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return UNIV

async def pilih_univ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    users[uid]["university"] = "UNNES" if q.data == "unnes" else "Non-UNNES"
    save_users()
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="male")],
        [InlineKeyboardButton("Perempuan", callback_data="female")],
        [InlineKeyboardButton("Lainnya", callback_data="other")]
    ]
    await q.edit_message_text(
        f"Universitas dipilih: {users[uid]['university']}\nSekarang pilih gender:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GENDER

async def pilih_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    gender_map = {"male": "Laki-laki", "female": "Perempuan", "other": "Lainnya"}
    users[uid]["gender"] = gender_map[q.data]
    save_users()
    keyboard = [[InlineKeyboardButton(str(a), callback_data=f"age_{a}") for a in range(18, 26)]]
    await q.edit_message_text(
        f"Gender dipilih: {users[uid]['gender']}\nSekarang pilih umur kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AGE

async def pilih_umur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    age = int(q.data.split("_")[1])
    users[uid]["age"] = age
    save_users()

    # Kirim ke admin
    msg = (
        f"🔔 Permintaan verifikasi:\n"
        f"Nama: {q.from_user.full_name}\nID: {uid}\n"
        f"Universitas: {users[uid]['university']}\nGender: {users[uid]['gender']}\nUmur: {age}"
    )
    kb = [[
        InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{uid}"),
        InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{uid}")
    ]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup(kb))
    await q.edit_message_text("✅ Permintaan verifikasi dikirim ke admin.")
    log_activity(f"User {uid} minta verifikasi.")
    return ConversationHandler.END

# ===== ADMIN =====
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("Gunakan: /registeradmin <kode>")
        return
    if context.args[0] == SECRET_ADMIN_CODE:
        if uid not in admins:
            admins.append(uid)
        await update.message.reply_text("✅ Anda kini admin.")
    else:
        await update.message.reply_text("❌ Kode salah.")

async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    if int(uid) not in admins:
        await q.answer("🚫 Bukan admin", show_alert=True)
        return
    action, target = q.data.split("_")
    if action == "approve":
        users[target]["verified"] = True
        save_users()
        await context.bot.send_message(chat_id=int(target), text="✅ Anda telah diverifikasi! Gunakan /find untuk mulai mencari partner.")
        await q.edit_message_text(f"User {target} disetujui ✅")
    else:
        users[target]["verified"] = False
        save_users()
        await context.bot.send_message(chat_id=int(target), text="❌ Verifikasi ditolak.")
        await q.edit_message_text(f"User {target} ditolak ❌")

# ===== STOP CHAT =====
async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    partner = users.get(uid, {}).get("partner")

    # Hapus dari waiting
    if uid in waiting_find:
        waiting_find.remove(uid)
    if uid in waiting_jodoh:
        waiting_jodoh.remove(uid)

    # Putuskan chat
    if partner:
        users[partner]["partner"] = None
        await context.bot.send_message(chat_id=int(partner), text="✋ Partner menghentikan chat.")
        users[uid]["partner"] = None
    save_users()
    await update.message.reply_text("🛑 Kamu telah menghentikan semua aktivitas (mencari & chat).")

# ===== FIND =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not is_verified(uid):
        await update.message.reply_text("⚠️ Harus diverifikasi dulu.")
        return
    if users[uid].get("partner"):
        await update.message.reply_text("⚠️ Kamu sedang chat. Gunakan /stop untuk berhenti.")
        return
    for pid in waiting_find:
        if pid != uid and is_verified(pid) and not users[pid].get("partner"):
            users[uid]["partner"] = pid
            users[pid]["partner"] = uid
            waiting_find.remove(pid)
            save_users()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(chat_id=int(pid), text="✅ Partner ditemukan! Mulai chat.")
            return
    waiting_find.append(uid)
    await update.message.reply_text("⌛ Menunggu partner lain yang juga klik /find...")

# ===== RELAY =====
async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    partner = users.get(uid, {}).get("partner")
    if partner:
        await context.bot.send_message(chat_id=int(partner), text=update.message.text)

# ===== LIST USER =====
async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in admins:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    text = "📋 Daftar user:\n"
    for u, info in users.items():
        text += f"ID: {u}, Verified: {info['verified']}, Univ: {info['university']}, Gender: {info['gender']}\n"
    await update.message.reply_text(text[:4000])

# ===== BROADCAST =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in admins:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    if not context.args:
        await update.message.reply_text("Gunakan: /broadcast <pesan>")
        return
    msg = " ".join(context.args)
    count = 0
    for u, i in users.items():
        if is_verified(u):
            try:
                await context.bot.send_message(chat_id=int(u), text=f"📢 Pesan dari admin:\n\n{msg}")
                count += 1
            except:
                pass
    await update.message.reply_text(f"✅ Broadcast terkirim ke {count} user.")

# ===== APP =====
conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        UNIV: [CallbackQueryHandler(pilih_univ, pattern="^(unnes|nonunnes)$")],
        GENDER: [CallbackQueryHandler(pilih_gender, pattern="^(male|female|other)$")],
        AGE: [CallbackQueryHandler(pilih_umur, pattern="^age_")]
    },
    fallbacks=[]
)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(conv)
app.add_handler(CallbackQueryHandler(admin_verify, pattern="^(approve|reject)_"))
app.add_handler(CommandHandler("registeradmin", register_admin))
app.add_handler(CommandHandler("find", find_partner))
app.add_handler(CommandHandler("stop", stop_all))
app.add_handler(CommandHandler("listuser", list_user))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

# ===== MAIN =====
if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")
    import asyncio
    from telegram import Bot

    async def stop_webhook():
        bot = Bot(TOKEN)
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook dihapus, siap polling...")

    asyncio.run(stop_webhook())
    app.run_polling()

