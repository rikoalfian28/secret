import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

# ===== KONFIG =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")
DATA_FILE = "users.json"

users = {}
waiting_find = set()
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
    return u.get("verified", False)

# ===== STATES =====
UNIVERSITY, GENDER, AGE = range(3)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users[user_id] = users.get(user_id, {"verified": False, "partner": None})
    save_data()
    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="univ_unnes")],
        [InlineKeyboardButton("Non-UNNES", callback_data="univ_nonunnes")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang di *Anonymous Kampus Bot!*\nPilih asal universitas kamu:",
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
        [InlineKeyboardButton("Perempuan", callback_data="gender_female")]
    ]
    await query.edit_message_text(
        f"🏫 Universitas: {users[user_id]['university']}\nPilih gender kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GENDER

async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    users[user_id]["gender"] = "Laki-laki" if query.data == "gender_male" else "Perempuan"
    await query.answer()
    keyboard = [[InlineKeyboardButton(str(age), callback_data=f"age_{age}") for age in range(18, 25)]]
    await query.edit_message_text(
        f"👤 Gender: {users[user_id]['gender']}\nSekarang pilih umur kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AGE

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    age = int(query.data.split("_")[1])
    users[user_id]["age"] = age
    save_data()
    await query.answer("Dikirim ke admin untuk verifikasi.")

    keyboard = [[
        InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{user_id}")
    ]]
    text = (
        f"🔔 Permintaan verifikasi:\n"
        f"Nama: {query.from_user.full_name}\nUser ID: {user_id}\n"
        f"Universitas: {users[user_id]['university']}\n"
        f"Gender: {users[user_id]['gender']}\nUmur: {age}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text("✅ Data kamu dikirim ke admin. Tunggu verifikasi ya.")
    return ConversationHandler.END

# ===== ADMIN VERIFIKASI =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    action, target = data[0], data[1]
    await query.answer("Diproses...")
    if user_id not in admins:
        await query.answer("🚫 Bukan admin.", show_alert=True)
        return

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

# ===== LIST USER =====
async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text("🚫 Bukan admin.")
        return
    msg = "👥 *Daftar User:*\n\n"
    for uid, data in users.items():
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
                await context.bot.send_message(int(uid), f"📢 Pesan Admin:\n{text}")
                count += 1
            except:
                pass
    await update.message.reply_text(f"✅ Broadcast dikirim ke {count} user.")

# ===== MAIN =====
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
app.add_handler(CommandHandler('listuser', list_user))
app.add_handler(CommandHandler('broadcast', broadcast))

if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")
    app.run_polling()
