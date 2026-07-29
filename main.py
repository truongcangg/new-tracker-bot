import os
import requests
import feedparser
import pandas as pd
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import streamlit as st
from google import genai

# Cấu hình trang Web
st.set_page_config(page_title="Trading Terminal & Trend Tracker", page_icon="📈", layout="wide")

# Khởi tạo Gemini Client
GEMINI_KEY = st.secrets.get("GEMINI") or os.environ.get("GEMINI")
client = None
if GEMINI_KEY:
    try:
        client = genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        st.error(f"Lỗi khởi tạo Gemini API: {e}")

# Quản lý danh sách nguồn tin trong Session State
if 'rss_sources' not in st.session_state:
    st.session_state.rss_sources = [
        "https://vnexpress.net/rss/tin-moi-nhat.rss",
        "https://tuoitre.vn/rss/tin-moi-nhat.rss"
    ]

# ----------------- HÀM XỬ LÝ DỮ LIỆU -----------------

def get_news_and_research():
    """Lấy bài viết từ danh sách các nguồn RSS"""
    articles = []
    for url in st.session_state.rss_sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'summary': getattr(entry, 'summary', '')
                })
        except Exception as e:
            st.warning(f"Không thể đọc nguồn: {url}")
    return articles

def get_github_trending():
    """Cào Top 10 GitHub Trending 24h"""
    url = "https://github.com/trending"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    repos = []
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('article.Box-row')
            for row in rows[:10]:
                title_elem = row.select_one('h2 a')
                if not title_elem: continue
                name = "".join(title_elem.text.split())
                
                stars_today = 0
                for span in row.find_all('span'):
                    text = span.get_text()
                    if 'stars today' in text or 'star today' in text:
                        num_str = "".join(filter(str.isdigit, text))
                        if num_str: stars_today = int(num_str)
                        break
                repos.append({'name': name, 'stars': stars_today, 'link': f"https://github.com/{name}"})
    except Exception as e:
        st.error(f"Lỗi cào GitHub: {e}")
    return repos

def analyze_with_ai(prompt):
    """Gọi Gemini phân tích"""
    if not client:
        return "⚠️ Chưa cấu hình GEMINI API Key trong Streamlit Secrets."
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Lỗi phân tích AI: {e}"

# ----------------- GIAO DIỆN WEB (STREAMLIT) -----------------

st.title("📈 Bảng Điều Khiển Giao Dịch & Chênh LệCH Thông Tin")
st.caption("Hệ thống tự động quét dữ liệu tin tức, bài nghiên cứu và xu hướng công nghệ GitHub.")

# Sidebar - Điều khiển
st.sidebar.header("⚙️ Quản lý nguồn tin")
new_url = st.sidebar.text_input("Thêm đường link RSS/Báo mới:")
if st.sidebar.button("➕ Thêm nguồn"):
    if new_url and new_url not in st.session_state.rss_sources:
        st.session_state.rss_sources.append(new_url)
        st.sidebar.success("Đã thêm nguồn tin mới thành công!")

st.sidebar.markdown("---")
st.sidebar.subheader("📡 Các nguồn hiện có:")
for idx, src in enumerate(st.session_state.rss_sources, 1):
    st.sidebar.text(f"{idx}. {src[:30]}...")

st.sidebar.markdown("---")
btn_refresh = st.sidebar.button("🔄 Cập nhật dữ liệu ngay")

# Layout chính 2 Cột
col1, col2 = st.columns([1, 1])

# CỘT 1: TIN TỨC & CHÊNH LỆCH THÔNG TIN
with col1:
    st.header("📰 Tin tức & Bài nghiên cứu")
    
    news_items = get_news_and_research()
    if news_items:
        # Chuẩn bị dữ liệu cho AI phân tích
        raw_text = "\n".join([f"- Tiêu đề: {item['title']}\nTóm tắt: {item['summary']}" for item in news_items[:5]])
        
        prompt_news = f"""
        Bạn là chuyên gia phân tích tài chính và giao dịch chênh lệch thông tin (Information Arbitrage).
        Dưới đây là các tin tức/nghiên cứu mới nhất:
        {raw_text}
        
        Hãy đưa ra báo cáo ngắn gọn:
        1. 🚨 **Giao dịch Chênh lệch thông tin:** Các tin tức nóng có thể tác động đến giá thị trường/cổ phiếu/ngành nào.
        2. 🔬 **Bài nghiên cứu/Công nghệ đột phá:** Yếu tố mới có thể tạo ra cơ hội dài hạn.
        3. 🎯 **Mức độ tác động:** (Cao / Trung bình / Thấp).
        """
        
        with st.spinner("Gemini đang phân tích tác động thị trường..."):
            ai_analysis = analyze_with_ai(prompt_news)
        
        st.subheader("🤖 AI Phân tích Tác động Thị trường")
        st.markdown(ai_analysis)
        
        st.markdown("---")
        st.subheader("📋 Danh sách bài báo vừa cập nhật")
        for item in news_items:
            with st.expander(item['title']):
                st.write(item['summary'])
                st.markdown(f"[🔗 Đọc bài gốc tại đây]({item['link']})")

# CỘT 2: TOP 10 GITHUB TRENDING
with col2:
    st.header("🔥 Top 10 GitHub Trending (24h)")
    
    repos = get_github_trending()
    if repos:
        # Vẽ biểu đồ
        df = pd.DataFrame(repos)
        
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.barh(df['name'], df['stars'], color='#2ea44f')
        ax.set_xlabel('Số Sao Tăng Trong 24h', fontweight='bold')
        ax.invert_yaxis()  # Đưa Top 1 lên trên
        plt.tight_layout()
        
        st.pyplot(fig)
        
        # AI Phân tích tiềm năng thay đổi thị trường
        repo_text = "\n".join([f"- {r['name']} (+{r['stars']} stars)" for r in repos])
        prompt_github = f"""
        Dưới đây là danh sách Top 10 dự án GitHub tăng trưởng nhanh nhất trong 24h qua:
        {repo_text}
        
        Hãy đánh giá:
        1. Dự án nào có **tiềm năng đột phá hoặc làm thay đổi thị trường/công nghệ**?
        2. Tóm tắt ngắn gọn ứng dụng thực tế và lý do nó tăng sao đột biến.
        """
        
        with st.spinner("Gemini đang đánh giá tiềm năng các dự án GitHub..."):
            ai_github_analysis = analyze_with_ai(prompt_github)
            
        st.subheader("💡 Đánh giá Tiềm năng Thay đổi Thị trường")
        st.markdown(ai_github_analysis)
