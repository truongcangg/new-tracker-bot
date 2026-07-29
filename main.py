# ----------------- HÀM XỬ LÝ DỮ LIỆU CÓ BỘ NHỚ ĐỆM & ĐA LUỒNG -----------------

@st.cache_data(ttl=1800, show_spinner=False) # Lưu bộ nhớ đệm trong 30 phút
def fetch_single_feed(url):
    """Cào 1 trang độc lập và trích xuất dữ liệu cơ bản để tránh lỗi lưu trữ (Pickle)"""
    try:
        feed = feedparser.parse(url)
        entries = []
        # Chỉ lấy 15 bài mới nhất mỗi nguồn để tối ưu RAM
        for entry in feed.entries[:15]: 
            parsed_time = getattr(entry, 'published_parsed', getattr(entry, 'updated_parsed', None))
            if parsed_time:
                entry_date = datetime.fromtimestamp(time.mktime(parsed_time))
            else:
                entry_date = datetime.now() # Nếu bài không ghi ngày, mặc định là tin mới
            
            # Lưu dữ liệu dưới dạng Dictionary thuần túy
            entries.append({
                'title': entry.title,
                'link': entry.link,
                'summary': getattr(entry, 'summary', ''),
                'date': entry_date 
            })
        return entries
    except:
        return []

def get_news_and_research(urls, target_date):
    """Cào nhiều trang cùng lúc (Đa luồng) và lọc theo ngày"""
    articles = []
    # Chuyển đổi ngày chọn thành mốc 00:00:00 của ngày đó
    target_date_start = datetime.combine(target_date, datetime.min.time())
    
    # Tung 20 luồng chạy song song để tăng tốc
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(fetch_single_feed, url): url for url in urls}
        for future in as_completed(future_to_url):
            entries = future.result()
            if entries:
                for item in entries:
                    # Bộ lọc ngày: Chỉ lấy tin từ mốc thời gian đã chọn trở về sau
                    if item['date'] >= target_date_start:
                        articles.append(item)
    
    # Sắp xếp bài báo từ mới nhất xuống cũ nhất
    articles = sorted(articles, key=lambda x: x['date'], reverse=True)
    return articles
