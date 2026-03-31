"""
Moodlist FastAPI 백엔드
"""

import sys
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import (
    get_song,
    get_songs_by_category,
    get_all_categories,
    get_pending_songs,
    find_similar_songs,
    group_songs_by_mood,
    get_stats
)
from pipeline.classify import add_and_classify, classify_pending_songs


# ======================
# 앱 초기화
# ======================

@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.database import init_db
    init_db()
    yield

app = FastAPI(
    title="Moodlist API",
    description="가사 기반 곡 분류 + 플레이리스트 생성",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================
# 요청/응답 모델
# ======================

class AddSongRequest(BaseModel):
    title: str
    artist: str
    spotify_id: Optional[str] = None
    image_url: Optional[str] = None

class SpotifyImportRequest(BaseModel):
    playlist_url: str

class SpotifyExportRequest(BaseModel):
    mood: str
    playlist_name: str
    description: str = ""
    public: bool = True


# ======================
# 곡 관리
# ======================

@app.post("/songs", summary="곡 추가 + 분류")
async def add_song(req: AddSongRequest):
    """
    곡 추가 후 분류.
    1. Spotify에서 곡 검색 → spotify_id + 영어 제목/아티스트 확보
    2. 이미 분류된 곡이면 기존 결과 즉시 반환
    3. 신규 곡은 Genius에서 가사 크롤링 후 GPT 분류
    """
    try:
        from pipeline.classify import add_and_classify_by_id
        if req.spotify_id:
            result = add_and_classify_by_id(req.spotify_id, req.title, req.artist, image_url=req.image_url)
        else:
            result = add_and_classify(req.title, req.artist)

        # 최종 저장 상태를 DB에서 다시 읽어 내려준다 (album_art_url 포함 보장)
        spotify_id = result.get("spotify_id")
        song = get_song(spotify_id) if spotify_id else None
        if song:
            return {
                "already_exists": result.get("already_exists", False),
                **song
            }
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/songs", summary="곡 목록 조회")
async def list_songs(
    category: Optional[str] = Query(None, description="카테고리 필터 (관심/짝사랑/썸/사랑/권태기/갈등/이별/자기자신/일상/기타)"),
):
    return get_songs_by_category(category)


@app.get("/songs/pending", summary="분류 대기 중인 곡 목록")
async def list_pending():
    return get_pending_songs()


@app.get("/songs/{spotify_id}", summary="곡 상세 조회")
async def get_song_detail(spotify_id: str):
    song = get_song(spotify_id)
    if not song:
        raise HTTPException(status_code=404, detail=f"Song {spotify_id} 없음")
    return song


@app.get("/songs/{spotify_id}/similar", summary="유사곡 검색")
async def similar_songs(
    spotify_id: str,
    top_k: int = Query(10, ge=1, le=50, description="반환할 유사곡 수")
):
    """mood 임베딩 벡터 유사도 기반 유사곡 검색"""
    song = get_song(spotify_id)
    if not song:
        raise HTTPException(status_code=404, detail=f"Song {spotify_id} 없음")
    if song.get("status") != "classified":
        raise HTTPException(status_code=400, detail="아직 분류되지 않은 곡입니다")

    similar = find_similar_songs(spotify_id, top_k=top_k)
    return {
        "base_song": {
            "spotify_id": song["spotify_id"],
            "title": song["title"],
            "artist": song["artist"],
            "mood": song.get("mood")
        },
        "similar": similar
    }


@app.post("/songs/{spotify_id}/reclassify", summary="재분류")
async def reclassify_song(spotify_id: str):
    """분류 결과 재분류"""
    song = get_song(spotify_id)
    if not song:
        raise HTTPException(status_code=404, detail=f"Song {spotify_id} 없음")

    from db.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE songs SET status = 'pending' WHERE spotify_id = :1", [spotify_id])
    conn.commit()
    conn.close()

    from pipeline.classify import classify_song
    try:
        result = classify_song(spotify_id)
        return {"spotify_id": spotify_id, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================
# 플레이리스트
# ======================

@app.get("/playlist/groups", summary="mood 유사도 기반 자동 그룹핑")
async def playlist_groups(
    top_k: int = Query(20, ge=5, le=100, description="그룹당 최대 곡 수")
):
    """전체 분류된 곡을 mood 유사도로 자동 그룹핑"""
    groups = group_songs_by_mood(top_k_per_group=top_k)
    return {"groups": groups}


# ======================
# Spotify
# ======================

@app.get("/spotify/preview", summary="Spotify 플레이리스트 트랙 목록 미리보기 (분류 없음)")
async def spotify_preview(playlist_url: str = Query(...)):
    """
    플레이리스트 URL로 트랙 목록만 가져옴. 분류하지 않음.
    프론트에서 곡 선택 후 개별 /songs 호출로 분류.
    """
    from pipeline.spotify import get_playlist_tracks, get_playlist_info, is_logged_in

    use_oauth = is_logged_in()
    try:
        info = get_playlist_info(playlist_url, use_oauth=use_oauth)
        tracks = get_playlist_tracks(playlist_url, use_oauth=use_oauth)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"플레이리스트 조회 실패: {e}")

    return {"playlist": info, "tracks": tracks}


@app.post("/spotify/import", summary="Spotify 플레이리스트 → 곡 일괄 추가+분류")
async def spotify_import(req: SpotifyImportRequest):
    """
    Spotify 플레이리스트 URL로 트랙 가져와서 일괄 분류.
    이미 DB에 있는 곡은 스킵.
    """
    from pipeline.spotify import get_playlist_tracks, get_playlist_info, is_logged_in

    use_oauth = is_logged_in()
    try:
        info = get_playlist_info(req.playlist_url, use_oauth=use_oauth)
        tracks = get_playlist_tracks(req.playlist_url, use_oauth=use_oauth)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"플레이리스트 조회 실패: {e}")

    results = []
    for track in tracks:
        try:
            result = add_and_classify(track["title"], track["artist"])
            results.append({
                "title": track["title"],
                "artist": track["artist"],
                "status": "ok",
                "already_exists": result.get("already_exists", False),
                "spotify_id": result.get("spotify_id"),
                "mood": result.get("mood"),
                "category": result.get("category")
            })
        except Exception as e:
            results.append({
                "title": track["title"],
                "artist": track["artist"],
                "status": "error",
                "error": str(e)
            })

    success = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] == "error"]

    return {
        "playlist": {"name": info.get("name"), "total": info.get("total")},
        "processed": len(success),
        "failed": len(failed),
        "results": results
    }


