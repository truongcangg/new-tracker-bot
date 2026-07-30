import streamlit as st
import feedparser
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import datetime
import pandas as pd
import plotly.express as px

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Trading Terminal & Trend Tracker", layout="wide")
st.title("📈 Bảng Điều Khiển Giao Dịch & Chênh Lệch Thông Tin")

# --- KẾT NỐI SUPABASE ---
@st.cache_resource
def init_db() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_db()

# --- HÀM CÀO DỮ LIỆU BÁO CHÍ (RSS) ---
def fetch_and_save_news(links):
    new_articles = 0
    for link in links:
        if not link.strip(): continue
        feed = feedparser.parse(link.strip())
        for entry in feed.entries[:10]:
            title = entry.title if 'title' in entry else 'No Title'
            link_url = entry.link if 'link' in entry else ''
            published = entry.published if 'published' in entry else datetime.datetime.now().isoformat()
            
            try:
                supabase.table("news").upsert({
                    "title": title,
                    "link": link_url,
                    "published_date": published,
                    "source": link.strip(),
                    "is_active": True
                }, on_conflict="link").execute()
                new_articles += 1
            except Exception:
                pass
    return new_articles

# --- HÀM CÀO DỮ LIỆU GITHUB TRENDING ---
def fetch_and_save_github():
    periods = ["daily", "weekly", "monthly"]
    for period in periods:
        url = f"https://github.com/trending?since={period}"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        repos = soup.find_all('article', class_='Box-row')
        
        today_str = datetime.date.today().isoformat()
        
        for repo in repos[:10]:
            h2 = repo.find('h2', class_='h3 lh-condensed')
            a_tag = h2.find('a') if h2 else None
            repo_name = a_tag.text.strip().replace('\n', '').replace(' ', '') if a_tag else "Unknown"
            repo_link = "https://github.com" + a_tag['href'] if a_tag else ""
            
            p_tag = repo.find('p', class_='col-9 color-fg-muted my-1 pr-4')
            description = p_tag.text.strip() if p_tag else "Không có mô tả"
            
            try:
                supabase.table("github_trending").upsert({
                    "repo_name": repo_name,
                    "repo_link": repo_link,
                    "description": description,
                    "period": period,
                    "fetched_date": today_str
                }, on_conflict="repo_link, period, fetched_date").execute()
            except Exception:
                pass

# ==========================================
# 1. HIỂN THỊ GIAO DIỆN NGAY LẬP TỨC (UI FIRST)
# ==========================================

# --- GIAO DIỆN SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Bảng Điều Khiển")
    
    time_filter = st.selectbox("📅 Chọn mốc thời gian:", ["Hôm nay", "Tuần này", "Tháng này"])
    
    now = datetime.datetime.now()
    if time_filter == "Hôm nay":
        start_date = now.date().isoformat()
    elif time_filter == "Tuần này":
        start_date = (now - datetime.timedelta(days=7)).date().isoformat()
    else:
        start_date = (now - datetime.timedelta(days=30)).date().isoformat()

    st.divider()
    # Khung giữ chỗ để hiện trạng thái cào dữ liệu sau cùng
    status_placeholder = st.empty() 

# --- GIAO DIỆN CHÍNH (TABS) ---
tab1, tab2 = st.tabs(["📰 Tin tức & Báo chí", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC (Load từ Database)
with tab1:
    st.subheader(f"Phân tích Báo chí ({time_filter})")
    
    news_response = supabase.table("news").select("*").gte("created_at", start_date).order("created_at", desc=True).execute()
    news_data = news_response.data
    
    st.info(f"Đã tìm thấy **{len(news_data)}** bài viết trong hệ thống.")
    
    if len(news_data) > 0:
        for item in news_data:
            with st.expander(f"📌 {item['title']}"):
                st.write(f"**Ngày đăng gốc:** {item['published_date']}")
                st.write(f"**Nguồn RSS:** {item['source']}")
                st.markdown(f"🔗 [Đọc bài báo trên trình duyệt]({item['link']})")
                
                if st.button("🔍 Kiểm tra bài báo", key=f"check_{item['id']}"):
                    try:
                        r = requests.head(item['link'], timeout=5, allow_redirects=True)
                        if r.status_code < 400:
                            st.success("🟢 BÀI BÁO ĐANG HOẠT ĐỘNG")
                        else:
                            st.error(f"🔴 LỖI {r.status_code}: Bài báo có thể đã bị xóa!")
                    except Exception:
                        st.error("🔴 LỖI MẠNG!")

# TAB 2: GITHUB TRENDING (Load từ Database)
with tab2:
    st.subheader(f"Dự án Công nghệ Nổi bật ({time_filter})")
    
    period_map = {"Hôm nay": "daily", "Tuần này": "weekly", "Tháng này": "monthly"}
    selected_period = period_map[time_filter]
    
    git_response = supabase.table("github_trending").select("*").eq("period", selected_period).order("fetched_date", desc=True).limit(10).execute()
    git_data = git_response.data
    
    if len(git_data) > 0:
        df = pd.DataFrame(git_data)
        df['Trend Score'] = range(len(df), 0, -1) 
        
        fig = px.bar(df, x='Trend Score', y='repo_name', orientation='h', 
                     title=f"Biểu đồ Xu hướng ({time_filter})", text='repo_name')
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("### Chi tiết các dự án:")
        for item in git_data:
            with st.expander(f"📦 {item['repo_name']}"):
                st.write(f"**Mô tả:** {item['description']}")
                st.markdown(f"🔗 [Truy cập GitHub]({item['repo_link']})")
                
                if st.button("🔍 Kiểm tra Repo", key=f"git_{item['id']}"):
                    try:
                        r = requests.head(item['repo_link'], timeout=5, allow_redirects=True)
                        if r.status_code < 400:
                            st.success("🟢 Dự án hoạt động bình thường!")
                        else:
                            st.error(f"🔴 Lỗi {r.status_code}: Repo đã bị xóa/Private!")
                    except Exception:
                        st.error("🔴 Lỗi kết nối!")
    else:
        st.warning(f"Chưa có dữ liệu GitHub cho '{time_filter}'. Hệ thống đang tự động cào ngầm, vui lòng đợi!")


# ==========================================
# 2. HỆ THỐNG CÀO DỮ LIỆU CHẠY NGẦM (BACKGROUND)
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def auto_scrape_data():
    try:
        with open("links.txt", "r") as f:
            links = f.readlines()
        fetch_and_save_news(links)
    except Exception:
        pass
    
    fetch_and_save_github()
    return datetime.datetime.now()

# Chạy ngầm và cập nhật trạng thái ở Sidebar sau khi giao diện đã hiển thị xong
with status_placeholder:
    with st.spinner("Đang cập nhật nguồn dữ liệu ngầm..."):
        last_run_time = auto_scrape_data()
    st.success(f"✅ Đã đồng bộ lúc {last_run_time.strftime('%H:%M:%S')}")
