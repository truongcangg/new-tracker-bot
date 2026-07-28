import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI")

def test_models():
    print("Đang truy vấn danh sách mô hình từ Google...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print("DANH SÁCH MÔ HÌNH HỢP LỆ CHO API KEY NÀY:")
        for model in data.get('models', []):
            print(model.get('name'))
    else:
        print(f"Lỗi truy cập API: {response.text}")

if __name__ == "__main__":
    test_models()
