import os
import time
import requests
import feedparser
from google import genai

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN_BOT")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI")

client = genai.Client(api_key=GEMINI_API_KEY)

def send_telegram(text):
    """Gửi tin nhắn về Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Cắt ngắn văn bản nếu quá dài (Telegram giới hạn 4096 ký tự/tin nhắn)
    if len(text) > 4000:
        text = text[:4000] + "\n... (Văn bản đã được cắt ngắn)"
        
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": text, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def get_github_trending():
    url = "https://api.github.com/search/repositories?q=created:>2026-07-01&sort=stars&order=desc&per_page=5"
    response = requests.get(url).json()
    items = response.get("items", [])
    
    result = "🔥 **DỰ ÁN GITHUB TRENDING:**\n"
    for item in items:
        desc = item.get('description') or 'Không có mô tả'
        result += f"- [{item['name']}]({item['html_url']}): ⭐ {item['stargazers_count']} stars - {desc}\n"
    return result

def get_news_feeds():
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
    print("Đang cào dữ liệu báo chí và GitHub...")
    news_data = get_news_feeds()
    github_data = get_github_trending()
    
    raw_content = f"Dữ liệu tin tức:\n{news_data}\n\nDữ liệu GitHub:\n{github_data}"
    
    prompt = f"""
    Bạn là trợ lý tổng hợp tin tức chuyên nghiệp. Dưới đây là dữ liệu thu thập được:
    
    {raw_content}
    
    Hãy lọc ra những thông tin quan trọng nhất, tóm tắt ngắn gọn thành một bản tin bằng Tiếng Việt.
    Định dạng tin nhắn đẹp mắt để gửi qua Telegram (dùng icon, gạch đầu dòng ngắn gọn, giữ lại link).
    """
    
    summary = ""
    # CƠ CHẾ DỰ PHÒNG: Thử gọi API tối đa 3 lần
    for attempt in range(3):
        try:
            print(f"Đang nhờ Gemini tóm tắt (Lần thử {attempt + 1}/3)...")
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt
            )
            summary = response.text
            print("AI tóm tắt thành công!")
            break # Thành công thì thoát khỏi vòng lặp thử lại
            
        except Exception as e:
            print(f"Lỗi API ở lần thử {attempt + 1}: {e}")
            if attempt < 2:
                print("Hệ thống Google đang bận. Chờ 15 giây rồi thử lại...")
                time.sleep(15)
            else:
                print("Máy chủ Google quá tải hoàn toàn. Kích hoạt gửi dữ liệu gốc dự phòng.")
                summary = f"⚠️ *Hệ thống AI tóm tắt đang kẹt mạng. Bot gửi bạn tin tức gốc để không lỡ thông tin:*\n\n{raw_content}"
    
    send_telegram(summary)
    print("Đã gửi tin nhắn về Telegram hoàn tất!")

if __name__ == "__main__":
    run()
