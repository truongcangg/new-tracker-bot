import os
import requests
import feedparser
import pandas as pd
from bs4 import BeautifulSoup
import plotly.express as px
import streamlit as st
from google import genai
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
import time

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

# Quản lý danh sách nguồn tin
if 'rss_sources' not in st.session_state:
    st.session_state.rss_sources = [
        "https://vnexpress.net/rss/tin-moi-nhat.rss",
        "https://tuoitre.vn/rss/tin-moi-nhat.rss"
    ]

# --- HỘP THOẠI POPUP (MODAL) ---
@st.dialog("📂 Quản lý Nguồn tin (Nhập hàng loạt)")
def manage_sources_modal():
    st.caption("Dán toàn bộ danh sách link của bạn vào khung dưới đây. **Mỗi dòng là 1 đường link**.")
    current_text = "\n".join(st.session_state.rss_sources)
    new_text = st.text_area("Danh sách đường link:", value=current_text, height=350)
    
    if st.button("💾 Lưu thay đổi", type="primary"):
        lines = new_text.split('\n')
        updated_sources = [line.strip() for line in lines if line.strip()]
        st.session_state.rss_sources = updated_sources
        # Khi đổi nguồn tin, xóa bộ nhớ đệm để tải lại
        fetch_single_feed.clear() 
        st.success(f"Đã cập nhật thành công {len(updated_sources)} nguồn tin!")
        st.rerun()

# ----------------- HÀM XỬ LÝ DỮ LIỆU CÓ BỘ NHỚ ĐỆM & ĐA LUỒNG -----------------

@st.cache_data(ttl=1800, show_spinner=False) # Lưu bộ nhớ đệm trong 30 phút
def fetch_single_feed(url):
    """Cào 1 trang độc lập"""
    try:
        return feedparser.parse(url)
    except:
        return None

def get_news_and_research(urls, target_date):
    """Cào nhiều trang cùng lúc (Đa luồng) và lọc theo ngày"""
    articles = []
    # Chuyển đổi ngày chọn thành mốc 00:00:00 của ngày đó
    target_date_start = datetime.combine(target_date, datetime.min.time())
    
    # Tung 20 luồng chạy song song để tăng tốc
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(fetch_single_feed, url): url for url in urls}
        for future in as_completed(future_to_url):
            feed = future.result()
            if feed and feed.entries:
                for entry in feed.entries:
                    # Chuyển đổi định dạng thời gian của bài báo
                    parsed_time = getattr(entry, 'published_parsed', getattr(entry, 'updated_parsed', None))
                    if parsed_time:
                        entry_date = datetime.fromtimestamp(time.mktime(parsed_time))
                    else:
                        entry_date = datetime.now() # Nếu bài không ghi ngày, mặc định là tin mới
                    
                    # Bộ lọc ngày: Chỉ lấy tin từ mốc thời gian đã chọn trở về sau
                    if entry_date >= target_date_start:
                        articles.append({
                            'title': entry.title,
                            'link': entry.link,
                            'summary': getattr(entry, 'summary', ''),
                            'date': entry_date
                        })
    
    # Sắp xếp bài báo từ mới nhất xuống cũ nhất
    articles = sorted(articles, key=lambda x: x['date'], reverse=True)
    return articles

@st.cache_data(ttl=1800, show_spinner=False)
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
        pass
    
    return sorted(repos, key=lambda x: x['stars'], reverse=True)

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

# 1. Nút quản lý nguồn tin
if st.sidebar.button("📂 Quản lý Nguồn tin", use_container_width=True):
    manage_sources_modal()

st.sidebar.markdown("---")

# 2. Bộ lọc ngày tháng (Mặc định là ngày hôm nay)
selected_date = st.sidebar.date_input("📅 Lọc tin từ ngày:", date.today())

st.sidebar.markdown("---")
# Nút xóa bộ nhớ đệm để tải lại từ đầu nếu muốn
if st.sidebar.button("🔄 Cập nhật dữ liệu AI ngay", use_container_width=True):
    fetch_single_feed.clear()
    get_github_trending.clear()
    st.rerun()

