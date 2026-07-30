import streamlit as st
import feedparser
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client
import datetime
import json
import pandas as pd
from groq import Groq
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET
# ==========================================
# CẤU HÌNH TRANG & GIAO DIỆN
# ==========================================
st.set_page_config(page_title="Trading Terminal & Trend Tracker", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #6C63FF 0%, #00D4FF 100%);
        padding: 24px 28px;
        border-radius: 14px;
        margin-bottom: 22px;
    }
    .main-header h1 { color: white; margin: 0; font-size: 28px; }
    .main-header p { color: #EAEAFF; margin: 4px 0 0 0; font-size: 14px; }
    .badge-ai {
        display: inline-block;
        background: rgba(108, 99, 255, 0.15);
        color: #8B7FFF;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .impact-box {
        background: rgba(0, 212, 255, 0.08);
        border-left: 3px solid #00D4FF;
        padding: 10px 14px;
        border-radius: 6px;
        margin: 8px 0;
    }
    div[data-testid="stMetric"] {
        background: rgba(120, 120, 140, 0.08);
        border-radius: 12px;
        padding: 14px 16px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>📈 Trading Terminal & Trend Tracker</h1>
    <p>Bảng điều khiển giao dịch, tin tức & xu hướng công nghệ — cập nhật tự động</p>
</div>
""", unsafe_allow_html=True)

# ==========================================
# KẾT NỐI SUPABASE & GROQ
# ==========================================
@st.cache_resource
def init_db() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_resource
def init_groq() -> Groq:
    return Groq(api_key=st.secrets["GROQ_API_KEY"])

supabase = init_db()
groq_client = init_groq()

MAX_WORKERS = 15          # so thread song song khi cao RSS
ANALYSIS_WORKERS = 8      # so thread song song khi goi Groq phan tich (thap hon de tranh rate-limit)


# ==========================================
# QUẢN LÝ NGUỒN RSS (đọc/ghi qua Supabase, không dùng links.txt nữa)
# ==========================================
def get_active_rss_sources():
    try:
        res = supabase.table("rss_sources").select("*").order("created_at", desc=True).execute()
        return res.data
    except Exception:
        return []


def add_rss_source(url: str):
    url = url.strip()
    if not url:
        return False, "Link trống."
    try:
        supabase.table("rss_sources").insert({"url": url, "is_active": True}).execute()
        return True, "Đã thêm nguồn mới!"
    except Exception:
        return False, "Không thêm được — link có thể đã tồn tại."


def delete_rss_source(source_id):
    try:
        supabase.table("rss_sources").delete().eq("id", source_id).execute()
    except Exception:
        pass
def check_rss_status(url):
    try:
        feed = feedparser.parse(url)

        if len(feed.entries) > 0:
            return True

        return False

    except Exception:
        return False

# ==========================================
# PHÂN TÍCH AI DÙNG CHUNG (Groq) - trả về JSON có cấu trúc
# ==========================================
def _parse_ai_json(raw_response: str):
    """Chuan hoa phan hoi cua Groq thanh dict {tom_tat, anh_huong_thi_truong, diem_noi_bat}."""
    if not raw_response:
        return None
    text = raw_response.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        if isinstance(data.get("diem_noi_bat"), str):
            data["diem_noi_bat"] = [data["diem_noi_bat"]]
        data.setdefault("tom_tat", "")
        data.setdefault("anh_huong_thi_truong", "")
        data.setdefault("diem_noi_bat", [])
        return data
    except Exception:
        # Neu model tra ve khong dung JSON, van luu lai noi dung tho vao tom_tat
        return {"tom_tat": text[:600], "anh_huong_thi_truong": "", "diem_noi_bat": []}


def _analyze_with_groq(raw_text: str, subject_type: str):
    """subject_type: 'news' hoặc 'github' — quyết định prompt phân tích phù hợp."""
    if not raw_text or len(raw_text.strip()) < 30:
        return None

    if subject_type == "news":
        system_prompt = (
            "Bạn là chuyên gia phân tích tin tức tài chính/công nghệ. "
            "Đọc nội dung bài báo được cung cấp và trả lời DUY NHẤT bằng JSON hợp lệ, "
            "không thêm chữ nào khác ngoài JSON, theo đúng format:\n"
            '{"tom_tat": "tóm tắt nội dung chính trong 2-4 câu", '
            '"anh_huong_thi_truong": "phân tích tác động có thể có đến thị trường/ngành liên quan trong 1-3 câu — '
            "nếu không có tác động rõ ràng thì ghi 'Không có tác động thị trường rõ ràng'\", "
            '"diem_noi_bat": ["điểm/số liệu nổi bật 1", "điểm nổi bật 2", "điểm nổi bật 3"]}'
        )
    else:
        system_prompt = (
            "Bạn là chuyên gia phân tích công nghệ và mã nguồn mở. "
            "Đọc thông tin về dự án GitHub được cung cấp và trả lời DUY NHẤT bằng JSON hợp lệ, "
            "không thêm chữ nào khác ngoài JSON, theo đúng format:\n"
            '{"tom_tat": "dự án này làm gì, giải quyết vấn đề gì, dùng công nghệ/ngôn ngữ chính nào trong 2-4 câu", '
            '"anh_huong_thi_truong": "vì sao dự án đang trending, tác động tiềm năng đến ngành/cộng đồng công nghệ '
            'liên quan trong 1-3 câu", '
            '"diem_noi_bat": ["tính năng/điểm nổi bật 1", "điểm nổi bật 2", "điểm nổi bật 3"]}'
        )

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text[:6000]},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        return _parse_ai_json(completion.choices[0].message.content)
    except Exception:
        return None


# ==========================================
# CÀO & PHÂN TÍCH BÀI BÁO (SONG SONG)
# ==========================================
def _parse_one_feed(link: str):
    """Cao va parse 1 link RSS (chay trong 1 thread). Khong ghi DB o day."""
    link = link.strip()
    if not link:
        return []
    articles = []
    try:
        feed = feedparser.parse(link)
        for entry in feed.entries[:10]:
            articles.append({
                "title": entry.title if "title" in entry else "No Title",
                "link": entry.link if "link" in entry else "",
                "published_date": entry.published if "published" in entry else datetime.datetime.now().isoformat(),
                "source": link,
                "is_active": True,
                "_rss_fallback_text": entry.get("summary", entry.get("description", "")),
            })
    except Exception:
        pass
    return articles


def _fetch_full_article_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(strip=True) for p in paragraphs)
        return text[:6000]
    except Exception:
        return ""


def _build_news_analysis(article: dict):
    full_text = _fetch_full_article_text(article["link"]) if article["link"] else ""
    if len(full_text.strip()) < 50:
        full_text = BeautifulSoup(article.get("_rss_fallback_text", ""), "html.parser").get_text()
    combined = f"Tiêu đề: {article['title']}\n\nNội dung: {full_text}"
    return _analyze_with_groq(combined, "news")


def fetch_and_save_news(links):
    """
    1) Cao + parse tat ca link RSS song song.
    2) Loai bo bai da co san trong DB (tranh phan tich lai bai cu).
    3) Phan tich AI (Groq) song song CHI cho bai that su moi.
    4) Ghi 1 lan bang upsert hang loat.
    """
    all_articles = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_parse_one_feed, link) for link in links]
        for future in as_completed(futures):
            try:
                all_articles.extend(future.result())
            except Exception:
                pass

    if not all_articles:
        return 0

    seen = set()
    deduped = []
    for a in all_articles:
        if a["link"] and a["link"] not in seen:
            seen.add(a["link"])
            deduped.append(a)

    all_links = [a["link"] for a in deduped if a["link"]]
    existing_links = set()
    try:
        for i in range(0, len(all_links), 200):
            chunk = all_links[i:i + 200]
            res = supabase.table("news").select("link").in_("link", chunk).execute()
            existing_links.update(row["link"] for row in res.data)
    except Exception:
        pass

    new_articles = [a for a in deduped if a["link"] not in existing_links]

    if new_articles:
        with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as executor:
            future_to_article = {executor.submit(_build_news_analysis, a): a for a in new_articles}
            for future in as_completed(future_to_article):
                article = future_to_article[future]
                try:
                    article["ai_analysis"] = future.result()
                except Exception:
                    article["ai_analysis"] = None

    payload = [
        {k: v for k, v in a.items() if k != "_rss_fallback_text"}
        for a in new_articles
    ]

    if payload:
        try:
            supabase.table("news").upsert(payload, on_conflict="link").execute()
        except Exception:
            pass

    return len(payload)


# ==========================================
# CÀO & PHÂN TÍCH DỰ ÁN GITHUB TRENDING (SONG SONG)
# ==========================================
def _scrape_trending_page(period: str, today_str: str):
    """Cao 1 trang GitHub Trending theo chu ky (daily/weekly/monthly) - khong phan tich AI o day."""
    repos = []
    try:
        url = f"https://github.com/trending?since={period}"
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.find_all("article", class_="Box-row")

        for repo in rows[:10]:
            h2 = repo.find("h2", class_="h3 lh-condensed")
            a_tag = h2.find("a") if h2 else None
            repo_name = a_tag.text.strip().replace("\n", "").replace(" ", "") if a_tag else "Unknown"
            repo_link = "https://github.com" + a_tag["href"] if a_tag else ""

            p_tag = repo.find("p", class_="col-9 color-fg-muted my-1 pr-4")
            description = p_tag.text.strip() if p_tag else "Không có mô tả"

            repos.append({
                "repo_name": repo_name,
                "repo_link": repo_link,
                "description": description,
                "period": period,
                "fetched_date": today_str,
            })
    except Exception:
        pass
    return repos


def _fetch_repo_readme_text(url: str) -> str:
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        readme = soup.find(id="readme") or soup.find("article")
        if readme:
            return readme.get_text(" ", strip=True)[:5000]
    except Exception:
        pass
    return ""


def _build_repo_analysis(repo: dict):
    readme_text = _fetch_repo_readme_text(repo["repo_link"]) if repo["repo_link"] else ""
    combined = f"Tên dự án: {repo['repo_name']}\nMô tả ngắn: {repo['description']}\n\nNội dung README: {readme_text}"
    return _analyze_with_groq(combined, "github")


def fetch_and_save_github():
    """
    1) Cao 3 trang trending (daily/weekly/monthly).
    2) Loai bo repo da co trong DB cho ngay hom nay (tranh phan tich lai).
    3) Phan tich AI song song CHI cho repo that su moi.
    4) Ghi 1 lan bang upsert hang loat.
    """
    today_str = datetime.date.today().isoformat()
    raw_repos = []
    for period in ["daily", "weekly", "monthly"]:
        raw_repos.extend(_scrape_trending_page(period, today_str))

    if not raw_repos:
        return 0

    seen = set()
    deduped = []
    for r in raw_repos:
        key = (r["repo_link"], r["period"])
        if r["repo_link"] and key not in seen:
            seen.add(key)
            deduped.append(r)

    existing_keys = set()
    try:
        res = supabase.table("github_trending").select("repo_link, period").eq("fetched_date", today_str).execute()
        existing_keys = {(row["repo_link"], row["period"]) for row in res.data}
    except Exception:
        pass

    new_repos = [r for r in deduped if (r["repo_link"], r["period"]) not in existing_keys]

    if new_repos:
        with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as executor:
            future_to_repo = {executor.submit(_build_repo_analysis, r): r for r in new_repos}
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    repo["ai_analysis"] = future.result()
                except Exception:
                    repo["ai_analysis"] = None

        try:
            supabase.table("github_trending").upsert(new_repos, on_conflict="repo_link, period, fetched_date").execute()
        except Exception:
            pass

    return len(new_repos)


def render_clickable_trend_chart(df: pd.DataFrame):
    """Bieu do cot ngang Plotly.js thuan de bar co the CLICK va mo thang link repo trong tab moi."""
    labels = json.dumps(df["repo_name"].tolist())
    values = json.dumps(df["Trend Score"].tolist())
    links = json.dumps(df["repo_link"].tolist())
    hover = json.dumps([d[:90] for d in df["description"].tolist()])

    html_code = f"""
    <div id="trend-chart" style="width:100%;height:440px;"></div>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <script>
        var labels = {labels};
        var values = {values};
        var links = {links};
        var hovertext = {hover};
        var data = [{{
            type: 'bar',
            orientation: 'h',
            x: values,
            y: labels,
            text: labels,
            textposition: 'auto',
            hovertext: hovertext,
            hoverinfo: 'text',
            marker: {{
                color: values,
                colorscale: [[0, '#6C63FF'], [1, '#00D4FF']],
                line: {{ width: 0 }}
            }}
        }}];
        var layout = {{
            margin: {{ l: 10, r: 20, t: 10, b: 30 }},
            yaxis: {{ autorange: 'reversed', automargin: true, showgrid: false }},
            xaxis: {{ showgrid: false, zeroline: false, title: 'Trend Score' }},
            plot_bgcolor: 'rgba(0,0,0,0)',
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: {{ color: '#EAEAEA' }}
        }};
        Plotly.newPlot('trend-chart', data, layout, {{ displayModeBar: false, responsive: true }});
        document.getElementById('trend-chart').on('plotly_click', function(evt) {{
            var idx = evt.points[0].pointIndex;
            window.open(links[idx], '_blank');
        }});
    </script>
    <p style="color:#888; font-size:12px; margin-top:4px;">💡 Nhấp vào một cột để mở repo trong tab mới.</p>
    """
    st.components.v1.html(html_code, height=470)


def render_ai_analysis_block(analysis: dict):
    """Hien thi tom tat + anh huong thi truong + diem noi bat cho ca bai bao lan du an github."""
    if not analysis:
        st.caption("_Chưa có phân tích AI cho mục này (có thể do lỗi khi phân tích hoặc nội dung quá ngắn)._")
        return

    summary = analysis.get("tom_tat")
    if summary:
        st.write(summary)

    impact = analysis.get("anh_huong_thi_truong")
    if impact:
        st.markdown(f'<div class="impact-box">🌍 <b>Ảnh hưởng:</b> {impact}</div>', unsafe_allow_html=True)

    points = analysis.get("diem_noi_bat") or []
    if points:
        st.markdown("**✨ Điểm nổi bật:**")
        for p in points:
            st.markdown(f"- {p}")


def render_time_filter(prefix: str):
    """
    Bo loc thoi gian DOC LAP cho tung tab (tin tuc / github).
    prefix dung de widget key khong bi trung giua 2 tab.
    """
    filter_mode = st.radio(
        "🔍 Chế độ lọc thời gian:",
        ["📅 Theo ngày cụ thể (Lịch)", "📊 Tổng hợp (Tuần/Tháng)"],
        key=f"{prefix}_filter_mode",
        horizontal=True,
    )
    now = datetime.datetime.now()

    if filter_mode == "📅 Theo ngày cụ thể (Lịch)":
        selected_date = st.date_input("Chọn một ngày:", now.date(), key=f"{prefix}_date")
        start_time = datetime.datetime.combine(selected_date, datetime.time.min).isoformat()
        end_time = datetime.datetime.combine(selected_date, datetime.time.max).isoformat()
        display_title = f"Ngày {selected_date.strftime('%d/%m/%Y')}"
        return {
            "mode": "date", "start": start_time, "end": end_time,
            "title": display_title, "selected_date": selected_date, "now": now,
        }
    else:
        time_period = st.selectbox("Chọn chu kỳ:", ["Tuần này", "Tháng này"], key=f"{prefix}_period")
        if time_period == "Tuần này":
            start_time = (now - datetime.timedelta(days=7)).isoformat()
        else:
            start_time = (now - datetime.timedelta(days=30)).isoformat()
        end_time = now.isoformat()
        return {
            "mode": "period", "start": start_time, "end": end_time,
            "title": time_period, "time_period": time_period, "now": now,
        }


# ==========================================
# 1. HIỂN THỊ GIAO DIỆN NGAY LẬP TỨC (UI FIRST)
# ==========================================

# --- SIDEBAR: Quản lý RSS + trạng thái đồng bộ ---
with st.sidebar:
    st.header("⚙️ Bảng Điều Khiển")

    with st.expander("🔗 Quản lý nguồn RSS", expanded=True):

        tab_add, tab_import = st.tabs(["➕ Thêm 1 link", "📥 Quick Import"])

        # ======================
        # THÊM 1 LINK
        # ======================
        with tab_add:

            new_link = st.text_input(
                "Link RSS",
                placeholder="https://vnexpress.net/rss/..."
            )

            if st.button("➕ Thêm nguồn", use_container_width=True):

                ok, msg = add_rss_source(new_link)

                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        # ======================
        # QUICK IMPORT
        # ======================
        with tab_import:

            rss_text = st.text_area(
                "Dán nhiều link (mỗi dòng một link)",
                height=180,
                placeholder="""https://vnexpress.net/rss/kinh-doanh.rss
