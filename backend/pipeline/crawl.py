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
from typing import List, Dict
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent
REPO_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

def insert_bronze(title, artist, raw_lyrics, source_url=None):
    pass  # Spotify-first 파이프라인으로 전환 후 미사용

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
_GENIUS_PUBLIC_API_BASE = "https://genius.com/api"
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


def _genius_public_get(path: str, params: Dict = None) -> Dict:
    url = f"{_GENIUS_PUBLIC_API_BASE}{path}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }
    response = requests.get(url, params=params or {}, headers=headers, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if payload.get("meta", {}).get("status") != 200:
        raise RuntimeError(f"Genius Public API 오류: {payload.get('meta')}")
    return payload.get("response", {})


def _normalize_compact(value: str) -> str:
    return _normalize_text(value).replace(" ", "")


def _build_artist_aliases(value: str) -> List[str]:
    raw = (value or "").strip()
    if not raw:
        return []

    aliases = set()
    whole = _normalize_text(raw, keep_parenthetical=True)
    if whole:
        aliases.add(whole)

    outside = _normalize_text(raw, keep_parenthetical=False)
    if outside:
        aliases.add(outside)

    parenthetical_contents = []
    parenthetical_contents.extend(re.findall(r"\(([^)]*)\)", raw))
    parenthetical_contents.extend(re.findall(r"\[([^\]]*)\]", raw))
    for content in parenthetical_contents:
        normalized = _normalize_text(content, keep_parenthetical=True)
        if normalized:
            aliases.add(normalized)

    return sorted(aliases)


def _split_artist_inputs(artist: str) -> List[str]:
    raw = (artist or "").strip()
    if not raw:
        return []

    parts = re.split(
        r"\s*(?:,|;|/|&| and | feat\.?| ft\.?| featuring )\s*",
        raw,
        flags=re.IGNORECASE,
    )
    dedup = []
    seen = set()
    for part in parts:
        clean = part.strip()
        if not clean:
            continue
        key = _normalize_compact(clean)
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(clean)
    return dedup


def _artist_anchor_match(anchor_artist: str, candidate_artist: str) -> Dict:
    anchor_aliases = _build_artist_aliases(anchor_artist)
    candidate_aliases = _build_artist_aliases(candidate_artist)
    if not anchor_aliases or not candidate_aliases:
        return {"score": 0.0, "exact": False}

    anchor_set = set(anchor_aliases)
    candidate_set = set(candidate_aliases)
    anchor_compact = {a.replace(" ", "") for a in anchor_set if a}
    candidate_compact = {a.replace(" ", "") for a in candidate_set if a}

    exact = bool((anchor_set & candidate_set) or (anchor_compact & candidate_compact))
    contains = any(
        (a and c and (a in c or c in a))
        for a in anchor_aliases
        for c in candidate_aliases
    )
    seq = max(
        (_sequence_ratio(a, c) for a in anchor_aliases for c in candidate_aliases),
        default=0.0,
    )

    score = 0.0
    if exact:
        score += 100.0
    if contains:
        score += 20.0
    score += seq * 15.0

    return {
        "score": round(score, 3),
        "exact": exact,
        "contains": contains,
        "sequence": round(seq, 3),
    }


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


def _search_artist_candidates_authenticated(anchor_artist: str, token: str = None, max_candidates: int = 30) -> List[dict]:
    """인증 API로 아티스트 후보 검색 (Public API 403 fallback)"""
    response = _genius_api_get(
        "/search",
        token=token,
        params={"q": anchor_artist, "per_page": min(max_candidates, 20)},
    )

    hits = response.get("hits", []) or []
    dedup = {}
    for hit in hits:
        result = hit.get("result", {}) or {}
        primary = result.get("primary_artist", {}) or {}
        artist_id = primary.get("id")
        artist_name = (primary.get("name") or "").strip()
        if not artist_id or not artist_name:
            continue
        if artist_id in dedup:
            continue
        dedup[artist_id] = {
            "id": artist_id,
            "name": artist_name,
            "url": primary.get("url", ""),
            "api_path": primary.get("api_path", ""),
        }
        if len(dedup) >= max_candidates:
            break

    return list(dedup.values())


def _search_artist_candidates_public(anchor_artist: str, token: str = None, max_candidates: int = 30) -> List[dict]:
    try:
        response = _genius_public_get(
            "/search/artist",
            params={"q": anchor_artist, "per_page": max_candidates},
        )
    except Exception:
        # Public API 차단 시 인증 API로 fallback
        return _search_artist_candidates_authenticated(anchor_artist, token=token, max_candidates=max_candidates)

    sections = response.get("sections", []) or []
    artist_hits = []
    for section in sections:
        if (section.get("type") or "").lower() == "artist":
            artist_hits.extend(section.get("hits", []) or [])

    # 일부 응답 포맷 대응
    if not artist_hits:
        artist_hits = response.get("hits", []) or []

    dedup = {}
    for hit in artist_hits:
        result = hit.get("result", {}) or {}
        artist_id = result.get("id")
        artist_name = (result.get("name") or "").strip()
        if not artist_id or not artist_name:
            continue
        if artist_id in dedup:
            continue
        dedup[artist_id] = {
            "id": artist_id,
            "name": artist_name,
            "url": result.get("url", ""),
            "api_path": result.get("api_path", ""),
        }
        if len(dedup) >= max_candidates:
            break

    return list(dedup.values())


def _rank_public_artist_candidates(anchor_artist: str, candidates: List[dict]) -> List[dict]:
    ranked = []
    for candidate in candidates:
        metrics = _artist_anchor_match(anchor_artist, candidate.get("name", ""))
        ranked.append(
            {
                "id": candidate.get("id"),
                "name": candidate.get("name", ""),
                "url": candidate.get("url", ""),
                "api_path": candidate.get("api_path", ""),
                "score": metrics["score"],
                "exact": metrics["exact"],
                "contains": metrics["contains"],
                "sequence": metrics["sequence"],
            }
        )
    ranked.sort(
        key=lambda c: (1 if c.get("exact") else 0, c.get("score", 0.0), c.get("sequence", 0.0)),
        reverse=True,
    )
    return ranked


def _select_artist_candidates_for_verification(ranked_candidates: List[dict], top_k: int = 3) -> List[dict]:
    if not ranked_candidates:
        return []

    selected = []
    seen_ids = set()

    def _append(candidate: dict):
        artist_id = candidate.get("id")
        if artist_id in seen_ids:
            return
        seen_ids.add(artist_id)
        selected.append(candidate)

    for candidate in ranked_candidates:
        if candidate.get("exact"):
            _append(candidate)
        if len(selected) >= top_k:
            return selected[:top_k]

    # exact가 없을 때는 강한 유사 후보까지 검증 대상으로 포함
    for candidate in ranked_candidates:
        if candidate.get("contains") and candidate.get("sequence", 0.0) >= 0.72:
            _append(candidate)
        if len(selected) >= top_k:
            return selected[:top_k]

    for candidate in ranked_candidates:
        if candidate.get("score", 0.0) >= 30.0:
            _append(candidate)
        if len(selected) >= top_k:
            return selected[:top_k]

    for candidate in ranked_candidates:
        _append(candidate)
        if len(selected) >= top_k:
            break

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


def summarize_search_diagnostics(diagnostics: dict) -> str:
    if not diagnostics:
        return "diagnostics 없음"

    stage = diagnostics.get("failure_stage") or "ok"
    anchor_artist = diagnostics.get("anchor_artist", "")
    artist_parts = diagnostics.get("artist_parts", []) or []
    parts_text = ", ".join(artist_parts[:3]) or "없음"
    selected = diagnostics.get("selected_artist")
    if selected:
        selected_text = (
            f"{selected.get('name', 'unknown')}[{selected.get('id', '-')}]"
            f"/score={selected.get('match_score', 0.0):.1f}"
        )
    else:
        selected_text = "없음"

    artist_candidates = diagnostics.get("artist_candidates", [])
    artist_candidate_count = diagnostics.get("artist_candidate_count", len(artist_candidates))
    artist_candidates_text = ", ".join(
        [f"{c.get('name', 'unknown')}[{c.get('score', 0.0):.1f}]" for c in artist_candidates[:3]]
    ) or "없음"

    verified_artists = diagnostics.get("verified_artists", [])
    verified_text = ", ".join(
        [f"{c.get('name', 'unknown')}[{c.get('score', 0.0):.1f}]" for c in verified_artists[:3]]
    ) or "없음"

    near_misses = diagnostics.get("near_misses", [])
    near_misses_text = ", ".join(
        [
            f"{m.get('title', '')}[{m.get('similarity', 0.0):.2f}"
            f"@{m.get('candidate_artist', '-')}]"
            for m in near_misses[:3]
        ]
    ) or "없음"

    return (
        f"stage={stage} | anchor={anchor_artist or '없음'} | parts={parts_text} | selected={selected_text} | "
        f"artist_candidate_count={artist_candidate_count} | "
        f"artist_candidates={artist_candidates_text} | "
        f"verified={verified_text} | "
        f"pages={diagnostics.get('pages_fetched', 0)} songs={diagnostics.get('songs_scanned', 0)} "
        f"non_primary_skip={diagnostics.get('non_primary_skipped', 0)} | "
        f"near={near_misses_text}"
    )


def search_song_with_diagnostics(
    title: str,
    artist: str,
    token: str = None,
    limit: int = 10,
    debug: bool = None,
    per_page: int = 30,
    max_pages: int = 6,
    verify_top_k: int = 2,
):
    """
    Artist-first 곡 검색.
    1) 아티스트 후보 탐색
    2) 아티스트 곡 목록 페이지 순회
    3) 제목 exact 매칭만 통과
    """
    debug_mode = _is_debug_enabled(debug)
    diagnostics = {
        "query_title": title,
        "query_artist": artist,
        "anchor_artist": "",
        "artist_parts": [],
        "artist_candidates": [],
        "artist_candidate_count": 0,
        "verified_artists": [],
        "selected_artist": None,
        "pages_fetched": 0,
        "songs_scanned": 0,
        "non_primary_skipped": 0,
        "exact_match_count": 0,
        "near_misses": [],
        "failure_stage": None,
        "error": None,
    }

    if not title or not title.strip():
        diagnostics["failure_stage"] = "empty_title"
        return [], diagnostics
    if not artist or not artist.strip():
        if debug_mode:
            print("[crawl.search_song] artist is required for artist-first matching.")
        diagnostics["failure_stage"] = "empty_artist"
        return [], diagnostics

    artist_parts = _split_artist_inputs(artist)
    anchor_artist = artist_parts[0] if artist_parts else artist.strip()
    diagnostics["artist_parts"] = artist_parts
    diagnostics["anchor_artist"] = anchor_artist

    if not anchor_artist:
        diagnostics["failure_stage"] = "empty_artist"
        return [], diagnostics

    try:
        artist_candidates = _search_artist_candidates_public(anchor_artist, token=token, max_candidates=30)
        ranked_candidates = _rank_public_artist_candidates(anchor_artist, artist_candidates)
        diagnostics["artist_candidate_count"] = len(ranked_candidates)
        diagnostics["artist_candidates"] = ranked_candidates[:5]
        verify_candidates = _select_artist_candidates_for_verification(
            ranked_candidates,
            top_k=max(1, verify_top_k),
        )

        if verify_candidates:
            diagnostics["selected_artist"] = {
                "id": verify_candidates[0]["id"],
                "name": verify_candidates[0]["name"],
                "match_score": verify_candidates[0]["score"],
            }

        if debug_mode:
            print(f"[crawl.search_song] title='{title}' artist='{artist}'")
            print(
                f"[crawl.search_song] artist_parts={artist_parts} "
                f"anchor='{anchor_artist}' candidates={len(ranked_candidates)}"
            )
            if diagnostics["selected_artist"]:
                print(
                    f"[crawl.search_song] selected_artist="
                    f"{diagnostics['selected_artist']['id']}:{diagnostics['selected_artist']['name']} "
                    f"(score={diagnostics['selected_artist']['match_score']})"
                )

        if not verify_candidates:
            diagnostics["failure_stage"] = "artist_selection"
            return [], diagnostics

        matches = []
        near_misses = []
        query_norm = _normalize_text(title, keep_parenthetical=True)
        for candidate in verify_candidates:
            candidate_id = candidate["id"]
            candidate_name = candidate["name"]
            diagnostics["verified_artists"].append(
                {
                    "id": candidate_id,
                    "name": candidate_name,
                    "score": candidate["score"],
                }
            )

            songs = _fetch_artist_songs(
                artist_id=candidate_id,
                token=token,
                per_page=per_page,
                max_pages=max_pages,
                debug=debug_mode,
            )
            diagnostics["pages_fetched"] += len({s.get("source_page") for s in songs})
            diagnostics["songs_scanned"] += len(songs)

            candidate_match_count = 0
            for song in songs:
                if song.get("primary_artist_id") != candidate_id:
                    diagnostics["non_primary_skipped"] += 1
                    continue
                if not _title_exact_match(title, song.get("title", "")):
                    candidate_norm = _normalize_text(song.get("title", ""), keep_parenthetical=True)
                    near_misses.append(
                        {
                            "title": song.get("title", ""),
                            "artist": song.get("artist", ""),
                            "candidate_artist": candidate_name,
                            "similarity": round(_sequence_ratio(query_norm, candidate_norm), 3),
                            "page": song.get("source_page"),
                        }
                    )
                    continue

                match = dict(song)
                match["match_score"] = 100.0
                match["match_reasons"] = ["artist_anchor_exact", "title_exact"]
                match["match_artist"] = {
                    "id": candidate_id,
                    "name": candidate_name,
                    "score": candidate["score"],
                }
                matches.append(match)
                candidate_match_count += 1

            if debug_mode:
                print(
                    f"[crawl.search_song] verified_artist={candidate_name}[{candidate_id}] "
                    f"exact_matches={candidate_match_count}"
                )

            # top-k 순차 검증: 첫 번째로 제목 exact가 나온 아티스트를 채택
            if candidate_match_count > 0:
                break

        if debug_mode:
            print(f"[crawl.search_song] exact_matches={len(matches)}")

        near_misses.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        diagnostics["near_misses"] = near_misses[:5]

        dedup = []
        seen_song_ids = set()
        for song in matches:
            song_id = song.get("id")
            if song_id in seen_song_ids:
                continue
            seen_song_ids.add(song_id)
            dedup.append(song)

        diagnostics["exact_match_count"] = len(dedup)
        if not dedup:
            diagnostics["failure_stage"] = "title_exact"
        return dedup[:limit], diagnostics
    except Exception as e:
        print(f"검색 실패: {e}")
        diagnostics["failure_stage"] = "exception"
        diagnostics["error"] = str(e)
        return [], diagnostics


def search_song(
    title: str,
    artist: str,
    token: str = None,
    limit: int = 10,
    debug: bool = None,
    per_page: int = 30,
    max_pages: int = 6,
    verify_top_k: int = 2,
):
    results, diagnostics = search_song_with_diagnostics(
        title=title,
        artist=artist,
        token=token,
        limit=limit,
        debug=debug,
        per_page=per_page,
        max_pages=max_pages,
        verify_top_k=verify_top_k,
    )
    if _is_debug_enabled(debug) and not results:
        print(f"[crawl.search_song] diagnostics: {summarize_search_diagnostics(diagnostics)}")
    return results


def get_lyrics(song_id: int = None, song_url: str = None, token: str = None):
    """
    곡 ID 또는 URL로 가사 가져오기 (data-lyrics-container 직접 스크래핑)
    Returns: str (가사) or None
    """
    import requests
    from bs4 import BeautifulSoup

    if not song_url:
        return None

    try:
        resp = requests.get(
            song_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://genius.com/",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"가사 가져오기 실패: HTTP {resp.status_code}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        if not containers:
            return None
        parts = []
        for container in containers:
            for br in container.find_all("br"):
                br.replace_with("\n")
            parts.append(container.get_text(separator="\n"))
        lyrics = "\n".join(parts).strip()
        return lyrics if lyrics else None
    except Exception as e:
        print(f"가사 가져오기 실패: {e}")
        return None


def _search_bugs_direct(korean_title: str, korean_artist: str) -> str | None:
    """
    bugs 검색 페이지를 직접 스크래핑해서 한국어 제목+아티스트로 트랙을 찾고 가사 반환.
    webkr 인덱싱에 없는 곡도 커버.
    """
    import requests
    from bs4 import BeautifulSoup

    query = f"{korean_title} {korean_artist}".strip()
    url = f"https://music.bugs.co.kr/search/track?q={requests.utils.quote(query)}"
    print(f"[bugs-direct] 검색 — query={query!r}")

    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[bugs-direct] 검색 실패: {e}")
        return None

    norm_title = re.sub(r"[^가-힣a-z0-9]", "", korean_title.lower())

    for row in soup.select("table.trackList tbody tr"):
        title_el = row.select_one("p.title a")
        if not title_el:
            continue
        row_title = title_el.text.strip()
        norm_row = re.sub(r"[^가-힣a-z0-9]", "", row_title.lower())
        if norm_title and norm_title in norm_row:
            # tr[trackid] 속성에서 트랙 ID 추출
            track_id = row.get("trackid")
            if not track_id:
                m = re.search(r"listen\('?(\d+)", title_el.get("onclick", ""))
                track_id = m.group(1) if m else None
            if not track_id:
                print(f"[bugs-direct] 트랙 ID 추출 실패: {row_title!r}")
                continue
            track_link = f"https://music.bugs.co.kr/track/{track_id}"
            print(f"[bugs-direct] ▶ 트랙 선택: {row_title!r} → {track_link!r}")
            return _scrape_bugs_lyrics(track_link)

    print(f"[bugs-direct] 제목 일치 결과 없음 — {korean_title!r}")
    return None


def _scrape_bugs_lyrics(url: str) -> str | None:
    """bugs.co.kr 트랙 페이지에서 가사 스크래핑"""
    import requests
    from bs4 import BeautifulSoup

    try:
        page = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"},
            timeout=10,
        )
        print(f"[bugs]   status_code={page.status_code}")
        soup = BeautifulSoup(page.text, "html.parser")

        selectors = [
            ("div.lyricsContainer", soup.find("div", class_="lyricsContainer")),
            ("div.lyrics",          soup.find("div", class_="lyrics")),
            ("div#lyrics",          soup.find("div", id="lyrics")),
            ("xmp",                 soup.find("xmp")),
            ("p.lyrics",            soup.find("p", class_="lyrics")),
        ]
        for name, c in selectors:
            preview = repr(c.get_text()[:80].strip()) if c else None
            print(f"[bugs]   selector={name!r} found={c is not None}, preview={preview}")

        lyric_el = next((c for _, c in selectors if c), None)
        if not lyric_el:
            print(f"[bugs]   가사 컨테이너 못 찾음, body 일부:")
            print(page.text[2000:4000])
            return None

        lyrics = lyric_el.get_text(separator="\n").strip()
        print(f"[bugs] ✓ 가사 추출 완료 — {len(lyrics)}자")
        return lyrics if lyrics else None
    except Exception as e:
        print(f"[bugs] 스크래핑 실패: {e}")
        return None


def _extract_korean_artist(items: list, english_artist: str) -> str | None:
    """
    webkr 결과 제목에서 영문 아티스트명 앞에 붙은 한글명 추출.
    예: "이해할 수 없는 것들 ... | 안희수 Ahn Heesu | ..." → "안희수"
    """
    from collections import Counter

    norm_english = re.sub(r"[^a-z]", "", english_artist.lower())
    if not norm_english:
        return None

    candidates = []
    for item in items:
        combined = re.sub(r"<[^>]+>", "", item.get("title", "") + " " + item.get("description", ""))
        # 영문 아티스트명이 포함된 결과에서만 추출
        if norm_english not in re.sub(r"[^a-z]", "", combined.lower()):
            continue
        # 한글명 추출 패턴 (3가지)
        # "안희수 Ahn Heesu" / "이영훈 (Lee Young Hoon)" / "Ahn Heesu (안희수)"
        patterns = [
            rf'([가-힣]{{2,6}})\s+{re.escape(english_artist)}',
            rf'([가-힣]{{2,6}})\s*\({re.escape(english_artist)}\)',
            rf'{re.escape(english_artist)}\s*\(([가-힣]{{2,6}})\)',
        ]
        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                candidates.append(match.group(1))
                break

    if not candidates:
        return None

    korean_name = Counter(candidates).most_common(1)[0][0]
    print(f"[naver] ▶ 한글 아티스트명 추출: {english_artist!r} → {korean_name!r}")
    return korean_name


def _extract_korean_title(items: list, english_title: str, korean_artist: str) -> str | None:
    """webkr 결과에서 한글 제목 추출.
    패턴 1: "한글제목 (영문제목)" — 영문 제목이 괄호 안에 있는 경우
    패턴 2: "한글아티스트 - 한글제목" — 아티스트명 뒤 제목
    """
    from collections import Counter

    candidates = []
    for item in items:
        combined = re.sub(r"<[^>]+>", "", item.get("title", "") + " " + item.get("description", ""))

        p1 = rf'([가-힣]{{2,}}(?:\s[가-힣]+)*)\s*\({re.escape(english_title)}\)'
        m = re.search(p1, combined, re.IGNORECASE)
        if m:
            candidates.append(m.group(1).strip())
            continue

        if korean_artist:
            p2 = rf'{re.escape(korean_artist)}\s*(?:\([^)]*\))?\s*[-–]\s*([가-힣]{{2,}}(?:\s[가-힣]+)*)'
            m = re.search(p2, combined)
            if m:
                candidates.append(m.group(1).strip())

    if not candidates:
        return None

    korean_title = Counter(candidates).most_common(1)[0][0]
    print(f"[naver] ▶ 한글 제목 추출: {english_title!r} → {korean_title!r}")
    return korean_title


def _get_korean_title_itunes(title: str, artist: str) -> tuple[str, str] | tuple[None, None]:
    """
    iTunes Search API (country=KR)로 한국어 제목+아티스트명 조회.
    반환: (trackName, artistName) 또는 (None, None)
    """
    import requests

    try:
        resp = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": f"{artist} {title}",
                "country": "KR",
                "media": "music",
                "entity": "song",
                "limit": 5,
            },
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        print(f"[itunes] 조회 실패: {e}")
        return None, None

    if not results:
        print(f"[itunes] 결과 없음 — title={title!r}, artist={artist!r}")
        return None, None

    # 첫 번째로 한글 제목인 결과 채택
    # 아티스트 체크를 하지 않는 이유: 영문 아티스트명(Shin In Ryu)으로 검색하면
    # iTunes가 한국어 아티스트명(신인류)으로 반환해서 일치 비교가 불가능
    for track in results:
        track_name = track.get("trackName", "")
        artist_name = track.get("artistName", "")
        if re.search(r"[가-힣]", track_name):
            print(f"[itunes] ▶ 한국어 제목: {track_name!r}, 아티스트: {artist_name!r} (검색={title!r})")
            return track_name, artist_name

    print(f"[itunes] 한국어 제목 없음 — title={title!r}, artist={artist!r}")
    return None, None


