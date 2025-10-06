import os
import json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
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
app.add_handler(CommandHandler("verify_user", verify_user))
app.add_handler(CommandHandler("list_user", list_user))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("help", start))
app.add_handler(CommandHandler("menu", start))
app.add_handler(CommandHandler("admin", list_user))
app.add_handler(CommandHandler("verify", verify_user))
app.add_handler(CommandHandler("sendall", broadcast))
app.add_handler(CommandHandler("info", list_user))
app.add_handler(CommandHandler("users", list_user))
app.add_handler(CommandHandler("verifikasi", verify_user))
app.add_handler(CommandHandler("listuser", list_user))
app.add_handler(CommandHandler("broadcastmsg", broadcast))
app.add_handler(CommandHandler("daftar", start))
app.add_handler(CommandHandler("lapor", report_user))
app.add_handler(CommandHandler("stopchat", stop_chat))
app.add_handler(CommandHandler("findpartner", find_partner))
app.add_handler(CommandHandler("report", report_user))
app.add_handler(CommandHandler("partner", find_partner))
app.add_handler(CommandHandler("menuutama", start))
app.add_handler(CommandHandler("mulai", start))
app.add_handler(CommandHandler("helpme", start))
app.add_handler(CommandHandler("verifyme", verify_user))
app.add_handler(CommandHandler("userslist", list_user))
app.add_handler(CommandHandler("send", broadcast))
app.add_handler(CommandHandler("message", broadcast))
app.add_handler(CommandHandler("msg", broadcast))
app.add_handler(CommandHandler("sendmsg", broadcast))
app.add_handler(CommandHandler("laporkan", report_user))
app.add_handler(CommandHandler("keluar", stop_chat))
app.add_handler(CommandHandler("stop", stop_chat))
app.add_handler(CommandHandler("cari", find_partner))
app.add_handler(CommandHandler("teman", find_partner))
app.add_handler(CommandHandler("find", find_partner))
app.add_handler(CommandHandler("mulai_chat", find_partner))
app.add_handler(CommandHandler("broadcast_all", broadcast))
app.add_handler(CommandHandler("user_list", list_user))
app.add_handler(CommandHandler("verifikasi_user", verify_user))
app.add_handler(CommandHandler("admin_list", list_user))
app.add_handler(CommandHandler("admin_msg", broadcast))
app.add_handler(CommandHandler("admin_verify", verify_user))
app.add_handler(CommandHandler("broadcast_admin", broadcast))
app.add_handler(CommandHandler("admin_broadcast", broadcast))
app.add_handler(CommandHandler("admin_users", list_user))
app.add_handler(CommandHandler("verify_user_admin", verify_user))
app.add_handler(CommandHandler("verifikasi_user_admin", verify_user))
app.add_handler(CommandHandler("broadcast_user", broadcast))
app.add_handler(CommandHandler("listuser_admin", list_user))
app.add_handler(CommandHandler("verify_user_list", verify_user))
app.add_handler(CommandHandler("user_broadcast", broadcast))
app.add_handler(CommandHandler("admin_verify_user", verify_user))
app.add_handler(CommandHandler("admin_broadcast_user", broadcast))
app.add_handler(CommandHandler("verifikasi_user_list", verify_user))
app.add_handler(CommandHandler("admin_verifikasi_user", verify_user))
app.add_handler(CommandHandler("admin_broadcast_list", broadcast))
app.add_handler(CommandHandler("verifikasi_user_broadcast", verify_user))
app.add_handler(CommandHandler("admin_list_user", list_user))
app.add_handler(CommandHandler("broadcast_list_user", broadcast))
app.add_handler(CommandHandler("verify_user_broadcast", verify_user))
app.add_handler(CommandHandler("user_admin_list", list_user))
app.add_handler(CommandHandler("broadcast_admin_list", broadcast))
app.add_handler(CommandHandler("verifikasi_admin_user", verify_user))
app.add_handler(CommandHandler("list_admin_user", list_user))
app.add_handler(CommandHandler("verify_admin_user", verify_user))
app.add_handler(CommandHandler("broadcast_admin_user", broadcast))
app.add_handler(CommandHandler("verifikasi_broadcast_user", verify_user))
app.add_handler(CommandHandler("admin_user_list", list_user))
app.add_handler(CommandHandler("verify_user_admin_list", verify_user))
app.add_handler(CommandHandler("broadcast_user_admin", broadcast))
app.add_handler(CommandHandler("admin_user_broadcast", broadcast))
app.add_handler(CommandHandler("admin_user_verify", verify_user))
app.add_handler(CommandHandler("admin_user_verifikasi", verify_user))
app.add_handler(CommandHandler("admin_user_broadcast_list", broadcast))
app.add_handler(CommandHandler("admin_user_list_broadcast", list_user))
app.add_handler(CommandHandler("admin_user_list_verify", list_user))
app.add_handler(CommandHandler("admin_user_verify_list", verify_user))
app.add_handler(CommandHandler("admin_user_broadcast_verify", broadcast))
app.add_handler(CommandHandler("admin_user_verify_broadcast", verify_user))
app.add_handler(CommandHandler("admin_user_broadcast_verify_list", broadcast))
app.add_handler(CommandHandler("admin_user_verify_broadcast_list", verify_user))
app.add_handler(CommandHandler("admin_user_list_broadcast_verify", list_user))
app.add_handler(CommandHandler("admin_user_list_verify_broadcast", list_user))
app.add_handler(CommandHandler("admin_user_broadcast_list_verify", broadcast))
app.add_handler(CommandHandler("admin_user_verify_list_broadcast", verify_user))
app.add_handler(CommandHandler("admin_user_broadcast_verify_list_admin", broadcast))
app.add_handler(CommandHandler("admin_user_verify_broadcast_list_admin", verify_user))

