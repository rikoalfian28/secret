# main.py - FULL
import os
import random
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# === STATE CONSTANTS ===
UNIVERSITY, GENDER, AGE = range(3)

# === In-memory data (ganti ke DB untuk persisten) ===
users = {}  # user_id -> dict with keys: verified, partner, university, gender, age, searching, banned
chat_logs = {}  # user_id -> list of (sender_label, message) up to last 20

# === Admin IDs ===
ADMIN_IDS = [7894393728]  # ganti dengan user ID admin-mu


# ---------------------------
# Helper utilities
# ---------------------------
async def safe_reply(update: Update, text: str, parse_mode=None, reply_markup=None):
    """Reply robustly to message or callback query."""
    if getattr(update, "message", None):
        return await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    elif getattr(update, "callback_query", None):
        # Prefer editing or sending a message in the callback context
        cq = update.callback_query
        if cq.message:
            return await cq.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            return await cq.answer(text)


def ensure_user(user_id: int):
    """Ensure user record exists."""
    if user_id not in users:
        users[user_id] = {
            "verified": False,
            "partner": None,
            "university": None,
            "gender": None,
            "age": None,
            "searching": False,
            "banned": False,
        }


def save_chat(user_id: int, sender: str, message: str):
    """Save chat history (max 20 entries per user)."""
    if user_id not in chat_logs:
        chat_logs[user_id] = []
    chat_logs[user_id].append((sender, message))
    if len(chat_logs[user_id]) > 20:
        chat_logs[user_id] = chat_logs[user_id][-20:]


