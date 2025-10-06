import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

users = {}
waiting_list = []

# ===== UTILITY =====
def load_users():
    global users
    if os.path.exists("users.json"):
        with open("users.json") as f:
            users.update(json.load(f))

def save_users():
    with open("users.json", "w") as f:
        json.dump(users, f, indent=2)

def is_verified(user_id):
    return users.get(str(user_id), {}).get("verified", False)

# ===== START & VERIFIKASI =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users.setdefault(user_id, {"verified": False, "gender": None, "age": None, "status": None, "partner": None})
    save_users()
    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="gender_male"),
         InlineKeyboardButton("Perempuan", callback_data="gender_female")]
    ]
    await update.message.reply_text(
        "👋 Selamat datang! Pilih gender kamu:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    users[user_id]["gender"] = "Laki-laki" if "male" in query.data else "Perempuan"
    save_users()

    ages_buttons = [
        [InlineKeyboardButton(str(a), callback_data=f"age_{a}") for a in range(18, 23)],
        [InlineKeyboardButton(str(a), callback_data=f"age_{a}") for a in range(23, 26)]
    ]
    await query.edit_message_text("🎂 Pilih umur kamu:", reply_markup=InlineKeyboardMarkup(ages_buttons))

async def select_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    users[user_id]["age"] = int(query.data.split("_")[1])
    save_users()

    keyboard = [
        [InlineKeyboardButton("Mahasiswa UNNES", callback_data="status_unnes")],
        [InlineKeyboardButton("Mahasiswa Lain", callback_data="status_other")],
        [InlineKeyboardButton("Bukan Mahasiswa", callback_data="status_non")]
    ]
    await query.edit_message_text("🎓 Pilih status:", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    status_map = {
        "status_unnes": "Mahasiswa UNNES",
        "status_other": "Mahasiswa Lain",
        "status_non": "Bukan Mahasiswa"
    }
    users[user_id]["status"] = status_map[query.data]
    save_users()

    await query.edit_message_text("✅ Data dikirim ke admin untuk verifikasi.")
    text = (
        f"🔔 Permintaan Verifikasi\n"
        f"👤 {query.from_user.full_name}\n"
        f"🆔 {user_id}\n"
        f"Gender: {users[user_id]['gender']}\n"
        f"Umur: {users[user_id]['age']}\n"
        f"Status: {users[user_id]['status']}"
    )
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Verifikasi", callback_data=f"approve_{user_id}")]])
    )

# ===== ADMIN VERIFIKASI =====
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return
    target = query.data.split("_")[1]
    users[target]["verified"] = True
    save_users()
    await query.edit_message_text(f"✅ User {target} diverifikasi!")
    await context.bot.send_message(target, "✅ Kamu telah diverifikasi admin!")

# ===== FIND / STOP =====
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not is_verified(user_id):
        await update.message.reply_text("⚠️ Harus diverifikasi admin.")
        return
    if users[user_id].get("partner"):
        await update.message.reply_text("⚠️ Sudah terhubung partner.")
        return
    for pid in waiting_list:
        if pid != user_id and is_verified(pid) and not users[pid].get("partner"):
            users[user_id]["partner"] = pid
            users[pid]["partner"] = user_id
            waiting_list.remove(pid)
            save_users()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(pid, "✅ Partner ditemukan! Mulai chat.")
            return
    waiting_list.append(user_id)
    await update.message.reply_text("⌛ Menunggu partner...")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner = users.get(user_id, {}).get("partner")
    if partner:
        users[user_id]["partner"] = None
        users[partner]["partner"] = None
        save_users()
        await context.bot.send_message(partner, "✋ Partner menghentikan chat.")
        await update.message.reply_text("✋ Kamu menghentikan chat.")
    elif user_id in waiting_list:
        waiting_list.remove(user_id)
        await update.message.reply_text("❌ Berhenti mencari partner.")
    else:
        await update.message.reply_text("⚠️ Tidak sedang chat atau mencari partner.")

# ===== CHAT RELAY =====
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner = users.get(user_id, {}).get("partner")
    if partner:
        await context.bot.send_message(partner, update.message.text)

# ===== ADMIN PANEL =====
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Hanya admin.")
        return
    keyboard = [
        [InlineKeyboardButton("📋 Belum Diverifikasi", callback_data="panel_unverified")],
        [InlineKeyboardButton("👥 Daftar User", callback_data="panel_users")]
    ]
    await update.message.reply_text("🔧 Panel Admin", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("🚫 Bukan admin", show_alert=True)
        return

    if query.data == "panel_unverified":
        unverified = [u for u in users if not users[u]["verified"]]
        if not unverified:
            await query.edit_message_text("✅ Tidak ada user menunggu verifikasi.")
            return
        text = "📋 User belum diverifikasi:\n\n"
        for uid in unverified:
            data = users[uid]
            text += f"🆔 {uid} | {data['gender']} | {data['age']} | {data['status']}\n"
        await query.edit_message_text(text)

    elif query.data == "panel_users":
        text = "👥 Daftar semua user:\n\n"
        for uid, data in users.items():
            verif = "✅" if data["verified"] else "❌"
            text += f"{verif} {uid} | {data['gender']} | {data['age']} | {data['status']}\n"
        await query.edit_message_text(text)

# ===== RUN BOT =====
load_users()
app = ApplicationBuilder().token(TOKEN).build()

# Handler user
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("find", find_partner))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(CallbackQueryHandler(select_gender, pattern="^gender_"))
app.add_handler(CallbackQueryHandler(select_age, pattern="^age_"))
app.add_handler(CallbackQueryHandler(select_status, pattern="^status_"))

# Handler admin
app.add_handler(CallbackQueryHandler(admin_approve, pattern="^approve_"))
app.add_handler(CallbackQueryHandler(admin_menu_handler, pattern="^panel_"))

# Relay chat
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

print("🚀 Bot Anonymous Kampus berjalan...")
app.run_polling()
