"""Bronze 랜딩존 적재.

크롤링 원본을 날짜 파티션 JSONL로 append 한다.

`classify_song()`이 정제본으로 `songs.lyrics` 컬럼을 덮어쓰기 때문에
원본 가사는 이 파일에만 남는다. 정제 로직을 바꾼 뒤 재처리하려면 여기가 출발점이다.

적재 실패가 분류 흐름을 막으면 안 되므로 예외를 삼키고 False를 반환한다.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent.parent
LANDING_DIR = Path(os.getenv("LANDING_DIR") or REPO_ROOT / "data" / "landing")


def write_landing_record(
    spotify_id: str,
    title: str,
    artist: str,
    raw_lyrics: str,
    source: str,
    source_url: Optional[str] = None,
    isrc: Optional[str] = None,
) -> bool:
    """원본 레코드 한 건을 랜딩존에 append 한다.

    파일 경로: data/landing/dt=YYYY-MM-DD/records.jsonl
    같은 곡이 여러 번 수집되면 그대로 여러 줄이 쌓인다. 중복 제거는 Silver의 책임이다.
    """
    try:
        now = datetime.now(timezone.utc)
        partition = LANDING_DIR / f"dt={now:%Y-%m-%d}"
        partition.mkdir(parents=True, exist_ok=True)

        record = {
            "spotify_id": spotify_id,
            "title": title,
            "artist": artist,
            "isrc": isrc,
            "raw_lyrics": raw_lyrics,
            "source": source,
            "source_url": source_url,
            "crawled_at": now.isoformat(),
        }

        with open(partition / "records.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True

    except Exception as e:
        print(f"[landing] 적재 실패, 분류는 계속 진행: {e}")
        return False
