import os
import requests
import feedparser
from google import genai

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN_BOT")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI")

client = genai.Client(api_key=GEMINI_API_KEY)

def send_telegram(text):
    """Gửi tin nhắn về Telegram và in ra phản hồi"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": text, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    # Yêu cầu in ra chính xác phản hồi từ máy chủ Telegram
    response = requests.post(url, json=payload)
    print("Phản hồi từ Telegram:", response.text)

def get_github_trending():
    url = "https://api.github.com/search/repositories?q=created:>2026-07-01&sort=stars&order=desc&per_page=5"
    response = requests.get(url).json()
    items = response.get("items", [])
    
    result = "🔥 **DỰ ÁN GITHUB TRENDING BỔ SUNG:**\n"
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
    
    response = client.models.generate_content(
        model='gemini-3.5-flash',
        contents=prompt
    )
    summary = response.text
    
    send_telegram(summary)
    print("Đã gửi báo cáo thành công!")

if __name__ == "__main__":
    run()
