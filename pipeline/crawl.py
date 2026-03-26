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
import re
import difflib
from typing import List, Dict, Optional
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

try:
    import requests
except ImportError:
    print("requests 패키지가 필요합니다.")
    print("설치: pip install requests")
    sys.exit(1)


def _resolve_token(token: str = None) -> str:
    resolved = token or os.getenv("GENIUS_ACCESS_TOKEN")
    if not resolved:
        raise ValueError(
            "Genius API 토큰이 필요합니다.\n"
            "1. https://genius.com/api-clients 에서 토큰 생성\n"
            "2. export GENIUS_ACCESS_TOKEN='your_token' 실행"
        )
    return resolved


def get_genius_client(token: str = None):
    """Genius API 클라이언트 생성"""
    token = _resolve_token(token)

    genius = lyricsgenius.Genius(
        token,
        verbose=False,
        remove_section_headers=True,  # [Verse], [Chorus] 등 제거
        skip_non_songs=True,
        retries=3
    )
    return genius


def _is_debug_enabled(debug: bool = None) -> bool:
    """디버그 모드 여부"""
    if debug is not None:
        return bool(debug)
    return os.getenv("GENIUS_SEARCH_DEBUG", "").lower() in {"1", "true", "yes", "on"}


_GENIUS_API_BASE = "https://api.genius.com"
_TITLE_META_KEYWORDS = {
    "feat",
    "ft",
    "featuring",
    "live",
    "remix",
    "acoustic",
    "instrumental",
    "version",
    "edit",
    "remaster",
    "demo",
    "karaoke",
    "cover",
}


def _title_is_short(value: str) -> bool:
    return len(_normalize_text(value).replace(" ", "")) <= 4


