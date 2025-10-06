import os
import json
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")
DATA_FILE = "users.json"

users = {}
waiting_find = set()
waiting_jodoh = set()
admins = [ADMIN_ID]

# ===== LOAD & SAVE =====
def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

def load_data():
    global users
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            users = json.load(f)
    else:
        users = {}

load_data()

def is_verified(uid):
    u = users.get(str(uid), {})
    return u.get("verified", False) and not u.get("blocked", False)

# ===== STATES =====
UNIVERSITY, GENDER, AGE = range(3)
REPORT_REASON = range(1)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users[user_id] = users.get(user_id, {
        "verified": False, "partner": None, "blocked": False,
        "university": None, "gender": None, "age": None
    })
    save_data()

    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="univ_unnes")],
        [InlineKeyboardButton("Non-UNNES", callback_data="univ_nonunnes")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang di *Anonymous Kampus Bot!*\n\n"
        "Pilih asal universitas kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return UNIVERSITY

async def select_university(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    users[user_id]["university"] = "UNNES" if query.data == "univ_unnes" else "Non-UNNES"
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="gender_male")],
        [InlineKeyboardButton("Perempuan", callback_data="gender_female")],
        [InlineKeyboardButton("Lainnya", callback_data="gender_other")]
    ]
    await query.edit_message_text(
        f"🏫 Universitas: {users[user_id]['university']}\n"
        "Pilih gender kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GENDER

async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    gender_map = {
        "gender_male": "Laki-laki",
        "gender_female": "Perempuan",
        "gender_other": "Lainnya"
    }
    users[user_id]["gender"] = gender_map[query.data]
    await query.answer()
    keyboard = [[InlineKeyboardButton(str(age), callback_data=f"age_{age}") for age in range(18, 26)]]
    await query.edit_message_text(
        f"👤 Gender: {users[user_id]['gender']}\n"
        "Sekarang pilih umur kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AGE

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    age = int(query.data.split("_")[1])
    users[user_id]["age"] = age
    save_data()
    await query.answer()

    keyboard = [[
        InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{user_id}")
    ]]
    text = (
        f"🔔 Permintaan verifikasi:\n"
        f"Nama: {query.from_user.full_name}\n"
        f"User ID: {user_id}\n"
        f"Universitas: {users[user_id]['university']}\n"
        f"Gender: {users[user_id]['gender']}\n"
        f"Umur: {age}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text("✅ Data kamu dikirim ke admin. Tunggu verifikasi ya.")
    return ConversationHandler.END

# ===== ADMIN VERIFIKASI =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in admins:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return

    _, action, target = query.data.split("_")
    target = str(target)
    if action == "approve":
        users[target]["verified"] = True
        await context.bot.send_message(int(target), "✅ Akun kamu telah diverifikasi!")
        await query.edit_message_text(f"✅ User {target} disetujui.")
    else:
        users[target]["verified"] = False
        await context.bot.send_message(int(target), "❌ Verifikasi kamu ditolak.")
        await query.edit_message_text(f"❌ User {target} ditolak.")
    save_data()

# ===== ADMIN MANUAL =====
async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("Gunakan: /registeradmin <kode>")
        return
    code = context.args[0]
    if code == SECRET_ADMIN_CODE:
        admins.append(update.effective_user.id)
        await update.message.reply_text("✅ Kamu sekarang admin.")
    else:
        await update.message.reply_text("❌ Kode salah.")

async def verify_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text("🚫 Bukan admin.")
        return
    if not context.args:
        await update.message.reply_text("Gunakan: /verify <user_id>")
        return
    uid = context.args[0]
    if uid not in users:
        await update.message.reply_text("User tidak ditemukan.")
        return
    users[uid]["verified"] = True
    save_data()
    await context.bot.send_message(int(uid), "✅ Kamu telah diverifikasi oleh admin.")
    await update.message.reply_text(f"User {uid} diverifikasi.")

# ===== LIST USER =====
async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text("🚫 Bukan admin.")
        return
    msg = "👥 *Daftar User:*\n\n"
    for uid, data in list(users.items())[:50]:
        status = "✅" if data.get("verified") else "⛔"
        msg += f"{uid} — {data.get('university','-')} — {status}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ===== BROADCAST =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text("🚫 Bukan admin.")
        return
    if not context.args:
        await update.message.reply_text("Gunakan: /broadcast <pesan>")
        return
    text = " ".join(context.args)
    count = 0
    for uid, data in users.items():
        if is_verified(uid):
            try:
                await context.bot.send_message(int(uid), f"📢 *Pesan Admin:*\n\n{text}", parse_mode="Markdown")
                count += 1
            except:
                pass
    await update.message.reply_text(f"✅ Broadcast dikirim ke {count} user.")

# ===== MATCHING =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Kamu belum diverifikasi.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Kamu sedang chat. Gunakan /stop untuk keluar.")
        return
    for partner_id in waiting_find.copy():
        if partner_id != user_id and is_verified(partner_id):
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            waiting_find.discard(partner_id)
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(int(partner_id), "✅ Partner ditemukan! Mulai chat.")
            save_data()
            return
    waiting_find.add(user_id)
    await update.message.reply_text("⌛ Menunggu partner...")

async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        users[user_id]["partner"] = None
        users[partner_id]["partner"] = None
        await context.bot.send_message(int(partner_id), "✋ Partner menghentikan chat.")
        await update.message.reply_text("✋ Kamu menghentikan chat.")
        save_data()
        return
    if user_id in waiting_find:
        waiting_find.discard(user_id)
        await update.message.reply_text("❌ Pencarian dibatalkan.")
    else:
        await update.message.reply_text("Tidak ada aktivitas yang sedang berlangsung.")

# ===== RELAY PESAN =====
async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")
    if partner_id:
        await context.bot.send_message(int(partner_id), text=update.message.text)

# ===== HANDLER =====
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        UNIVERSITY: [CallbackQueryHandler(select_university, pattern='^univ_')],
        GENDER: [CallbackQueryHandler(select_gender, pattern='^gender_')],
        AGE: [CallbackQueryHandler(select_age, pattern='^age_')]
    },
    fallbacks=[]
)

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(admin_verify, pattern='^(approve|reject)_'))
app.add_handler(CommandHandler('registeradmin', register_admin))
app.add_handler(CommandHandler('verify', verify_manual))
app.add_handler(CommandHandler('listuser', list_user))
app.add_handler(CommandHandler('broadcast', broadcast))
app.add_handler(CommandHandler('find', find_partner))
app.add_handler(CommandHandler('stop', stop_all))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")
    app.run_polling()
