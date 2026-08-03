import streamlit as st
import requests
import feedparser
import datetime
import json
from collections import Counter
from itertools import combinations

import pandas as pd
from supabase import create_client, Client
from groq import Groq

import core  # toan bo logic cao + phan tich AI, dung chung voi scraper.py (GitHub Actions)

# ==========================================
# CẤU HÌNH TRANG
# ==========================================
st.set_page_config(
    page_title="AI Trend Terminal",
    layout="wide",
    page_icon="📈",
    initial_sidebar_state="expanded",
)

# ==========================================
# DESIGN TOKENS (dùng lại xuyên suốt mọi CSS/JS trong file)
# ==========================================
BG = "#0B0F1A"
PANEL_FROM = "#131A2B"
PANEL_TO = "#0D1220"
BORDER = "rgba(255,255,255,0.07)"
TEXT = "#F2F4F8"
TEXT_DIM = "#8A93A8"
TEXT_DIMMER = "#5B6272"
VIOLET = "#6C63FF"
BLUE = "#4C8DFF"
CYAN = "#00D4FF"
GREEN = "#22C55E"
RED = "#EF4444"
AMBER = "#F59E0B"

SENTIMENT_COLOR = {"Positive": GREEN, "Neutral": TEXT_DIM, "Negative": RED}
SENTIMENT_ICON = {"Positive": "🟢", "Neutral": "⚪", "Negative": "🔴"}

