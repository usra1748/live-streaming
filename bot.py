import os
import json
import asyncio
import threading
from livestream import is_streaming
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from functools import wraps
from livestream import start_streaming, stop_streaming, schedule_stop, set_notifier

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def load_streaming():
    if not os.path.exists("streaming.json"):
        return {}
    with open("streaming.json", "r") as f:
        return json.load(f)

def save_streaming(data):
    with open("streaming.json", "w") as f:
        json.dump(data, f, indent=2)

config = load_config()
TELEGRAM_TOKEN = config["telegram_token"]
ADMIN_IDS = config.get("admin_ids", [])

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            if update.message:
                await update.message.reply_text("🚫 Kamu tidak memiliki izin untuk menggunakan bot ini.")
            elif update.callback_query:
                await update.callback_query.answer("🚫 Tidak diizinkan.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def send_status(user_id, message, context):
    try:
        await context.bot.send_message(chat_id=user_id, text=message)
    except Exception as e:
        print(f"[ERROR] Gagal kirim pesan ke Telegram: {e}")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📤 Upload Video", callback_data='upload')],
        [InlineKeyboardButton("⚙️ Set RTMP", callback_data='set_rtmp')],
        [InlineKeyboardButton("🔑 Input Stream Key", callback_data='set_key')],
        [InlineKeyboardButton("🎞 Pilih Video", callback_data='choose_video')],
        [InlineKeyboardButton("🎚 Set Resolusi", callback_data='set_resolution')],
        [InlineKeyboardButton("📱 Mode Live (Portrait/Landscape)", callback_data='set_mode')],
        [InlineKeyboardButton("🔁 Auto Looping", callback_data='toggle_looping')],
        [InlineKeyboardButton("▶️ Start Live", callback_data='start_live')],
        [InlineKeyboardButton("⏹ Stop Live", callback_data='stop_live')],
        [InlineKeyboardButton("🕐 Jadwal Stop", callback_data='schedule_stop')],
        [InlineKeyboardButton("🗑 Hapus Video", callback_data='delete_video')],
        [InlineKeyboardButton("📋 Show Configure", callback_data='show_config')],
        [InlineKeyboardButton("📡 Cek Status Live", callback_data='check_status')]
    ]
    message = "❗️BOT CREATOR : BENY - SHARE IT HUB"
    if update.callback_query:
        await update.callback_query.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)

