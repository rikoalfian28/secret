import os, json, base64, logging, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)

# ===== KONFIGURASI =====
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATA_FILE = "users.json"

# ===== LOGGING =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)

# ===== DATA =====
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()
waiting = []

# ===== UTIL =====
def is_verified(uid): return users.get(str(uid), {}).get("verified", False)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in users:
        users[uid] = {"name": update.effective_user.full_name, "verified": False, "partner": None}
        save_users()
    kb = [[InlineKeyboardButton("✅ Minta Verifikasi", callback_data="req_verify")]]
    await update.message.reply_text(
        "👋 Selamat datang di Anonymous Kampus!\nKlik tombol di bawah untuk verifikasi.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ===== MINTA VERIFIKASI =====
async def req_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = str(q.from_user.id)
    await q.answer()
    text = f"🔔 Permintaan verifikasi:\n👤 {users[uid]['name']}\n🆔 {uid}"
    kb = [[InlineKeyboardButton("✅ Verifikasi", callback_data=f"verify_{uid}")]]
    await context.bot.send_message(ADMIN_ID, text, reply_markup=InlineKeyboardMarkup(kb))
    await q.edit_message_text("📨 Permintaan verifikasi dikirim ke admin.")

# ===== ADMIN VERIFIKASI =====
async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("🚫 Bukan admin", show_alert=True)
    uid = q.data.split("_")[1]
    users[uid]["verified"] = True
    save_users()
    await context.bot.send_message(uid, "✅ Anda telah diverifikasi oleh admin!")
    await q.edit_message_text(f"✅ {users[uid]['name']} (ID {uid}) telah diverifikasi.")

# ===== CARI PARTNER =====
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if not is_verified(uid):
        return await update.message.reply_text("⚠️ Kamu belum diverifikasi admin.")
    if users[uid].get("partner"):
        return await update.message.reply_text("⚠️ Kamu sudah punya partner. Gunakan /stop untuk keluar.")
    for pid in waiting:
        if pid != uid and is_verified(pid) and not users[pid].get("partner"):
            users[uid]["partner"] = pid
            users[pid]["partner"] = uid
            waiting.remove(pid)
            save_users()
            await update.message.reply_text("✅ Partner ditemukan! Mulai chat.")
            await context.bot.send_message(pid, "✅ Partner ditemukan! Mulai chat.")
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
        await context.bot.send_message(pid, "✋ Partner menghentikan chat.")
    await update.message.reply_text("✅ Chat dihentikan atau pencarian dibatalkan.")

# ===== RELAY CHAT =====
async def relay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    pid = users.get(uid, {}).get("partner")
    if pid:
        await context.bot.send_message(pid, update.message.text)

# ===== BROADCAST =====
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 Hanya admin.")
    msg = " ".join(context.args)
    if not msg: return await update.message.reply_text("Gunakan: /broadcast <pesan>")
    count = 0
    for uid, info in users.items():
        if is_verified(uid):
            try:
                await context.bot.send_message(uid, f"📢 Pesan Admin:\n\n{msg}")
                count += 1
            except: pass
    await update.message.reply_text(f"✅ Broadcast dikirim ke {count} user.")

# ===== BACKUP GITHUB =====
async def backup_to_github():
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPO")
    if not (token and repo and os.path.exists(DATA_FILE)):
        return "⚠️ Konfigurasi GitHub tidak lengkap."
    url = f"https://api.github.com/repos/{repo}/contents/users.json"
    headers = {"Authorization": f"token {token}"}
    with open(DATA_FILE, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None
    data = {"message": "Backup users.json", "content": content, "branch": "main"}
    if sha: data["sha"] = sha
    r = requests.put(url, headers=headers, json=data)
    return "✅ Backup sukses!" if r.status_code in [200,201] else f"❌ Gagal: {r.text}"

async def backup_users(update, ctx): 
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(await backup_to_github())

# ===== MAIN APP =====
app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(req_verify, pattern="req_verify"))
app.add_handler(CallbackQueryHandler(admin_verify, pattern="verify_"))
app.add_handler(CommandHandler("find", find))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("backup_users", backup_users))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay))

if __name__ == "__main__":
    print("🚀 Bot Anonymous Kampus v21+ berjalan...")
    app.run_polling()