def search_lyrics_naver(title: str, artist: str, isrc: str | None = None) -> str | None:
    """
    Genius 실패 시 Naver fallback.
    1. webkr 검색 → bugs.co.kr 트랙 링크 → 가사 스크래핑
    2. iTunes KR → 한국어 제목 획득 → bugs 재검색
    3. webkr 결과에서 한글명 추출 → bugs 재검색
    """
    import requests
    from bs4 import BeautifulSoup

    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[naver] NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 없음, fallback 스킵")
        return None

    query = f"{title} {artist} 가사"
    print(f"[naver] ▶ 웹 검색 — query={query!r}")

    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/webkr.json",
            params={"query": query, "display": 5},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=10,
        )
        print(f"[naver]   status_code={resp.status_code}")
        print(f"[naver]   raw response={resp.text[:1000]}")
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception as e:
        print(f"[naver] 웹 검색 실패: {e}")
        return None

    print(f"[naver]   검색 결과 수: {len(items)}")
    for i, item in enumerate(items):
        raw_title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        print(f"[naver]   [{i}] title={raw_title!r}, link={item.get('link')!r}")

    def _matches_query(item_title: str, title: str, artist: str) -> bool:
        normalized = item_title.lower()
        norm_title = re.sub(r"[^a-z0-9가-힣]", "", title.lower())
        norm_item = re.sub(r"[^a-z0-9가-힣]", "", normalized)
        title_match = title.lower() in normalized or (norm_title and norm_title in norm_item)
        artist_match = artist.lower() in normalized
        if len(artist) >= 4:
            return title_match and artist_match
        return title_match

    # 1단계: webkr 결과에서 bugs.co.kr 링크 탐색
    bugs_link = None
    for item in items:
        link = item.get("link", "")
        raw_title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        if "music.bugs.co.kr/track/" in link:
            if _matches_query(raw_title, title, artist):
                bugs_link = link
                print(f"[naver] ▶ 벅스 트랙 링크 선택: {bugs_link!r} (title={raw_title!r})")
                break
            else:
                print(f"[naver]   벅스 링크 스킵 (곡 불일치): {raw_title!r}")

    if bugs_link:
        print(f"[naver] ▶ 벅스 트랙 페이지 스크래핑 — url={bugs_link!r}")
        lyrics = _scrape_bugs_lyrics(bugs_link)
        if lyrics:
            return lyrics

    # 2단계: iTunes KR → 한국어 제목+아티스트 획득 → bugs 재검색
    print(f"[naver] ▶ iTunes KR 한국어 제목 조회 — title={title!r}, artist={artist!r}")
    itunes_korean_title, itunes_korean_artist = _get_korean_title_itunes(title, artist)
    if itunes_korean_title:
        # iTunes 아티스트명 우선, 없으면 webkr 추출, 그것도 없으면 영문 원본
        korean_artist = _extract_korean_artist(items, artist)
        search_artist = korean_artist or itunes_korean_artist or artist
        query_itunes = f"{itunes_korean_title} {search_artist} 가사"
        print(f"[naver] ▶ iTunes 한국어 제목으로 재검색 — query={query_itunes!r}")
        try:
            resp_it = requests.get(
                "https://openapi.naver.com/v1/search/webkr.json",
                params={"query": query_itunes, "display": 5},
                headers={
                    "X-Naver-Client-Id": client_id,
                    "X-Naver-Client-Secret": client_secret,
                },
                timeout=10,
            )
            resp_it.raise_for_status()
            items_it = resp_it.json().get("items", [])
        except Exception as e:
            print(f"[naver] iTunes 재검색 실패: {e}")
            items_it = []

        def _pick_bugs_by_title(items_list: list, ko_title: str) -> str | None:
            norm_ko = re.sub(r"[^가-힣a-z0-9]", "", ko_title.lower())
            for it in items_list:
                lnk = it.get("link", "")
                rt = re.sub(r"<[^>]+>", "", it.get("title", ""))
                if "music.bugs.co.kr/track/" in lnk:
                    norm_rt = re.sub(r"[^가-힣a-z0-9]", "", rt.lower())
                    if norm_ko and norm_ko in norm_rt:
                        print(f"[naver] ▶ iTunes 경로 벅스 링크 선택: {lnk!r}")
                        return _scrape_bugs_lyrics(lnk)
                    print(f"[naver]   iTunes 경로 벅스 링크 스킵 (제목 불일치): {rt!r}")
            return None

        lyrics = _pick_bugs_by_title(items_it, itunes_korean_title)
        if lyrics:
            return lyrics

        # search_artist가 영문인 경우(iTunes도 영문 아티스트 반환) 한국어 제목만으로 재시도
        if not re.search(r"[가-힣]", search_artist):
            query_title_only = f"{itunes_korean_title} 가사"
            print(f"[naver] ▶ iTunes 한국어 제목만으로 재검색 — query={query_title_only!r}")
            try:
                resp_to = requests.get(
                    "https://openapi.naver.com/v1/search/webkr.json",
                    params={"query": query_title_only, "display": 5},
                    headers={
                        "X-Naver-Client-Id": client_id,
                        "X-Naver-Client-Secret": client_secret,
                    },
                    timeout=10,
                )
                resp_to.raise_for_status()
                items_to = resp_to.json().get("items", [])
            except Exception as e:
                print(f"[naver] iTunes 제목만 재검색 실패: {e}")
                items_to = []

            lyrics = _pick_bugs_by_title(items_to, itunes_korean_title)
            if lyrics:
                return lyrics

        # webkr에서 bugs 링크를 못 찾은 경우 bugs 직접 검색
        lyrics = _search_bugs_direct(itunes_korean_title, search_artist)
        if lyrics:
            return lyrics

    # 3단계: webkr 결과에서 한글 아티스트명/제목 추출 → 한글명으로 재검색
    korean_artist = _extract_korean_artist(items, artist)
    if not korean_artist:
        print("[naver] 한글 아티스트명 추출 실패, fallback 중단")
        return None

    korean_title = _extract_korean_title(items, title, korean_artist)
    search_title = korean_title or title
    query2 = f"{search_title} {korean_artist} 가사"
    print(f"[naver] ▶ 한글명으로 재검색 — query={query2!r}")

    try:
        resp2 = requests.get(
            "https://openapi.naver.com/v1/search/webkr.json",
            params={"query": query2, "display": 5},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=10,
        )
        resp2.raise_for_status()
        items2 = resp2.json().get("items", [])
    except Exception as e:
        print(f"[naver] 재검색 실패: {e}")
        return None

    print(f"[naver]   재검색 결과 수: {len(items2)}")
    for i, item in enumerate(items2):
        raw_title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        print(f"[naver]   [{i}] title={raw_title!r}, link={item.get('link')!r}")

    for item in items2:
        link = item.get("link", "")
        raw_title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        if "music.bugs.co.kr/track/" in link:
            if _matches_query(raw_title, search_title, korean_artist):
                print(f"[naver] ▶ 재검색 벅스 링크 선택: {link!r} (title={raw_title!r})")
                lyrics = _scrape_bugs_lyrics(link)
                if lyrics:
                    return lyrics
            else:
                print(f"[naver]   재검색 벅스 링크 스킵 (곡 불일치): {raw_title!r}")

    print("[naver] 재검색에서도 벅스 링크 없음, fallback 중단")
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

        results, diagnostics = search_song_with_diagnostics(
            title=title,
            artist=artist,
            token=token,
            limit=20,
            debug=debug_mode,
        )
        
        if not results:
            if debug_mode:
                print(
                    "[crawl.search_and_get_lyrics] no exact match. "
                    f"{summarize_search_diagnostics(diagnostics)}"
                )
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
