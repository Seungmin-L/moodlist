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

# ======================
# 커넥션 풀
# ======================

_pool: oracledb.ConnectionPool | None = None

def _get_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(
            user=os.getenv("ORACLE_USER"),
            password=os.getenv("ORACLE_PASSWORD"),
            dsn=os.getenv("ORACLE_DSN"),
            min=2,
            max=10,
            increment=1,
            tcp_connect_timeout=15,
        )
    return _pool


def _clob_output_type_handler(cursor, metadata):
    """CLOB 컬럼을 LOB descriptor 대신 일반 문자열로 즉시 반환.
    이를 설정하지 않으면 각 CLOB마다 .read() 네트워크 왕복이 발생해 쿼리가 수십 배 느려진다."""
    if metadata.type_code is oracledb.DB_TYPE_CLOB:
        return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)


def get_connection():
    """커넥션 풀에서 커넥션 반환. CLOB 자동 문자열 변환 핸들러 적용."""
    conn = _get_pool().acquire()
    conn.outputtypehandler = _clob_output_type_handler
    return conn


def _row_to_dict(cursor, row):
    """커서 컬럼명 기반으로 row를 dict로 변환.
    outputtypehandler 덕분에 CLOB은 이미 str이므로 .read() 불필요."""
    columns = [col[0].lower() for col in cursor.description]
    return dict(zip(columns, row))