# ==========================================
# CSS TOÀN CỤC
# ==========================================
st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; font-size: 15.5px; }}
    .mono {{ font-family: 'JetBrains Mono', monospace; }}
    .stApp {{ background-color: {BG}; }}
    #MainMenu, footer, header[data-testid="stHeader"] {{ background: transparent; }}
    .block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1440px; }}

    /* ---------- Sidebar / nav rail ---------- */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #0D1220 0%, #0A0E18 100%);
        border-right: 1px solid {BORDER};
    }}
    section[data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}
    .brand {{ display:flex; align-items:center; gap:10px; padding: 4px 4px 18px 4px; margin-bottom: 6px; border-bottom: 1px solid {BORDER}; }}
    .brand-badge {{
        width:34px; height:34px; border-radius:10px; flex-shrink:0;
        background: linear-gradient(135deg, {VIOLET}, {CYAN});
        display:flex; align-items:center; justify-content:center; font-size:16px;
    }}
    .brand-name {{ color:{TEXT}; font-weight:800; font-size:15px; letter-spacing:-0.2px; line-height:1.2; }}
    .brand-sub {{ color:{TEXT_DIM}; font-size:10.5px; font-weight:600; letter-spacing:0.3px; }}

    section[data-testid="stSidebar"] div[data-testid="stButton"] button {{
        width: 100%; text-align: left; justify-content: flex-start;
        background: transparent; border: 1px solid transparent; color: {TEXT_DIM};
        font-weight: 600; font-size: 13.5px; padding: 9px 12px; border-radius: 10px;
        box-shadow: none; transition: background 0.15s ease, color 0.15s ease;
    }}
    section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {{
        background: rgba(255,255,255,0.05); color: {TEXT}; border-color: {BORDER};
    }}
    section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {{
        background: linear-gradient(90deg, rgba(108,99,255,0.18), rgba(0,212,255,0.08));
        color: {TEXT}; border: 1px solid rgba(108,99,255,0.4);
    }}
    section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"]:hover {{
        background: linear-gradient(90deg, rgba(108,99,255,0.24), rgba(0,212,255,0.12));
    }}
    .sidebar-footer-box {{
        margin-top: 14px; padding: 12px 13px; border-radius: 12px;
        background: rgba(255,255,255,0.03); border: 1px solid {BORDER};
    }}
    .sync-dot {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:{GREEN}; margin-right:6px;
        box-shadow: 0 0 6px {GREEN}; }}
    .sync-label {{ font-size: 11px; color:{TEXT_DIM}; font-weight:600; }}
    .sync-value {{ font-size: 12.5px; color:{TEXT}; font-weight:700; margin-top:2px; }}

    /* ---------- Page header ---------- */
    .page-header {{ display:flex; align-items:flex-end; justify-content:space-between; margin-bottom: 22px; flex-wrap: wrap; gap: 12px; }}
    .page-title {{ color:{TEXT}; font-size: 26px; font-weight: 800; letter-spacing:-0.3px; margin:0; display:flex; align-items:center; gap:10px;}}
    .page-subtitle {{ color:{TEXT_DIM}; font-size: 14px; font-weight:500; margin-top: 5px; }}
    .header-chip {{
        background: {PANEL_FROM}; border: 1px solid {BORDER}; border-radius: 999px;
        padding: 7px 14px; font-size: 12.5px; font-weight:600; color:{TEXT_DIM};
    }}

    /* ---------- KPI cards ---------- */
    .kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }}
    .kpi-card {{
        background: linear-gradient(180deg, {PANEL_FROM} 0%, {PANEL_TO} 100%);
        border: 1px solid {BORDER}; border-radius: 14px; padding: 16px 18px;
    }}
    .kpi-label {{ font-size: 12px; color: {TEXT_DIM}; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }}
    .kpi-value {{ font-family:'JetBrains Mono',monospace; font-size: 27px; color: {TEXT}; font-weight: 700; margin-top: 7px; }}
    .kpi-sub {{ font-size: 12.5px; font-weight: 600; margin-top: 5px; color:{TEXT_DIM}; }}
    .kpi-sub.up {{ color: {GREEN}; }}
    .kpi-sub.down {{ color: {RED}; }}

    /* ---------- Generic panel/card ---------- */
    .panel-card {{
        background: linear-gradient(160deg, {PANEL_FROM} 0%, {PANEL_TO} 100%);
        border: 1px solid {BORDER}; border-radius: 16px; padding: 18px 20px; margin-bottom: 16px;
    }}
    .panel-card-title {{ font-size: 14px; font-weight: 800; color:{TEXT}; margin-bottom: 4px; letter-spacing:0.2px; }}
    .panel-card-sub {{ font-size: 12.5px; color:{TEXT_DIMMER}; margin-bottom: 12px; }}

    /* ---------- item card (bai bao / repo) ---------- */
    .item-card {{
        background: #10161F; border: 1px solid {BORDER}; border-left: 3px solid {VIOLET};
        border-radius: 12px; padding: 18px 20px; margin-bottom: 14px;
    }}
    .item-card.sentiment-Positive {{ border-left-color: {GREEN}; }}
    .item-card.sentiment-Negative {{ border-left-color: {RED}; }}
    .item-card.sentiment-Neutral  {{ border-left-color: {TEXT_DIM}; }}
    .item-title {{ font-size: 17px; font-weight: 700; color: {TEXT}; margin: 0 0 8px 0; line-height: 1.45; }}
    .item-rank {{ font-family:'JetBrains Mono',monospace; color:{TEXT_DIM}; font-size:12.5px; margin-right:8px; }}

    .pill-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
    .pill {{ font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 999px; background: rgba(108,99,255,0.14); color: #A79BFF; }}
    .pill-sentiment-Positive {{ background: rgba(34,197,94,0.14); color: #4ADE80; }}
    .pill-sentiment-Negative {{ background: rgba(239,68,68,0.14); color: #F87171; }}
    .pill-sentiment-Neutral  {{ background: rgba(138,147,168,0.14); color: #B3BACB; }}
    .pill-importance {{ background: rgba(0,212,255,0.14); color: #5FDFFF; }}
    .pill-tag {{ background: rgba(255,255,255,0.06); color: #C7CCDA; }}

    .badge-ai {{ display: inline-block; background: rgba(108,99,255,0.12); color: #A79BFF; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 600; margin-bottom: 10px; }}
    .impact-box {{ background: rgba(0,212,255,0.06); border-left: 3px solid {CYAN}; padding: 10px 14px; border-radius: 8px; margin: 10px 0; font-size: 14px; color: #D7DCE8; }}
    .detail-box {{ background: rgba(255,255,255,0.03); border-left: 3px solid {VIOLET}; padding: 12px 14px; border-radius: 8px; font-size: 14px; line-height: 1.7; color: #C7CCDA; }}

    div[data-testid="stMetric"] {{ background: rgba(120,120,140,0.08); border-radius: 12px; padding: 14px 16px; }}
    div[data-testid="stVegaLiteChart"] .vega-actions {{ display: none !important; }}

    /* ---------- rising topic row ---------- */
    .topic-row {{ display:flex; align-items:center; gap:10px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }}
    .topic-row:last-child {{ border-bottom:none; }}
    .topic-rank {{ width:20px; height:20px; border-radius:6px; background:rgba(108,99,255,0.14); color:#A79BFF; font-size:11.5px; font-weight:800; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
    .topic-name {{ font-size:13.5px; color:{TEXT}; font-weight:600; flex:1; }}
    .topic-count {{ font-family:'JetBrains Mono',monospace; font-size:12.5px; color:{TEXT_DIM}; font-weight:700; }}

    /* ---------- heatmap ---------- */
    .heat-wrap {{ overflow-x:auto; }}
    .heat-table {{ border-collapse: collapse; width:100%; }}
    .heat-table td, .heat-table th {{ text-align:center; font-size:11px; padding:4px; }}
    .heat-table th {{ color:{TEXT_DIMMER}; font-weight:600; }}
    .heat-cat {{ text-align:left !important; color:{TEXT_DIM}; font-weight:600; font-size:11.5px; padding-right:8px !important; white-space:nowrap; }}
    .heat-cell {{ width:34px; height:22px; border-radius:5px; font-family:'JetBrains Mono',monospace; font-size:10px; display:flex; align-items:center; justify-content:center; }}

    /* ---------- RSS source row ---------- */
    .rss-row {{ display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:10px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); margin-bottom:8px; }}
    .rss-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
    .rss-name {{ font-size:13.5px; color:{TEXT}; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .rss-url {{ font-size:11px; color:{TEXT_DIMMER}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}

    /* nav badge for filter radios rendered horizontally */
    div[role="radiogroup"] {{ gap: 4px; }}
</style>
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
if "page" not in st.session_state:
    st.session_state["page"] = "dashboard"

# ==========================================
# QUẢN LÝ NGUỒN RSS + TIỆN ÍCH DÙNG CHUNG
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


def toggle_rss_source(source_id, is_active: bool):
    try:
        supabase.table("rss_sources").update({"is_active": not is_active}).eq("id", source_id).execute()
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


def _format_relative(ts_str: str) -> str:
    try:
        ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        diff = now - ts
        mins = int(diff.total_seconds() // 60)
        if mins < 60:
            return f"{max(mins, 0)} phút trước"
        hours = mins // 60
        if hours < 24:
            return f"{hours} giờ trước"
        return f"{hours // 24} ngày trước"
    except Exception:
        return ""


def _delta_html(current: float, previous: float, suffix: str = "") -> str:
    """Tra ve HTML span the hien % thay doi so voi ky truoc (▲/▼ + mau)."""
    if previous == 0:
        if current == 0:
            return '<div class="kpi-sub">Chưa có dữ liệu kỳ trước</div>'
        return '<div class="kpi-sub up">▲ Mới so với kỳ trước</div>'
    pct = round(((current - previous) / previous) * 100, 1)
    cls = "up" if pct >= 0 else "down"
    arrow = "▲" if pct >= 0 else "▼"
    return f'<div class="kpi-sub {cls}">{arrow} {abs(pct)}% {suffix}</div>'


# ==========================================
# COMPONENT DÙNG CHUNG
# ==========================================
def render_page_header(icon: str, title: str, subtitle: str, chip_text: str = None):
    chip_html = f'<div class="header-chip">{chip_text}</div>' if chip_text else ""
    st.markdown(f"""
    <div class="page-header">
        <div>
            <div class="page-title">{icon} {title}</div>
            <div class="page-subtitle">{subtitle}</div>
        </div>
        {chip_html}
    </div>
    """, unsafe_allow_html=True)


def render_kpi_row(items: list):
    """items: list of {label, value, sub_html (optional raw html) or sub (plain text)}"""
    cards_html = ""
    for item in items:
        if "sub_html" in item:
            sub_html = item["sub_html"]
        elif item.get("sub"):
            sub_html = f'<div class="kpi-sub">{item["sub"]}</div>'
        else:
            sub_html = ""
        cards_html += (
            f'<div class="kpi-card"><div class="kpi-label">{item["label"]}</div>'
            f'<div class="kpi-value">{item["value"]}</div>{sub_html}</div>'
        )
    st.markdown(f'<div class="kpi-row">{cards_html}</div>', unsafe_allow_html=True)


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

    sentiment_icon = SENTIMENT_ICON.get(sentiment, "⚪")
    pills = f'<span class="pill">{category}</span>'
    pills += f'<span class="pill pill-sentiment-{sentiment}">{sentiment_icon} {sentiment}</span>'
    pills += f'<span class="pill pill-importance">⭐ {importance}/10</span>'
    for t in tags:
        pills += f'<span class="pill pill-tag">🏷️ {t}</span>'
    return f'<div class="pill-row">{pills}</div>'


def render_item_card_open(item: dict, badge_text: str, rank: int = None):
    sentiment = item.get("sentiment") or core.DEFAULT_SENTIMENT
    title = item.get("title") or item.get("repo_name", "")
    rank_html = f'<span class="item-rank">#{rank}</span>' if rank else ""
    st.markdown(
        f'<div class="item-card sentiment-{sentiment}">'
        f'<div class="item-title">{rank_html}{title}</div>'
        f'{_pill_row_html(item)}'
        f'<span class="badge-ai">{badge_text}</span>',
        unsafe_allow_html=True,
    )


def render_item_card_close():
    st.markdown('</div>', unsafe_allow_html=True)


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


def render_github_search_control(prefix: str):
    return st.text_input("🔎 Tìm kiếm dự án (tên repo / mô tả)", key=f"{prefix}_search",
                          placeholder="VD: llm, agent, rust...").strip().lower()


def apply_github_search(data: list, query: str) -> list:
    if not query:
        return data
    return [d for d in data if query in f"{d.get('repo_name', '')} {d.get('description', '')}".lower()]


# ==========================================
# BIỂU ĐỒ (Chart.js / Plotly / vis-network — nhúng qua components.v1.html)
# ==========================================
def render_donut_with_center(canvas_id: str, labels: list, values: list, colors: list,
                              center_value: str, center_label: str, height: int = 210):
    html_code = f"""
    <div style="position:relative; height:{height}px;">
        <canvas id="{canvas_id}"></canvas>
        <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:none;">
            <div style="font-size:22px; font-weight:800; color:{TEXT};">{center_value}</div>
            <div style="font-size:10.5px; color:{TEXT_DIM}; font-weight:600;">{center_label}</div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <script>
        new Chart(document.getElementById('{canvas_id}'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{ data: {json.dumps(values)}, backgroundColor: {json.dumps(colors)}, borderWidth: 0 }}]
            }},
            options: {{
                responsive: true, maintainAspectRatio: false, cutout: '72%',
                plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '{TEXT_DIM}', boxWidth: 8, padding: 8, font: {{ size: 10.5 }} }} }} }}
            }}
        }});
    </script>
    """
    st.components.v1.html(html_code, height=height + 40)


def render_line_chart(canvas_id: str, labels: list, values: list, height: int = 230, label: str = ""):
    html_code = f"""
    <canvas id="{canvas_id}" height="{height}"></canvas>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
    <script>
        Chart.defaults.color = '{TEXT_DIM}';
        Chart.defaults.font.size = 10.5;
        new Chart(document.getElementById('{canvas_id}'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: '{label}', data: {json.dumps(values)},
                    borderColor: '{CYAN}', backgroundColor: 'rgba(0,212,255,0.12)',
                    tension: 0.35, fill: true, pointRadius: 2, borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true, plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ grid: {{ display: false }} }},
                    y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, beginAtZero: true, ticks: {{ precision: 0 }} }}
                }}
            }}
        }});
    </script>
    """
    st.components.v1.html(html_code, height=height + 30)


def render_clickable_trend_chart(df: pd.DataFrame):
    labels = json.dumps(df["repo_name"].tolist())
    values = json.dumps(df["Trend Score"].tolist())
    links = json.dumps(df["repo_link"].tolist())
    hover = json.dumps([d[:90] for d in df["description"].tolist()])

    html_code = f"""
    <div id="trend-chart" style="width:100%;height:420px;"></div>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <script>
        var labels = {labels};
        var values = {values};
        var links = {links};
        var hovertext = {hover};
        var data = [{{
            type: 'bar', orientation: 'h', x: values, y: labels, text: labels,
            textposition: 'auto', hovertext: hovertext, hoverinfo: 'text',
            marker: {{ color: values, colorscale: [[0, '{VIOLET}'], [1, '{CYAN}']], line: {{ width: 0 }} }}
        }}];
        var layout = {{
            margin: {{ l: 10, r: 20, t: 10, b: 30 }},
            yaxis: {{ autorange: 'reversed', automargin: true, showgrid: false, fixedrange: true, color: '{TEXT_DIM}' }},
            xaxis: {{ showgrid: false, zeroline: false, title: 'Trend Score', fixedrange: true, color: '{TEXT_DIM}' }},
            dragmode: false,
            plot_bgcolor: 'rgba(0,0,0,0)', paper_bgcolor: 'rgba(0,0,0,0)', font: {{ color: '{TEXT_DIM}' }}
        }};
        Plotly.newPlot('trend-chart', data, layout, {{
            displayModeBar: false, responsive: true, scrollZoom: false, doubleClick: false
        }});
        document.getElementById('trend-chart').on('plotly_click', function(evt) {{
            window.open(links[evt.points[0].pointIndex], '_blank');
        }});
    </script>
    <p style="color:{TEXT_DIMMER}; font-size:12px; margin-top:6px;">💡 Nhấp vào một cột để mở repo trong tab mới.</p>
    """
    st.components.v1.html(html_code, height=460)


def _build_tag_graph(data: list):
    tag_counts = Counter()
    edge_counts = Counter()
    for item in data:
        tags = list(dict.fromkeys(item.get("tags") or []))
        for t in tags:
            tag_counts[t] += 1
        for a, b in combinations(sorted(tags), 2):
            edge_counts[(a, b)] += 1
    return tag_counts, edge_counts


def render_tag_mindmap(data: list, height: int = 520):
    tag_counts, edge_counts = _build_tag_graph(data)

    if len(tag_counts) < 2:
        st.caption("Chưa đủ dữ liệu tags để vẽ mind map (cần ít nhất vài bài đã được phân tích AI).")
        return

    top_tags = [t for t, _ in tag_counts.most_common(40)]
    top_tags_set = set(top_tags)
    nodes = [{"id": t, "label": t, "value": tag_counts[t]} for t in top_tags]
    edges = [{"from": a, "to": b, "value": c} for (a, b), c in edge_counts.items()
              if a in top_tags_set and b in top_tags_set and c > 0]

    html_code = f"""
    <div id="mindmap" style="width:100%;height:{height}px;background:transparent;"></div>
    <script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
    <script>
        var nodes = new vis.DataSet({json.dumps(nodes)});
        var edges = new vis.DataSet({json.dumps(edges)});
        var container = document.getElementById('mindmap');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            nodes: {{
                shape: 'dot', scaling: {{ min: 12, max: 46 }},
                font: {{ color: '{TEXT}', size: 13, face: 'Inter' }},
                color: {{ background: '{VIOLET}', border: '{CYAN}', highlight: {{ background: '{CYAN}' }} }}
            }},
            edges: {{ color: {{ color: 'rgba(140,140,170,0.3)', highlight: '{CYAN}' }}, smooth: {{ type: 'continuous' }} }},
            physics: {{ stabilization: true, barnesHut: {{ gravitationalConstant: -2600, springLength: 105, springConstant: 0.03 }} }},
            interaction: {{ hover: true, tooltipDelay: 100, zoomView: false, dragView: true }}
        }};
        new vis.Network(container, data, options);
    </script>
    """
    st.components.v1.html(html_code, height=height + 10)


# ==========================================
# TRANG: DASHBOARD (Trading Terminal Dashboard)
# ==========================================
def render_dashboard_page():
    now = datetime.datetime.now(datetime.timezone.utc)
    week_ago = now - datetime.timedelta(days=7)
    prev_week_ago = now - datetime.timedelta(days=14)
    today_str = datetime.date.today().isoformat()
    yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    try:
        news_7d = supabase.table("news").select(
            "title,category,sentiment,tags,source,link,created_at"
        ).gte("created_at", week_ago.isoformat()).order("created_at", desc=True).execute().data
    except Exception:
        news_7d = []

    try:
        news_prev_7d = supabase.table("news").select("sentiment,created_at").gte(
            "created_at", prev_week_ago.isoformat()
        ).lt("created_at", week_ago.isoformat()).execute().data
    except Exception:
        news_prev_7d = []

    try:
        git_today = supabase.table("github_trending").select("repo_name").eq(
            "period", "daily"
        ).eq("fetched_date", today_str).execute().data
    except Exception:
        git_today = []

    try:
        git_yesterday = supabase.table("github_trending").select("repo_name").eq(
            "period", "daily"
        ).eq("fetched_date", yesterday_str).execute().data
    except Exception:
        git_yesterday = []

    try:
        rss_total = len(supabase.table("rss_sources").select("id").execute().data)
    except Exception:
        rss_total = 0

    last_sync = get_last_sync_time()
    chip = f"🟢 Đồng bộ gần nhất: {_format_relative(last_sync.isoformat())}" if last_sync else "⚪ Chưa có dữ liệu"
    render_page_header("📊", "Trading Terminal Dashboard", "Tổng quan toàn bộ dữ liệu & xu hướng thị trường công nghệ — 7 ngày qua", chip)

    total_articles = len(news_7d)
    total_prev = len(news_prev_7d)
    category_counts = Counter(n.get("category") or core.DEFAULT_CATEGORY for n in news_7d)
    sentiment_counts = Counter(n.get("sentiment") or core.DEFAULT_SENTIMENT for n in news_7d)
    prev_sentiment_counts = Counter(n.get("sentiment") or core.DEFAULT_SENTIMENT for n in news_prev_7d)
    pos_pct = round((sentiment_counts.get("Positive", 0) / total_articles) * 100) if total_articles else 0
    prev_pos_pct = round((prev_sentiment_counts.get("Positive", 0) / total_prev) * 100) if total_prev else 0

    # ---------- KPI row ----------
    render_kpi_row([
        {"label": "Tổng bài viết", "value": f"{total_articles:,}", "sub_html": _delta_html(total_articles, total_prev, "so với tuần trước")},
        {"label": "Nguồn RSS", "value": str(rss_total), "sub": "đang hoạt động"},
        {"label": "GitHub Trending", "value": str(len(git_today)), "sub_html": _delta_html(len(git_today), len(git_yesterday), "so với hôm qua")},
        {"label": "Sentiment tích cực", "value": f"{pos_pct}%", "sub_html": _delta_html(pos_pct, prev_pos_pct, "so với tuần trước")},
    ])

    # ---------- charts row: trend line / category donut / sentiment donut ----------
    day_buckets = {(now.date() - datetime.timedelta(days=i)): 0 for i in range(6, -1, -1)}
    for n in news_7d:
        try:
            d = datetime.datetime.fromisoformat(n["created_at"].replace("Z", "+00:00")).date()
            if d in day_buckets:
                day_buckets[d] += 1
        except Exception:
            pass
    trend_labels = [d.strftime("%d/%m") for d in day_buckets]
    trend_values = list(day_buckets.values())

    top_categories = category_counts.most_common(5)
    cat_labels = [c for c, _ in top_categories] or ["Chưa có dữ liệu"]
    cat_values = [v for _, v in top_categories] or [1]

    sent_labels = ["Positive", "Neutral", "Negative"]
    sent_values = [sentiment_counts.get(s, 0) for s in sent_labels]
    if sum(sent_values) == 0:
        sent_values = [1, 0, 0]

    col1, col2, col3 = st.columns([1.3, 1, 1])
    with col1:
        st.markdown('<div class="panel-card"><div class="panel-card-title">Xu hướng bài viết theo thời gian</div>'
                     '<div class="panel-card-sub">Số bài viết mới mỗi ngày, 7 ngày gần nhất</div></div>', unsafe_allow_html=True)
        render_line_chart("trendLine", trend_labels, trend_values, height=210, label="Bài viết")
    with col2:
        st.markdown('<div class="panel-card"><div class="panel-card-title">Phân bố theo Category</div>'
                     '<div class="panel-card-sub">Top 5 chuyên mục nổi bật</div></div>', unsafe_allow_html=True)
        render_donut_with_center("catDonut", cat_labels, cat_values, [VIOLET, BLUE, CYAN, AMBER, GREEN],
                                  f"{total_articles:,}", "Tổng số")
    with col3:
        st.markdown('<div class="panel-card"><div class="panel-card-title">Sentiment Distribution</div>'
                     '<div class="panel-card-sub">Cảm xúc thị trường trong tin tức</div></div>', unsafe_allow_html=True)
        render_donut_with_center("sentDonut", sent_labels, sent_values, [GREEN, TEXT_DIM, RED],
                                  f"{pos_pct}%", "Tích cực")

    # ---------- news + sources row ----------
    latest_news = news_7d[:6]
    source_counts = Counter((n.get("source") or "Unknown") for n in news_7d).most_common(6)
    max_src = max((c for _, c in source_counts), default=1)

    col4, col5 = st.columns([1.2, 1])
    with col4:
        st.markdown('<div class="panel-card"><div class="panel-card-title">📰 Tin tức mới nhất</div></div>', unsafe_allow_html=True)
        if latest_news:
            rows = "".join(
                f'<a href="{n.get("link", "#")}" target="_blank" '
                f'style="display:flex;align-items:center;gap:10px;padding:9px 4px;text-decoration:none;'
                f'border-bottom:1px solid rgba(255,255,255,0.04);">'
                f'<span style="width:7px;height:7px;border-radius:50%;flex-shrink:0;'
                f'background:{SENTIMENT_COLOR.get(n.get("sentiment") or core.DEFAULT_SENTIMENT, TEXT_DIM)};"></span>'
                f'<span style="font-size:13px;color:#DDE1EC;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{(n.get("title") or "")[:70]}</span>'
                f'<span style="font-size:11px;color:{TEXT_DIMMER};flex-shrink:0;">{_format_relative(n.get("created_at",""))}</span></a>'
                for n in latest_news
            )
            st.markdown(f'<div>{rows}</div>', unsafe_allow_html=True)
        else:
            st.caption("Chưa có bài viết trong 7 ngày qua.")
    with col5:
        st.markdown('<div class="panel-card"><div class="panel-card-title">📡 Top nguồn tin</div></div>', unsafe_allow_html=True)
        if source_counts:
            rows = "".join(
                f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
                f'<span style="font-size:11.5px;color:#C7CCDA;width:120px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{(s.split("//")[-1].split("/")[0])[:26]}</span>'
                f'<div style="flex:1;height:7px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden;">'
                f'<div style="height:100%;border-radius:4px;width:{round((c/max_src)*100)}%;background:linear-gradient(90deg,{VIOLET},{CYAN});"></div></div>'
                f'<span class="mono" style="font-size:11.5px;color:{TEXT_DIM};width:24px;text-align:right;">{c}</span></div>'
                for s, c in source_counts
            )
            st.markdown(f'<div>{rows}</div>', unsafe_allow_html=True)
        else:
            st.caption("Chưa có dữ liệu nguồn.")

    # ---------- category activity heatmap (real data, thay cho "market heatmap") ----------
    st.markdown('<div class="panel-card"><div class="panel-card-title">🗓️ Bản đồ hoạt động theo Category (7 ngày)</div>'
                 '<div class="panel-card-sub">Màu càng đậm = số bài viết trong category đó, ngày đó càng nhiều</div></div>', unsafe_allow_html=True)
    top5_cats = [c for c, _ in category_counts.most_common(5)]
    if top5_cats:
        day_list = list(day_buckets.keys())
        cat_day_counts = {c: {d: 0 for d in day_list} for c in top5_cats}
        for n in news_7d:
            cat = n.get("category") or core.DEFAULT_CATEGORY
            if cat not in cat_day_counts:
                continue
            try:
                d = datetime.datetime.fromisoformat(n["created_at"].replace("Z", "+00:00")).date()
                if d in cat_day_counts[cat]:
                    cat_day_counts[cat][d] += 1
            except Exception:
                pass
        max_cell = max((v for row in cat_day_counts.values() for v in row.values()), default=1) or 1
        header_cells = "".join(f"<th>{d.strftime('%d/%m')}</th>" for d in day_list)
        body_rows = ""
        for cat in top5_cats:
            cells = ""
            for d in day_list:
                v = cat_day_counts[cat][d]
                alpha = 0.08 + 0.72 * (v / max_cell) if max_cell else 0.08
                cells += f'<td><div class="heat-cell" style="background:rgba(108,99,255,{alpha:.2f});" title="{v} bài">{v if v else ""}</div></td>'
            body_rows += f'<tr><td class="heat-cat">{cat}</td>{cells}</tr>'
        st.markdown(f"""
        <div class="heat-wrap"><table class="heat-table">
            <tr><th></th>{header_cells}</tr>
            {body_rows}
        </table></div>
        """, unsafe_allow_html=True)
    else:
        st.caption("Chưa có đủ dữ liệu để vẽ heatmap.")

    # ---------- trending keywords ----------
    all_tags = Counter(t for n in news_7d for t in (n.get("tags") or []))
    trending_tags = [t for t, _ in all_tags.most_common(12)]
    st.markdown('<div class="panel-card"><div class="panel-card-title">🔥 Trending Keywords</div></div>', unsafe_allow_html=True)
    if trending_tags:
        tags_html = "".join(f'<span class="pill pill-tag" style="margin-right:6px;">{t}</span>' for t in trending_tags)
        st.markdown(f'<div class="pill-row">{tags_html}</div>', unsafe_allow_html=True)
    else:
        st.caption("Chưa có tags.")


# ==========================================
# TRANG: TIN TỨC & BÁO CHÍ (Trend Intelligence style)
# ==========================================
def render_news_page():
    render_page_header("📰", "Tin tức & Báo chí", "Phân tích xu hướng & tin tức công nghệ, tài chính bằng AI")

    news_filter = render_time_filter("news")

    news_response = (
        supabase.table("news").select("*")
        .gte("created_at", news_filter["start"]).lte("created_at", news_filter["end"])
        .order("created_at", desc=True).execute()
    )
    news_data = news_response.data
    sources = get_active_rss_sources()

    news_filters = render_news_search_and_filter_controls("news", news_data)
    filtered_news = apply_news_filters(news_data, news_filters)

    pos = sum(1 for d in news_data if (d.get("sentiment") or core.DEFAULT_SENTIMENT) == "Positive")
    high_impact = sum(1 for d in news_data if (d.get("importance") or 0) >= 8)
    render_kpi_row([
        {"label": "Tổng bài viết", "value": f"{len(filtered_news)}/{len(news_data)}", "sub": f"đang hiển thị / tổng — {news_filter['title']}"},
        {"label": "Nguồn RSS", "value": str(len(sources)), "sub": "đang theo dõi"},
        {"label": "Tích cực (Positive)", "value": str(pos), "sub": f"{round(pos/len(news_data)*100) if news_data else 0}% tổng số"},
        {"label": "Mức độ cao (≥8/10)", "value": str(high_impact), "sub": "bài quan trọng"},
    ])

    # ---------- rising topics + trend chart ----------
    tag_counts = Counter(t for n in news_data for t in (n.get("tags") or []))
    top_topics = tag_counts.most_common(6)

    day_counts = Counter()
    for n in news_data:
        try:
            d = datetime.datetime.fromisoformat(n["created_at"].replace("Z", "+00:00")).date()
            day_counts[d] += 1
        except Exception:
            pass
    day_sorted = sorted(day_counts.keys())
    if len(day_sorted) > 14:
        day_sorted = day_sorted[-14:]
    trend_labels = [d.strftime("%d/%m") for d in day_sorted] or ["--"]
    trend_values = [day_counts[d] for d in day_sorted] or [0]

    colL, colR = st.columns([1.4, 1])
    with colL:
        st.markdown(f'<div class="panel-card"><div class="panel-card-title">Trend Score Over Time</div>'
                     f'<div class="panel-card-sub">Số bài viết theo ngày trong khoảng: {news_filter["title"]}</div></div>', unsafe_allow_html=True)
        render_line_chart("newsTrendLine", trend_labels, trend_values, height=200, label="Bài viết")
    with colR:
        if top_topics:
            rows = "".join(
                f'<div class="topic-row"><span class="topic-rank">{i+1}</span>'
                f'<span class="topic-name">{t}</span><span class="topic-count">{c} bài</span></div>'
                for i, (t, c) in enumerate(top_topics)
            )
        else:
            rows = '<div style="color:#5B6272;font-size:12px;">Chưa có tags trong khoảng thời gian này.</div>'
        st.markdown(
            '<div class="panel-card"><div class="panel-card-title">🚀 Top Rising Topics</div>'
            '<div class="panel-card-sub">Tags xuất hiện nhiều nhất</div>' + rows + '</div>',
            unsafe_allow_html=True,
        )

    with st.expander("📊 Thống kê chi tiết & Knowledge mini-map", expanded=False):
        if news_data:
            df = pd.DataFrame(news_data)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**📂 Category Distribution**")
                st.bar_chart(df["category"].fillna(core.DEFAULT_CATEGORY).value_counts())
            with c2:
                st.markdown("**😊 Sentiment Distribution**")
                st.bar_chart(df["sentiment"].fillna(core.DEFAULT_SENTIMENT).value_counts())
            with c3:
                st.markdown("**⭐ Importance Distribution**")
                st.bar_chart(df["importance"].fillna(core.DEFAULT_IMPORTANCE).astype(int).value_counts().sort_index())
        else:
            st.caption("Chưa có dữ liệu để thống kê.")

    st.divider()
    st.markdown(f"#### Danh sách bài viết ({len(filtered_news)})")
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


# ==========================================
# TRANG: GITHUB TRENDING
# ==========================================
def render_github_page():
    render_page_header("🔥", "GitHub Trending", "Dự án công nghệ nổi bật, phân tích tiềm năng bằng AI")

    git_filter = render_time_filter("github")

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
            {"label": "Trend Score cao nhất", "value": str(int(df["Trend Score"].max())), "sub": df.iloc[0]["repo_name"][:24]},
            {"label": "Kỳ đang xem", "value": git_filter["title"], "sub": "bộ lọc thời gian"},
            {"label": "Khớp tìm kiếm", "value": str(len(df)), "sub": f'"{git_search_query}"' if git_search_query else "không lọc"},
        ])

        st.markdown('<div class="panel-card"><div class="panel-card-title">Trend Score theo dự án</div>'
                     '<div class="panel-card-sub">Nhấp vào một cột để mở repo</div></div>', unsafe_allow_html=True)
        render_clickable_trend_chart(df)

        st.markdown(f"#### Chi tiết các dự án ({len(df)})")
        for idx, item in enumerate(df.to_dict("records"), start=1):
            render_item_card_open(item, "🤖 Phân tích AI", rank=idx)
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
        render_kpi_row([
            {"label": "Dự án nổi bật", "value": "0", "sub": git_filter["title"]},
            {"label": "Trend Score cao nhất", "value": "—", "sub": "chưa có dữ liệu"},
            {"label": "Kỳ đang xem", "value": git_filter["title"], "sub": "bộ lọc thời gian"},
            {"label": "Khớp tìm kiếm", "value": "0", "sub": f'"{git_search_query}"' if git_search_query else "không lọc"},
        ])
        st.warning(
            "Chưa có dữ liệu cho mốc thời gian này (hoặc không khớp từ khóa tìm kiếm). "
            "*(Lưu ý: Dữ liệu của những ngày trước khi tạo hệ thống sẽ không tồn tại).*"
        )


# ==========================================
# TRANG: KNOWLEDGE GRAPH (mind map giữa các tags)
# ==========================================
def render_graph_page():
    render_page_header("🕸️", "Knowledge Graph", "Mạng lưới kết nối giữa các chủ đề, công nghệ & xu hướng trong tin tức")

    lookback = st.radio("Phạm vi dữ liệu:", ["7 ngày qua", "30 ngày qua", "Toàn bộ"], horizontal=True, key="graph_range")
    now = datetime.datetime.now(datetime.timezone.utc)
    query = supabase.table("news").select("title,category,tags,created_at")
    if lookback == "7 ngày qua":
        query = query.gte("created_at", (now - datetime.timedelta(days=7)).isoformat())
    elif lookback == "30 ngày qua":
        query = query.gte("created_at", (now - datetime.timedelta(days=30)).isoformat())
    try:
        graph_data = query.order("created_at", desc=True).execute().data
    except Exception:
        graph_data = []

    tag_counts, edge_counts = _build_tag_graph(graph_data)

    render_kpi_row([
        {"label": "Node (Tags)", "value": str(len(tag_counts)), "sub": "chủ đề khác nhau"},
        {"label": "Kết nối (Edges)", "value": str(len(edge_counts)), "sub": "cặp tag cùng xuất hiện"},
        {"label": "Bài viết đã phân tích", "value": str(len(graph_data)), "sub": lookback},
        {"label": "Tag phổ biến nhất", "value": (tag_counts.most_common(1)[0][0][:16] if tag_counts else "—"),
         "sub": f"{tag_counts.most_common(1)[0][1]} lần" if tag_counts else "chưa có dữ liệu"},
    ])

    col_graph, col_info = st.columns([2.2, 1])
    with col_graph:
        st.markdown('<div class="panel-card"><div class="panel-card-title">Graph Explorer</div>'
                     '<div class="panel-card-sub">Bubble càng lớn = tag xuất hiện càng nhiều. Đường nối = 2 tag cùng xuất hiện trong 1 bài báo. Kéo để di chuyển, không cuộn để zoom.</div></div>',
                     unsafe_allow_html=True)
        render_tag_mindmap(graph_data, height=560)
    with col_info:
        st.markdown('<div class="panel-card"><div class="panel-card-title">🧭 Legend</div>'
                     f'<div style="display:flex;align-items:center;gap:8px;margin-top:6px;">'
                     f'<span style="width:12px;height:12px;border-radius:50%;background:{VIOLET};display:inline-block;"></span>'
                     f'<span style="font-size:12px;color:{TEXT_DIM};">Chủ đề / Tag</span></div>'
                     f'<div style="display:flex;align-items:center;gap:8px;margin-top:6px;">'
                     f'<span style="width:16px;height:2px;background:rgba(140,140,170,0.6);display:inline-block;"></span>'
                     f'<span style="font-size:12px;color:{TEXT_DIM};">Cùng xuất hiện trong 1 bài</span></div>'
                     '</div>', unsafe_allow_html=True)

        top_tags = tag_counts.most_common(10)
        if top_tags:
            rows = "".join(
                f'<div class="topic-row"><span class="topic-rank">{i+1}</span>'
                f'<span class="topic-name">{t}</span><span class="topic-count">{c}</span></div>'
                for i, (t, c) in enumerate(top_tags)
            )
        else:
            rows = '<div style="color:#5B6272;font-size:12px;">Chưa có dữ liệu tags trong phạm vi đã chọn.</div>'
        st.markdown(
            '<div class="panel-card"><div class="panel-card-title">📈 Top Tags</div>' + rows + '</div>',
            unsafe_allow_html=True,
        )


# ==========================================
# TRANG: NGUỒN DỮ LIỆU & CÀI ĐẶT
# ==========================================
def render_settings_page():
    render_page_header("⚙️", "Nguồn dữ liệu & Cài đặt", "Quản lý nguồn RSS và theo dõi tình trạng đồng bộ dữ liệu")

    last_sync = get_last_sync_time()
    sources = get_active_rss_sources()
    render_kpi_row([
        {"label": "Nguồn RSS", "value": str(len(sources)), "sub": "đang theo dõi"},
        {"label": "Đồng bộ gần nhất", "value": _format_relative(last_sync.isoformat()) if last_sync else "—", "sub": "news + github_trending"},
        {"label": "Chu kỳ tự động", "value": "~20 phút", "sub": "qua GitHub Actions + cron-job.org"},
        {"label": "Lần chạy thủ công", "value": str(len(st.session_state.get("manual_run_log", []))), "sub": "trong phiên này"},
    ])

    col_manage, col_status = st.columns([1.5, 1])

    with col_manage:
        st.markdown('<div class="panel-card"><div class="panel-card-title">🔗 Quản lý nguồn RSS</div></div>', unsafe_allow_html=True)
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
                "Dán nhiều link (mỗi dòng một link)", height=160,
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
                st.success(f"✅ Imported: {imported} — 🔁 Duplicate: {duplicated} — ❌ Invalid: {invalid}")
                st.rerun()

        st.caption(f"📡 Đang theo dõi **{len(sources)}** nguồn RSS")
        if not sources:
            st.info("Chưa có nguồn RSS nào.")
        else:
            for src in sources:
                is_active = src.get("is_active", True)
                dot_color = GREEN if is_active else TEXT_DIMMER
                dot_glow = f"box-shadow:0 0 5px {GREEN};" if is_active else ""
                name = src.get("name") or src["url"]
                st.markdown(
                    f'<div class="rss-row"><span class="rss-dot" style="background:{dot_color};{dot_glow}"></span>'
                    f'<div style="flex:1;min-width:0;"><div class="rss-name">{name}</div>'
                    f'<div class="rss-url">{src["url"]}</div></div></div>',
                    unsafe_allow_html=True,
                )
                c1, c2, c3 = st.columns([1, 1, 1])
                with c1:
                    if st.button("🟢 ON" if is_active else "⚪ OFF", key=f"toggle_{src['id']}", use_container_width=True):
                        toggle_rss_source(src["id"], is_active)
                        st.rerun()
                with c2:
                    if st.button("🔍 Kiểm tra", key=f"check_{src['id']}", use_container_width=True):
                        is_ok = check_rss_status(src["url"])
                        (st.success if is_ok else st.error)(
                            "RSS hoạt động" if is_ok else "RSS lỗi hoặc không còn tồn tại"
                        )
                with c3:
                    if st.button("🗑️ Xoá", key=f"del_{src['id']}", use_container_width=True):
                        delete_rss_source(src["id"])
                        st.rerun()

    with col_status:
        st.markdown('<div class="panel-card"><div class="panel-card-title">🕒 Trạng thái đồng bộ</div>'
                     '<div class="panel-card-sub">Dữ liệu được GitHub Actions cào & phân tích tự động mỗi ~20 phút, không phụ thuộc việc bạn có mở app hay không.</div></div>',
                     unsafe_allow_html=True)
        if last_sync:
            st.success(f"✅ Dữ liệu mới nhất trong DB: {last_sync.strftime('%H:%M:%S %d/%m/%Y')}")
        else:
            st.info("Chưa có dữ liệu nào trong DB.")

        manual_run = st.button("▶️ Chạy cào dữ liệu ngay (thủ công)", use_container_width=True)

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
                    links = [s["url"] for s in sources if s.get("is_active", True)]
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
                st.rerun()


# ==========================================
# SIDEBAR: BRAND + ĐIỀU HƯỚNG
# ==========================================
NAV_ITEMS = [
    ("dashboard", "📊", "Dashboard"),
    ("news", "📰", "Tin tức & Báo chí"),
    ("github", "🔥", "GitHub Trending"),
    ("graph", "🕸️", "Knowledge Graph"),
    ("settings", "⚙️", "Nguồn dữ liệu & Cài đặt"),
]

with st.sidebar:
    st.markdown("""
    <div class="brand">
        <div class="brand-badge">📈</div>
        <div>
            <div class="brand-name">AI Trend Terminal</div>
            <div class="brand-sub">TRACKER &nbsp;•&nbsp; LIVE DATA</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    for key, icon, label in NAV_ITEMS:
        is_active = st.session_state["page"] == key
        if st.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state["page"] = key
            st.rerun()

    _last_sync_sidebar = get_last_sync_time()
    _sync_text = _format_relative(_last_sync_sidebar.isoformat()) if _last_sync_sidebar else "chưa có dữ liệu"
    st.markdown(f"""
    <div class="sidebar-footer-box">
        <div class="sync-label"><span class="sync-dot"></span>ĐỒNG BỘ DỮ LIỆU</div>
        <div class="sync-value">{_sync_text}</div>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# ĐIỀU HƯỚNG TRANG
# ==========================================
PAGE_RENDERERS = {
    "dashboard": render_dashboard_page,
    "news": render_news_page,
    "github": render_github_page,
    "graph": render_graph_page,
    "settings": render_settings_page,
}
PAGE_RENDERERS.get(st.session_state["page"], render_dashboard_page)()