https://vnexpress.net/rss/the-gioi.rss
https://techcrunch.com/feed"""
            )

            if st.button("🚀 Import tất cả", use_container_width=True):

                imported = 0
                duplicated = 0
                invalid = 0

                urls = [
                    u.strip()
                    for u in rss_text.splitlines()
                    if u.strip()
                ]

                for url in urls:

                    if not url.startswith(("http://", "https://")):
                        invalid += 1
                        continue

                    ok, _ = add_rss_source(url)

                    if ok:
                        imported += 1
                    else:
                        duplicated += 1

                st.success(
                    f"""
✅ Imported: {imported}

🔁 Duplicate: {duplicated}

❌ Invalid: {invalid}
"""
                )

                st.rerun()

        st.divider()

        # ======================
        # DANH SÁCH RSS
        # ======================
        sources = get_active_rss_sources()

        st.caption(f"📡 Đang theo dõi **{len(sources)}** nguồn RSS")

        if len(sources) == 0:
            st.info("Chưa có nguồn RSS nào.")
        else:

            for src in sources:

                c1, c2, c3 = st.columns([5,1,1])

                with c1:
                    display = src["url"]
                    if len(display) > 45:
                        display = display[:42] + "..."
                    st.text(display)

with c2:

    if st.button("🔍", key=f"check_{src['id']}"):

        ok = check_rss_status(src["url"])

        if ok:
            st.success("RSS hoạt động")
        else:
            st.error("RSS lỗi hoặc không còn tồn tại")