def init_db():
    """테이블 및 인덱스 초기화 (없을 때만 생성)"""
    conn = get_connection()
    cursor = conn.cursor()

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
            album_art_url   VARCHAR2(1000),
            created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
            classified_at   TIMESTAMP
        )
    """)
        conn.commit()
        print("songs 테이블 생성 완료")

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
        try:
            cursor.execute("ALTER TABLE songs ADD (album_art_url VARCHAR2(1000))")
            conn.commit()
            print("album_art_url 컬럼 추가 완료")
        except oracledb.DatabaseError:
            pass

    conn.close()


# ======================
# 곡 추가 / 조회
# ======================

def insert_song(spotify_id: str, title: str, artist: str, lyrics: str = None, source_url: str = None, album_art_url: str = None) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO songs (spotify_id, title, artist, lyrics, source_url, album_art_url)
            VALUES (:1, :2, :3, :4, :5, :6)
        """, [spotify_id, title, artist, lyrics, source_url, album_art_url])
        conn.commit()
        return {"spotify_id": spotify_id, "already_exists": False, "status": "pending"}

    except oracledb.IntegrityError:
        if album_art_url:
            cursor.execute("""
                UPDATE songs
                SET album_art_url = :1
                WHERE spotify_id = :2
                  AND (album_art_url IS NULL OR TRIM(album_art_url) = '')
            """, [album_art_url, spotify_id])
            conn.commit()

        cursor.execute("""
            SELECT spotify_id, category, mood, emotions, primary_emotion,
                   emotional_arc, tags, narrative, confidence, status, error_message,
                   album_art_url
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE songs SET lyrics = :1 WHERE spotify_id = :2", [lyrics, spotify_id])
    conn.commit()
    conn.close()


def update_classification(spotify_id: str, result: dict = None, error: str = None):
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT spotify_id, title, artist, lyrics, source_url, category, mood,
               emotions, primary_emotion, emotional_arc, tags, narrative,
               confidence, status, error_message, album_art_url, created_at, classified_at
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
    conn = get_connection()
    cursor = conn.cursor()
    if category:
        cursor.execute("""
            SELECT spotify_id, title, artist, category, mood, emotions,
                   primary_emotion, emotional_arc, tags, narrative,
                   confidence, status, album_art_url, classified_at
            FROM songs
            WHERE status = 'classified' AND category = :1
            ORDER BY classified_at DESC
        """, [category])
    else:
        cursor.execute("""
            SELECT spotify_id, title, artist, category, mood, emotions,
                   primary_emotion, emotional_arc, tags, narrative,
                   confidence, status, album_art_url, classified_at
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
    """
    2축 하이브리드 유사도: text embedding (0.6) + emotion vector (0.4)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT mood_embedding, emotion_vector FROM songs WHERE spotify_id = :1",
        [spotify_id],
    )
    row = cursor.fetchone()
    if not row or row[0] is None:
        conn.close()
        return []

    query_emb = row[0]
    query_emo = row[1]

    if query_emo is not None:
        cursor.execute("""
            SELECT spotify_id, title, artist, mood, category, album_art_url,
                   VECTOR_DISTANCE(mood_embedding, :1, COSINE) AS emb_dist,
                   VECTOR_DISTANCE(emotion_vector, :2, COSINE) AS emo_dist
            FROM songs
            WHERE status = 'classified'
              AND mood_embedding IS NOT NULL
              AND spotify_id != :3
        """, [query_emb, query_emo, spotify_id])
        rows = cursor.fetchall()
        cols = [c[0].lower() for c in cursor.description]
        scored = []
        for r in rows:
            d = dict(zip(cols, r))
            emb_d = d.pop("emb_dist", 1.0) or 1.0
            emo_d = d.pop("emo_dist", 1.0) or 1.0
            d["similarity"] = 0.6 * emb_d + 0.4 * emo_d
            scored.append(d)
        scored.sort(key=lambda x: x["similarity"])
        result = scored[:top_k]
    else:
        cursor.execute("""
            SELECT spotify_id, title, artist, mood, category, album_art_url,
                   VECTOR_DISTANCE(mood_embedding, :1, COSINE) AS similarity
            FROM songs
            WHERE status = 'classified'
              AND mood_embedding IS NOT NULL
              AND spotify_id != :2
            ORDER BY similarity
            FETCH FIRST :3 ROWS ONLY
        """, [query_emb, spotify_id, top_k])
        rows = cursor.fetchall()
        result = [_row_to_dict(cursor, row) for row in rows]

    conn.close()
    return result


def group_songs_by_mood(top_k_per_group: int = 20) -> list:
    """
    mood 기준 자동 그룹핑.
    한 번의 쿼리로 전체 임베딩을 읽어온 뒤 Python에서 그룹핑하여
    N+1 쿼리 문제를 제거.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 전체 분류된 곡 + 임베딩 + emotion_vector + narrative 한 번에 가져오기
    cursor.execute("""
        SELECT spotify_id, title, artist, mood, category, album_art_url,
               narrative, mood_embedding, emotion_vector
        FROM songs
        WHERE status = 'classified' AND mood_embedding IS NOT NULL
        ORDER BY classified_at
    """)
    all_rows = cursor.fetchall()
    conn.close()

    if not all_rows:
        return []

    # 컬럼 인덱스 매핑
    col_names = ["spotify_id", "title", "artist", "mood", "category",
                 "album_art_url", "narrative", "mood_embedding", "emotion_vector"]

    songs = []
    for row in all_rows:
        d = {}
        for i, col in enumerate(col_names):
            val = row[i]
            if hasattr(val, 'read'):
                val = val.read()
            d[col] = val
        songs.append(d)

    # Python에서 코사인 유사도 계산 (Oracle 왕복 없이)
    import math

    def cosine_dist(a, b) -> float:
        if not a or not b:
            return 1.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 1.0
        return 1.0 - dot / (na * nb)

    # mood_embedding + emotion_vector를 list[float]로 변환
    for s in songs:
        emb = s["mood_embedding"]
        s["_vec"] = list(emb) if emb is not None else []
        emo = s.get("emotion_vector")
        s["_emo"] = list(emo) if emo is not None else []

    grouped_ids: set = set()
    groups = []

    for seed in songs:
        if seed["spotify_id"] in grouped_ids:
            continue

        seed_vec = seed["_vec"]
        if not seed_vec:
            continue

        seed_emo = seed["_emo"]

        # 2축 하이브리드: text embedding (0.6) + emotion vector (0.4)
        scored = []
        for s in songs:
            emb_d = cosine_dist(seed_vec, s["_vec"])
            if seed_emo and s["_emo"]:
                emo_d = cosine_dist(seed_emo, s["_emo"])
                dist = 0.6 * emb_d + 0.4 * emo_d
            else:
                dist = emb_d
            scored.append((dist, s))

        scored.sort(key=lambda x: x[0])
        group_songs = [s for dist, s in scored if dist <= 0.45][:top_k_per_group]

        for s in group_songs:
            grouped_ids.add(s["spotify_id"])

        # 반환 형태에서 내부 필드 제거
        clean_songs = [
            {k: v for k, v in s.items()
             if k not in ("_vec", "_emo", "mood_embedding", "emotion_vector")}
            for s in group_songs
        ]

        groups.append({
            "mood": seed["mood"],
            "category": seed["category"],
            "songs": clean_songs,
        })

    return groups


# ======================
# 통계
# ======================

def get_stats() -> dict:
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
