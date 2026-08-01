"""
scraper.py
----------
Entry point CHO GITHUB ACTIONS. Chay doc lap, khong dinh dang gi lien quan
Streamlit, nen thuc thi on dinh 100% moi lan cron kich hoat — khong con phu
thuoc vao viec co ai mo app tren trinh duyet hay khong.

Chay thu cong: SUPABASE_URL=... SUPABASE_KEY=... GROQ_API_KEY=... python scraper.py
"""

import os
import signal
import sys
import time

import core


class ScraperTimeoutError(TimeoutError):
    pass


def _handle_timeout(signum, frame):
    raise ScraperTimeoutError("Scraper exceeded SCRAPER_TIMEOUT_SECONDS")


def main():
    start = time.time()
    timeout_seconds = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "780"))
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _handle_timeout)
        signal.alarm(timeout_seconds)

    try:
        supabase_url = os.environ["SUPABASE_URL"]
        supabase_key = os.environ["SUPABASE_KEY"]
        groq_api_key = os.environ["GROQ_API_KEY"]
    except KeyError as e:
        print(f"[scraper] LỖI: thiếu biến môi trường {e}. "
              f"Kiểm tra lại GitHub Actions Secrets (Settings → Secrets and variables → Actions).")
        sys.exit(1)

    supabase = core.create_supabase_client(supabase_url, supabase_key)
    groq_client = core.create_groq_client(groq_api_key)

    # --- Tin tức ---
    news_count = 0
    try:
        sources = supabase.table("rss_sources").select("url, is_active").execute().data
        links = [s["url"] for s in sources if s.get("is_active", True)]
        print(f"[scraper] Đang theo dõi {len(links)} nguồn RSS.")
        if links:
            news_count = core.fetch_and_save_news(supabase, groq_client, links)
    except Exception as e:
        print(f"[scraper] Lỗi khi cào tin tức: {e}")

    # --- GitHub Trending ---
    git_count = 0
    try:
        git_count = core.fetch_and_save_github(supabase, groq_client)
    except Exception as e:
        print(f"[scraper] Lỗi khi cào GitHub Trending: {e}")

    elapsed = round(time.time() - start, 1)
    print(f"[scraper] Hoàn tất trong {elapsed}s — {news_count} bài báo mới, {git_count} dự án GitHub mới.")
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


if __name__ == "__main__":
    try:
        main()
    except ScraperTimeoutError as e:
        print(f"[scraper] LỖI: {e}")
        sys.exit(124)
