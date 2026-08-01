"""
core.py
-------
Toan bo logic cao du lieu + phan tich AI, TACH RIENG khoi Streamlit.
Ly do: file main.py cu la mot script Streamlit (dung st.cache_data, st.sidebar...),
nen khi GitHub Actions chay "python main.py" moi 10 phut, logic cao du lieu
KHONG duoc dam bao thuc thi dung/on dinh (nhieu ham st.* khong hoat dong binh
thuong khi chay ngoai "streamlit run"). Day la nguyen nhan chinh khien du lieu
chi thuc su cap nhat khi ban tu mo app tren trinh duyet.

core.py khong import streamlit, nen co the chay boi:
- scraper.py qua GitHub Actions (cron doc lap, khong can ai mo app)
- main.py (nut "Chay ngay" thu cong, dung de test)
"""

import datetime
import json
import random
import threading
import time

import feedparser
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client, Client
from groq import Groq

# ==========================================
# CẤU HÌNH CHUNG
# ==========================================
MAX_WORKERS = 15                 # so thread song song khi cao RSS
ANALYSIS_WORKERS = 3             # so thread song song khi goi Groq (giam vi da gop batch)
BATCH_SIZE = 4                   # so bai bao / repo gop chung trong 1 lan goi Groq
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_MAX_RETRIES = 4
GROQ_MAX_TOKENS_PER_ITEM = 350   # ngan sach output UOC LUONG cho MOI item trong 1 batch

DEFAULT_CATEGORY = "Other"
DEFAULT_SENTIMENT = "Neutral"
DEFAULT_IMPORTANCE = 5
MAX_TAGS = 5

VALID_CATEGORIES = {
    "AI", "Startup", "Finance", "Stock", "Crypto", "Cloud",
    "Cybersecurity", "Science", "Healthcare", "Semiconductor",
    "Robotics", "Energy", "Space", "Gaming", "Education",
    "Government", "Biotech", "Other",
}
VALID_SENTIMENTS = {"Positive", "Neutral", "Negative"}


def create_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


def create_groq_client(api_key: str) -> Groq:
    return Groq(api_key=api_key)


# ==========================================
# GIỚI HẠN TỐC ĐỘ GỌI GROQ (RPM + ước lượng TPM)
# ==========================================
class _GroqBudget:
    """
    Gioi han CA so request/phut LAN so token uoc luong/phut trong cung 1 cua so
    truot 60s. Dashboard Groq cua ban cho thay diem nghen thuc te la TPM
    (~6.2K token/phut) chu khong chi RPM, nen chi gioi han so request la chua du.
    """
    def __init__(self, max_calls: int, max_tokens: int, period: float = 60.0):
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.period = period
        self.calls = []  # list[(timestamp, uoc_luong_token)]
        self.lock = threading.Lock()

    def wait(self, estimated_tokens: int):
        while True:
            with self.lock:
                now = time.monotonic()
                self.calls = [(t, tok) for t, tok in self.calls if now - t < self.period]
                used_tokens = sum(tok for _, tok in self.calls)
                if len(self.calls) < self.max_calls and used_tokens + estimated_tokens <= self.max_tokens:
                    self.calls.append((now, estimated_tokens))
                    return
                sleep_for = (self.period - (now - self.calls[0][0])) if self.calls else 1.0
            time.sleep(max(sleep_for, 0.1))


# An toan duoi muc quan sat duoc tren dashboard Groq (~25-30 RPM, ~6.2K TPM cho free tier)
_groq_budget = _GroqBudget(max_calls=20, max_tokens=5000)


