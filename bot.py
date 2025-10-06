import os
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "admin123")
DATA_FILE = "users.json"

# ===================== FUNGSI UTILITAS =====================

def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()
waiting_users = []

# ===================== FITUR ADMIN =====================

async def register_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        return await update.message.reply_text("Gunakan format: /registeradmin <kode>")
    code = context.args[0]
    if code == SECRET_ADMIN_CODE:
        users[str(update.effective_user.id)] = {"verified": True, "is_admin": True}
        save_users()
        await update.message.reply_text("✅ Kamu telah menjadi admin!")
    else:
        await update.message.reply_text("❌ Kode salah!")

async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Hanya admin yang dapat melihat daftar user.")
    text = "📋 Daftar user:\n"
    for uid, data in users.items():
        text += f"ID: {uid}, Verified: {data.get('verified')}, Univ: {data.get('university', '-')}, Gender: {data.get('gender', '-')}\n"
    await update.message.reply_text(text)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ Kamu bukan admin.")
    if not context.args:
        return await update.message.reply_text("Gunakan: /broadcast <pesan>")
    message = " ".join(context.args)
    count = 0
    for uid in users.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 Pesan admin:\n{message}")
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ Pesan terkirim ke {count} user.")

# ===================== FITUR USER =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {
            "verified": False,
            "partner": None,
            "university": "-",
            "gender": "-",
            "age": "-",
            "is_admin": False
        }
        save_users()
    await update.message.reply_text(
        "👋 Selamat datang di *AnonKampus Bot*!\n"
        "Ketik /find untuk mencari partner anonim.\n"
        "Gunakan /stop untuk berhenti chatting.\n\n"
        "Admin bisa gunakan /listuser atau /broadcast.",
        parse_mode="Markdown"
    )

async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if users[user_id].get("partner"):
        return await update.message.reply_text("⚠️ Kamu sudah dalam sesi chat. Ketik /stop untuk keluar dulu.")

    if waiting_users and waiting_users[0] != user_id:
        partner_id = waiting_users.pop(0)
        users[user_id]["partner"] = partner_id
        users[partner_id]["partner"] = user_id
        save_users()
        await update.message.reply_text("✅ Partner ditemukan! Mulailah chat.")
        await context.bot.send_message(partner_id, "✅ Partner ditemukan! Mulailah chat.")
    else:
        waiting_users.append(user_id)
        await update.message.reply_text("⏳ Menunggu partner...")

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")

    if partner_id:
        users[user_id]["partner"] = None
        users[partner_id]["partner"] = None
        save_users()
        await update.message.reply_text("❌ Kamu menghentikan chat.")
        await context.bot.send_message(partner_id, "🚫 Partner kamu menghentikan chat.")
    else:
        if user_id in waiting_users:
            waiting_users.remove(user_id)
        await update.message.reply_text("✅ Kamu tidak sedang dalam chat.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    partner_id = users.get(user_id, {}).get("partner")

    if not partner_id:
        return await update.message.reply_text("❗ Kamu belum punya partner. Ketik /find untuk mulai.")
    await context.bot.send_message(partner_id, update.message.text)

# ===================== MAIN APP =====================

app = ApplicationBuilder().token(TOKEN).build()

# Command user
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("find", find_partner))
app.add_handler(CommandHandler("stop", stop_chat))

# Command admin
app.add_handler(CommandHandler("registeradmin", register_admin))
app.add_handler(CommandHandler("listuser", list_user))
app.add_handler(CommandHandler("broadcast", broadcast))

# Pesan teks biasa
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ===================== ENTRY POINT =====================

if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")

    async def main():
        bot = Bot(TOKEN)
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook dihapus, bot siap polling...")
        await app.run_polling()

    asyncio.run(main())
