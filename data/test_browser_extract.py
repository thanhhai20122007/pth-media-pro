import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright
from core.config import BROWSER_DATA_DIR

def extract_video_with_browser(url):
    print(f"\n[BrowserExtractor] Testing: {url}")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox'],
            viewport={'width': 1280, 'height': 800}
        )
        page = context.pages[0] if context.pages else context.new_page()
        video_urls = []
        page.on('response', lambda res: video_urls.append(res.url) if ('video' in res.headers.get('content-type', '') or '.mp4' in res.url) and 'blob:' not in res.url else None)
        
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(3000)
            
            og_v = None
            if page.locator('meta[property="og:video"]').count() > 0:
                og_v = page.locator('meta[property="og:video"]').first.get_attribute('content')
            elif page.locator('meta[property="og:video:secure_url"]').count() > 0:
                og_v = page.locator('meta[property="og:video:secure_url"]').first.get_attribute('content')
                
            tag_v = None
            if page.locator('video').count() > 0:
                tag_v = page.locator('video').first.get_attribute('src')
                
            title = page.title()
            print('Title:', title)
            print('og:video:', og_v[:80] if og_v else 'None')
            print('tag video:', tag_v[:80] if tag_v else 'None')
            print('Captured network streams:', len(video_urls))
            for u in video_urls[:3]:
                print(' ->', u[:80])
                
            best_video = og_v or tag_v or (video_urls[0] if video_urls else None)
            return best_video
        except Exception as e:
            print('Browser error:', e)
            return None
        finally:
            context.close()

if __name__ == '__main__':
    extract_video_with_browser('https://www.facebook.com/watch/?v=10153231379946729')