@app.post("/spotify/export", summary="mood 그룹 → Spotify 플레이리스트 생성")
async def spotify_export(req: SpotifyExportRequest):
    """
    특정 mood 곡들을 Spotify 플레이리스트로 생성.
    spotify_id를 직접 사용하므로 검색 단계 스킵.
    """
    from pipeline.spotify import create_playlist, add_tracks_to_playlist

    groups = group_songs_by_mood()
    target_songs = []
    for group in groups:
        if group["mood"] == req.mood:
            target_songs = group["songs"]
            break

    if not target_songs:
        raise HTTPException(status_code=404, detail=f"mood '{req.mood}' 곡 없음")

    try:
        playlist = create_playlist(
            name=req.playlist_name,
            description=req.description or f"Moodlist - {req.mood}",
            public=req.public
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"플레이리스트 생성 실패: {e}")

    # spotify_id로 바로 URI 생성 (검색 불필요)
    track_uris = [f"spotify:track:{song['spotify_id']}" for song in target_songs]

    if track_uris:
        add_tracks_to_playlist(playlist["id"], track_uris)

    return {
        "playlist_url": playlist.get("url"),
        "added": len(track_uris)
    }


@app.get("/search/suggestions", summary="Spotify 실시간 검색 제안")
async def search_suggestions(q: str = Query(..., min_length=1)):
    """입력 중인 쿼리로 Spotify 트랙 검색 (앨범 아트 포함)"""
    from pipeline.spotify import get_spotify_client_simple
    try:
        sp = get_spotify_client_simple()
        results = sp.search(q=q, type="track", limit=7)
        tracks = results.get("tracks", {}).get("items", [])
        return [
            {
                "spotify_id": t["id"],
                "title": t["name"],
                "artist": ", ".join(a["name"] for a in t["artists"]),
                "image_url": t["album"]["images"][-1]["url"] if t["album"]["images"] else None,
            }
            for t in tracks
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/spotify/auth", summary="Spotify 로그인 상태 확인")
async def spotify_auth():
    from pipeline.spotify import is_logged_in, get_spotify_client_oauth
    if not is_logged_in():
        return {"logged_in": False}
    try:
        sp = get_spotify_client_oauth()
        user = sp.current_user()
        return {"logged_in": True, "user": user.get("display_name")}
    except Exception as e:
        return {"logged_in": False, "error": str(e)}


@app.get("/spotify/login", summary="Spotify OAuth 로그인 URL 반환")
async def spotify_login():
    """프론트에서 받은 URL을 새 창으로 열어 로그인"""
    from pipeline.spotify import get_auth_url
    return {"auth_url": get_auth_url()}


@app.get("/spotify/callback", summary="Spotify OAuth 콜백 처리")
async def spotify_callback(code: str = Query(None), error: str = Query(None)):
    if error:
        return HTMLResponse(
            f"<html><body><p>로그인 실패: {error}</p><script>window.close()</script></body></html>"
        )
    if not code:
        return HTMLResponse("<html><body><p>잘못된 요청</p></body></html>")
    from pipeline.spotify import exchange_code
    try:
        exchange_code(code)
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;display:flex;align-items:center;"
            "justify-content:center;height:100vh;margin:0'>"
            "<div style='text-align:center'>"
            "<p style='font-size:1.2rem'>✅ Spotify 로그인 완료!</p>"
            "<p style='color:#888'>이 창을 닫아도 됩니다.</p>"
            "<script>setTimeout(()=>window.close(),1500)</script>"
            "</div></body></html>"
        )
    except Exception as e:
        return HTMLResponse(f"<html><body><p>오류: {e}</p></body></html>")


@app.get("/spotify/me/playlists", summary="내 Spotify 플레이리스트 목록")
async def my_playlists():
    from pipeline.spotify import is_logged_in, get_my_playlists
    if not is_logged_in():
        raise HTTPException(status_code=401, detail="Spotify 로그인이 필요합니다")
    try:
        return get_my_playlists()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================
# 통계
# ======================

@app.get("/stats", summary="전체 통계")
async def stats():
    return get_stats()


@app.get("/categories", summary="카테고리 목록")
async def categories():
    return get_all_categories()


# ======================
# 실행
# ======================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)