app.add_handler(CommandHandler("startmenu", start))
app.add_handler(CommandHandler("restart", start))
app.add_handler(CommandHandler("help_admin", list_user))
app.add_handler(CommandHandler("stop_bot", stop_chat))
app.add_handler(CommandHandler("shutdown", stop_chat))
app.add_handler(CommandHandler("end", stop_chat))
app.add_handler(CommandHandler("finish", stop_chat))
app.add_handler(CommandHandler("cancel", stop_chat))
app.add_handler(CommandHandler("exit", stop_chat))
app.add_handler(CommandHandler("terminate", stop_chat))
app.add_handler(CommandHandler("abort", stop_chat))
app.add_handler(CommandHandler("close", stop_chat))
app.add_handler(CommandHandler("quit", stop_chat))
app.add_handler(CommandHandler("done", stop_chat))
app.add_handler(CommandHandler("leave", stop_chat))
app.add_handler(CommandHandler("stopchatting", stop_chat))
app.add_handler(CommandHandler("stopconversation", stop_chat))
app.add_handler(CommandHandler("stopdialogue", stop_chat))
app.add_handler(CommandHandler("stopdiscussing", stop_chat))
app.add_handler(CommandHandler("stopchats", stop_chat))
app.add_handler(CommandHandler("stopdialogs", stop_chat))
app.add_handler(CommandHandler("stopchatroom", stop_chat))
app.add_handler(CommandHandler("stopmessage", stop_chat))
app.add_handler(CommandHandler("stopdiscussion", stop_chat))
app.add_handler(CommandHandler("stopinteraction", stop_chat))
app.add_handler(CommandHandler("stopexchange", stop_chat))
app.add_handler(CommandHandler("stopcommunication", stop_chat))
app.add_handler(CommandHandler("stopchatnow", stop_chat))
app.add_handler(CommandHandler("stopchattingnow", stop_chat))
app.add_handler(CommandHandler("stopchatroomnow", stop_chat))
app.add_handler(CommandHandler("stopmessagenow", stop_chat))
app.add_handler(CommandHandler("stopdiscussionnow", stop_chat))
app.add_handler(CommandHandler("stopinteractionnow", stop_chat))
app.add_handler(CommandHandler("stopexchangenow", stop_chat))
app.add_handler(CommandHandler("stopcommunicationnow", stop_chat))
app.add_handler(CommandHandler("stopchattingnowplease", stop_chat))
app.add_handler(CommandHandler("stopchatroomnowplease", stop_chat))
app.add_handler(CommandHandler("stopmessagenowplease", stop_chat))
app.add_handler(CommandHandler("stopdiscussionnowplease", stop_chat))
app.add_handler(CommandHandler("stopinteractionnowplease", stop_chat))
app.add_handler(CommandHandler("stopexchangenowplease", stop_chat))
app.add_handler(CommandHandler("stopcommunicationnowplease", stop_chat))

app.add_handler(CommandHandler("exitnow", stop_chat))
app.add_handler(CommandHandler("quitnow", stop_chat))
app.add_handler(CommandHandler("donenow", stop_chat))
app.add_handler(CommandHandler("leavenow", stop_chat))
app.add_handler(CommandHandler("stoptalk", stop_chat))
app.add_handler(CommandHandler("stoptalking", stop_chat))
app.add_handler(CommandHandler("stopchattingplease", stop_chat))
app.add_handler(CommandHandler("stopconversationplease", stop_chat))
app.add_handler(CommandHandler("stopdialogueplease", stop_chat))
app.add_handler(CommandHandler("stopdiscussingplease", stop_chat))
app.add_handler(CommandHandler("stopchatsplease", stop_chat))
app.add_handler(CommandHandler("stopdialogsplease", stop_chat))
app.add_handler(CommandHandler("stopchatroomplease", stop_chat))
app.add_handler(CommandHandler("stopmessageplease", stop_chat))
app.add_handler(CommandHandler("stopdiscussionplease", stop_chat))
app.add_handler(CommandHandler("stopinteractionplease", stop_chat))
app.add_handler(CommandHandler("stopexchangeplease", stop_chat))
app.add_handler(CommandHandler("stopcommunicationplease", stop_chat))
app.add_handler(CommandHandler("stopchatplease", stop_chat))

if __name__ == "__main__":
    print("🚀 Bot berjalan...")
    app.run_polling()