@admin_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    s = load_streaming()
    user_id = query.from_user.id

    if data == "upload":
        await query.edit_message_text("Silakan kirim file video ke bot.")

    elif data == "set_rtmp":
        keyboard = [
            [InlineKeyboardButton("YouTube", callback_data='rtmp_youtube')],
            [InlineKeyboardButton("Facebook", callback_data='rtmp_facebook')]
        ]
        await query.edit_message_text("Pilih platform RTMP:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "rtmp_youtube":
        s["rtmp_url"] = "rtmp://a.rtmp.youtube.com/live2"
        save_streaming(s)
        await query.edit_message_text("✅ RTMP diatur ke YouTube.")
        await show_main_menu(update, context)

    elif data == "rtmp_facebook":
        s["rtmp_url"] = "rtmps://live-api-s.facebook.com:443/rtmp/"
        save_streaming(s)
        await query.edit_message_text("✅ RTMP diatur ke Facebook.")
        await show_main_menu(update, context)

    elif data == "set_key":
        context.user_data["awaiting_key"] = True
        await query.edit_message_text("Kirim stream key Anda:")

    elif data == "choose_video":
        files = [f for f in os.listdir("videos") if f.endswith((".mp4", ".mkv", ".mov"))]
        if files:
            keyboard = [[InlineKeyboardButton(f, callback_data=f"video_{f}")] for f in files]
            await query.edit_message_text("Pilih video:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ Tidak ada video di folder /videos.")
            await show_main_menu(update, context)

    elif data.startswith("video_"):
        filename = data.split("video_")[1]
        s["video_path"] = os.path.join("videos", filename)
        save_streaming(s)
        await query.edit_message_text(f"✅ Video dipilih: {filename}")
        await show_main_menu(update, context)

    elif data == "set_resolution":
        keyboard = [
            [InlineKeyboardButton("1080p60", callback_data='res_1080p60')],
            [InlineKeyboardButton("720p60", callback_data='res_720p60')],
            [InlineKeyboardButton("480p", callback_data='res_480p')],
        ]
        await query.edit_message_text("Pilih resolusi:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("res_"):
        res = data.split("res_")[1]
        s["resolution"] = res
        save_streaming(s)
        await query.edit_message_text(f"✅ Resolusi diatur: {res}")
        await show_main_menu(update, context)

    elif data == "set_mode":
        keyboard = [
            [InlineKeyboardButton("📲 Portrait", callback_data='mode_portrait')],
            [InlineKeyboardButton("🖥 Landscape", callback_data='mode_landscape')],
        ]
        await query.edit_message_text("Pilih mode live streaming:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "mode_portrait":
        s["mode"] = "portrait"
        save_streaming(s)
        await query.edit_message_text("✅ Mode diatur ke *Portrait* (Vertikal)")
        await show_main_menu(update, context)

    elif data == "mode_landscape":
        s["mode"] = "landscape"
        save_streaming(s)
        await query.edit_message_text("✅ Mode diatur ke *Landscape* (Horizontal)")
        await show_main_menu(update, context)

    elif data == "toggle_looping":
        looping = s.get("looping", False)
        s["looping"] = not looping
        save_streaming(s)
        status = "✅ Auto Looping *AKTIF*" if s["looping"] else "❌ Auto Looping *NONAKTIF*"
        await query.edit_message_text(status, parse_mode="Markdown")
        await show_main_menu(update, context)

    elif data == "start_live":
        missing = []
        if not s.get("video_path") or not os.path.exists(s["video_path"]):
            missing.append("🎞 Video")
        if not s.get("rtmp_url"):
            missing.append("📡 RTMP")
        if not s.get("stream_key"):
            missing.append("🔑 Stream Key")
        if not s.get("resolution"):
            missing.append("🎚 Resolusi")
        if not s.get("mode"):
            missing.append("📱 Mode Live")

        if missing:
            await query.edit_message_text(f"❌ Konfigurasi berikut belum lengkap:\n\n" + "\n".join(missing))
        else:
            await query.edit_message_text("▶️ Memulai streaming...")
            set_notifier(lambda uid, msg: send_status(uid, msg, context), user_id)

            # Jalankan streaming di thread non-blocking
            threading.Thread(target=lambda: asyncio.run(start_streaming()), daemon=True).start()

    elif data == "stop_live":
        await query.edit_message_text("⏹ Menghentikan streaming...")
        await stop_streaming()
        await show_main_menu(update, context)

    elif data == "schedule_stop":
        context.user_data["awaiting_schedule"] = True
        await query.edit_message_text("Kirim waktu (menit) untuk menghentikan streaming:")

    elif data == "delete_video":
        files = [f for f in os.listdir("videos") if f.endswith((".mp4", ".mkv", ".mov"))]
        if files:
            keyboard = [[InlineKeyboardButton(f"🗑 {f}", callback_data=f"del_{f}")] for f in files]
            await query.edit_message_text("Pilih video yang ingin dihapus:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ Tidak ada video di folder /videos.")
            await show_main_menu(update, context)

    elif data.startswith("del_"):
        filename = data.split("del_")[1]
        filepath = os.path.join("videos", filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            await query.edit_message_text(f"🗑 Video {filename} berhasil dihapus.")
        else:
            await query.edit_message_text(f"❌ File {filename} tidak ditemukan.")
        await show_main_menu(update, context)

    elif data == "show_config":
        config_text = (
            f"🎞 Video: {s.get('video_path', '❌ Belum dipilih')}\n"
            f"🔗 RTMP: {s.get('rtmp_url', '❌ Belum diatur')}\n"
            f"🔑 Stream Key: {s.get('stream_key', '❌ Belum diatur')}\n"
            f"📏 Resolusi: {s.get('resolution', '❌ Belum diatur')}\n"
            f"📱 Mode: {s.get('mode', '❌ Belum diatur')}\n"
            f"🔁 Auto Looping: {'AKTIF' if s.get('looping', False) else 'NONAKTIF'}"
        )
        await query.edit_message_text(f"📋 Konfigurasi Saat Ini:\n{config_text}")
        await show_main_menu(update, context)

    elif data == "check_status":
        if os.path.exists("streaming.json"):
            s = load_streaming()
            live_status = "✅ ONLINE" if is_streaming() else "🔴 OFFLINE"
            status_text = (
                f"Live Streaming Status\n"
                f"{live_status}\n\n"
                f"Platform: {s.get('rtmp_url', '-')}\n"
                f"Video: {os.path.basename(s.get('video_path', '-')) if s.get('video_path') else '-'}\n"
                f"Resolution: {s.get('resolution', '-')}\n"
                f"Mode: {s.get('mode', '-')}\n"
                f"Looping: {'Aktif' if s.get('looping', False) else 'Nonaktif'}\n"
            )
            await query.edit_message_text(status_text)
        else:
            await query.edit_message_text("❌ Belum ada konfigurasi streaming ditemukan.")


@admin_only
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = load_streaming()

    if context.user_data.get("awaiting_key"):
        s["stream_key"] = update.message.text.strip()
        save_streaming(s)
        context.user_data["awaiting_key"] = False
        await update.message.reply_text("✅ Stream key disimpan.")
        await show_main_menu(update, context)

    elif context.user_data.get("awaiting_schedule"):
        try:
            minutes = int(update.message.text)
            await update.message.reply_text(f"✅ Streaming akan dihentikan dalam {minutes} menit.")
            asyncio.create_task(schedule_stop(minutes * 60))
        except ValueError:
            await update.message.reply_text("❌ Masukkan angka yang benar.")
        context.user_data["awaiting_schedule"] = False
        await show_main_menu(update, context)

    elif update.message.video or update.message.document:
        file = update.message.video or update.message.document
        os.makedirs("videos", exist_ok=True)
        file_path = f"videos/{file.file_name}"
        telegram_file = await file.get_file()
        await telegram_file.download_to_drive(file_path)
        await update.message.reply_text(f"✅ Video diunggah: {file.file_name}")
        await show_main_menu(update, context)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
