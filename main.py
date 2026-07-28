import os
import requests
import feedparser
from google import genai

# Lấy biến môi trường khớp chính xác với tên Secret
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN_BOT")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI")

# Khởi tạo client Gemini theo chuẩn thư viện mới
client = genai.Client(api_key=GEMINI_API_KEY)

def send_telegram(text):
    """Gửi tin nhắn về Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": text, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

def get_github_trending():
    """Lấy dự án GitHub tăng sao nhanh"""
    url = "https://api.github.com/search/repositories?q=created:>2026-07-01&sort=stars&order=desc&per_page=5"
    response = requests.get(url).json()
    items = response.get("items", [])
    
    result = "🔥 **DỰ ÁN GITHUB TRENDING:**\n"
    for item in items:
        desc = item.get('description') or 'Không có mô tả'
        result += f"- [{item['name']}]({item['html_url']}): ⭐ {item['stargazers_count']} stars - {desc}\n"
    return result

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
    print("Đang cào dữ liệu...")
    news_data = get_news_feeds()
    github_data = get_github_trending()
    
    raw_content = f"Dữ liệu tin tức:\n{news_data}\n\nDữ liệu GitHub:\n{github_data}"
    
    prompt = f"""
    Bạn là trợ lý tổng hợp tin tức chuyên nghiệp. Dưới đây là dữ liệu thu thập được:
    
    {raw_content}
    
    Hãy lọc ra những thông tin quan trọng nhất, tóm tắt ngắn gọn thành một bản tin bằng Tiếng Việt.
    Định dạng tin nhắn đẹp mắt để gửi qua Telegram (dùng icon, gạch đầu dòng ngắn gọn, giữ lại link).
    """
    
   # Đổi sang mô hình Flash siêu tốc, không bị lỗi 404
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents=prompt
    )
    summary = response.text
    
    send_telegram(summary)
    print("Đã gửi báo cáo thành công!")

if __name__ == "__main__":
    run()
