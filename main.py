import streamlit as st
import requests
import feedparser
import datetime
import json
import pandas as pd
from supabase import create_client, Client
from groq import Groq

import core  # toan bo logic cao + phan tich AI, dung chung voi scraper.py (GitHub Actions)

# ==========================================
# CẤU HÌNH TRANG & GIAO DIỆN (theme tối, hiện đại, kiểu trading dashboard)
# ==========================================
st.set_page_config(page_title="Trading Terminal & Trend Tracker", layout="wide", page_icon="📈")

st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Nen tong the toi hon, trung tinh hon mac dinh cua Streamlit */
    .stApp { background-color: #0B0F1A; }

    .main-header {
        background: linear-gradient(120deg, #6C63FF 0%, #4C8DFF 55%, #00D4FF 100%);
        padding: 26px 32px;
        border-radius: 18px;
        margin-bottom: 24px;
        box-shadow: 0 8px 30px rgba(76, 141, 255, 0.15);
    }
    .main-header h1 { color: white; margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.3px; }
    .main-header p { color: rgba(255,255,255,0.85); margin: 6px 0 0 0; font-size: 13.5px; font-weight: 500; }

    /* ---------- KPI cards (hang chi so dau moi tab) ---------- */
    .kpi-row { display: flex; gap: 14px; margin-bottom: 22px; flex-wrap: wrap; }
    .kpi-card {
        flex: 1 1 180px;
        background: linear-gradient(180deg, #131A2B 0%, #0F1524 100%);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 16px 18px;
    }
    .kpi-label { font-size: 12px; color: #8A93A8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; }
    .kpi-value { font-size: 24px; color: #F2F4F8; font-weight: 800; margin-top: 6px; }
    .kpi-sub { font-size: 12px; color: #6C63FF; font-weight: 600; margin-top: 4px; }

    /* ---------- Card bai bao / repo ---------- */
    .item-card {
        background: #10161F;
        border: 1px solid rgba(255,255,255,0.06);
        border-left: 3px solid #6C63FF;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 14px;
    }
    .item-card.sentiment-Positive { border-left-color: #22C55E; }
    .item-card.sentiment-Negative { border-left-color: #EF4444; }
    .item-card.sentiment-Neutral  { border-left-color: #8A93A8; }

    .item-title { font-size: 16px; font-weight: 700; color: #F2F4F8; margin: 0 0 8px 0; line-height: 1.4; }

    .pill-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .pill {
        font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px;
        background: rgba(108, 99, 255, 0.14); color: #A79BFF;
    }
    .pill-sentiment-Positive { background: rgba(34,197,94,0.14); color: #4ADE80; }
    .pill-sentiment-Negative { background: rgba(239,68,68,0.14); color: #F87171; }
    .pill-sentiment-Neutral  { background: rgba(138,147,168,0.14); color: #B3BACB; }
    .pill-importance { background: rgba(0,212,255,0.14); color: #5FDFFF; }
    .pill-tag { background: rgba(255,255,255,0.06); color: #C7CCDA; }

    .badge-ai {
        display: inline-block; background: rgba(108, 99, 255, 0.12); color: #A79BFF;
        padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-bottom: 10px;
    }
    .impact-box {
        background: rgba(0, 212, 255, 0.06); border-left: 3px solid #00D4FF;
        padding: 10px 14px; border-radius: 8px; margin: 10px 0; font-size: 13.5px; color: #D7DCE8;
    }
    .detail-box {
        background: rgba(255,255,255,0.03); border-left: 3px solid #6C63FF;
        padding: 12px 14px; border-radius: 8px; font-size: 13.5px; line-height: 1.7; color: #C7CCDA;
    }

    div[data-testid="stMetric"] { background: rgba(120, 120, 140, 0.08); border-radius: 12px; padding: 14px 16px; }

    /* An thanh cong cu zoom mac dinh cua vega/altair chart trong dashboard thong ke */
    div[data-testid="stVegaLiteChart"] .vega-actions { display: none !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
    <h1>📈 Trading Terminal & Trend Tracker</h1>
    <p>Bảng điều khiển giao dịch, tin tức & xu hướng công nghệ — cập nhật tự động mỗi 20 phút qua GitHub Actions</p>
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

if "manual_run_log" not in st.session_state:
    st.session_state["manual_run_log"] = []


# ==========================================
# QUẢN LÝ NGUỒN RSS
# ==========================================
def get_active_rss_sources():
    try:
        res = supabase.table("rss_sources").select("*").order("created_at", desc=True).execute()
        return res.data
    except Exception:
        return []


def get_rss_info(url: str):
    try:
        feed = feedparser.parse(url)
        if feed.bozo:
            return None, 0
        return feed.feed.get("title", url), len(feed.entries)
    except Exception:
        return None, 0


def add_rss_source(url: str):
    url = url.strip()
    if not url:
        return False, "Link trống."
    try:
        name, article_count = get_rss_info(url)
        supabase.table("rss_sources").insert({
            "name": name if name else url,
            "url": url,
            "is_active": True,
            "last_checked": datetime.datetime.now().isoformat(),
            "last_article_count": article_count,
        }).execute()
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
        return len(feed.entries) > 0
    except Exception:
        return False


def get_last_sync_time():
    latest = None
    for table in ("news", "github_trending"):
        try:
            res = supabase.table(table).select("created_at").order("created_at", desc=True).limit(1).execute()
            if res.data:
                ts = datetime.datetime.fromisoformat(res.data[0]["created_at"].replace("Z", "+00:00"))
                if latest is None or ts > latest:
                    latest = ts
        except Exception:
            pass
    return latest


# ==========================================
# COMPONENT: KPI ROW (hang the chi so kieu dashboard chuyen nghiep)
# ==========================================
def render_kpi_row(items: list):
    """items: list of {label, value, sub (optional)}"""
    cards_html = ""
    for item in items:
        sub_html = f'<div class="kpi-sub">{item["sub"]}</div>' if item.get("sub") else ""
        cards_html += f"""
        <div class="kpi-card">
            <div class="kpi-label">{item['label']}</div>
            <div class="kpi-value">{item['value']}</div>
            {sub_html}
        </div>
        """
    st.markdown(f'<div class="kpi-row">{cards_html}</div>', unsafe_allow_html=True)


# ==========================================
# HIỂN THỊ PHÂN TÍCH AI
# ==========================================
def render_ai_analysis_block(analysis: dict):
    if not analysis:
        st.caption("Chưa có phân tích AI cho mục này (có thể do lỗi khi phân tích hoặc nội dung quá ngắn).")
        return

    summary = analysis.get("tom_tat")
    if summary:
        st.write(summary)

    detail = analysis.get("phan_tich_chi_tiet")
    if detail:
        with st.expander("📖 Xem phân tích chi tiết"):
            st.markdown(f'<div class="detail-box">{detail}</div>', unsafe_allow_html=True)

    impact = analysis.get("anh_huong_thi_truong")
    if impact:
        st.markdown(f'<div class="impact-box">🌍 <b>Ảnh hưởng:</b> {impact}</div>', unsafe_allow_html=True)

    related = analysis.get("doi_tuong_lien_quan") or []
    if related:
        st.markdown("**🎯 Đối tượng liên quan:** " + ", ".join(related))

    points = analysis.get("diem_noi_bat") or []
    if points:
        st.markdown("**✨ Điểm nổi bật:**")
        for p in points:
            st.markdown(f"- {p}")


def _pill_row_html(item: dict) -> str:
    category = item.get("category") or core.DEFAULT_CATEGORY
    sentiment = item.get("sentiment") or core.DEFAULT_SENTIMENT
    importance = item.get("importance", core.DEFAULT_IMPORTANCE)
    tags = (item.get("tags") or [])[:4]

    sentiment_icon = {"Positive": "🟢", "Neutral": "⚪", "Negative": "🔴"}.get(sentiment, "⚪")
    pills = f'<span class="pill">{category}</span>'
    pills += f'<span class="pill pill-sentiment-{sentiment}">{sentiment_icon} {sentiment}</span>'
    pills += f'<span class="pill pill-importance">⭐ {importance}/10</span>'
    for t in tags:
        pills += f'<span class="pill pill-tag">🏷️ {t}</span>'
    return f'<div class="pill-row">{pills}</div>'


def render_item_card_open(item: dict, badge_text: str):
    """Mo the item (chua title + pill + badge AI). Dung chung cho news va github."""
    sentiment = item.get("sentiment") or core.DEFAULT_SENTIMENT
    title = item.get("title") or item.get("repo_name", "")
    st.markdown(
        f'<div class="item-card sentiment-{sentiment}">'
        f'<div class="item-title">{title}</div>'
        f'{_pill_row_html(item)}'
        f'<span class="badge-ai">{badge_text}</span>',
        unsafe_allow_html=True,
    )


def render_item_card_close():
    st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# BIỂU ĐỒ (KHOÁ ZOOM/PAN — chỉ giữ tương tác click-mở-link)
# ==========================================
def render_clickable_trend_chart(df: pd.DataFrame):
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
            type: 'bar', orientation: 'h', x: values, y: labels, text: labels,
            textposition: 'auto', hovertext: hovertext, hoverinfo: 'text',
            marker: {{ color: values, colorscale: [[0, '#6C63FF'], [1, '#00D4FF']], line: {{ width: 0 }} }}
        }}];
        var layout = {{
            margin: {{ l: 10, r: 20, t: 10, b: 30 }},
            yaxis: {{ autorange: 'reversed', automargin: true, showgrid: false, fixedrange: true }},
            xaxis: {{ showgrid: false, zeroline: false, title: 'Trend Score', fixedrange: true }},
            dragmode: false,
            plot_bgcolor: 'rgba(0,0,0,0)', paper_bgcolor: 'rgba(0,0,0,0)', font: {{ color: '#EAEAEA' }}
        }};
        // scrollZoom: false + fixedrange = khong the phong to/thu nho hay keo pan bieu do
        Plotly.newPlot('trend-chart', data, layout, {{
            displayModeBar: false, responsive: true, scrollZoom: false, doubleClick: false
        }});
        document.getElementById('trend-chart').on('plotly_click', function(evt) {{
            window.open(links[evt.points[0].pointIndex], '_blank');
        }});
    </script>
    <p style="color:#6C7386; font-size:12px; margin-top:6px;">💡 Nhấp vào một cột để mở repo trong tab mới.</p>
    """
    st.components.v1.html(html_code, height=470)


def render_tag_mindmap(data: list):
    from collections import Counter
    from itertools import combinations

    tag_counts = Counter()
    edge_counts = Counter()
    for item in data:
        tags = list(dict.fromkeys(item.get("tags") or []))
        for t in tags:
            tag_counts[t] += 1
        for a, b in combinations(sorted(tags), 2):
            edge_counts[(a, b)] += 1

    if len(tag_counts) < 2:
        st.caption("Chưa đủ dữ liệu tags để vẽ mind map (cần ít nhất vài bài đã được phân tích AI).")
        return

    top_tags = [t for t, _ in tag_counts.most_common(30)]
    top_tags_set = set(top_tags)
    nodes = [{"id": t, "label": t, "value": tag_counts[t]} for t in top_tags]
    edges = [{"from": a, "to": b, "value": c} for (a, b), c in edge_counts.items()
              if a in top_tags_set and b in top_tags_set and c > 0]

    html_code = f"""
    <div id="mindmap" style="width:100%;height:480px;background:transparent;"></div>
    <script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
    <script>
        var nodes = new vis.DataSet({json.dumps(nodes)});
        var edges = new vis.DataSet({json.dumps(edges)});
        var container = document.getElementById('mindmap');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            nodes: {{
                shape: 'dot', scaling: {{ min: 12, max: 42 }},
                font: {{ color: '#EAEAEA', size: 13, face: 'Inter' }},
                color: {{ background: '#6C63FF', border: '#00D4FF', highlight: {{ background: '#00D4FF' }} }}
            }},
            edges: {{ color: {{ color: 'rgba(140,140,170,0.3)', highlight: '#00D4FF' }}, smooth: {{ type: 'continuous' }} }},
            physics: {{ stabilization: true, barnesHut: {{ gravitationalConstant: -2600, springLength: 105, springConstant: 0.03 }} }},
            interaction: {{ hover: true, tooltipDelay: 100, zoomView: false, dragView: true }}
        }};
        // zoomView: false -> khong the cuon chuot de phong to/thu nho mind map (tranh giat khi cuon trang)
        new vis.Network(container, data, options);
    </script>
    """
    st.components.v1.html(html_code, height=490)


def render_time_filter(prefix: str):
    filter_mode = st.radio(
        "🔍 Chế độ lọc thời gian:",
        ["📅 Theo ngày cụ thể (Lịch)", "📊 Tổng hợp (Tuần/Tháng)"],
        key=f"{prefix}_filter_mode", horizontal=True,
    )
    now = datetime.datetime.now()

    if filter_mode == "📅 Theo ngày cụ thể (Lịch)":
        selected_date = st.date_input("Chọn một ngày:", now.date(), key=f"{prefix}_date")
        start_time = datetime.datetime.combine(selected_date, datetime.time.min).isoformat()
        end_time = datetime.datetime.combine(selected_date, datetime.time.max).isoformat()
        display_title = f"Ngày {selected_date.strftime('%d/%m/%Y')}"
        return {"mode": "date", "start": start_time, "end": end_time,
                "title": display_title, "selected_date": selected_date, "now": now}
    else:
        time_period = st.selectbox("Chọn chu kỳ:", ["Tuần này", "Tháng này"], key=f"{prefix}_period")
        start_time = (now - datetime.timedelta(days=7 if time_period == "Tuần này" else 30)).isoformat()
        end_time = now.isoformat()
        return {"mode": "period", "start": start_time, "end": end_time,
                "title": time_period, "time_period": time_period, "now": now}


# ==========================================
# SEARCH + SMART FILTER + DASHBOARD THỐNG KÊ
# ==========================================
def _get_news_summary_text(item: dict) -> str:
    analysis = item.get("ai_analysis") or {}
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except Exception:
            analysis = {}
    return (analysis.get("tom_tat") or "") if isinstance(analysis, dict) else ""


def render_news_search_and_filter_controls(prefix: str, data: list):
    all_categories = sorted({d.get("category") or core.DEFAULT_CATEGORY for d in data})
    all_sentiments = sorted({d.get("sentiment") or core.DEFAULT_SENTIMENT for d in data})
    all_sources = sorted({d.get("source") or "" for d in data if d.get("source")})
    all_tags = sorted({t for d in data for t in (d.get("tags") or [])})

    search_query = st.text_input(
        "🔎 Tìm kiếm (tiêu đề / tóm tắt / tags / category / nguồn)",
        key=f"{prefix}_search", placeholder="VD: Nvidia, lãi suất, AI chip...",
    )

    with st.expander("⚙️ Smart Filter", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            f_category = st.multiselect("Category", all_categories, key=f"{prefix}_f_category")
            f_sentiment = st.multiselect("Sentiment", all_sentiments, key=f"{prefix}_f_sentiment")
            f_tags = st.multiselect("Tags", all_tags, key=f"{prefix}_f_tags")
        with c2:
            f_source = st.multiselect("Nguồn (source)", all_sources, key=f"{prefix}_f_source",
                                       format_func=lambda u: u[:45] + "..." if len(u) > 45 else u)
            f_importance = st.slider("Importance", 1, 10, (1, 10), key=f"{prefix}_f_importance")

    return {
        "search": search_query.strip().lower(), "category": f_category, "sentiment": f_sentiment,
        "tags": f_tags, "source": f_source, "importance_range": f_importance,
    }


def apply_news_filters(data: list, filters: dict) -> list:
    result = []
    for item in data:
        if filters["category"] and (item.get("category") or core.DEFAULT_CATEGORY) not in filters["category"]:
            continue
        if filters["sentiment"] and (item.get("sentiment") or core.DEFAULT_SENTIMENT) not in filters["sentiment"]:
            continue
        if filters["source"] and (item.get("source") or "") not in filters["source"]:
            continue
        item_tags = item.get("tags") or []
        if filters["tags"] and not set(filters["tags"]).intersection(item_tags):
            continue
        importance = item.get("importance", core.DEFAULT_IMPORTANCE) or core.DEFAULT_IMPORTANCE
        lo, hi = filters["importance_range"]
        if not (lo <= importance <= hi):
            continue
        if filters["search"]:
            haystack = " ".join([
                item.get("title", ""), _get_news_summary_text(item),
                item.get("category", ""), item.get("source", ""), " ".join(item_tags),
            ]).lower()
            if filters["search"] not in haystack:
                continue
        result.append(item)
    return result


def render_news_dashboard_stats(data: list):
    if not data:
        return
    df = pd.DataFrame(data)

    with st.expander("📊 Thống kê tổng quan", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**📂 Category Distribution**")
            st.bar_chart(df["category"].fillna(core.DEFAULT_CATEGORY).value_counts())
        with col2:
            st.markdown("**😊 Sentiment Distribution**")
            st.bar_chart(df["sentiment"].fillna(core.DEFAULT_SENTIMENT).value_counts())
        with col3:
            st.markdown("**⭐ Importance Distribution**")
            st.bar_chart(df["importance"].fillna(core.DEFAULT_IMPORTANCE).astype(int).value_counts().sort_index())

        col4, col5 = st.columns(2)
        with col4:
            st.markdown("**🏷️ Top Tags**")
            tag_series = df["tags"].dropna().explode()
            tag_series = tag_series[tag_series.astype(bool)]
            if len(tag_series) > 0:
                st.bar_chart(tag_series.value_counts().head(10))
            else:
                st.caption("Chưa có tags.")
        with col5:
            st.markdown("**📡 Top Sources**")
            src_counts = df["source"].fillna("Unknown").value_counts().head(10)
            src_counts.index = [s[:35] + "..." if len(s) > 35 else s for s in src_counts.index]
            st.bar_chart(src_counts)

        if "created_at" in df.columns:
            st.markdown("**📅 Số bài viết theo ngày**")
            dates = pd.to_datetime(df["created_at"], errors="coerce").dt.date
            st.bar_chart(dates.value_counts().sort_index())

        st.markdown("**🕸️ Mind Map — mối liên kết giữa các chủ đề/tags**")
        st.caption("Bubble càng lớn = tag xuất hiện càng nhiều. Đường nối = 2 tag cùng xuất hiện trong 1 bài báo.")
        render_tag_mindmap(data)


def render_github_search_control(prefix: str):
    return st.text_input("🔎 Tìm kiếm dự án (tên repo / mô tả)", key=f"{prefix}_search",
                          placeholder="VD: llm, agent, rust...").strip().lower()


def apply_github_search(data: list, query: str) -> list:
    if not query:
        return data
    return [d for d in data if query in f"{d.get('repo_name', '')} {d.get('description', '')}".lower()]


# ==========================================
# 1. HIỂN THỊ GIAO DIỆN NGAY LẬP TỨC (UI FIRST)
# ==========================================

with st.sidebar:
    st.header("⚙️ Bảng Điều Khiển")

    with st.expander("🔗 Quản lý nguồn RSS", expanded=True):
        tab_add, tab_import = st.tabs(["➕ Thêm 1 link", "📥 Quick Import"])

        with tab_add:
            new_link = st.text_input("Link RSS", placeholder="https://vnexpress.net/rss/...")
            if st.button("➕ Thêm nguồn", use_container_width=True):
                ok, msg = add_rss_source(new_link)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

        with tab_import:
            rss_text = st.text_area(
                "Dán nhiều link (mỗi dòng một link)", height=180,
                placeholder="https://vnexpress.net/rss/kinh-doanh.rss\nhttps://vnexpress.net/rss/the-gioi.rss\nhttps://techcrunch.com/feed",
            )
            if st.button("🚀 Import tất cả", use_container_width=True):
                imported = duplicated = invalid = 0
                for url in [u.strip() for u in rss_text.splitlines() if u.strip()]:
                    if not url.startswith(("http://", "https://")):
                        invalid += 1
                        continue
                    ok, _ = add_rss_source(url)
                    imported += ok
                    duplicated += (not ok)
                st.success(f"✅ Imported: {imported}\n\n🔁 Duplicate: {duplicated}\n\n❌ Invalid: {invalid}")
                st.rerun()

        st.divider()
        sources = get_active_rss_sources()
        st.caption(f"📡 Đang theo dõi **{len(sources)}** nguồn RSS")
        if not sources:
            st.info("Chưa có nguồn RSS nào.")
        else:
            for src in sources:
                c1, c2, c3 = st.columns([5, 1, 1])
                with c1:
                    display = src["url"]
                    st.text(display[:42] + "..." if len(display) > 45 else display)
                with c2:
                    if st.button("🔍", key=f"check_{src['id']}"):
                        is_ok = check_rss_status(src["url"])
                        (st.success if is_ok else st.error)(
                            "RSS hoạt động" if is_ok else "RSS lỗi hoặc không còn tồn tại"
                        )
                with c3:
                    if st.button("🗑️", key=f"del_{src['id']}"):
                        delete_rss_source(src["id"])
                        st.rerun()

    st.divider()
    st.caption(
        "🕒 Dữ liệu được **GitHub Actions cào & phân tích tự động mỗi 20 phút**, "
        "không phụ thuộc việc bạn có mở app hay không. Nút bên dưới chỉ để chạy thử/kiểm tra ngay."
    )
    manual_run = st.button("▶️ Chạy cào dữ liệu ngay (thủ công)", use_container_width=True)

    last_sync = get_last_sync_time()
    status_placeholder = st.empty()
    if last_sync:
        status_placeholder.success(f"✅ Dữ liệu mới nhất trong DB: {last_sync.strftime('%H:%M:%S %d/%m/%Y')}")
    else:
        status_placeholder.info("Chưa có dữ liệu nào trong DB.")

    manual_log = st.session_state.get("manual_run_log", [])
    with st.expander(f"🐞 Log lần chạy thủ công gần nhất ({len(manual_log)})", expanded=False):
        if not manual_log:
            st.caption("Chưa chạy thủ công lần nào trong phiên này.")
        else:
            for entry in reversed(manual_log[-10:]):
                st.caption(entry)

if manual_run:
    with st.spinner("Đang cào + phân tích ngay (có thể mất 1-2 phút tùy số lượng bài mới)..."):
        try:
            links = [s["url"] for s in get_active_rss_sources() if s.get("is_active", True)]
            news_count = core.fetch_and_save_news(supabase, groq_client, links) if links else 0
            git_count = core.fetch_and_save_github(supabase, groq_client)
            st.session_state["manual_run_log"].append(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] OK — {news_count} bài mới, {git_count} repo mới."
            )
            st.success(f"✅ Xong! {news_count} bài báo mới, {git_count} dự án GitHub mới.")
        except Exception as e:
            st.session_state["manual_run_log"].append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] LỖI: {e}")
            st.error(f"🔴 Lỗi khi chạy: {e}")
        st.session_state["manual_run_log"] = st.session_state["manual_run_log"][-30:]

# --- TABS (mỗi tab có bộ lọc thời gian RIÊNG) ---
tab1, tab2 = st.tabs(["📰 Tin tức & Báo chí", "🔥 Top 10 GitHub Trending"])

# TAB 1: TIN TỨC
with tab1:
    news_filter = render_time_filter("news")
    st.subheader(f"Phân tích Báo chí ({news_filter['title']})")

    news_response = (
        supabase.table("news").select("*")
        .gte("created_at", news_filter["start"]).lte("created_at", news_filter["end"])
        .order("created_at", desc=True).execute()
    )
    news_data = news_response.data

    render_news_dashboard_stats(news_data)

    news_filters = render_news_search_and_filter_controls("news", news_data)
    filtered_news = apply_news_filters(news_data, news_filters)

    pos = sum(1 for d in news_data if (d.get("sentiment") or core.DEFAULT_SENTIMENT) == "Positive")
    high_impact = sum(1 for d in news_data if (d.get("importance") or 0) >= 8)
    render_kpi_row([
        {"label": "Tổng bài viết", "value": f"{len(filtered_news)}/{len(news_data)}", "sub": "đang hiển thị / tổng"},
        {"label": "Nguồn RSS", "value": str(len(sources)), "sub": "đang theo dõi"},
        {"label": "Tích cực (Positive)", "value": str(pos), "sub": f"{round(pos/len(news_data)*100) if news_data else 0}% tổng số"},
        {"label": "Mức độ cao (≥8/10)", "value": str(high_impact), "sub": "bài quan trọng"},
    ])

    if filtered_news:
        for item in filtered_news:
            render_item_card_open(item, "🤖 Phân tích AI — đọc được kể cả khi bài gốc bị xóa")
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
            render_item_card_close()
    else:
        st.info("Không tìm thấy bài viết nào khớp với bộ lọc / từ khóa tìm kiếm hiện tại.")

# TAB 2: GITHUB TRENDING
with tab2:
    git_filter = render_time_filter("github")
    st.subheader(f"Dự án Công nghệ Nổi bật ({git_filter['title']})")

    if git_filter["mode"] == "date":
        git_response = (
            supabase.table("github_trending").select("*")
            .eq("fetched_date", git_filter["selected_date"].isoformat()).eq("period", "daily")
            .order("created_at", desc=True).limit(10).execute()
        )
    else:
        period_val = "weekly" if git_filter["time_period"] == "Tuần này" else "monthly"
        past_date = (git_filter["now"].date() - datetime.timedelta(days=7 if period_val == "weekly" else 30)).isoformat()
        git_response = (
            supabase.table("github_trending").select("*")
            .eq("period", period_val).gte("fetched_date", past_date)
            .order("fetched_date", desc=True).execute()
        )

    git_data = git_response.data
    git_search_query = render_github_search_control("github")
    git_data = apply_github_search(git_data, git_search_query)

    if git_data:
        df = pd.DataFrame(git_data)
        df = df.drop_duplicates(subset=["repo_link"]).head(10)
        df["Trend Score"] = range(len(df), 0, -1)

        render_kpi_row([
            {"label": "Dự án nổi bật", "value": str(len(df)), "sub": git_filter["title"]},
            {"label": "Trend Score cao nhất", "value": str(int(df["Trend Score"].max())), "sub": df.iloc[0]["repo_name"][:20]},
        ])
        render_clickable_trend_chart(df)

        st.write("### Chi tiết các dự án:")
        for item in df.to_dict("records"):
            render_item_card_open(item, "🤖 Phân tích AI")
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
            render_item_card_close()
    else:
        st.warning(
            "Chưa có dữ liệu cho mốc thời gian này (hoặc không khớp từ khóa tìm kiếm). "
            "*(Lưu ý: Dữ liệu của những ngày trước khi tạo hệ thống sẽ không tồn tại).*"
        )
