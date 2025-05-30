import subprocess, json, asyncio, signal, time, os
import shutil
import platform
import psutil

CONFIG_FILE = 'streaming.json'
ffmpeg_process = None
MAX_RETRIES = 3
streaming_active = False

send_status_message = None
current_user_id = None

def set_notifier(notifier_func, user_id):
    global send_status_message, current_user_id
    send_status_message = notifier_func
    current_user_id = user_id

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"[ERROR] Config file '{CONFIG_FILE}' tidak ditemukan.")
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def find_ffmpeg():
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        print(f"[INFO] ffmpeg ditemukan di PATH sistem: {ffmpeg_in_path}")
        return ffmpeg_in_path

    root_dir = os.path.dirname(os.path.abspath(__file__))
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.lower() in ("ffmpeg", "ffmpeg.exe"):
                full_path = os.path.join(dirpath, filename)
                print(f"[INFO] ffmpeg ditemukan di lokal folder: {full_path}")
                return full_path

    raise FileNotFoundError(
        "[ERROR] ffmpeg executable tidak ditemukan.\n"
        "Pastikan ffmpeg tersedia di PATH atau folder lokal project."
    )

def find_first_video(base_dir='videos'):
    supported_ext = ('.mp4', '.mkv', '.mov', '.avi', '.flv', '.webm')
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith(supported_ext):
                return os.path.join(root, file)
    return None

YOUTUBE_PRESET = {
    "480p": {
        "resolution": "854x480", "fps": "60",
        "video_bitrate": "1500k", "audio_bitrate": "128k",
        "maxrate": "2000k", "bufsize": "4000k"
    },
    "720p60": {
        "resolution": "1280x720", "fps": "60",
        "video_bitrate": "4500k", "audio_bitrate": "192k",
        "maxrate": "6000k", "bufsize": "12000k"
    },
    "1080p60": {
        "resolution": "1920x1080", "fps": "60",
        "video_bitrate": "9000k", "audio_bitrate": "192k",
        "maxrate": "12000k", "bufsize": "24000k"
    }
}

def adjust_resolution_for_mode(resolution: str, mode: str) -> str:
    if mode == "portrait":
        width, height = resolution.split("x")
        return f"{height}x{width}"
    return resolution

async def start_streaming():
    global ffmpeg_process, streaming_active
    streaming_active = True

    try:
        config = load_config()
        ffmpeg_path = find_ffmpeg()
    except Exception as e:
        print(str(e))
        if send_status_message:
            asyncio.create_task(send_status_message(current_user_id, f"🚫 Gagal memulai live: {str(e)}"))
        return

    url = f"{config['rtmp_url']}/{config['stream_key']}"
    quality = config.get("resolution", "720p60")
    input_file = config.get("video_path")
    mode = config.get("mode", "landscape")
    looping = config.get("looping", False)

    if not input_file:
        input_file = find_first_video()
        if input_file:
            print(f"[INFO] File video ditemukan otomatis: {input_file}")
        else:
            error_msg = "[ERROR] Tidak ditemukan file video di folder videos."
            print(error_msg)
            if send_status_message:
                asyncio.create_task(send_status_message(current_user_id, f"🚫 {error_msg}"))
            return

    if not os.path.exists(input_file):
        error_msg = f"[ERROR] File video tidak ditemukan: {input_file}"
        print(error_msg)
        if send_status_message:
            asyncio.create_task(send_status_message(current_user_id, f"🚫 {error_msg}"))
        return

    preset = YOUTUBE_PRESET.get(quality, YOUTUBE_PRESET["720p60"])
    final_resolution = adjust_resolution_for_mode(preset["resolution"], mode)

    while streaming_active:
        retries = 0
        while retries <= MAX_RETRIES and streaming_active:
            print(f"[INFO] Starting stream in {mode.upper()} mode... Attempt {retries + 1}/{MAX_RETRIES + 1}")
            cmd = [
                ffmpeg_path, "-re", "-stream_loop", "-1" if looping else "0", "-i", input_file,
                "-s", final_resolution,
                "-r", preset["fps"],
                "-c:v", "libx264", "-preset", "veryfast",
                "-b:v", preset["video_bitrate"],
                "-maxrate", preset["maxrate"],
                "-bufsize", preset["bufsize"],
                "-c:a", "aac", "-b:a", preset["audio_bitrate"],
                "-f", "flv", url
            ]

            try:
                ffmpeg_process = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    bufsize=1
                )
                print("[INFO] FFmpeg started.")

                with open("ffmpeg.lock", "w") as f:
                    f.write("live")

                if send_status_message and retries == 0:
                    asyncio.create_task(send_status_message(current_user_id, "✅ Live berhasil dimulai!"))

                while streaming_active:
                    if ffmpeg_process.poll() is not None:
                        break
                    line = ffmpeg_process.stderr.readline()
                    if line:
                        print("[FFMPEG]", line.decode(errors="ignore").strip())

                returncode = ffmpeg_process.returncode
                if returncode != 0:
                    print(f"[WARN] FFmpeg exited with code {returncode}")
                    retries += 1
                    time.sleep(3)
                else:
                    print("[INFO] Streaming ended normally.")
                    break

            except Exception as e:
                print(f"[ERROR] Gagal menjalankan FFmpeg: {e}")
                if send_status_message:
                    asyncio.create_task(send_status_message(current_user_id, f"🚫 Error FFmpeg: {str(e)}"))
                break

        if not looping or not streaming_active:
            break

    if os.path.exists("ffmpeg.lock"):
        os.remove("ffmpeg.lock")

    if retries > MAX_RETRIES and send_status_message:
        asyncio.create_task(send_status_message(current_user_id, "🚫 Gagal menjalankan live setelah beberapa percobaan."))

async def stop_streaming():
    global ffmpeg_process, streaming_active
    streaming_active = False
    if ffmpeg_process:
        print("[INFO] Stopping stream...")

        try:
            if platform.system() == "Windows":
                ffmpeg_process.terminate()
            else:
                ffmpeg_process.send_signal(signal.SIGINT)

            ffmpeg_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()

        ffmpeg_process = None

        if os.path.exists("ffmpeg.lock"):
            os.remove("ffmpeg.lock")

        print("[INFO] Stream stopped.")
        if send_status_message:
            await send_status_message(current_user_id, "🛑 Live streaming dihentikan.")

async def schedule_stop(delay_seconds):
    print(f"[INFO] Scheduling stop in {delay_seconds} seconds...")
    await asyncio.sleep(delay_seconds)
    await stop_streaming()

def is_streaming():
    """Cek apakah proses FFmpeg sedang berjalan di sistem."""
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'ffmpeg' in proc.info['name'].lower():
            return True
    return False