# TẠO NÚT CHUYỂN TRANG (TABS)
tab_news, tab_github = st.tabs(["📰 Tin tức & Nghiên cứu", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC
with tab_news:
    st.header("Phân tích Báo chí & Tác động Thị trường")
    st.caption(f"Trạng thái: Đang quét **{len(st.session_state.rss_sources)}** nguồn tin. Hệ thống đa luồng đang hoạt động ⚡")
    
    with st.spinner(f"Đang cào dữ liệu từ ngày {selected_date.strftime('%d/%m/%Y')}..."):
        news_items = get_news_and_research(st.session_state.rss_sources, selected_date)
    
    if news_items:
        st.success(f"Đã tìm thấy **{len(news_items)}** bài viết mới từ {selected_date.strftime('%d/%m/%Y')}.")
        
        # Chỉ lấy 10 tin nóng nhất đưa cho AI phân tích để tránh quá tải
        top_articles_for_ai = news_items[:10]
        raw_text = "\n".join([f"- Tiêu đề: {item['title']}\nTóm tắt: {item['summary']}" for item in top_articles_for_ai])
        
        prompt_news = f"""
        Bạn là chuyên gia phân tích tài chính và giao dịch chênh lệch thông tin.
        Dữ liệu {len(top_articles_for_ai)} tin tức mới nhất hôm nay:
        {raw_text}
        
        Viết báo cáo ngắn:
        1. Giao dịch Chênh lệch thông tin: Tác động đến giá thị trường/cổ phiếu/ngành nào.
        2. Mức độ tác động: (Cao/Trung bình/Thấp).
        """
        
        with st.spinner("Gemini đang đọc báo và phân tích tác động thị trường..."):
            ai_analysis = analyze_with_ai(prompt_news)
        
        st.subheader("🤖 Đánh giá AI")
        st.info(ai_analysis)
        
        st.markdown("---")
        st.subheader("📋 Danh sách bài viết")
        for item in news_items:
            # Hiển thị tiêu đề kèm theo giờ giấc rõ ràng
            time_str = item['date'].strftime('%H:%M %d/%m')
            with st.expander(f"[{time_str}] {item['title']}"):
                st.write(item['summary'])
                st.markdown(f"[🔗 Đọc toàn bộ]({item['link']})")
    else:
        st.warning(f"Chưa có bài báo nào mới từ ngày {selected_date.strftime('%d/%m/%Y')}.")

# TAB 2: GITHUB TRENDING
with tab_github:
    st.header("Phân tích Công nghệ Đột phá & Lịch sử Tăng trưởng")
    
    with st.spinner("Đang tải dữ liệu GitHub..."):
        repos = get_github_trending()
        
    if repos:
        df = pd.DataFrame(repos)
        
        # Bản vá lỗi Plotly: color_continuous_scale
        fig = px.bar(
            df, 
            x='stars', 
            y='name', 
            orientation='h',
            title='Top 10 Dự án tăng sao nhiều nhất (24h qua)',
            labels={'stars': 'Số sao tăng trong 24h', 'name': 'Dự án'},
            color='stars',
            color_continuous_scale='Greens'
        )
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("### 📊 Chi tiết dự án & Tra cứu Lịch sử Sao")
        for r in repos:
            star_history_link = f"https://star-history.com/#{r['name']}&Date"
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"- **[{r['name']}]({r['link']})** (+{r['stars']} sao)")
            with c2:
                st.markdown(f"[📈 Xem Star History]({star_history_link})")
        
        st.markdown("---")
        repo_text = "\n".join([f"- {r['name']} (+{r['stars']} stars)" for r in repos])
        prompt_github = f"""
        Danh sách Top 10 dự án GitHub tăng trưởng nhanh nhất:
        {repo_text}
        
        Đánh giá: Dự án nào có tiềm năng đột phá làm thay đổi thị trường/công nghệ? Lý do tăng sao?
        """
        
        with st.spinner("Gemini đang đánh giá tiềm năng thay đổi thị trường..."):
            ai_github_analysis = analyze_with_ai(prompt_github)
            
        st.subheader("💡 Đánh giá Tiềm năng Thay đổi Thị trường từ AI")
        st.success(ai_github_analysis)
