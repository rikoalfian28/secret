import os
import json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DATA_FILE = "users.json"

# ---------------- Data Handler ----------------
def load_users():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_users(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

users = load_users()
active_chats = {}

# ---------------- Helper ----------------
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Cari Partner", callback_data="find")],
        [InlineKeyboardButton("🛑 Stop Chat", callback_data="stop")],
        [InlineKeyboardButton("🚨 Laporkan", callback_data="report")]
    ]
    await update.message.reply_text("Pilih menu:", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- Command ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)

    if uid not in users:
        users[uid] = {"verified": False, "report": 0, "name": user.first_name}
        save_users(users)

    if not users[uid]["verified"]:
        await update.message.reply_text("👋 Hai! Akunmu belum diverifikasi admin.")
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔔 Permintaan verifikasi dari {user.first_name} (ID: {uid})\nGunakan /verify_user {uid}"
            )
        return

    await send_main_menu(update, context)

async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    await query.answer()

    if not users[uid]["verified"]:
        await query.edit_message_text("⚠️ Kamu belum diverifikasi oleh admin.")
        return

    for partner_id, status in active_chats.items():
        if status is None and partner_id != uid:
            active_chats[partner_id] = uid
            active_chats[uid] = partner_id
            await context.bot.send_message(int(partner_id), "🤝 Partner ditemukan! Mulailah chat!")
            await context.bot.send_message(int(uid), "🤝 Partner ditemukan! Mulailah chat!")
            return

    active_chats[uid] = None
    await query.edit_message_text("🔎 Mencari partner... tunggu sebentar.")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    await query.answer()

    if uid in active_chats:
        partner_id = active_chats.get(uid)
        if partner_id:
            await context.bot.send_message(int(partner_id), "🚫 Partner menghentikan chat.")
            active_chats.pop(partner_id, None)
        active_chats.pop(uid, None)
        await query.edit_message_text("🛑 Kamu telah menghentikan chat.")
    else:
        await query.edit_message_text("Kamu belum dalam chat.")

async def report_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    await query.answer()
    partner_id = active_chats.get(uid)

    if partner_id:
        users[partner_id]["report"] += 1
        save_users(users)
        await context.bot.send_message(ADMIN_ID, f"🚨 {uid} melaporkan {partner_id}")
        await query.edit_message_text("✅ Laporan dikirim ke admin.")
    else:
        await query.edit_message_text("⚠️ Kamu belum dalam chat.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in active_chats and active_chats[uid]:
        partner_id = active_chats[uid]
        await context.bot.send_message(int(partner_id), f"💬 {update.message.text}")

# ---------------- Admin ----------------
async def verify_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Hanya admin yang bisa memverifikasi.")
    if not context.args:
        return await update.message.reply_text("Gunakan: /verify_user <user_id>")
    uid = context.args[0]
    if uid in users:
        users[uid]["verified"] = True
        save_users(users)
        await update.message.reply_text(f"✅ User {uid} diverifikasi.")
        await context.bot.send_message(int(uid), "✅ Akunmu telah diverifikasi admin!")
    else:
        await update.message.reply_text("User tidak ditemukan.")

async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Akses admin saja.")
    text = "📋 Daftar User:\n"
    for uid, u in users.items():
        text += f"- {u['name']} | ID: {uid} | {'✔️' if u['verified'] else '❌'}\n"
    await update.message.reply_text(text)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Akses admin saja.")
    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Gunakan: /broadcast <pesan>")
    for uid in users.keys():
        try:
            await context.bot.send_message(int(uid), f"📢 Pesan admin:\n{msg}")
        except:
            pass
    await update.message.reply_text("✅ Broadcast selesai.")

# ---------------- Main ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(find_partner, pattern="^find$"))
app.add_handler(CallbackQueryHandler(stop_chat, pattern="^stop$"))
app.add_handler(CallbackQueryHandler(report_user, pattern="^report$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
app.add_handler(CommandHandler("verify_user", verify_user))
app.add_handler(CommandHandler("list_user", list_user))
app.add_handler(CommandHandler("broadcast", broadcast))

if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")
    app.run_polling()
