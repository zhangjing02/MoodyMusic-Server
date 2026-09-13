import os, sys, time, requests

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_UPLOAD_URL = 'https://m-api.changgepd.ccwu.cc/api/admin/assets/upload'
PROXIES = {
    'http': 'http://127.0.0.1:7897',
    'https': 'http://127.0.0.1:7897'
}

SCENES = [
    "karen_street_acoustic",
    "karen_midnight_cafe",
    "karen_candle_devotion",
    "karen_worship_jazz",
    "karen_mountain_chapel",
    "karen_peaceful_rest",
    "karen_morning_grace",
    "karen_rainy_night"
]

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VIDEO_DIR = os.path.join(WORKSPACE, "backend", "frontend", "src", "assets", "video")
IMAGE_DIR = os.path.join(WORKSPACE, "backend", "frontend", "src", "assets", "images")

items_to_upload = []
for s in SCENES:
    items_to_upload.append((os.path.join(VIDEO_DIR, f"{s}.mp4"), f"{s}.mp4", "video/mp4"))
    items_to_upload.append((os.path.join(VIDEO_DIR, f"{s}.webm"), f"{s}.webm", "video/webm"))
    items_to_upload.append((os.path.join(IMAGE_DIR, f"{s}.jpg"), f"{s}.jpg", "image/jpeg"))

print(f"Total items to upload: {len(items_to_upload)}", flush=True)
success_count = 0

for filepath, filename, mime in items_to_upload:
    if not os.path.exists(filepath):
        print(f"[MISSING] {filepath}", flush=True)
        continue
    size = os.path.getsize(filepath)
    print(f"Uploading {filename} ({size / 1024 / 1024:.2f} MB)...", end='', flush=True)
    uploaded = False
    for attempt in range(1, 4):
        try:
            with open(filepath, 'rb') as f:
                resp = requests.post(
                    API_UPLOAD_URL,
                    files={'file': (filename, f, mime)},
                    data={'category': 'ambient', 'filename': filename},
                    proxies=PROXIES,
                    timeout=180
                )
            if resp.status_code == 200:
                print(f" -> OK (200)", flush=True)
                success_count += 1
                uploaded = True
                break
            else:
                print(f" -> ERROR {resp.status_code}", flush=True)
        except Exception as e:
            print(f" -> RETRY {attempt} ({e})", flush=True)
            time.sleep(2)

print(f"\nUpload complete! Successfully uploaded {success_count} / {len(items_to_upload)} files.", flush=True)
