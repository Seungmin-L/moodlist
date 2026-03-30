"""
Spotify 플레이리스트 연동 모듈

플레이리스트 URL에서 곡 목록을 가져오고, 새 플레이리스트 생성
"""

import os
import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
REPO_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
except ImportError:
    print("spotipy 패키지가 필요합니다.")
    print("설치: pip install spotipy")
    sys.exit(1)


# OAuth 스코프 (필요한 권한들)
SCOPES = [
    "playlist-read-private",      # 비공개 플레이리스트 읽기
    "playlist-read-collaborative", # 협업 플레이리스트 읽기
    "playlist-modify-public",      # 공개 플레이리스트 생성/수정
    "playlist-modify-private",     # 비공개 플레이리스트 생성/수정
]


def get_spotify_client_simple():
    """Spotify API 클라이언트 생성 (로그인 없이, 공개 데이터만)"""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError(
            "Spotify API 키가 필요합니다.\n"
            ".env 파일에 SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET 추가"
        )
    
    auth_manager = SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_spotify_client_oauth(cache_path: str = None):
    """
    Spotify API 클라이언트 생성 (OAuth 로그인, 전체 기능)
    처음 실행 시 브라우저에서 로그인 필요
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = "http://127.0.0.1:8888/callback"
    
    if not client_id or not client_secret:
        raise ValueError(
            "Spotify API 키가 필요합니다.\n"
            ".env 파일에 SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET 추가"
        )
    
    if cache_path is None:
        cache_path = str(REPO_ROOT / ".spotify_cache")
    
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=" ".join(SCOPES),
        cache_path=cache_path,
        open_browser=True
    )
    
    return spotipy.Spotify(auth_manager=auth_manager)


def is_logged_in(cache_path: str = None) -> bool:
    """OAuth 로그인 상태 확인"""
    if cache_path is None:
        cache_path = str(REPO_ROOT / ".spotify_cache")
    
    try:
        if not os.path.exists(cache_path):
            return False
        
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        redirect_uri = "http://127.0.0.1:8888/callback"
        
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=" ".join(SCOPES),
            cache_path=cache_path,
            open_browser=False
        )
        
        token_info = auth_manager.get_cached_token()
        return token_info is not None
    except:
        return False


def get_current_user(sp=None):
    """현재 로그인한 유저 정보"""
    if sp is None:
        sp = get_spotify_client_oauth()
    return sp.current_user()


def extract_playlist_id(url_or_id: str) -> str:
    """
    Spotify 플레이리스트 URL 또는 ID에서 ID 추출
    """
    match = re.search(r'playlist[/:]([a-zA-Z0-9]+)', url_or_id)
    if match:
        return match.group(1)
    
    if re.match(r'^[a-zA-Z0-9]+$', url_or_id):
        return url_or_id
    
    raise ValueError(f"유효하지 않은 플레이리스트 URL/ID: {url_or_id}")


def get_playlist_tracks(playlist_url: str, use_oauth: bool = False) -> list:
    """
    플레이리스트에서 곡 목록 가져오기
    use_oauth=True면 비공개 플레이리스트도 접근 가능
    """
    if use_oauth:
        sp = get_spotify_client_oauth()
    else:
        sp = get_spotify_client_simple()
    
    playlist_id = extract_playlist_id(playlist_url)
    
    tracks = []
    offset = 0
    limit = 100
    
    while True:
        results = sp.playlist_tracks(
            playlist_id,
            offset=offset,
            limit=limit,
            fields="items(track(id,name,uri,artists(name),album(name))),total"
        )
        
        for item in results.get("items", []):
            track = item.get("track")
            if not track:
                continue
            
            artists = ", ".join([a["name"] for a in track.get("artists", [])])
            
            tracks.append({
                "id": track.get("id", ""),
                "uri": track.get("uri", ""),
                "title": track.get("name", ""),
                "artist": artists,
                "album": track.get("album", {}).get("name", "")
            })
        
        offset += limit
        if offset >= results.get("total", 0):
            break
    
    return tracks


def get_playlist_info(playlist_url: str, use_oauth: bool = False) -> dict:
    """플레이리스트 정보 가져오기"""
    if use_oauth:
        sp = get_spotify_client_oauth()
    else:
        sp = get_spotify_client_simple()
    
    playlist_id = extract_playlist_id(playlist_url)
    
    playlist = sp.playlist(
        playlist_id,
        fields="name,description,tracks(total),images"
    )
    
    image_url = None
    if playlist.get("images"):
        image_url = playlist["images"][0].get("url")
    
    return {
        "name": playlist.get("name", ""),
        "description": playlist.get("description", ""),
        "total": playlist.get("tracks", {}).get("total", 0),
        "image": image_url
    }


def get_my_playlists(use_oauth: bool = True) -> list:
    """내 플레이리스트 목록 가져오기"""
    sp = get_spotify_client_oauth()
    
    playlists = []
    offset = 0
    limit = 50
    
    while True:
        results = sp.current_user_playlists(offset=offset, limit=limit)
        
        for item in results.get("items", []):
            image_url = None
            if item.get("images"):
                image_url = item["images"][0].get("url")
            
            playlists.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "total": item.get("tracks", {}).get("total", 0),
                "public": item.get("public", False),
                "image": image_url
            })
        
        offset += limit
        if offset >= results.get("total", 0):
            break
    
    return playlists


def create_playlist(name: str, description: str = "", public: bool = True) -> dict:
    """
    새 플레이리스트 생성
    Returns: {"id": ..., "url": ...}
    """
    sp = get_spotify_client_oauth()
    user = sp.current_user()
    user_id = user["id"]
    
    playlist = sp.user_playlist_create(
        user=user_id,
        name=name,
        public=public,
        description=description
    )
    
    return {
        "id": playlist["id"],
        "url": playlist["external_urls"]["spotify"]
    }


def add_tracks_to_playlist(playlist_id: str, track_uris: list) -> bool:
    """
    플레이리스트에 곡 추가
    track_uris: ["spotify:track:xxx", ...] 형식
    """
    sp = get_spotify_client_oauth()
    
    # 100개씩 나눠서 추가 (API 제한)
    for i in range(0, len(track_uris), 100):
        batch = track_uris[i:i+100]
        sp.playlist_add_items(playlist_id, batch)
    
    return True


_COVER_KEYWORDS = [
    "karaoke", "cover", "tribute", "instrumental", "originally performed",
    "made famous", "in the style of", "backing track", "minus one",
    "카라오케", "커버", "MR", "반주",
]

def _is_cover(track: dict) -> bool:
    name = track.get("name", "").lower()
    artists = " ".join(a["name"] for a in track.get("artists", [])).lower()
    return any(kw.lower() in name or kw.lower() in artists for kw in _COVER_KEYWORDS)


def search_track(title: str, artist: str = "") -> dict:
    """
    Spotify에서 곡 검색 (카라오케/커버 버전 필터링)
    Returns: {"id": ..., "uri": ..., "title": ..., "artist": ...} or None
    """
    sp = get_spotify_client_simple()

    query = f"track:{title}"
    if artist:
        query += f" artist:{artist}"

    results = sp.search(q=query, type="track", limit=5)

    tracks = results.get("tracks", {}).get("items", [])
    if not tracks:
        return None

    # 카라오케/커버 아닌 첫 번째 결과 선택, 없으면 첫 번째
    track = next((t for t in tracks if not _is_cover(t)), tracks[0])
    artists = ", ".join([a["name"] for a in track.get("artists", [])])

    return {
        "id": track["id"],
        "uri": track["uri"],
        "title": track["name"],
        "artist": artists
    }


# ======================
# CLI
# ======================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Spotify 플레이리스트 관리")
    parser.add_argument("url", nargs="?", help="플레이리스트 URL")
    parser.add_argument("--login", action="store_true", help="Spotify 로그인")
    parser.add_argument("--me", action="store_true", help="내 정보 확인")
    parser.add_argument("--my-playlists", action="store_true", help="내 플레이리스트 목록")
    parser.add_argument("--create", metavar="NAME", help="새 플레이리스트 생성")
    
    args = parser.parse_args()
    
    try:
        if args.login:
            sp = get_spotify_client_oauth()
            user = sp.current_user()
            print(f"✅ 로그인 성공: {user['display_name']}")
        
        elif args.me:
            user = get_current_user()
            print(f"👤 {user['display_name']}")
            print(f"   ID: {user['id']}")
        
        elif args.my_playlists:
            playlists = get_my_playlists()
            print(f"\n📚 내 플레이리스트 ({len(playlists)}개):\n")
            for p in playlists:
                status = "🔓" if p['public'] else "🔒"
                print(f"  {status} {p['name']} ({p['total']}곡)")
        
        elif args.create:
            result = create_playlist(args.create)
            print(f"✅ 플레이리스트 생성됨: {result['url']}")
        
        elif args.url:
            print("곡 목록 가져오는 중...")
            tracks = get_playlist_tracks(args.url, use_oauth=is_logged_in())
            print(f"\n총 {len(tracks)}곡:\n")
            for i, t in enumerate(tracks[:20], 1):
                print(f"  {i}. {t['title']} - {t['artist']}")
            if len(tracks) > 20:
                print(f"  ... 외 {len(tracks) - 20}곡")
        
        else:
            print("사용법:")
            print("  python spotify.py --login              # Spotify 로그인")
            print("  python spotify.py --me                 # 내 정보")
            print("  python spotify.py --my-playlists       # 내 플레이리스트")
            print("  python spotify.py 'URL'                # 플레이리스트 곡 목록")
            print("  python spotify.py --create '이름'      # 새 플레이리스트")
    
    except Exception as e:
        print(f"오류: {e}")