def _estimate_tokens(text: str) -> int:
    # uoc luong tho ~3 ky tu/token (tieng Viet co dau thuong "nang" hon tieng Anh)
    return max(1, len(text) // 3)


# ==========================================
# CHUẨN HÓA JSON TRẢ VỀ TỪ GROQ
# ==========================================
def _normalize_metadata(data: dict) -> dict:
    category = data.get("category")
    if not isinstance(category, str) or category not in VALID_CATEGORIES:
        category = DEFAULT_CATEGORY
    data["category"] = category

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    data["tags"] = [str(t).strip() for t in tags if str(t).strip()][:MAX_TAGS]

    sentiment = data.get("sentiment")
    if not isinstance(sentiment, str) or sentiment not in VALID_SENTIMENTS:
        sentiment = DEFAULT_SENTIMENT
    data["sentiment"] = sentiment

    try:
        importance = int(data.get("importance"))
    except (TypeError, ValueError):
        importance = DEFAULT_IMPORTANCE
    data["importance"] = max(1, min(10, importance))

    for key in ("tom_tat", "phan_tich_chi_tiet", "anh_huong_thi_truong"):
        if not isinstance(data.get(key), str):
            data[key] = data.get(key) or ""

    if not isinstance(data.get("diem_noi_bat"), list):
        data["diem_noi_bat"] = []
    if not isinstance(data.get("doi_tuong_lien_quan"), list):
        data["doi_tuong_lien_quan"] = []

    return data


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def _build_batch_prompt(subject_type: str, count: int) -> str:
    """Prompt yeu cau schema CHI TIET HON ban cu: them phan_tich_chi_tiet + doi_tuong_lien_quan."""
    if subject_type == "news":
        categories_str = ", ".join(sorted(VALID_CATEGORIES))
        schema = (
            '{"tom_tat": "tóm tắt ngắn 2-3 câu để xem nhanh", '
            '"phan_tich_chi_tiet": "phân tích chi tiết 5-8 câu: bối cảnh, diễn biến chính, hệ quả trước mắt và dài hạn", '
            '"anh_huong_thi_truong": "tác động cụ thể đến thị trường/ngành liên quan trong 2-3 câu — '
            "nếu không rõ ràng thì ghi 'Không có tác động thị trường rõ ràng'\", "
            '"doi_tuong_lien_quan": ["công ty/ngành/quốc gia bị ảnh hưởng trực tiếp, tối đa 5"], '
            '"diem_noi_bat": ["điểm/số liệu nổi bật 1", "điểm nổi bật 2", "điểm nổi bật 3"], '
            f'"category": "một giá trị DUY NHẤT trong: {categories_str}", '
            '"tags": ["tối đa 5 từ khóa: công ty/công nghệ/sản phẩm/quốc gia"], '
            '"sentiment": "một trong: Positive, Neutral, Negative", '
            '"importance": "số nguyên 1-10 thể hiện mức độ quan trọng với thị trường"}'
        )
        role = "chuyên gia phân tích tin tức tài chính/công nghệ, viết phân tích sâu và cụ thể, tránh chung chung"
    else:
        schema = (
            '{"tom_tat": "dự án làm gì, dùng công nghệ/ngôn ngữ chính nào - 2-3 câu", '
            '"phan_tich_chi_tiet": "phân tích chi tiết 5-8 câu: kiến trúc/cách hoạt động, vấn đề nó giải quyết, '
            'use-case thực tế", '
            '"anh_huong_thi_truong": "vì sao dự án đang trending, tác động tiềm năng đến ngành/cộng đồng công nghệ '
            'liên quan trong 2-3 câu", '
            '"doi_tuong_lien_quan": ["công nghệ/ngành/công ty cạnh tranh hoặc liên quan, tối đa 5"], '
            '"diem_noi_bat": ["tính năng/điểm nổi bật 1", "điểm nổi bật 2", "điểm nổi bật 3"]}'
        )
        role = "chuyên gia phân tích công nghệ và mã nguồn mở, viết phân tích sâu và cụ thể, tránh chung chung"

    return (
        f"Bạn là {role}. Bạn sẽ nhận {count} mục, mỗi mục được đánh số [1], [2], ... "
        f"Với MỖI mục, tạo 1 object JSON theo đúng format:\n{schema}\n\n"
        f"Trả lời DUY NHẤT bằng MỘT MẢNG JSON hợp lệ có đúng {count} phần tử theo đúng thứ tự đầu vào, "
        "không thêm chữ nào khác ngoài mảng JSON, không thêm markdown code fence."
    )


def _analyze_single_with_groq(groq_client, text: str, subject_type: str):
    """Goi Groq cho DUY NHAT 1 item — dung lam fallback khi 1 batch bi loi toan bo."""
    if not text or len(text.strip()) < 30:
        return None

    system_prompt = _build_batch_prompt(subject_type, 1)
    user_content = f"[1]\n{text[:2500]}"
    estimated_tokens = _estimate_tokens(system_prompt + user_content) + GROQ_MAX_TOKENS_PER_ITEM

    for attempt in range(GROQ_MAX_RETRIES):
        _groq_budget.wait(estimated_tokens)
        try:
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=GROQ_MAX_TOKENS_PER_ITEM,
            )
            raw = _strip_code_fence(completion.choices[0].message.content)
            data = json.loads(raw)
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                return None
            return _normalize_metadata(data)
        except Exception as e:
            error_text = str(e).lower()
            is_retryable = any(k in error_text for k in ("429", "rate", "timeout", "timed out", "connection"))
            if is_retryable and attempt < GROQ_MAX_RETRIES - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
                continue
            return None
    return None


def _analyze_batch_with_groq(groq_client, texts: list, subject_type: str):
    """
    Gui NHIEU item (toi da BATCH_SIZE) trong 1 lan goi Groq -> giam manh so luong
    request, tu do giam kha nang bi 429 so voi cach goi tung item 1 nhu truoc.
    Tra ve list dict CUNG DO DAI voi `texts`, giu dung thu tu.
    """
    n = len(texts)
    if n == 0:
        return []

    system_prompt = _build_batch_prompt(subject_type, n)
    user_content = "\n\n".join(f"[{i + 1}]\n{t[:2500]}" for i, t in enumerate(texts))
    estimated_tokens = _estimate_tokens(system_prompt + user_content) + GROQ_MAX_TOKENS_PER_ITEM * n
    max_output_tokens = min(GROQ_MAX_TOKENS_PER_ITEM * n, 3000)

    last_error = None
    for attempt in range(GROQ_MAX_RETRIES):
        _groq_budget.wait(estimated_tokens)
        try:
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=max_output_tokens,
            )
            raw = _strip_code_fence(completion.choices[0].message.content)
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("Phản hồi không phải mảng JSON")
            return [
                _normalize_metadata(data[i]) if i < len(data) and isinstance(data[i], dict) else None
                for i in range(n)
            ]
        except Exception as e:
            last_error = e
            error_text = str(e).lower()
            is_retryable = any(k in error_text for k in ("429", "rate", "timeout", "timed out", "connection"))
            if is_retryable and attempt < GROQ_MAX_RETRIES - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
                continue
            break

    # Ca batch that bai (vd model tra JSON sai dinh dang) -> fallback phan tich TUNG item rieng
    print(f"[core] Batch analyze ({subject_type}, {n} items) lỗi: {last_error}. Fallback từng item.")
    return [_analyze_single_with_groq(groq_client, t, subject_type) for t in texts]


