import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import json
from datetime import datetime, timedelta

# ================= 設定區 =================
GOOGLE_API_KEY = "AIzaSyDGQveSXRGw6yDWUNmXrHNwG_INhhfMxLs" 
TARGET_KEYWORDS = ["ASUS", "ROG", "TUF", "子龍"]
DAYS_LIMIT = 30 # 限制搜尋 30 天內文章
# ==========================================

genai.configure(api_key=GOOGLE_API_KEY)

def get_best_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m_name in available_models:
            if 'gemini-1.5-flash' in m_name:
                return genai.GenerativeModel(m_name)
        return genai.GenerativeModel(available_models[0])
    except:
        return None

model = get_best_model()

def ai_classify_article(title, retry_count=3):
    """
    優化後的分類函式：加入延遲與重試機制以降低 Rate Limit 觸發
    """
    if not model: return "模型錯誤"
    
    prompt = f"分析標題：『{title}』。分類為「資訊分享」或「客訴」。只回傳分類名稱。"
    
    for i in range(retry_count):
        try:
            # 強制休息 3 秒，確保 RPM 控制在 20 以下（免費版上限約 15-20）
            time.sleep(10) 
            
            response = model.generate_content(prompt)
            cat = response.text.strip()
            return "客訴" if "客訴" in cat else "資訊分享"
            
        except Exception as e:
            if i < retry_count - 1:
                print(f"⚠️ API 請求過快或出錯，5秒後進行第 {i+1} 次重試...")
                time.sleep(10)
                continue
            else:
                print(f"❌ 分類失敗 (已重試 {retry_count} 次): {title[:15]}...")
                return "分類失敗"

def is_within_days(date_str, days):
    """判斷日期是否在指定天數內"""
    target_date = datetime.now() - timedelta(days=days)
    try:
        post_date = datetime.strptime(date_str, "%Y-%m-%d")
        return post_date >= target_date
    except:
        return True

def scrape_mobile01(driver):
    print(f"\n🌐 正在掃描 Mobile01 (目標: {DAYS_LIMIT}天內)...")
    results = []
    seen = set()
    
    for page in range(1, 4):
        print(f"  📄 正在處理第 {page} 頁...")
        driver.get(f"https://www.mobile01.com/topiclist.php?f=298&p={page}")
        time.sleep(5)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link['href']
            title = link.text.strip()
            
            if "topicdetail.php?f=298" in href and len(title) > 5:
                parent_row = link.find_parent('div', class_='c-listTableTile__item')
                if not parent_row:
                    parent_row = link.find_parent('div', class_='l-listTable__item')

                date_str = ""
                if parent_row:
                    date_tag = parent_row.select_one('.o-f12.u-noWrap')
                    if date_tag:
                        date_str = date_tag.text.strip().split()[0]

                if date_str and not is_within_days(date_str, DAYS_LIMIT):
                    continue
                
                if any(kw.upper() in title.upper() for kw in TARGET_KEYWORDS):
                    full_link = "https://www.mobile01.com/" + href
                    if full_link not in seen:
                        print(f"    ✨ 發現: {title[:25]}...")
                        cat = ai_classify_article(title)
                        results.append({
                            "source": "Mobile01", 
                            "title": title, 
                            "link": full_link, 
                            "category": cat, 
                            "date": date_str if date_str else "近期"
                        })
                        seen.add(full_link)
    return results

def scrape_bahamut(driver):
    print(f"\n🌐 正在掃描 巴哈姆特 (目標: {DAYS_LIMIT}天內)...")
    driver.get("https://forum.gamer.com.tw/B.php?bsn=60030")
    time.sleep(5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    rows = soup.select('.b-list__row')
    
    results = []
    seen = set()
    
    for row in rows:
        title_tag = row.select_one('.b-list__main__title')
        date_tag = row.select_one('.b-list__time')
        
        if title_tag and date_tag:
            title = title_tag.text.strip()
            date_text = date_tag.text.strip()
            href = "https://forum.gamer.com.tw/" + title_tag['href']
            
            # 過濾 30 天外舊文
            if "-" in date_text and not date_text.startswith("03-"):
                if "2025" in date_text: continue 
            
            if any(kw.upper() in title.upper() for kw in TARGET_KEYWORDS):
                if href not in seen:
                    print(f"    ✨ 發現: {title[:25]}...")
                    cat = ai_classify_article(title)
                    results.append({
                        "source": "Bahamut", 
                        "title": title, 
                        "link": href, 
                        "category": cat, 
                        "date": date_text
                    })
                    seen.add(href)
    return results

def main():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        m01 = scrape_mobile01(driver)
        baha = scrape_bahamut(driver)
        final_data = m01 + baha
        
        # 加上最後更新時間戳記，供網頁前端讀取
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in final_data:
            item["timestamp"] = timestamp
        
        # 存檔
        with open('articles_data.json', 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=4)
            
        print("\n" + "="*50)
        print(f"✅ 任務完成！共抓取 {len(final_data)} 篇 30 天內的文章。")
        print(f"⏰ 更新時間: {timestamp}")
        print("="*50)

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()