with c3:

    if st.button("🗑️", key=f"del_{src['id']}"):

        delete_rss_source(src["id"])
        st.rerun()

    st.divider()

    status_placeholder = st.empty()

# --- TABS (mỗi tab có bộ lọc thời gian RIÊNG) ---
tab1, tab2 = st.tabs(["📰 Tin tức & Báo chí", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC
with tab1:
    news_filter = render_time_filter("news")
    st.subheader(f"Phân tích Báo chí ({news_filter['title']})")

    news_response = supabase.table("news").select("*").gte("created_at", news_filter["start"]).lte("created_at", news_filter["end"]).order("created_at", desc=True).execute()
    news_data = news_response.data

    st.metric("📰 Tổng số bài viết", len(news_data))

    if len(news_data) > 0:
        for item in news_data:
            with st.container(border=True):
                st.markdown(f"#### 📌 {item['title']}")
                st.markdown('<span class="badge-ai">🤖 Phân tích AI — đọc được kể cả khi bài gốc bị xóa</span>', unsafe_allow_html=True)

                render_ai_analysis_block(item.get("ai_analysis"))

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"🔗 [Đọc bài gốc]({item['link']})")
                with col2:
                    if st.button("🔍 Kiểm tra trạng thái bài gốc", key=f"check_{item['id']}"):
                        try:
                            r = requests.head(item["link"], timeout=5, allow_redirects=True)
                            if r.status_code < 400:
                                st.success("🟢 BÀI BÁO GỐC ĐANG HOẠT ĐỘNG")
                            else:
                                st.error(f"🔴 LỖI {r.status_code}: Bài gốc có thể đã bị xóa — nhưng phân tích AI ở trên vẫn còn.")
                        except Exception:
                            st.error("🔴 LỖI MẠNG — không kiểm tra được, nhưng phân tích AI ở trên vẫn còn.")
    else:
        st.info("Chưa có bài viết nào trong khoảng thời gian này.")

# TAB 2: GITHUB TRENDING
with tab2:
    git_filter = render_time_filter("github")
    st.subheader(f"Dự án Công nghệ Nổi bật ({git_filter['title']})")

    if git_filter["mode"] == "date":
        git_response = supabase.table("github_trending").select("*").eq("fetched_date", git_filter["selected_date"].isoformat()).eq("period", "daily").order("created_at", desc=True).limit(10).execute()
    else:
        period_val = "weekly" if git_filter["time_period"] == "Tuần này" else "monthly"
        past_date = (git_filter["now"].date() - datetime.timedelta(days=7 if period_val == "weekly" else 30)).isoformat()
        git_response = supabase.table("github_trending").select("*").eq("period", period_val).gte("fetched_date", past_date).order("fetched_date", desc=True).execute()

    git_data = git_response.data

    if len(git_data) > 0:
        df = pd.DataFrame(git_data)
        df = df.drop_duplicates(subset=["repo_link"]).head(10)
        df["Trend Score"] = range(len(df), 0, -1)

        st.metric("🔥 Dự án đang nổi bật", len(df))
        render_clickable_trend_chart(df)

        st.write("### Chi tiết các dự án:")
        for item in df.to_dict("records"):
            with st.container(border=True):
                st.markdown(f"#### 📦 {item['repo_name']}")
                st.markdown('<span class="badge-ai">🤖 Phân tích AI</span>', unsafe_allow_html=True)

                render_ai_analysis_block(item.get("ai_analysis"))

                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"🔗 [Truy cập GitHub]({item['repo_link']})")
                with col2:
                    if st.button("🔍 Kiểm tra Repo", key=f"git_{item['id']}"):
                        try:
                            r = requests.head(item["repo_link"], timeout=5, allow_redirects=True)
                            if r.status_code < 400:
                                st.success("🟢 Dự án hoạt động bình thường!")
                            else:
                                st.error(f"🔴 Lỗi {r.status_code}: Repo đã bị xóa/Private!")
                        except Exception:
                            st.error("🔴 Lỗi kết nối!")
    else:
        st.warning("Chưa có dữ liệu cho mốc thời gian này. *(Lưu ý: Dữ liệu của những ngày trước khi tạo hệ thống sẽ không tồn tại).*")


# ==========================================
# 2. HỆ THỐNG CÀO DỮ LIỆU CHẠY NGẦM (BACKGROUND)
# ==========================================
@st.cache_data(ttl=900, show_spinner=False)
def auto_scrape_data():
    try:
        active_sources = get_active_rss_sources()
        links = [s["url"] for s in active_sources if s.get("is_active", True)]
        if links:
            fetch_and_save_news(links)
    except Exception:
        pass
    fetch_and_save_github()
    return datetime.datetime.now()


with status_placeholder:
    with st.spinner("Đang cập nhật nguồn dữ liệu ngầm..."):
        last_run_time = auto_scrape_data()
    st.success(f"✅ Đã đồng bộ lúc {last_run_time.strftime('%H:%M:%S')}")
