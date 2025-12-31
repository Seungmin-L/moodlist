"""
네이버 검색 API로 영어 제목 → 한국어 제목 찾기
"""

import os
import re
import urllib.request
import urllib.parse
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


def search_naver(query: str, display: int = 5) -> list:
    """네이버 웹 검색 API 호출"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("네이버 API 키가 없습니다.")
        return []
    
    encoded_query = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/webkr.json?query={encoded_query}&display={display}"
    
    try:
        request = urllib.request.Request(url)
        request.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
        request.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)
        
        response = urllib.request.urlopen(request)
        
        if response.getcode() == 200:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('items', [])
    except Exception as e:
        print(f"네이버 검색 오류: {e}")
    
    return []


def extract_korean_title(text: str, english_title: str) -> str:
    """
    텍스트에서 한국어 제목 추출
    
    패턴 예시:
    - "첫눈에...(Snowy Wish)" → "첫눈에..."
    - "밤편지 (Through the Night)" → "밤편지"
    - "첫눈에... (Snowy Wish)" → "첫눈에..."
    """
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    
    # 패턴 1: 한국어제목(영어제목) 또는 한국어제목 (영어제목)
    # 영어 제목 앞에 있는 한글 부분 추출
    eng_escaped = re.escape(english_title)
    
    # "한국어제목(Snowy Wish)" 또는 "한국어제목 (Snowy Wish)"
    pattern1 = rf'([가-힣][가-힣\s\.\!\?\,\.\.\.]+)\s*\({eng_escaped}\)'
    match = re.search(pattern1, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # 패턴 2: "한국어 (영어)" 형태 - 더 유연하게
    pattern2 = rf'([가-힣][가-힣\s\.\!\?\,\.\.\.]+)\s*\([^)]*{eng_escaped}[^)]*\)'
    match = re.search(pattern2, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # 패턴 3: 제목에서 "/" 앞부분 (예: "첫눈에... / 소녀시대")
    pattern3 = rf'([가-힣][가-힣\s\.\!\?\,\.\.\.]+)\s*/\s*'
    match = re.search(pattern3, text)
    if match:
        korean = match.group(1).strip()
        # 영어 제목이 같이 있는지 확인
        if english_title.lower() in text.lower():
            return korean
    
    return None


def find_korean_title(english_title: str, artist: str) -> dict:
    """
    영어 제목으로 네이버 검색 → 한국어 제목 찾기
    
    Returns:
        {
            "korean_title": "한국어 제목",
            "korean_artist": "한국어 아티스트명",
            "found": True/False
        }
    """
    result = {
        "korean_title": None,
        "korean_artist": None,
        "found": False
    }
    
    # 검색어
    query = f"{english_title} {artist} 가사"
    search_results = search_naver(query, display=5)
    
    if not search_results:
        return result
    
    # 검색 결과에서 한국어 제목 추출 시도
    for item in search_results:
        title = item.get('title', '')
        description = item.get('description', '')
        
        # 제목에서 먼저 시도
        korean_title = extract_korean_title(title, english_title)
        if korean_title:
            result["korean_title"] = korean_title
            result["found"] = True
            
            # 아티스트명도 추출 시도
            korean_artist = extract_korean_artist(title, artist)
            if korean_artist:
                result["korean_artist"] = korean_artist
            
            return result
        
        # 설명에서 시도
        korean_title = extract_korean_title(description, english_title)
        if korean_title:
            result["korean_title"] = korean_title
            result["found"] = True
            return result
    
    return result


def extract_korean_artist(text: str, english_artist: str) -> str:
    """아티스트명에서 한국어 추출"""
    text = re.sub(r'<[^>]+>', '', text)
    
    # "소녀시대 (GIRLS' GENERATION)" 패턴
    pattern = rf'([가-힣]+)\s*\([^)]*{re.escape(english_artist)}[^)]*\)'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # "아이유 (IU)" 패턴
    pattern2 = rf'([가-힣]+)\s*\(\s*{re.escape(english_artist)}\s*\)'
    match = re.search(pattern2, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return None


# ======================
# CLI 테스트
# ======================
if __name__ == "__main__":
    test_cases = [
        ("Snowy Wish", "Girls Generation"),
        ("Through the Night", "IU"),
        ("Love In My Heart", "BABYMONSTER"),
    ]
    
    for eng_title, artist in test_cases:
        print(f"\n{'='*50}")
        print(f"영어: {eng_title} - {artist}")
        
        result = find_korean_title(eng_title, artist)
        
        if result["found"]:
            print(f"한국어: {result['korean_title']} - {result.get('korean_artist', artist)}")
        else:
            print("한국어 제목 못 찾음")