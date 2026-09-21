import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def crawl_kyobo_recent_reviews(target_count=30):
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    driver.maximize_window()
    
    driver.get("https://kyobobook.co.kr")
    time.sleep(3)
    
    reviews_list = []
    
    try:
        # 1. 검색창 찾기 및 검색어 입력
        search_box = driver.find_element(By.ID, "searchKeyword")
        search_box.click()
        search_box.clear()
        
        keyword = "어린왕자"
        for char in keyword:
            search_box.send_keys(char)
            time.sleep(0.1)
            
        time.sleep(0.5)
        search_box.send_keys(Keys.ENTER)
        print(f"🚀 '{keyword}' 검색을 성공적으로 실행했습니다.")
        
        # 2. [오타 수정 완료] By.開 -> By.XPATH로 정상 변경
        first_book_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "(//a[contains(@class, 'prod_info') or contains(@class, 'prod_link')])"))
        )
        driver.execute_script("arguments[0].click();", first_book_link)
        time.sleep(4)
        
        # 3. 상세 페이지 내부 스크롤 및 리뷰 탭 클릭
        print("🔍 리뷰 탭 탐색 및 페이지 스크롤 중...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        time.sleep(2)
        
        review_tab_xpath = (
            "//button[.//span[contains(text(), '리뷰')]] | "
            "//a[contains(text(), '리뷰')] | "
            "//li[contains(@class, 'tab_item') or contains(@class, 'nav_item')][.//span[contains(text(), '리뷰')]]"
        )
        
        review_tab = WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.XPATH, review_tab_xpath))
        )
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", review_tab)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", review_tab)
        print("🔓 리뷰 탭 진입 성공!")
        time.sleep(4)
        
        # 4. '최신순' 정렬 버튼 탐색 및 우회 클릭
        print("✨ 리뷰 정렬 기준을 '최신순'으로 변경합니다...")
        driver.execute_script("window.scrollBy(0, 300);")
        time.sleep(1.5)
        
        sort_elements = driver.find_elements(By.XPATH, "//button | //a | //span")
        for elem in sort_elements:
            try:
                if "최신순" in elem.text:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", elem)
                    print("👍 기준 정렬 완료 (최신순)")
                    break
            except:
                continue
            
        time.sleep(4)
        
        # 5. 리뷰 데이터 수집 루프 시작 (목표: 30개)
        page_num = 1
        while len(reviews_list) < target_count:
            print(f"📦 {page_num}페이지 최신 리뷰 수집 중... (현재 수집: {len(reviews_list)}/{target_count}개)")
            time.sleep(2.5) 
            
            review_items = driver.find_elements(By.XPATH, "//*[@id='kloverReview']//ul/li | //div[contains(@class, 'comment_list') or contains(@class, 'review_list')]//li")
            
            if not review_items:
                print("⚠️ 현재 페이지에서 리뷰 요소를 더 이상 찾지 못했습니다.")
                break
                
            page_collected = 0
            for item in review_items:
                if len(reviews_list) >= target_count:
                    break
                
                try:
                    if not item.text.strip():
                        continue
                        
                    # 작성자 추출
                    try: 
                        writer_elem = item.find_element(By.XPATH, ".//*[contains(text(), '***') or contains(@class, 'id') or contains(@class, 'witer')]")
                        writer = writer_elem.text.strip()
                    except: 
                        writer = "종이책 구매자"
                        
                    # 작성일자 [오타 수정 완료] By.開 -> By.XPATH로 정상 변경
                    try: 
                        date_elem = item.find_element(By.XPATH, ".//*[contains(text(), '202')]")
                        date = date_elem.text.strip()
                    except: 
                        date = ""
                        
                    # 평점 추출
                    try:
                        score_text = item.text.split('\n')
                        score = score_text[0] if "점" in score_text[0] or "★" in score_text[0] else "5"
                    except: 
                        score = "5"
                        
                    # 본문 내용 추출
                    try:
                        content_element = item.find_element(By.XPATH, ".//p[contains(@class, 'fz-14') or contains(@class, 'break-word') or contains(@class, 'comment_text')]")
                        content = content_element.text.strip()
                    except: 
                        lines = [line.strip() for line in item.text.split('\n') if line.strip()]
                        content = lines[1] if len(lines) > 1 else item.text.strip()
                    
                    if content and len(content) > 2:
                        if not any(r['리뷰내용'] == content for r in reviews_list):
                            reviews_list.append({
                                "작성자": writer,
                                "작성일자": date,
                                "평점": score,
                                "리뷰내용": content
                            })
                            page_collected += 1
                    
                except Exception:
                    continue
            
            print(f"   ㄴ {page_num}페이지에서 {page_collected}개의 유효 리뷰를 추출했습니다.")
            if len(reviews_list) >= target_count:
                break
                
            # 6. 하단 페이지 번호 이동 로직
            try:
                page_num += 1
                driver.execute_script("window.scrollBy(0, 350);")
                time.sleep(1)
                
                next_page_xpath = f"//button[text()='{page_num}'] | //a[text()='{page_num}']"
                next_page_btn = driver.find_element(By.XPATH, next_page_xpath)
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_page_btn)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", next_page_btn)
                print(f"➡️ 다음 페이지 버튼 인식 완료! [{page_num}페이지]로 이동합니다.")
            except Exception:
                print(f"🚫 {page_num}페이지 전환 버튼 탐색 실패로 인해 수집을 마칩니다.")
                break

    except Exception as e:
        print(f"❌ 크롤링 도중 오류가 발생했습니다: {e}")
        
    finally:
        driver.quit()
        print(f"🏁 크롤링 프로세스 최종 종료. 총 {len(reviews_list)}개의 리뷰 확보.")
        
        # 7. CSV 파일 저장
        if reviews_list:
            df = pd.DataFrame(reviews_list)
            output_filename = "kyobo_recent_reviews_30.csv"
            df.to_csv(output_filename, index=False, encoding="utf-8-sig")
            print(f"💾 CSV 파일 최종 저장 완료: {output_filename}")
        else:
            print("수집된 리뷰 데이터가 존재하지 않습니다.")

if __name__ == "__main__":
    crawl_kyobo_recent_reviews(target_count=30)
