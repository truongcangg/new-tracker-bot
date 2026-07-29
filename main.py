import streamlit as st

# Cấu hình giao diện Web (phải đặt ở dòng đầu tiên)
st.set_page_config(page_title="Trading Dashboard", page_icon="📈", layout="wide")

st.title("📈 Bảng điều khiển Giao dịch & Chênh lệch thông tin")

# Chia màn hình thành 2 cột lớn
col1, col2 = st.columns(2)

with col1:
    st.header("📰 Tin tức & Nghiên cứu")
    st.info("Khu vực này sẽ tự động cập nhật bài báo, báo cáo nghiên cứu và dùng AI phân tích tác động thị trường.")

with col2:
    st.header("🔥 Top 10 GitHub Trending")
    st.info("Khu vực này sẽ hiển thị dự án công nghệ tăng trưởng nhanh và đánh giá tiềm năng thay đổi thị trường của dự án.")

# Thanh điều khiển bên trái (Sidebar) để thêm nguồn tin
st.sidebar.header("⚙️ Quản lý nguồn tin")
new_url = st.sidebar.text_input("Nhập link bài báo/RSS mới:")
if st.sidebar.button("Thêm nguồn"):
    st.sidebar.success(f"Đã ghi nhận link: {new_url}")

st.sidebar.markdown("---")
st.sidebar.write("Trạng thái hệ thống: **Đang xây dựng...** 🟢")
