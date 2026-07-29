import os
import requests
import feedparser
import pandas as pd
from bs4 import BeautifulSoup
import plotly.express as px
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

# Quản lý danh sách nguồn tin (Chuyển về dạng Danh sách để quản lý hàng loạt)
if 'rss_sources' not in st.session_state:
    st.session_state.rss_sources = [
        "https://vnexpress.net/rss/tin-moi-nhat.rss",
        "https://tuoitre.vn/rss/tin-moi-nhat.rss"
    ]

# --- HỘP THOẠI POPUP (MODAL) NHẬP LINK HÀNG LOẠT ---
@st.dialog("📂 Quản lý Nguồn tin (Nhập hàng loạt)")
def manage_sources_modal():
    st.caption("Dán toàn bộ danh sách link của bạn vào khung dưới đây. **Mỗi dòng là 1 đường link** (giống như soạn thảo trên Word/Notepad).")
    
    # Gộp danh sách hiện tại thành văn bản có xuống dòng
    current_text = "\n".join(st.session_state.rss_sources)
    
    # Khung văn bản lớn (Text Area)
    new_text = st.text_area("Danh sách đường link:", value=current_text, height=350)
    
    if st.button("💾 Lưu thay đổi", type="primary"):
        # Tách văn bản thành từng dòng, xóa khoảng trắng và bỏ qua các dòng trống
        lines = new_text.split('\n')
        updated_sources = [line.strip() for line in lines if line.strip()]
        
        # Cập nhật vào hệ thống
        st.session_state.rss_sources = updated_sources
        
        st.success(f"Đã cập nhật thành công {len(updated_sources)} nguồn tin!")
        st.rerun()

# ----------------- HÀM XỬ LÝ DỮ LIỆU -----------------

def get_news_and_research():
    articles = []
    urls = st.session_state.rss_sources
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'summary': getattr(entry, 'summary', '')
                })
        except Exception:
            pass
    return articles

def get_github_trending():
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
    
    # Sắp xếp danh sách theo số sao từ cao xuống thấp
    repos = sorted(repos, key=lambda x: x['stars'], reverse=True)
    return repos

def analyze_with_ai(prompt):
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

# ----------------- GIAO DIỆN WEB CHÍNH -----------------

st.title("📈 Bảng Điều Khiển Giao Dịch & Chênh Lệch Thông Tin")

# SIDEBAR: THANH ĐIỀU KHIỂN
st.sidebar.header("⚙️ Bảng Điều Khiển")

# Nút bấm mở cửa sổ Popup quản lý nguồn tin
if st.sidebar.button("📂 Quản lý Nguồn tin (Nhập hàng loạt)", use_container_width=True):
    manage_sources_modal()

st.sidebar.markdown("---")
btn_refresh = st.sidebar.button("🔄 Cập nhật dữ liệu AI ngay", use_container_width=True)

# TẠO NÚT CHUYỂN TRANG (TABS)
tab_news, tab_github = st.tabs(["📰 Tin tức & Nghiên cứu", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC
with tab_news:
    st.header("Phân tích Báo chí & Tác động Thị trường")
    
    st.caption(f"Trạng thái: Đang theo dõi **{len(st.session_state.rss_sources)}** nguồn tin.")
    
    news_items = get_news_and_research()
    if news_items:
        raw_text = "\n".join([f"- Tiêu đề: {item['title']}\nTóm tắt: {item['summary']}" for item in news_items[:5]])
        prompt_news = f"""
        Bạn là chuyên gia phân tích tài chính và giao dịch chênh lệch thông tin.
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
    st.header("Phân tích Công nghệ Đột phá & Lịch sử Tăng trưởng")
    repos = get_github_trending()
    if repos:
        df = pd.DataFrame(repos)
        
        # Biểu đồ động Plotly
        fig = px.bar(
            df, 
            x='stars', 
            y='name', 
            orientation='h',
            title='Top 10 Dự án tăng sao nhiều nhất (24h qua - Đã sắp xếp giảm dần)',
            labels={'stars': 'Số sao tăng trong 24h', 'name': 'Dự án'},
            color='stars',
            color_continuousScale='Greens'
        )
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("### 📊 Chi tiết dự án & Tra cứu Lịch sử Sao (Star History)")
        st.caption("Bấm vào tên dự án để xem mã nguồn hoặc bấm nút 'Xem Star History' để mở biểu đồ lịch sử chi tiết:")
        
        for r in repos:
            star_history_link = f"https://star-history.com/#{r['name']}&Date"
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"- **[{r['name']}]({r['link']})** (Tăng **+{r['stars']}** sao trong 24h)")
            with c2:
                st.markdown(f"[📈 Xem Star History]({star_history_link})")
        
        st.markdown("---")
        repo_text = "\n".join([f"- {r['name']} (+{r['stars']} stars)" for r in repos])
        prompt_github = f"""
        Danh sách Top 10 dự án GitHub tăng trưởng nhanh nhất trong 24h:
        {repo_text}
        
        Đánh giá: Dự án nào có tiềm năng đột phá làm thay đổi thị trường/công nghệ? Lý do tăng sao?
        """
        
        with st.spinner("Gemini đang đánh giá tiềm năng thay đổi thị trường..."):
            ai_github_analysis = analyze_with_ai(prompt_github)
            
        st.subheader("💡 Đánh giá Tiềm năng Thay đổi Thị trường từ AI")
        st.success(ai_github_analysis)
