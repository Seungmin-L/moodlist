"""
Spotify market=KR 테스트
영어 제목 → ISRC → market=KR 검색 → 한국어 제목?
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Spotify 클라이언트
auth_manager = SpotifyClientCredentials(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET")
)
sp = spotipy.Spotify(auth_manager=auth_manager)

def test_korean_title(track_name: str, artist_name: str):
    """영어 제목으로 검색 → ISRC → market=KR로 재검색"""
    
    print(f"\n{'='*60}")
    print(f"테스트: {track_name} - {artist_name}")
    print('='*60)
    
    # 1. 기본 검색 (market 없이)
    print("\n[1] 기본 검색 (market 없음)")
    query = f"track:{track_name} artist:{artist_name}"
    results = sp.search(q=query, type="track", limit=1)
    
    if not results['tracks']['items']:
        print("  → 검색 결과 없음")
        return
    
    track = results['tracks']['items'][0]
    print(f"  제목: {track['name']}")
    print(f"  아티스트: {track['artists'][0]['name']}")
    
    # 2. Track ID로 상세 정보 (ISRC 포함)
    print("\n[2] ISRC 조회")
    track_id = track['id']
    track_detail = sp.track(track_id)
    isrc = track_detail.get('external_ids', {}).get('isrc')
    print(f"  ISRC: {isrc}")
    
    if not isrc:
        print("  → ISRC 없음")
        return
    
    # 3. ISRC로 market=KR 검색
    print("\n[3] ISRC로 market=KR 검색")
    kr_results = sp.search(q=f"isrc:{isrc}", type="track", limit=1, market="KR")
    
    if kr_results['tracks']['items']:
        kr_track = kr_results['tracks']['items'][0]
        print(f"  제목: {kr_track['name']}")
        print(f"  아티스트: {kr_track['artists'][0]['name']}")
    else:
        print("  → 결과 없음")
    
    # 4. 비교를 위해 다른 market도 테스트
    print("\n[4] market=US 검색")
    us_results = sp.search(q=f"isrc:{isrc}", type="track", limit=1, market="US")
    
    if us_results['tracks']['items']:
        us_track = us_results['tracks']['items'][0]
        print(f"  제목: {us_track['name']}")
        print(f"  아티스트: {us_track['artists'][0]['name']}")
    else:
        print("  → 결과 없음")
    
    # 5. Track ID로 직접 market=KR 조회
    print("\n[5] Track ID로 market=KR 직접 조회")
    try:
        kr_track_direct = sp.track(track_id, market="KR")
        print(f"  제목: {kr_track_direct['name']}")
        print(f"  아티스트: {kr_track_direct['artists'][0]['name']}")
    except Exception as e:
        print(f"  → 에러: {e}")


if __name__ == "__main__":
    # 테스트 케이스들
    test_cases = [
        ("Snowy Wish", "Girls' Generation"),  # 첫눈에...
        ("Through the Night", "IU"),           # 밤편지
        ("Love In My Heart", "BABYMONSTER"),   # 스크린샷에서 본 곡
    ]
    
    for track, artist in test_cases:
        test_korean_title(track, artist)