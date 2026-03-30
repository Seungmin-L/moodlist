"""
네이버 검색 API로 영어 제목 → 한국어 제목 찾기 테스트
"""

import os
import urllib.request
import urllib.parse
import json
from dotenv import load_dotenv

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


def search_naver(query: str, display: int = 5) -> list:
    """네이버 검색 API 호출"""
    encoded_query = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/webkr.json?query={encoded_query}&display={display}"
    
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", NAVER_CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", NAVER_CLIENT_SECRET)
    
    response = urllib.request.urlopen(request)
    
    if response.getcode() == 200:
        result = json.loads(response.read().decode('utf-8'))
        return result.get('items', [])
    else:
        return []


def find_korean_title(english_title: str, artist: str) -> str:
    """영어 제목으로 검색해서 한국어 제목 찾기"""
    
    # 검색어 조합
    queries = [
        f"{english_title} {artist} 가사",
        f"{english_title} {artist} 노래",
        f"{english_title} {artist}",
    ]
    
    for query in queries:
        print(f"\n검색: {query}")
        results = search_naver(query)
        
        for item in results:
            title = item.get('title', '')
            description = item.get('description', '')
            
            # HTML 태그 제거
            import re
            title = re.sub(r'<[^>]+>', '', title)
            description = re.sub(r'<[^>]+>', '', description)
            
            print(f"  제목: {title}")
            print(f"  설명: {description[:100]}...")
            print()
    
    return None


if __name__ == "__main__":
    test_cases = [
        ("Snowy Wish", "Girls Generation"),
        ("Through the Night", "IU"),
    ]
    
    for eng_title, artist in test_cases:
        print("=" * 60)
        print(f"테스트: {eng_title} - {artist}")
        print("=" * 60)
        find_korean_title(eng_title, artist)