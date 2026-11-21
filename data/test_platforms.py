import subprocess
import json

test_urls = {
    "YouTube Video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "YouTube Shorts": "https://www.youtube.com/shorts/kJQP7kiw5Fk",
}

for name, url in test_urls.items():
    print(f"\n[Testing {name}] {url}")
    cmd = [
        "yt-dlp",
        "--impersonate", "chrome",
        "--skip-download",
        "--print", "%(title)s (%(resolution)s)",
        url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            print(f" -> SUCCESS: {res.stdout.strip()}")
        else:
            print(f" -> FAILED: {res.stderr.strip()[:200]}")
    except Exception as e:
        print(f" -> ERROR: {e}")