# ==========================================
# CÀO & PHÂN TÍCH BÀI BÁO
# ==========================================
def _parse_one_feed(link: str):
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
        return " ".join(p.get_text(strip=True) for p in paragraphs)[:6000]
    except Exception:
        return ""


def _build_news_text(article: dict) -> str:
    full_text = _fetch_full_article_text(article["link"]) if article["link"] else ""
    if len(full_text.strip()) < 50:
        full_text = BeautifulSoup(article.get("_rss_fallback_text", ""), "html.parser").get_text()
    return f"Tiêu đề: {article['title']}\n\nNội dung: {full_text}"


def _apply_news_metadata(article: dict, analysis):
    article["ai_analysis"] = analysis
    if analysis:
        article["category"] = analysis.get("category", DEFAULT_CATEGORY)
        article["tags"] = analysis.get("tags", [])
        article["sentiment"] = analysis.get("sentiment", DEFAULT_SENTIMENT)
        article["importance"] = analysis.get("importance", DEFAULT_IMPORTANCE)
    else:
        article["category"] = DEFAULT_CATEGORY
        article["tags"] = []
        article["sentiment"] = DEFAULT_SENTIMENT
        article["importance"] = DEFAULT_IMPORTANCE
    return article


def fetch_and_save_news(supabase: Client, groq_client: Groq, links: list) -> int:
    """
    1) Cào + parse RSS song song.
    2) Loại bài đã có trong DB (không phân tích lại).
    3) Gộp bài MỚI thành từng batch BATCH_SIZE, phân tích song song theo batch
       (giảm mạnh số request Groq so với 1-request-1-bài trước đây).
    4) Ghi 1 lần bằng upsert hàng loạt.
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
        texts = [_build_news_text(a) for a in new_articles]
        text_batches = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
        article_batches = [new_articles[i:i + BATCH_SIZE] for i in range(0, len(new_articles), BATCH_SIZE)]

        with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as executor:
            futures = {
                executor.submit(_analyze_batch_with_groq, groq_client, t_batch, "news"): a_batch
                for t_batch, a_batch in zip(text_batches, article_batches)
            }
            for future in as_completed(futures):
                a_batch = futures[future]
                try:
                    analyses = future.result()
                except Exception:
                    analyses = [None] * len(a_batch)
                for article, analysis in zip(a_batch, analyses):
                    _apply_news_metadata(article, analysis)

    payload = [{k: v for k, v in a.items() if k != "_rss_fallback_text"} for a in new_articles]

    if payload:
        try:
            supabase.table("news").upsert(payload, on_conflict="link").execute()
        except Exception:
            pass

    return len(payload)


# ==========================================
# CÀO & PHÂN TÍCH DỰ ÁN GITHUB TRENDING
# ==========================================
def scrape_trending_page(period: str, today_str: str):
    repos = []
    try:
        url = f"https://github.com/trending?since={period}"
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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


def _build_repo_text(repo: dict) -> str:
    readme_text = _fetch_repo_readme_text(repo["repo_link"]) if repo["repo_link"] else ""
    return f"Tên dự án: {repo['repo_name']}\nMô tả ngắn: {repo['description']}\n\nNội dung README: {readme_text}"


def fetch_and_save_github(supabase: Client, groq_client: Groq) -> int:
    today_str = datetime.date.today().isoformat()
    raw_repos = []
    for period in ["daily", "weekly", "monthly"]:
        raw_repos.extend(scrape_trending_page(period, today_str))

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
        texts = [_build_repo_text(r) for r in new_repos]
        text_batches = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
        repo_batches = [new_repos[i:i + BATCH_SIZE] for i in range(0, len(new_repos), BATCH_SIZE)]

        with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as executor:
            futures = {
                executor.submit(_analyze_batch_with_groq, groq_client, t_batch, "github"): r_batch
                for t_batch, r_batch in zip(text_batches, repo_batches)
            }
            for future in as_completed(futures):
                r_batch = futures[future]
                try:
                    analyses = future.result()
                except Exception:
                    analyses = [None] * len(r_batch)
                for repo, analysis in zip(r_batch, analyses):
                    repo["ai_analysis"] = analysis

        try:
            supabase.table("github_trending").upsert(new_repos, on_conflict="repo_link, period, fetched_date").execute()
        except Exception:
            pass

    return len(new_repos)
