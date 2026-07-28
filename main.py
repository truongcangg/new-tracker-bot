import os
import time
import requests
import feedparser
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
from google import genai

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN_BOT")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI")

client = genai.Client(api_key=GEMINI_API_KEY)

def send_telegram_photo(photo_path, caption):
    """Gửi ảnh biểu đồ và kèm nội dung chữ về Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    if len(caption) > 1000:
        caption = caption[:1000] + "..."
        
    with open(photo_path, 'rb') as photo:
        files = {'photo': photo}
        data = {
            "chat_id": TELEGRAM_CHAT_ID, 
            "caption": caption, 
            "parse_mode": "Markdown"
        }
        requests.post(url, data=data, files=files)

def get_github_trending():
    """Cào Top 10 dự án GitHub Trending tăng trưởng nhanh nhất trong 24h"""
    url = "https://github.com/trending"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    repos = []
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select('article.Box-row')
            
            for row in rows[:10]:
                # Lấy tên dự án
                title_elem = row.select_one('h2 a')
                if not title_elem:
                    continue
                name = "".join(title_elem.text.split()) # Xóa khoảng trắng thừa
                
                # Lấy số sao tăng trong ngày (24h)
                stars_today = 0
                for span in row.find_all('span'):
                    text = span.get_text()
                    if 'stars today' in text or 'star today' in text:
                        num_str = "".join(filter(str.isdigit, text))
                        if num_str:
                            stars_today = int(num_str)
                        break
                
                repos.append({'name': name, 'stars': stars_today})
    except Exception as e:
        print(f"Lỗi cào GitHub Trending: {e}")
        
    # Nếu cào lỗi hoặc trống, tạo dữ liệu giả lập để không bị lỗi vẽ biểu đồ
    if not repos:
        repos = [{'name': 'Placeholder/Repo', 'stars': 100}]
        
    return repos

def draw_chart(repos):
    """Vẽ biểu đồ Top 10 dự án và lưu thành file ảnh chart.png"""
    names = [r['name'].split('/')[-1] for r in repos]
    stars = [r['stars'] for r in repos]
    
    # Đảo ngược lại để hiển thị tháp từ trên xuống dưới cho đẹp mắt
    names.reverse()
    stars.reverse()
    
    plt.figure(figsize=(10, 6))
    plt.barh(names, stars, color='#2ea44f')
    plt.xlabel('Stars Gained Today (24h)', fontsize=12, fontweight='bold')
    plt.title('🔥 Top 10 GitHub Trending Fast-Growing Projects', fontsize=14, fontweight='bold', color='#1f2328')
    plt.grid(axis='x', linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    # Lưu file ảnh
    plt.savefig('chart.png', dpi=300)
    plt.close()

def get_news_feeds():
    """Lấy tin tức từ RSS"""
    rss_urls = [
        "https://vnexpress.net/rss/tin-moi-nhat.rss",
        "https://tuoitre.vn/rss/tin-moi-nhat.rss"
    ]
    articles = []
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            summary = getattr(entry, 'summary', '')
            articles.append(f"Tiêu đề: {entry.title}\nLink: {entry.link}\nTóm tắt: {summary}\n---")
    return "\n".join(articles)

def run():
    print("Đang cào dữ liệu GitHub Trending và Tin tức...")
    repos = get_github_trending()
    news_data = get_news_feeds()
    
    # Vẽ biểu đồ từ dữ liệu GitHub
    draw_chart(repos)
    
    # Chuẩn bị nội dung chữ tóm tắt
    github_text = "🔥 **TOP 10 DỰ ÁN GITHUB TĂNG TRƯỞNG NHANH NHẤT (24H):**\n"
    for idx, r in enumerate(repos, 1):
        github_text += f"{idx}. `{r['name']}` (+{r['stars']} stars)\n"
        
    raw_content = f"{github_text}\n\nDữ liệu báo chí:\n{news_data}"
    
    prompt = f"""
    Bạn là trợ lý tổng hợp thông tin chuyên nghiệp. Dưới đây là dữ liệu Top 10 GitHub Trending và tin tức mới nhất:
    
    {raw_content}
    
    Hãy viết một bản tin ngắn gọn, súc tích bằng Tiếng Việt để gửi kèm theo hình ảnh biểu đồ.
    """
    
    summary = ""
    for attempt in range(3):
        try:
            print(f"Đang gọi Gemini tạo bản tin (Lần thử {attempt + 1}/3)...")
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt
            )
            summary = response.text
            break
        except Exception as e:
            print(f"Lỗi AI: {e}")
            if attempt < 2:
                time.sleep(15)
            else:
                summary = f"📊 Biểu đồ Top 10 GitHub Trending và Tin tức cập nhật lúc này."
    
    # Gửi ảnh kèm nội dung về Telegram
    send_telegram_photo('chart.png', summary)
    print("Đã gửi ảnh biểu đồ và bản tin về Telegram thành công!")

if __name__ == "__main__":
    run()
