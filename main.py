import streamlit as st
import feedparser
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import datetime
import pandas as pd
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed  # <-- MOI: cho phep cao song song

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Trading Terminal & Trend Tracker", layout="wide")
st.title("📈 Bảng Điều Khiển Giao Dịch & Chênh Lệch Thông Tin")

# --- KẾT NỐI SUPABASE ---
@st.cache_resource
def init_db() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_db()

MAX_WORKERS = 15  # so thread chay song song khi cao RSS - co the chinh 10-20


# --- HÀM PHỤ: CÀO 1 LINK RSS DUY NHẤT (chạy trong 1 thread) ---
def _parse_one_feed(link: str):
    """
    Cao va parse 1 link RSS. Tra ve list cac dict bai bao (co the rong neu loi).
    Khong ghi DB o day - chi parse, de tranh nhieu thread cung ghi DB 1 luc.
    """
    link = link.strip()
    if not link:
        return []

    articles = []
    try:
        feed = feedparser.parse(link)
        for entry in feed.entries[:10]:
            title = entry.title if 'title' in entry else 'No Title'
            link_url = entry.link if 'link' in entry else ''
            published = entry.published if 'published' in entry else datetime.datetime.now().isoformat()
            articles.append({
                "title": title,
                "link": link_url,
                "published_date": published,
                "source": link,
                "is_active": True
            })
    except Exception:
        pass
    return articles


# --- HÀM CÀO DỮ LIỆU BÁO CHÍ (RSS) - DA TAI CAU TRUC SONG SONG ---
def fetch_and_save_news(links):
    """
    Ban song song: gui toan bo link cho ThreadPoolExecutor thay vi
    'for link in links' tuan tu. Sau khi tat ca thread parse xong,
    ghi 1 lan bang upsert hang loat (giam so request toi Supabase).
    """
    new_articles = 0
    all_articles = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_parse_one_feed, link) for link in links]
        for future in as_completed(futures):
            try:
                all_articles.extend(future.result())
            except Exception:
                pass

    if all_articles:
        try:
            # upsert hang loat - Supabase se tu bo qua ban ghi trung theo "link"
            supabase.table("news").upsert(all_articles, on_conflict="link").execute()
            new_articles = len(all_articles)
        except Exception:
            pass

    return new_articles


# --- HÀM CÀO DỮ LIỆU GITHUB TRENDING (giữ nguyên, không đổi) ---
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

    filter_mode = st.radio("🔍 Chế độ lọc dữ liệu:", ["📅 Theo ngày cụ thể (Lịch)", "📊 Tổng hợp (Tuần/Tháng)"])

    now = datetime.datetime.now()

    if filter_mode == "📅 Theo ngày cụ thể (Lịch)":
        selected_date = st.date_input("Chọn một ngày:", now.date())
        start_time = datetime.datetime.combine(selected_date, datetime.time.min).isoformat()
        end_time = datetime.datetime.combine(selected_date, datetime.time.max).isoformat()
        display_title = f"Ngày {selected_date.strftime('%d/%m/%Y')}"
    else:
        time_period = st.selectbox("Chọn chu kỳ:", ["Tuần này", "Tháng này"])
        if time_period == "Tuần này":
            start_time = (now - datetime.timedelta(days=7)).isoformat()
        else:
            start_time = (now - datetime.timedelta(days=30)).isoformat()
        end_time = now.isoformat()
        display_title = time_period

    st.divider()
    status_placeholder = st.empty()

# --- GIAO DIỆN CHÍNH (TABS) ---
tab1, tab2 = st.tabs(["📰 Tin tức & Báo chí", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC
with tab1:
    st.subheader(f"Phân tích Báo chí ({display_title})")

    news_response = supabase.table("news").select("*").gte("created_at", start_time).lte("created_at", end_time).order("created_at", desc=True).execute()
    news_data = news_response.data

    st.info(f"Đã tìm thấy **{len(news_data)}** bài viết.")

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

# TAB 2: GITHUB TRENDING
with tab2:
    st.subheader(f"Dự án Công nghệ Nổi bật ({display_title})")

    if filter_mode == "📅 Theo ngày cụ thể (Lịch)":
        git_response = supabase.table("github_trending").select("*").eq("fetched_date", selected_date.isoformat()).eq("period", "daily").order("created_at", desc=True).limit(10).execute()
    else:
        period_val = "weekly" if time_period == "Tuần này" else "monthly"
        past_date = (now.date() - datetime.timedelta(days=7 if period_val == "weekly" else 30)).isoformat()
        git_response = supabase.table("github_trending").select("*").eq("period", period_val).gte("fetched_date", past_date).order("fetched_date", desc=True).execute()

    git_data = git_response.data

    if len(git_data) > 0:
        df = pd.DataFrame(git_data)
        df = df.drop_duplicates(subset=['repo_link']).head(10)
        df['Trend Score'] = range(len(df), 0, -1)

        fig = px.bar(df, x='Trend Score', y='repo_name', orientation='h',
                      title=f"Biểu đồ Xu hướng ({display_title})", text='repo_name')
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        st.write("### Chi tiết các dự án:")
        for item in df.to_dict('records'):
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
        st.warning(f"Chưa có dữ liệu cho mốc thời gian này. *(Lưu ý: Dữ liệu của những ngày trước khi tạo hệ thống sẽ không tồn tại).*")


# ==========================================
# 2. HỆ THỐNG CÀO DỮ LIỆU CHẠY NGẦM (BACKGROUND)
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def auto_scrape_data():
    try:
        with open("links.txt", "r") as f:
            links = f.readlines()
        fetch_and_save_news(links)   # <-- gio da chay song song ben trong
    except Exception:
        pass
    fetch_and_save_github()
    return datetime.datetime.now()

with status_placeholder:
    with st.spinner("Đang cập nhật nguồn dữ liệu ngầm..."):
        last_run_time = auto_scrape_data()
    st.success(f"✅ Đã đồng bộ lúc {last_run_time.strftime('%H:%M:%S')}")