# ---------------------------
# Menu / Start / Registration
# ---------------------------
async def show_main_menu(update: Optional[Update] = None, context: Optional[ContextTypes.DEFAULT_TYPE] = None, chat_id: Optional[int] = None):
    """
    Show main menu.
    Cari Doi button only shown between:
      - Saturday >= 18:00 (local server time) up to Sunday 23:59
    """
    now = datetime.now()
    day = now.weekday()  # Monday=0 .. Sunday=6
    hour = now.hour

    keyboard = [
        [InlineKeyboardButton("🔍 Find", callback_data="find")],
        [InlineKeyboardButton("✏️ Ubah Profil", callback_data="ubah_profil")],
        [InlineKeyboardButton("👤 Profil", callback_data="profil")],
    ]

    # Insert Cari Doi only Sat 18:00 -> Sun 23:59
    if (day == 5 and hour >= 18) or (day == 6):
        keyboard.insert(1, [InlineKeyboardButton("💘 Cari Doi", callback_data="cari_doi")])

    text = "✅ Kamu sudah diverifikasi!\nPilih tombol untuk memulai percakapan:"
    markup = InlineKeyboardMarkup(keyboard)

    if update and getattr(update, "message", None):
        await update.message.reply_text(text, reply_markup=markup)
    elif update and getattr(update, "callback_query", None):
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif chat_id and context:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)

    if users[user_id].get("banned"):
        await safe_reply(update, "⚠️ Kamu telah diblokir admin dan tidak bisa menggunakan bot ini.")
        return ConversationHandler.END

    if users[user_id].get("verified"):
        if users[user_id].get("searching"):
            await safe_reply(update, "⏳ Kamu sedang mencari partner...\nGunakan /stop untuk membatalkan.")
        elif users[user_id].get("partner"):
            await safe_reply(update, "💬 Kamu sedang dalam percakapan anonim.\nGunakan /stop untuk mengakhiri.")
        else:
            await show_main_menu(update, context)
        return ConversationHandler.END

    # not verified -> start registration
    keyboard = [
        [InlineKeyboardButton("UNNES", callback_data="unnes")],
        [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")],
    ]
    await safe_reply(update, "👋 Selamat datang di Anonymous Kampus!\nPilih asal universitas kamu:", reply_markup=InlineKeyboardMarkup(keyboard))
    return UNIVERSITY


async def handle_university(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)
    users[user_id]["university"] = "UNNES" if query.data == "unnes" else "Non-UNNES"

    keyboard = [
        [InlineKeyboardButton("Laki-laki", callback_data="male")],
        [InlineKeyboardButton("Perempuan", callback_data="female")],
    ]
    await query.edit_message_text("🚻 Pilih gender kamu:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER


async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)
    users[user_id]["gender"] = "Laki-laki" if query.data == "male" else "Perempuan"

    await query.edit_message_text("🎂 Masukkan usia kamu (contoh: 21):")
    return AGE


async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    age_text = update.message.text.strip()
    if not age_text.isdigit():
        await safe_reply(update, "⚠️ Usia harus berupa angka. Coba lagi:")
        return AGE

    age = int(age_text)
    if age < 18 or age > 25:
        await safe_reply(update, "⚠️ Usia hanya diperbolehkan 18–25 tahun. Coba lagi:")
        return AGE

    users[user_id]["age"] = age
    await safe_reply(update, "📩 Data kamu sudah dikirim ke admin untuk diverifikasi. Tunggu ya!")
    await request_admin_verification(user_id, context)
    return ConversationHandler.END


# ---------------------------
# Profil user (diri sendiri)
# ---------------------------
async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    profil = users[user_id]

    if profil.get("banned"):
        status_text = "🚫 Diblokir Admin"
    elif profil.get("partner"):
        status_text = f"💬 Sedang ngobrol dengan User {profil['partner']}"
    elif profil.get("searching"):
        status_text = "🔎 Sedang mencari partner"
    else:
        status_text = "⏸️ Idle (tidak mencari / tidak ngobrol)"

    teks = "📝 **Profil Kamu (Detail)**\n"
    teks += f"🆔 User ID: `{user_id}`\n"
    teks += f"🏫 Universitas: {profil.get('university') or '-'}\n"
    teks += f"🚻 Gender: {profil.get('gender') or '-'}\n"
    teks += f"🎂 Usia: {profil.get('age') or '-'}\n"
    teks += f"📌 Status Aktivitas: {status_text}\n"
    teks += f"✅ Verifikasi: {'Sudah' if profil.get('verified') else 'Belum'}\n"
    teks += f"🚫 Banned: {'Ya' if profil.get('banned') else 'Tidak'}\n\n"
    teks += "🔒 Profil ini **hanya bisa kamu lihat sendiri**.\nIdentitasmu tetap **anonymous**."

    await safe_reply(update, teks, parse_mode="Markdown")


# ---------------------------
# Stop command (keluar pencarian/percakapan)
# ---------------------------
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    partner_id = users[user_id].get("partner")

    if partner_id:
        # inform partner
        try:
            await context.bot.send_message(chat_id=partner_id, text="❌ Partner keluar dari percakapan.")
        except:
            pass
        users[partner_id]["partner"] = None

    users[user_id]["partner"] = None
    users[user_id]["searching"] = False
    await safe_reply(update, "❌ Kamu keluar dari percakapan / pencarian partner.")


# ---------------------------
# Request admin verification (kirim ke semua admin)
# ---------------------------
async def request_admin_verification(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    # ensure user exists
    ensure_user(user_id)
    u = users[user_id]
    text = (
        f"🔔 Permintaan verifikasi baru!\n\n"
        f"👤 User ID: {user_id}\n"
        f"🏫 Universitas: {u.get('university')}\n"
        f"🚻 Gender: {u.get('gender')}\n"
        f"🎂 Usia: {u.get('age')}\n\n"
        "✅ Approve atau ❌ Reject?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")],
        [InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_{user_id}")],
        [InlineKeyboardButton("✅ Unban User", callback_data=f"unban_{user_id}")],
    ]

    for admin_id in ADMIN_IDS:
        try:
            print(f"DEBUG: Sending verification request to admin {admin_id}")
            await context.bot.send_message(admin_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            print(f"ERROR sending verification to {admin_id}: {e}")


# ---------------------------
# Report command - send log to admin
# ---------------------------
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    partner_id = users[user_id].get("partner")
    if not partner_id:
        await safe_reply(update, "⚠️ Kamu tidak sedang dalam percakapan anonim.")
        return

    # build log text from user's chat_logs (we saved symmetrical logs)
    log_text = "📑 Riwayat Chat Terakhir:\n\n"
    for sender, msg in chat_logs.get(user_id, []):
        prefix = "🟢 Kamu" if sender == "user" else "🔵 Partner"
        log_text += f"{prefix}: {msg}\n"

    for admin_id in ADMIN_IDS:
        keyboard = [
            [
                InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_{partner_id}"),
                InlineKeyboardButton("✅ Unban User", callback_data=f"unban_{partner_id}"),
            ]
        ]
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 LAPORAN USER!\n\nPelapor: {user_id}\nTerlapor: {partner_id}\n\n{log_text}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            print(f"ERROR send report to {admin_id}: {e}")

    await safe_reply(update, "📩 Laporan sudah dikirim ke admin. Terima kasih!")


# ---------------------------
# Admin: show user profile (helper)
# ---------------------------
async def show_user_profile(context: ContextTypes.DEFAULT_TYPE, chat_id: int, target_id: int):
    ensure_user(target_id)
    profil = users[target_id]

    if profil.get("banned"):
        status_text = "🚫 Diblokir Admin"
    elif profil.get("partner"):
        status_text = f"💬 Sedang ngobrol dengan User {profil['partner']}"
    elif profil.get("searching"):
        status_text = "🔎 Sedang mencari partner"
    else:
        status_text = "⏸️ Idle (tidak mencari / tidak ngobrol)"

    teks = "📝 **Profil User (Detail)**\n"
    teks += f"🆔 User ID: `{target_id}`\n"
    teks += f"🏫 Universitas: {profil.get('university') or '-'}\n"
    teks += f"🚻 Gender: {profil.get('gender') or '-'}\n"
    teks += f"🎂 Usia: {profil.get('age') or '-'}\n"
    teks += f"📌 Status Aktivitas: {status_text}\n"
    teks += f"✅ Verifikasi: {'Sudah' if profil.get('verified') else 'Belum'}\n"
    teks += f"🚫 Banned: {'Ya' if profil.get('banned') else 'Tidak'}\n"

    keyboard = [
        [InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{target_id}"),
         InlineKeyboardButton("✅ Unban", callback_data=f"unban_{target_id}")],
    ]

    await context.bot.send_message(chat_id, teks, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ---------------------------
# Admin panel - clickable lists
# ---------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return

    keyboard = [
        [InlineKeyboardButton("📋 Semua User", callback_data="list_users")],
        [InlineKeyboardButton("✅ Terverifikasi", callback_data="list_verified")],
        [InlineKeyboardButton("⏳ Belum Verif", callback_data="list_unverified")],
        [InlineKeyboardButton("🚫 Banned", callback_data="list_banned")],
    ]
    await safe_reply(update, "⚙️ Panel Admin:", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    admin_id = query.from_user.id

    if admin_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Kamu bukan admin.")
        return

    if action == "list_users":
        if not users:
            await query.edit_message_text("📋 Belum ada user terdaftar.")
            return
        keyboard = [[InlineKeyboardButton(f"User {uid}", callback_data=f"detail_{uid}")] for uid in users.keys()]
        await query.edit_message_text("📋 Semua User:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "list_verified":
        verified = [uid for uid, u in users.items() if u.get("verified")]
        if not verified:
            await query.edit_message_text("✅ Tidak ada user terverifikasi.")
            return
        keyboard = [[InlineKeyboardButton(f"User {uid}", callback_data=f"detail_{uid}")] for uid in verified]
        await query.edit_message_text("✅ User Terverifikasi:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "list_unverified":
        unver = [uid for uid, u in users.items() if not u.get("verified")]
        if not unver:
            await query.edit_message_text("⏳ Semua user sudah terverifikasi.")
            return
        keyboard = [[InlineKeyboardButton(f"User {uid}", callback_data=f"detail_{uid}")] for uid in unver]
        await query.edit_message_text("⏳ User Belum Verifikasi:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "list_banned":
        banned = [uid for uid, u in users.items() if u.get("banned")]
        if not banned:
            await query.edit_message_text("🚫 Tidak ada user banned.")
            return
        keyboard = [[InlineKeyboardButton(f"User {uid}", callback_data=f"detail_{uid}")] for uid in banned]
        await query.edit_message_text("🚫 User Banned:", reply_markup=InlineKeyboardMarkup(keyboard))


# ---------------------------
# Admin detail handler (click user)
# ---------------------------
async def admin_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id

    if admin_id not in ADMIN_IDS:
        await query.edit_message_text("❌ Kamu bukan admin.")
        return

    parts = query.data.split("_", 1)
    if len(parts) != 2:
        await query.edit_message_text("⚠️ Data tidak valid.")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await query.edit_message_text("⚠️ ID user tidak valid.")
        return

    await show_user_profile(context, admin_id, target_id)


# ---------------------------
# Admin button actions (approve/reject/ban/unban)
# Note: this handler accepts both verification buttons and ban/unban
# ---------------------------
async def admin_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 1)
    action = parts[0]

    if len(parts) != 2:
        await query.edit_message_text("❌ Data tidak valid.")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await query.edit_message_text("❌ ID user tidak valid.")
        return

    ensure_user(target_id)

    if action == "approve":
        users[target_id]["verified"] = True
        await query.edit_message_text(f"✅ User {target_id} diverifikasi.")
        try:
            await context.bot.send_message(target_id, "🎉 Profil kamu sudah diverifikasi!")
            await show_main_menu(context=context, chat_id=target_id)
        except:
            pass

    elif action == "reject":
        users[target_id]["verified"] = False
        await query.edit_message_text(f"❌ User {target_id} ditolak.")
        try:
            await context.bot.send_message(target_id, "⚠️ Verifikasi kamu ditolak. Silakan coba lagi.")
        except:
            pass

    elif action == "ban":
        users[target_id]["banned"] = True
        await query.edit_message_text(f"🚫 User {target_id} telah diblokir oleh admin.")
        try:
            await context.bot.send_message(target_id, "⚠️ Kamu telah diblokir oleh admin dan tidak bisa lagi menggunakan bot.")
        except:
            pass

    elif action == "unban":
        users[target_id]["banned"] = False
        await query.edit_message_text(f"✅ User {target_id} telah di-unban oleh admin.")
        try:
            await context.bot.send_message(target_id, "✅ Kamu sudah di-unban oleh admin. Silakan gunakan bot kembali.")
        except:
            pass


# ---------------------------
# Manual ban/unban commands
# ---------------------------
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return

    if not context.args:
        await safe_reply(update, "⚠️ Gunakan format: /ban <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "⚠️ User ID harus berupa angka.")
        return

    ensure_user(target_id)
    users[target_id]["banned"] = True
    await safe_reply(update, f"✅ User {target_id} berhasil diblokir.")
    try:
        await context.bot.send_message(target_id, "⚠️ Kamu telah diblokir oleh admin dan tidak bisa lagi menggunakan bot.")
    except:
        pass


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS:
        await safe_reply(update, "❌ Kamu bukan admin.")
        return

    if not context.args:
        await safe_reply(update, "⚠️ Gunakan format: /unban <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "⚠️ User ID harus berupa angka.")
        return

    ensure_user(target_id)
    users[target_id]["banned"] = False
    await safe_reply(update, f"✅ User {target_id} sudah di-unban.")
    try:
        await context.bot.send_message(target_id, "✅ Kamu sudah di-unban oleh admin. Silakan gunakan bot kembali.")
    except:
        pass


# ---------------------------
# Button handler for menu: find / cari_doi / ubah_profil / profil
# - also handles the searching logic and statistics display
# ---------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)

    # blocked check
    if users[user_id].get("banned"):
        await query.edit_message_text("⚠️ Kamu diblokir admin.")
        return

    action = query.data

    if action in ["find", "cari_doi"]:
        # prevent repeat clicking while searching
        if users[user_id].get("partner"):
            await query.edit_message_text("⚠️ Kamu sedang dalam percakapan. Gunakan /stop untuk keluar.")
            return
        if users[user_id].get("searching"):
            # still searching -> inform user
            total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
            total_searching = sum(1 for u in users.values() if u.get("searching") and u.get("verified") and not u.get("banned"))
            teks = (
                f"⏳ Kamu sudah mencari partner.\n\n"
                f"👥 User terverifikasi: {total_verified}\n"
                f"🟢 Sedang online/mencari: {total_searching}\n\n"
                f"Gunakan /stop untuk membatalkan."
            )
            await query.edit_message_text(teks)
            return

        # start searching (find partner)
        # only match against other verified & searching & not banned users
        candidates = [uid for uid, u in users.items()
                      if u.get("searching") and uid != user_id and u.get("verified") and not u.get("banned")]
        if candidates:
            partner_id = random.choice(candidates)
            users[user_id]["partner"] = partner_id
            users[partner_id]["partner"] = user_id
            users[user_id]["searching"] = False
            users[partner_id]["searching"] = False
            # notify both
            await context.bot.send_message(user_id, "💬 Partner ditemukan! Sekarang kamu bisa ngobrol anonim.")
            await context.bot.send_message(partner_id, "💬 Partner ditemukan! Sekarang kamu bisa ngobrol anonim.")
        else:
            users[user_id]["searching"] = True
            # stats
            total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
            total_searching = sum(1 for u in users.values() if u.get("searching") and u.get("verified") and not u.get("banned"))
            teks = (
                f"🔍 Sedang mencari partner...\n\n"
                f"👥 User terverifikasi: {total_verified}\n"
                f"🟢 Sedang online/mencari: {total_searching}\n\n"
                f"Gunakan /stop untuk membatalkan."
            )
            await query.edit_message_text(teks)

    elif action == "ubah_profil":
        # reset profile & re-run registration (requires admin re-verify)
        users[user_id].update({"verified": False, "university": None, "gender": None, "age": None})
        keyboard = [
            [InlineKeyboardButton("UNNES", callback_data="unnes")],
            [InlineKeyboardButton("Non-UNNES", callback_data="nonunnes")],
        ]
        await query.edit_message_text("✏️ Ubah profil kamu.\nPilih asal universitas:", reply_markup=InlineKeyboardMarkup(keyboard))
        return UNIVERSITY

    elif action == "profil":
        await profil(update, context)


# ---------------------------
# Relay chat between partners
# ---------------------------
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    partner_id = users[user_id].get("partner")

    if partner_id:
        msg = update.message.text
        save_chat(user_id, "user", msg)
        save_chat(partner_id, "partner", msg)
        try:
            await context.bot.send_message(chat_id=partner_id, text=msg)
        except Exception as e:
            print(f"ERROR sending relayed message: {e}")
    else:
        await safe_reply(update, "⚠️ Kamu tidak sedang dalam percakapan anonim.")


# ---------------------------
# Utility commands
# ---------------------------
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await safe_reply(update, f"🆔 User ID kamu: `{user_id}`", parse_mode="Markdown")


async def online_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show count or details of users currently searching.
       For regular users show counts only; for admin show details."""
    user_id = update.effective_user.id
    total_verified = sum(1 for u in users.values() if u.get("verified") and not u.get("banned"))
    searching_verified = [uid for uid, u in users.items() if u.get("searching") and u.get("verified") and not u.get("banned")]

    if user_id in ADMIN_IDS:
        if not searching_verified:
            await safe_reply(update, "📭 Tidak ada user terverifikasi yang sedang mencari partner.")
            return
        teks = "🟢 User terverifikasi yang sedang mencari:\n\n"
        for uid in searching_verified:
            u = users[uid]
            teks += f"- `{uid}` | {u.get('gender') or '?'} | {u.get('age') or '?'} tahun\n"
        teks += f"\n👥 Total verified: {total_verified}\n🟢 Sedang mencari: {len(searching_verified)}"
        await safe_reply(update, teks, parse_mode="Markdown")
    else:
        teks = f"👥 User terverifikasi: {total_verified}\n🟢 Sedang online/mencari: {len(searching_verified)}"
        await safe_reply(update, teks)


# ---------------------------
# Main: register handlers and run
# ---------------------------
def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    app = ApplicationBuilder().token(TOKEN).build()

    # Conversation for registration
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            UNIVERSITY: [CallbackQueryHandler(handle_university, pattern="^(unnes|nonunnes)$")],
            GENDER: [CallbackQueryHandler(handle_gender, pattern="^(male|female)$")],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    # Add handlers
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("adminpanel", admin_panel))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("online", online_cmd))

    # Callbacks
    app.add_handler(CallbackQueryHandler(admin_action_handler, pattern="^(approve|reject|ban|unban)_"))
    app.add_handler(CallbackQueryHandler(admin_panel_handler, pattern="^(list_users|list_verified|list_unverified|list_banned)$"))
    app.add_handler(CallbackQueryHandler(admin_detail_handler, pattern="^detail_"))
    app.add_handler(CallbackQueryHandler(button_handler))  # catch-all for menu buttons

    # Relay chat messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, relay_message))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