def _normalize_text(value: str, keep_parenthetical: bool = True) -> str:
    """제목/아티스트 비교용 정규화"""
    if not value:
        return ""

    text = value.strip().lower()
    if keep_parenthetical:
        text = text.replace("(", " ").replace(")", " ")
        text = text.replace("[", " ").replace("]", " ")
    else:
        text = re.sub(r"\([^)]*\)", " ", text)
        text = re.sub(r"\[[^\]]*\]", " ", text)
    # 특수 문자 정리
    text = re.sub(r"[^a-z0-9가-힣\\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(value: str) -> List[str]:
    """공백 토큰화 + 길이 1 토큰 제거"""
    return [t for t in _normalize_text(value).split() if len(t) > 1]


def _sequence_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _genius_api_get(path: str, token: str = None, params: Dict = None) -> Dict:
    access_token = _resolve_token(token)
    url = f"{_GENIUS_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, params=params or {}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if payload.get("meta", {}).get("status") != 200:
        raise RuntimeError(f"Genius API 오류: {payload.get('meta')}")
    return payload.get("response", {})


def _is_meta_parenthetical(content: str) -> bool:
    normalized = _normalize_text(content)
    if not normalized:
        return False
    tokens = set(normalized.split())
    if _TITLE_META_KEYWORDS & tokens:
        return True
    return any(phrase in normalized for phrase in ("radio edit", "extended mix", "bonus track"))


def _build_title_aliases(title: str) -> List[str]:
    raw = (title or "").strip()
    aliases = set()
    if not raw:
        return []

    whole = _normalize_text(raw, keep_parenthetical=True)
    if whole:
        aliases.add(whole)

    parenthetical_contents = []
    parenthetical_contents.extend(re.findall(r"\(([^)]*)\)", raw))
    parenthetical_contents.extend(re.findall(r"\[([^\]]*)\]", raw))
    parenthetical_contents = [c.strip() for c in parenthetical_contents if c.strip()]

    for content in parenthetical_contents:
        if _is_meta_parenthetical(content):
            continue
        normalized_content = _normalize_text(content, keep_parenthetical=True)
        if normalized_content:
            aliases.add(normalized_content)

    outside = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", raw)
    outside = _normalize_text(outside, keep_parenthetical=True)
    if outside and (not parenthetical_contents or all(not _is_meta_parenthetical(c) for c in parenthetical_contents)):
        aliases.add(outside)

    return sorted(aliases)


def _title_exact_match(query_title: str, candidate_title: str) -> bool:
    query_forms = {
        _normalize_text(query_title, keep_parenthetical=True),
        _normalize_text(query_title, keep_parenthetical=False),
    }
    query_forms = {q for q in query_forms if q}
    if not query_forms:
        return False

    aliases = set(_build_title_aliases(candidate_title))
    if not aliases:
        return False

    if any(q in aliases for q in query_forms):
        return True

    if any(_title_is_short(q) for q in query_forms):
        return False

    compact_queries = {q.replace(" ", "") for q in query_forms}
    compact_aliases = {a.replace(" ", "") for a in aliases}
    return bool(compact_queries & compact_aliases)


def _artist_match_score(query_artist: str, candidate_artist: str) -> float:
    q = _normalize_text(query_artist)
    c = _normalize_text(candidate_artist)
    if not q or not c:
        return 0.0
    if q == c:
        return 100.0

    score = 0.0
    if q in c or c in q:
        score += 42.0

    q_tokens = set(_tokenize(query_artist))
    c_tokens = set(_tokenize(candidate_artist))
    if q_tokens:
        overlap = len(q_tokens & c_tokens) / len(q_tokens)
        score += overlap * 45.0

    score += _sequence_ratio(q, c) * 13.0
    return round(score, 3)


def _search_artist_candidates(artist_name: str, token: str = None, max_candidates: int = 20) -> List[dict]:
    response = _genius_api_get("/search", token=token, params={"q": artist_name})
    hits = response.get("hits", [])

    dedup = {}
    for hit in hits:
        result = hit.get("result", {})
        primary_artist = result.get("primary_artist", {})
        artist_id = primary_artist.get("id")
        artist_display_name = primary_artist.get("name", "").strip()
        if not artist_id or not artist_display_name:
            continue
        if artist_id not in dedup:
            dedup[artist_id] = {
                "id": artist_id,
                "name": artist_display_name,
            }
        if len(dedup) >= max_candidates:
            break

    return list(dedup.values())


def _select_best_artist_candidate(candidates: List[dict], artist_name: str) -> Optional[dict]:
    if not candidates:
        return None

    ranked = []
    for candidate in candidates:
        score = _artist_match_score(artist_name, candidate.get("name", ""))
        ranked.append((score, candidate))

    ranked.sort(key=lambda x: x[0], reverse=True)
    best_score, best_candidate = ranked[0]
    if best_score < 35.0:
        return None
    selected = dict(best_candidate)
    selected["match_score"] = best_score
    return selected


def _fetch_artist_songs(
    artist_id: int,
    token: str = None,
    per_page: int = 50,
    max_pages: int = 20,
    debug: bool = False,
) -> List[dict]:
    songs = []
    page = 1
    seen_pages = set()

    while page and page not in seen_pages and len(seen_pages) < max_pages:
        seen_pages.add(page)
        response = _genius_api_get(
            f"/artists/{artist_id}/songs",
            token=token,
            params={"sort": "popularity", "per_page": per_page, "page": page},
        )
        page_songs = response.get("songs", []) or []

        if debug:
            print(
                f"[crawl.search_song] artist_id={artist_id} page={page} "
                f"fetched={len(page_songs)}"
            )

        for song in page_songs:
            primary_artist = song.get("primary_artist", {}) or {}
            songs.append(
                {
                    "title": song.get("title", ""),
                    "artist": primary_artist.get("name", "Unknown"),
                    "id": song.get("id"),
                    "url": song.get("url", ""),
                    "primary_artist_id": primary_artist.get("id"),
                    "source_page": page,
                }
            )

        next_page = response.get("next_page")
        if not next_page:
            break
        page = next_page

    return songs


def search_song(
    title: str,
    artist: str,
    token: str = None,
    limit: int = 10,
    debug: bool = None,
    per_page: int = 50,
    max_pages: int = 20,
):
    """
    Artist-first 곡 검색.
    1) 아티스트 후보 탐색
    2) 아티스트 곡 목록 페이지 순회
    3) 제목 exact 매칭만 통과
    """
    debug_mode = _is_debug_enabled(debug)

    if not title or not title.strip():
        return []
    if not artist or not artist.strip():
        if debug_mode:
            print("[crawl.search_song] artist is required for artist-first matching.")
        return []

    try:
        artist_candidates = _search_artist_candidates(artist, token=token, max_candidates=20)
        selected_artist = _select_best_artist_candidate(artist_candidates, artist)

        if debug_mode:
            print(f"[crawl.search_song] title='{title}' artist='{artist}'")
            print(f"[crawl.search_song] artist_candidates={len(artist_candidates)}")
            if selected_artist:
                print(
                    f"[crawl.search_song] selected_artist="
                    f"{selected_artist['id']}:{selected_artist['name']} "
                    f"(score={selected_artist['match_score']})"
                )

        if not selected_artist:
            return []

        songs = _fetch_artist_songs(
            artist_id=selected_artist["id"],
            token=token,
            per_page=per_page,
            max_pages=max_pages,
            debug=debug_mode,
        )

        matches = []
        for song in songs:
            if song.get("primary_artist_id") != selected_artist["id"]:
                continue
            if not _title_exact_match(title, song.get("title", "")):
                continue

            match = dict(song)
            match["match_score"] = 100.0
            match["match_reasons"] = ["artist_first", "title_exact"]
            match["match_artist"] = {
                "id": selected_artist["id"],
                "name": selected_artist["name"],
                "score": selected_artist["match_score"],
            }
            matches.append(match)

        if debug_mode:
            print(f"[crawl.search_song] exact_matches={len(matches)}")

        dedup = []
        seen_song_ids = set()
        for song in matches:
            song_id = song.get("id")
            if song_id in seen_song_ids:
                continue
            seen_song_ids.add(song_id)
            dedup.append(song)

        return dedup[:limit]
    except Exception as e:
        print(f"검색 실패: {e}")
        return []


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


def search_and_get_lyrics(
    title: str,
    artist: str = "",
    token: str = None,
    debug: bool = None,
):
    """
    제목과 아티스트로 artist-first exact 검색 후 가사 반환
    Returns: {"title": ..., "artist": ..., "lyrics": ..., "url": ...} or None
    """
    genius = get_genius_client(token)
    
    try:
        debug_mode = _is_debug_enabled(debug)
        if not artist:
            if debug_mode:
                print("[crawl.search_and_get_lyrics] artist is required.")
            return None

        results = search_song(
            title=title,
            artist=artist,
            token=token,
            limit=20,
            debug=debug_mode,
        )
        
        if not results:
            return None

        if debug_mode:
            print(
                f"[crawl.search_and_get_lyrics] title='{title}' artist='{artist}' "
                f"result_count={len(results)}"
            )
        
        # 번역/로마자 버전 필터링
        filtered = filter_original_korean(results)
        
        if not filtered:
            # 필터링 후 결과 없으면 원본 결과 사용
            filtered = results
        
        # 첫 번째 결과로 가사 가져오기
        best_match = filtered[0]
        if debug_mode:
            print(
                f"[crawl.search_and_get_lyrics] selected='{best_match['title']}' / "
                f"'{best_match['artist']}'"
            )
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
        print("  python crawl.py '곡 제목' -a '아티스트'      # artist-first 검색 + 저장")
        print("  python crawl.py '아티스트' --artist-mode     # 아티스트 곡 전체")
        print("  python crawl.py '곡 제목' -a '아티스트' --search")
        print("")
        print("환경변수 설정 필요: export GENIUS_ACCESS_TOKEN='your_token'")
        sys.exit(0)
    
    try:
        if args.search:
            # 검색만 (artist-first)
            if not args.artist:
                print("오류: --search 모드에서는 --artist가 필수입니다.")
                sys.exit(1)
            results = search_song(
                title=args.query,
                artist=args.artist,
                token=args.token,
            )
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
