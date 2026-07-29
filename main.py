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

# Quản lý danh sách nguồn tin bằng DataFrame để cho phép Sửa/Xóa/Thêm trực tiếp
if 'rss_sources_df' not in st.session_state:
    st.session_state.rss_sources_df = pd.DataFrame({
        "Đường link (URL)": [
            "https://vnexpress.net/rss/tin-moi-nhat.rss",
            "https://tuoitre.vn/rss/tin-moi-nhat.rss"
        ]
    })

# ----------------- HÀM XỬ LÝ DỮ LIỆU -----------------

def get_news_and_research():
    """Lấy bài viết từ danh sách các nguồn"""
    articles = []
    # Lấy danh sách link đang có trong bảng, bỏ qua các ô trống
    urls = st.session_state.rss_sources_df['Đường link (URL)'].dropna().tolist()
    
    for url in urls:
        if not url.strip(): continue
        try:
            feed = feedparser.parse(url.strip())
            for entry in feed.entries[:3]:
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'summary': getattr(entry, 'summary', '')
                })
        except Exception:
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
        return "⚠️ Chưa cấu hình GEMINI API Key."
    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Lỗi phân tích AI: {e}"

# ----------------- GIAO DIỆN WEB -----------------

st.title("📈 Bảng Điều Khiển Giao Dịch & Chênh Lệch Thông Tin")

# SIDEBAR: THANH ĐIỀU KHIỂN BÊN TRÁI
st.sidebar.header("⚙️ Bảng Điều Khiển")

# Nút tam giác quản lý (Expander)
with st.sidebar.expander("📂 Quản lý nguồn tin (Sửa/Xóa/Thêm)", expanded=False):
    st.caption("Nhấp đúp vào link để SỬA, chọn dòng bấm phím Delete để XÓA, hoặc gõ vào ô trống dưới cùng để THÊM.")
    
    # Bảng dữ liệu tương tác
    edited_df = st.data_editor(
        st.session_state.rss_sources_df,
        num_rows="dynamic", # Cho phép thêm dòng mới
        use_container_width=True,
        hide_index=True
    )
    # Lưu lại trạng thái sau khi chỉnh sửa
    st.session_state.rss_sources_df = edited_df

st.sidebar.markdown("---")
btn_refresh = st.sidebar.button("🔄 Cập nhật dữ liệu AI ngay")

# MAIN AREA: TẠO NÚT BẤM CHUYỂN TRANG (TABS)
tab_news, tab_github = st.tabs(["📰 Tin tức & Nghiên cứu", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC
with tab_news:
    st.header("Phân tích Báo chí & Tác động Thị trường")
    news_items = get_news_and_research()
    if news_items:
        raw_text = "\n".join([f"- Tiêu đề: {item['title']}\nTóm tắt: {item['summary']}" for item in news_items[:5]])
        prompt_news = f"""
        Bạn là chuyên gia phân tích tài chính và giao dịch chênh lệch thông tin (Information Arbitrage).
        Dữ liệu mới nhất:
        {raw_text}
        
        Viết báo cáo ngắn:
        1. Giao dịch Chênh lệch thông tin: Tác động đến giá thị trường/cổ phiếu/ngành nào.
        2. Mức độ tác động: (Cao/Trung bình/Thấp).
        """
        
        with st.spinner("Gemini đang phân tích tác động thị trường..."):
            ai_analysis = analyze_with_ai(prompt_news)
        
        st.subheader("🤖 Đánh giá AI")
        st.info(ai_analysis)
        
        st.markdown("---")
        st.subheader("📋 Danh sách bài viết gốc")
        for item in news_items:
            with st.expander(item['title']):
                st.write(item['summary'])
                st.markdown(f"[🔗 Đọc toàn bộ]({item['link']})")

# TAB 2: GITHUB TRENDING
with tab_github:
    st.header("Phân tích Công nghệ Đột phá")
    repos = get_github_trending()
    if repos:
        # Vẽ biểu đồ hiển thị rộng rãi hơn trên 1 tab
        df = pd.DataFrame(repos)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(df['name'], df['stars'], color='#2ea44f')
        ax.set_xlabel('Số Sao Tăng Trong 24h', fontweight='bold')
        ax.invert_yaxis() 
        plt.tight_layout()
        st.pyplot(fig)
        
        repo_text = "\n".join([f"- {r['name']} (+{r['stars']} stars)" for r in repos])
        prompt_github = f"""
        Danh sách Top 10 dự án GitHub tăng trưởng nhanh nhất trong 24h:
        {repo_text}
        
        Đánh giá: Dự án nào có tiềm năng đột phá làm thay đổi thị trường/công nghệ? Lý do tăng sao?
        """
        
        with st.spinner("Gemini đang đánh giá tiềm năng thay đổi thị trường..."):
            ai_github_analysis = analyze_with_ai(prompt_github)
            
        st.subheader("💡 Tiềm năng Thay đổi Thị trường")
        st.success(ai_github_analysis)
