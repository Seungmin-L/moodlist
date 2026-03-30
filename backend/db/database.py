"""
Oracle Cloud ATP 기반 DB 모듈

- songs 단일 테이블 (Spotify ID를 PK로 사용)
- Oracle 23ai VECTOR 타입으로 mood 임베딩 저장
- VECTOR_DISTANCE로 유사곡 검색
"""

import array
import json
import os
from dotenv import load_dotenv
from pathlib import Path
import oracledb

PROJECT_ROOT = Path(__file__).parent.parent
REPO_ROOT = PROJECT_ROOT.parent
load_dotenv(REPO_ROOT / ".env")


def get_connection():
    """Oracle DB 연결 반환"""
    return oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=os.getenv("ORACLE_DSN"),
        tcp_connect_timeout=15
    )


def _row_to_dict(cursor, row):
    """커서 컬럼명 기반으로 row를 dict로 변환 (connection 닫히기 전에 호출해야 함)"""
    columns = [col[0].lower() for col in cursor.description]
    result = {}
    for col, val in zip(columns, row):
        if hasattr(val, 'read'):
            val = val.read()
        result[col] = val
    return result


def init_db():
    """테이블 및 인덱스 초기화 (없을 때만 생성)"""
    conn = get_connection()
    cursor = conn.cursor()

    # 테이블이 이미 존재하면 스킵
    try:
        cursor.execute("""
            CREATE TABLE songs (
            spotify_id      VARCHAR2(50)   NOT NULL PRIMARY KEY,
            title           VARCHAR2(500)  NOT NULL,
            artist          VARCHAR2(500)  NOT NULL,
            lyrics          CLOB,
            source_url      VARCHAR2(1000),
            category        VARCHAR2(100),
            mood            VARCHAR2(500),
            mood_embedding  VECTOR(1536, FLOAT64),
            emotions        CLOB,
            primary_emotion VARCHAR2(100),
            emotional_arc   VARCHAR2(200),
            tags            CLOB,
            narrative       CLOB,
            confidence      NUMBER(3,2),
            status          VARCHAR2(20)   DEFAULT 'pending',
            error_message   CLOB,
            created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
            classified_at   TIMESTAMP
        )
    """)
        conn.commit()
        print("songs 테이블 생성 완료")

        # 벡터 인덱스 생성
        try:
            cursor.execute("""
                CREATE VECTOR INDEX idx_mood_embedding
                ON songs(mood_embedding)
                ORGANIZATION NEIGHBOR PARTITIONS
                DISTANCE COSINE
            """)
            conn.commit()
        except oracledb.DatabaseError:
            pass

    except oracledb.DatabaseError:
        print("songs 테이블 이미 존재, 스킵")

    conn.close()


# ======================
# 곡 추가 / 조회
# ======================

def insert_song(spotify_id: str, title: str, artist: str, lyrics: str = None, source_url: str = None) -> dict:
    """
    곡 추가.
    이미 있으면 기존 레코드 반환 (already_exists=True).
    없으면 신규 INSERT (status='pending').
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO songs (spotify_id, title, artist, lyrics, source_url)
            VALUES (:1, :2, :3, :4, :5)
        """, [spotify_id, title, artist, lyrics, source_url])
        conn.commit()
        return {"spotify_id": spotify_id, "already_exists": False, "status": "pending"}

    except oracledb.IntegrityError:
        cursor.execute("""
            SELECT spotify_id, category, mood, emotions, primary_emotion,
                   emotional_arc, tags, narrative, confidence, status, error_message
            FROM songs
            WHERE spotify_id = :1
        """, [spotify_id])
        row = cursor.fetchone()
        result = _row_to_dict(cursor, row)
        result["already_exists"] = True
        if result.get("emotions"):
            result["emotions"] = json.loads(result["emotions"])
        if result.get("tags"):
            result["tags"] = json.loads(result["tags"])
        return result
    finally:
        conn.close()


def update_lyrics(spotify_id: str, lyrics: str):
    """가사 업데이트"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE songs SET lyrics = :1 WHERE spotify_id = :2", [lyrics, spotify_id])
    conn.commit()
    conn.close()


def update_classification(spotify_id: str, result: dict = None, error: str = None):
    """
    분류 결과 저장.
    result가 있으면 status='classified',
    error가 있으면 status='error'.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if error:
        cursor.execute("""
            UPDATE songs
            SET status = 'error', error_message = :1
            WHERE spotify_id = :2
        """, [error, spotify_id])
    else:
        embedding = result.get("mood_embedding") or []
        oracle_vector = array.array('d', embedding) if embedding else None

        cursor.execute("""
            UPDATE songs SET
                category        = :1,
                mood            = :2,
                mood_embedding  = :3,
                emotions        = :4,
                primary_emotion = :5,
                emotional_arc   = :6,
                tags            = :7,
                narrative       = :8,
                confidence      = :9,
                status          = 'classified',
                error_message   = NULL,
                classified_at   = CURRENT_TIMESTAMP
            WHERE spotify_id = :10
        """, [
            result.get("category", "기타"),
            result.get("mood", ""),
            oracle_vector,
            json.dumps(result.get("emotions", {}), ensure_ascii=False),
            result.get("primary_emotion", ""),
            result.get("emotional_arc", ""),
            json.dumps(result.get("tags", []), ensure_ascii=False),
            result.get("narrative", ""),
            result.get("confidence", 0.0),
            spotify_id
        ])

    conn.commit()
    conn.close()


