import os
import json
import logging
import base64
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

# ===== KONFIGURASI DASAR =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SECRET_ADMIN_CODE = os.getenv("SECRET_ADMIN_CODE", "KAMPUS123")
DATA_FILE = "users.json"

# ===== LOGGING =====
os.makedirs("logs", exist_ok=True)
logging.basicConfig(filename="logs/activity.log", level=logging.INFO, format="%(asctime)s - %(message)s")

def log(msg):
    print(msg)
    logging.info(msg)

# ===== DATA USERS =====
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()
admins = [ADMIN_ID]
waiting = []

# ===== CEK VERIFIKASI =====
def is_verified(uid): return users.get(str(uid), {}).get("verified", False)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in users:
        users[uid] = {"name": update.effective_user.full_name, "verified": False, "partner": None}
        save_users()
    keyboard = [[InlineKeyboardButton("✅ Minta Verifikasi", callback_data="req_verify")]]
    await update.message.reply_text("👋 Selamat datang di Anonymous Kampus!\nGunakan tombol di bawah untuk verifikasi.", reply_markup=InlineKeyboardMarkup(keyboard))

async def req_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    await query.answer()
    text = f"🔔 Permintaan verifikasi baru:\nNama: {users[uid]['name']}\nUser ID: {uid}"
    keyboard = [[InlineKeyboardButton("✅ Setujui", callback_data=f"approve_{uid}"),
                 InlineKeyboardButton("❌ Tolak", callback_data=f"reject_{uid}")]]
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=InlineKeyboardMarkup(keyboard))
    await query.edit_message_text("✅ Permintaan verifikasi telah dikirim ke admin.")

# ===== ADMIN APPROVE =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in admins:
        return await query.answer("🚫 Bukan admin", show_alert=True)
    await query.answer()
    act, uid = query.data.split("_")
    if act == "approve":
        users[uid]["verified"] = True
        save_users()
        await context.bot.send_message(chat_id=uid, text="✅ Anda telah diverifikasi!")
        await query.edit_message_text(f"User {uid} disetujui ✅")
    else:
        users[uid]["verified"] = False
        save_users()
        await context.bot.send_message(chat_id=uid, text="❌ Verifikasi ditolak.")
        await query.edit_message_text(f"User {uid} ditolak ❌")

# ===== FIND PARTNER =====
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not is_verified(uid):
        return await update.message.reply_text("⚠️ Kamu belum diverifikasi admin.")
    if users[uid].get("partner"):
        return await update.message.reply_text("⚠️ Kamu sudah punya partner. Gunakan /stop untuk berhenti.")
    for pid in waiting:
        if pid != uid and is_verified(pid) and not users[pid].get("partner"):
            users[uid]["partner"] = pid
            users[pid]["partner"] = uid
            waiting.remove(pid)
            save_users()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(chat_id=pid, text="✅ Partner ditemukan! Mulai chat.")
            return
    waiting.append(uid)
    await update.message.reply_text("⌛ Menunggu partner lain...")

# ===== STOP CHAT =====
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    pid = users.get(uid, {}).get("partner")
    if uid in waiting:
        waiting.remove(uid)
    if pid:
        users[uid]["partner"] = None
        users[pid]["partner"] = None
        save_users()
        await context.bot.send_message(chat_id=pid, text="✋ Partner menghentikan chat.")
    await update.message.reply_text("✅ Kamu telah keluar dari chat atau membatalkan pencarian.")

# ===== RELAY CHAT =====
async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    pid = users.get(uid, {}).get("partner")
    if pid:
        await context.bot.send_message(chat_id=pid, text=update.message.text)

# ===== REPORT =====
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Gunakan: /report <pesan>")
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 Laporan dari {users[uid]['name']} ({uid}):\n{msg}")
    await update.message.reply_text("✅ Laporan dikirim ke admin.")

# ===== LIST USER =====
async def list_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        return await update.message.reply_text("🚫 Hanya admin.")
    text = "📋 Daftar User:\n"
    for i, (uid, info) in enumerate(users.items(), start=1):
        text += f"{i}. {info['name']} - {'✅' if info.get('verified') else '❌'} (ID: {uid})\n"
    await update.message.reply_text(text)

# ===== BROADCAST =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        return await update.message.reply_text("🚫 Hanya admin.")
    msg = " ".join(context.args)
    if not msg:
        return await update.message.reply_text("Gunakan: /broadcast <pesan>")
    count = 0
    for uid, info in users.items():
        if is_verified(uid):
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 Pesan admin:\n\n{msg}")
                count += 1
            except:
                pass
    await update.message.reply_text(f"✅ Broadcast dikirim ke {count} user.")

# ===== BACKUP KE GITHUB =====
async def backup_to_github():
    if not os.path.exists(DATA_FILE):
        return "⚠️ Tidak ada file users.json"
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    url = f"https://api.github.com/repos/{repo}/contents/users.json"
    headers = {"Authorization": f"token {token}"}
    with open(DATA_FILE, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None
    data = {"message": "Backup otomatis users.json", "content": content, "branch": "main"}
    if sha: data["sha"] = sha
    res = requests.put(url, headers=headers, data=json.dumps(data))
    return "✅ Backup sukses!" if res.status_code in [200,201] else f"❌ Gagal: {res.text}"

async def restore_from_github():
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    url = f"https://api.github.com/repos/{repo}/contents/users.json"
    headers = {"Authorization": f"token {token}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = base64.b64decode(res.json()["content"])
        with open(DATA_FILE, "wb") as f: f.write(content)
        return "✅ Restore sukses!"
    return f"❌ Gagal: {res.text}"

async def backup_users(update, context):
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("🚫 Hanya admin.")
    msg = await backup_to_github()
    await update.message.reply_text(msg)

async def restore_users(update, context):
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("🚫 Hanya admin.")
    msg = await restore_from_github()
    await update.message.reply_text(msg)

# ===== APP =====
app = ApplicationBuilder().token(TOKEN).build()

# ===== HANDLER =====
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(req_verify, pattern="req_verify"))
app.add_handler(CallbackQueryHandler(admin_verify, pattern="^(approve|reject)_"))
app.add_handler(CommandHandler("find", find))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("list_user", list_user))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("backup_users", backup_users))
app.add_handler(CommandHandler("restore_users", restore_users))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus berjalan...")
    app.run_polling()
