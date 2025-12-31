"""
Genius API를 이용한 가사 크롤링 모듈

사용 전 준비:
1. https://genius.com/api-clients 에서 API 클라이언트 생성
2. Client Access Token 복사
3. 환경변수 설정: export GENIUS_ACCESS_TOKEN="your_token_here"
   또는 .env 파일에 GENIUS_ACCESS_TOKEN=your_token_here
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from db.database import insert_bronze

try:
    import lyricsgenius
except ImportError:
    print("lyricsgenius 패키지가 필요합니다.")
    print("설치: pip install lyricsgenius")
    sys.exit(1)


def get_genius_client(token: str = None):
    """Genius API 클라이언트 생성"""
    token = token or os.getenv("GENIUS_ACCESS_TOKEN")
    
    if not token:
        raise ValueError(
            "Genius API 토큰이 필요합니다.\n"
            "1. https://genius.com/api-clients 에서 토큰 생성\n"
            "2. export GENIUS_ACCESS_TOKEN='your_token' 실행"
        )
    
    genius = lyricsgenius.Genius(
        token,
        verbose=False,
        remove_section_headers=True,  # [Verse], [Chorus] 등 제거
        skip_non_songs=True,
        retries=3
    )
    return genius


def search_song(query: str, token: str = None):
    """
    곡 검색
    Returns: [{"title": ..., "artist": ..., "id": ..., "url": ...}, ...]
    """
    genius = get_genius_client(token)
    
    try:
        # Genius API 검색
        response = genius.search_songs(query)
    except Exception as e:
        print(f"검색 실패: {e}")
        return []
    
    results = []
    hits = response.get("hits", [])
    
    for hit in hits:
        song_info = hit.get("result", {})
        results.append({
            "title": song_info.get("title", ""),
            "artist": song_info.get("primary_artist", {}).get("name", "Unknown"),
            "id": song_info.get("id"),
            "url": song_info.get("url", "")
        })
    
    return results


def get_lyrics(song_id: int = None, song_url: str = None, token: str = None):
    """
    곡 ID 또는 URL로 가사 가져오기
    Returns: str (가사) or None
    """
    genius = get_genius_client(token)
    
    try:
        if song_url:
            lyrics = genius.lyrics(song_url=song_url)
        elif song_id:
            lyrics = genius.lyrics(song_id=song_id)
        else:
            return None
        return lyrics
    except Exception as e:
        print(f"가사 가져오기 실패: {e}")
        return None


def filter_original_korean(results: list):
    """
    검색 결과에서 번역/로마자 버전 제외하고 원본 한국어 가사 우선 반환
    """
    # 제외할 키워드 (번역, 로마자 등)
    exclude_keywords = [
        "english translation",
        "romanized",
        "romanization",
        "traduction",
        "traducción",
        "tradução",
        "перевод",
        "翻訳",
        "日本語",
        "中文",
        "bản dịch",
        "genius english",
        "genius romanization",
    ]
    
    filtered = []
    for r in results:
        title_lower = r.get("title", "").lower()
        url_lower = r.get("url", "").lower()
        artist_lower = r.get("artist", "").lower()
        
        # 제외 키워드 체크
        should_exclude = any(kw in title_lower or kw in url_lower or kw in artist_lower 
                           for kw in exclude_keywords)
        
        if not should_exclude:
            filtered.append(r)
    
    return filtered


def search_and_get_lyrics(title: str, artist: str = "", token: str = None):
    """
    제목과 아티스트로 검색 후 가사 반환 (한국어 원본 우선)
    Returns: {"title": ..., "artist": ..., "lyrics": ..., "url": ...} or None
    """
    genius = get_genius_client(token)
    
    try:
        # 먼저 검색 결과 가져오기
        search_query = f"{title} {artist}".strip()
        response = genius.search_songs(search_query)
        hits = response.get("hits", [])
        
        if not hits:
            return None
        
        # 결과 정리
        results = []
        for hit in hits:
            song_info = hit.get("result", {})
            results.append({
                "title": song_info.get("title", ""),
                "artist": song_info.get("primary_artist", {}).get("name", "Unknown"),
                "id": song_info.get("id"),
                "url": song_info.get("url", "")
            })
        
        # 번역/로마자 버전 필터링
        filtered = filter_original_korean(results)
        
        if not filtered:
            # 필터링 후 결과 없으면 원본 결과 사용
            filtered = results
        
        # 첫 번째 결과로 가사 가져오기
        best_match = filtered[0]
        lyrics = genius.lyrics(song_url=best_match["url"])
        
        if lyrics:
            return {
                "title": best_match["title"],
                "artist": best_match["artist"],
                "lyrics": lyrics,
                "url": best_match["url"]
            }
    except Exception as e:
        print(f"검색 실패: {e}")
    
    return None


def crawl_and_save(title: str, artist: str = "", token: str = None):
    """
    검색 → 가사 크롤링 → Bronze 저장
    """
    print(f"검색 중: {title} - {artist if artist else '(아티스트 미지정)'}")
    
    result = search_and_get_lyrics(title, artist, token)
    
    if not result or not result.get("lyrics"):
        print("  ✗ 가사를 찾을 수 없음")
        return None
    
    bronze_id = insert_bronze(
        title=result["title"],
        artist=result["artist"],
        raw_lyrics=result["lyrics"],
        source_url=result["url"]
    )
    
    print(f"  ✓ 저장 완료: {result['title']} - {result['artist']} (ID: {bronze_id})")
    
    return {
        "bronze_id": bronze_id,
        "title": result["title"],
        "artist": result["artist"]
    }


def crawl_artist_songs(artist_name: str, max_songs: int = 10, token: str = None):
    """
    아티스트의 곡들 크롤링
    """
    genius = get_genius_client(token)
    
    print(f"'{artist_name}' 아티스트 검색 중...")
    
    try:
        artist = genius.search_artist(artist_name, max_songs=max_songs, sort="popularity")
    except Exception as e:
        print(f"아티스트 검색 실패: {e}")
        return []
    
    if not artist:
        print("아티스트를 찾을 수 없음")
        return []
    
    saved = []
    
    for song in artist.songs:
        bronze_id = insert_bronze(
            title=song.title,
            artist=song.artist,
            raw_lyrics=song.lyrics,
            source_url=song.url
        )
        saved.append({
            "bronze_id": bronze_id,
            "title": song.title,
            "artist": song.artist
        })
        print(f"  ✓ {song.title} (ID: {bronze_id})")
    
    print(f"\n총 {len(saved)}곡 저장됨")
    return saved


def crawl_multiple_songs(songs: list, token: str = None):
    """
    여러 곡 크롤링
    songs: [{"title": ..., "artist": ...}, ...]
    """
    saved = []
    
    for song in songs:
        result = crawl_and_save(
            title=song.get("title", ""),
            artist=song.get("artist", ""),
            token=token
        )
        if result:
            saved.append(result)
    
    return saved


# ======================
# CLI
# ======================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Genius 가사 크롤러")
    parser.add_argument("query", nargs="?", help="곡 제목 또는 아티스트")
    parser.add_argument("-a", "--artist", help="아티스트명 (곡 검색 시)")
    parser.add_argument("-n", "--max-songs", type=int, default=10, help="아티스트 모드: 최대 곡 수")
    parser.add_argument("--artist-mode", action="store_true", help="아티스트의 모든 곡 크롤링")
    parser.add_argument("--search", action="store_true", help="검색만 (저장 안 함)")
    parser.add_argument("--token", help="Genius API 토큰 (환경변수 대신)")
    
    args = parser.parse_args()
    
    if not args.query:
        print("사용법:")
        print("  python crawl.py '곡 제목'                    # 곡 검색 + 저장")
        print("  python crawl.py '곡 제목' -a '아티스트'      # 아티스트 지정 검색")
        print("  python crawl.py '아티스트' --artist-mode     # 아티스트 곡 전체")
        print("  python crawl.py '검색어' --search            # 검색만 (저장 안 함)")
        print("")
        print("환경변수 설정 필요: export GENIUS_ACCESS_TOKEN='your_token'")
        sys.exit(0)
    
    try:
        if args.search:
            # 검색만
            results = search_song(args.query, args.token)
            print(f"\n검색 결과 ({len(results)}개):")
            for r in results[:10]:
                print(f"  - {r['title']} / {r['artist']}")
                print(f"    URL: {r['url']}")
        
        elif args.artist_mode:
            # 아티스트 모드
            crawl_artist_songs(args.query, args.max_songs, args.token)
        
        else:
            # 단일 곡 검색 + 저장
            crawl_and_save(args.query, args.artist or "", args.token)
    
    except ValueError as e:
        print(f"오류: {e}")
        sys.exit(1)