def get_pending_songs() -> list:
    """분류 대기 중인 곡 (status='pending' 또는 'error') 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT spotify_id, title, artist, lyrics, status, error_message
        FROM songs
        WHERE status IN ('pending', 'error')
        ORDER BY created_at
    """)
    rows = cursor.fetchall()
    result = [_row_to_dict(cursor, row) for row in rows]
    conn.close()
    return result


def get_song(spotify_id: str) -> dict | None:
    """단일 곡 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT spotify_id, title, artist, lyrics, source_url, category, mood,
               emotions, primary_emotion, emotional_arc, tags, narrative,
               confidence, status, error_message, created_at, classified_at
        FROM songs WHERE spotify_id = :1
    """, [spotify_id])
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    result = _row_to_dict(cursor, row)
    conn.close()
    if result.get("emotions"):
        result["emotions"] = json.loads(result["emotions"])
    if result.get("tags"):
        result["tags"] = json.loads(result["tags"])
    return result


def get_songs_by_category(category: str = None) -> list:
    """카테고리별 곡 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute("""
            SELECT spotify_id, title, artist, category, mood, emotions,
                   primary_emotion, emotional_arc, tags, narrative,
                   confidence, status, classified_at
            FROM songs
            WHERE status = 'classified' AND category = :1
            ORDER BY classified_at DESC
        """, [category])
    else:
        cursor.execute("""
            SELECT spotify_id, title, artist, category, mood, emotions,
                   primary_emotion, emotional_arc, tags, narrative,
                   confidence, status, classified_at
            FROM songs
            WHERE status = 'classified'
            ORDER BY classified_at DESC
        """)
    rows = cursor.fetchall()
    result = []
    for row in rows:
        d = _row_to_dict(cursor, row)
        if d.get("emotions"):
            d["emotions"] = json.loads(d["emotions"])
        if d.get("tags"):
            d["tags"] = json.loads(d["tags"])
        result.append(d)
    conn.close()
    return result


def get_all_categories() -> list:
    """분류된 카테고리 목록"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT category FROM songs
        WHERE status = 'classified' AND category IS NOT NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


# ======================
# 벡터 유사도 검색
# ======================

def find_similar_songs(spotify_id: str, top_k: int = 10) -> list:
    """Oracle VECTOR_DISTANCE로 유사곡 검색"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT mood_embedding FROM songs WHERE spotify_id = :1", [spotify_id])
    row = cursor.fetchone()
    if not row or row[0] is None:
        conn.close()
        return []

    query_vector = row[0]

    cursor.execute("""
        SELECT spotify_id, title, artist, mood, category,
               VECTOR_DISTANCE(mood_embedding, :1, COSINE) AS similarity
        FROM songs
        WHERE status = 'classified'
          AND mood_embedding IS NOT NULL
          AND spotify_id != :2
        ORDER BY similarity
        FETCH FIRST :3 ROWS ONLY
    """, [query_vector, spotify_id, top_k])

    rows = cursor.fetchall()
    result = [_row_to_dict(cursor, row) for row in rows]
    conn.close()
    return result


def group_songs_by_mood(top_k_per_group: int = 20) -> list:
    """
    mood 기준 대표 곡들을 뽑고, 각 대표 곡과 유사한 곡들로 그룹 구성.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT spotify_id, title, artist, mood, category
        FROM songs
        WHERE status = 'classified' AND mood_embedding IS NOT NULL
        ORDER BY classified_at
    """)
    all_songs = [_row_to_dict(cursor, row) for row in cursor.fetchall()]

    if not all_songs:
        conn.close()
        return []

    groups = []
    grouped_ids = set()

    for song in all_songs:
        if song["spotify_id"] in grouped_ids:
            continue

        cursor.execute("""
            SELECT spotify_id, title, artist, mood, category,
                   VECTOR_DISTANCE(mood_embedding,
                       (SELECT mood_embedding FROM songs WHERE spotify_id = :1),
                       COSINE) AS similarity
            FROM songs
            WHERE status = 'classified'
              AND mood_embedding IS NOT NULL
            ORDER BY similarity
            FETCH FIRST :2 ROWS ONLY
        """, [song["spotify_id"], top_k_per_group])

        group_songs = [_row_to_dict(cursor, row) for row in cursor.fetchall()]
        similar = [s for s in group_songs if s.get("similarity", 1) <= 0.2]

        for s in similar:
            grouped_ids.add(s["spotify_id"])

        groups.append({
            "mood": song["mood"],
            "category": song["category"],
            "songs": similar
        })

    conn.close()
    return groups


# ======================
# 통계
# ======================

def get_stats() -> dict:
    """전체 통계"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM songs")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) FROM songs GROUP BY status")
    status_dist = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT category, COUNT(*) FROM songs
        WHERE status = 'classified'
        GROUP BY category
    """)
    category_dist = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()
    return {
        "total": total,
        "status_distribution": status_dist,
        "category_distribution": category_dist
    }


if __name__ == "__main__":
    init_db()
