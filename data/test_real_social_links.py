import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.downloader import download_video_smart

test_suite = [
    {
        "platform": "Threads Share Link (Ảnh người dùng)",
        "url": "https://www.threads.com/share/BAXQgoYm98",
        "format": "video"
    },
    {
        "platform": "Threads Post Chuẩn",
        "url": "https://www.threads.net/@kfury/post/DaGcWDwj8tW",
        "format": "video"
    },
    {
        "platform": "TikTok Video (Không logo)",
        "url": "https://www.tiktok.com/@tiktok/video/7710348513128828191",
        "format": "video"
    },
    {
        "platform": "YouTube Shorts",
        "url": "https://www.youtube.com/shorts/kJQP7kiw5Fk",
        "format": "video"
    },
    {
        "platform": "Facebook Reel",
        "url": "https://www.facebook.com/reel/10153231379946729",
        "format": "video"
    }
]

print("=" * 80)
print("     BẮT ĐẦU TEST THỰC TẾ CÁC NỀN TẢNG MXH CHO OMNIVIDEO PRO")
print("=" * 80)

results = []

for idx, item in enumerate(test_suite, start=101):
    plat = item["platform"]
    url = item["url"]
    print(f"\n[{idx}] Đang test {plat}...")
    print(f"    URL: {url}")
    
    def on_prog(pct, spd):
        pass

    try:
        res = download_video_smart(url, task_id=idx, format_type="video", progress_callback=on_prog)
        f_path = res.get("file_path", "")
        f_size = os.path.getsize(f_path) if f_path and os.path.exists(f_path) else 0
        f_size_mb = f_size / (1024 * 1024)
        print(f" -> THÀNH CÔNG!")
        print(f"    Tiêu đề: {res.get('title', '')[:50]}")
        print(f"    Tệp: {os.path.basename(f_path)} ({f_size_mb:.2f} MB)")
        results.append((plat, True, f"{f_size_mb:.2f} MB"))
    except Exception as e:
        print(f" -> THẤT BẠI: {e}")
        results.append((plat, False, str(e)[:60]))

print("\n" + "=" * 80)
print("                    KẾT QUẢ TỔNG HỢP KIỂM THỬ")
print("=" * 80)
for plat, ok, detail in results:
    status_icon = "✅ THÀNH CÔNG" if ok else "❌ THẤT BẠI"
    print(f"{plat:<30} | {status_icon:<14} | {detail}")
print("=" * 80)
