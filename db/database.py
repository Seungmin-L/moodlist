import json
import sqlite3
from datetime import datetime
from pathlib import Path

# DB 파일 경로
DB_PATH = Path(__file__).parent.parent / "data" / "songs.db"


def get_connection():
    """DB 연결 반환"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # dict처럼 접근 가능
    return conn


def init_db():
    """테이블 초기화 (Medallion 아키텍처)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Bronze: 크롤링 원본
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS songs_bronze (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            raw_lyrics TEXT,
            source_url TEXT,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(title, artist)
        )
    """)
    
    # Silver: 정제된 데이터
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS songs_silver (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bronze_id INTEGER NOT NULL,
            clean_lyrics TEXT NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bronze_id) REFERENCES songs_bronze(id)
        )
    """)
    
    # Gold: 분류 완료
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS songs_gold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            silver_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            mood TEXT DEFAULT '',
            mood_embedding TEXT DEFAULT '',
            emotions TEXT DEFAULT '{}',
            primary_emotion TEXT DEFAULT '',
            emotional_arc TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            narrative TEXT DEFAULT '',
            confidence REAL,
            classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (silver_id) REFERENCES songs_silver(id)
        )
    """)
    
    # 플레이리스트 관리
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlist_songs (
            playlist_id INTEGER,
            gold_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (playlist_id, gold_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(id),
            FOREIGN KEY (gold_id) REFERENCES songs_gold(id)
        )
    """)
    
    # 기존 songs_gold 테이블에 새 컬럼 추가 (마이그레이션)
    new_columns = [
        ("mood", "TEXT DEFAULT ''"),
        ("mood_embedding", "TEXT DEFAULT ''"),
        ("emotions", "TEXT DEFAULT '{}'"),
        ("primary_emotion", "TEXT DEFAULT ''"),
        ("emotional_arc", "TEXT DEFAULT ''"),
        ("tags", "TEXT DEFAULT '[]'"),
        ("narrative", "TEXT DEFAULT ''"),
    ]
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE songs_gold ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # 이미 존재하는 컬럼

    conn.commit()
    conn.close()
    print(f"DB 초기화 완료: {DB_PATH}")


# ======================
# Bronze 레이어 함수
# ======================

def insert_bronze(title: str, artist: str, raw_lyrics: str, source_url: str = None):
    """크롤링 원본 데이터 저장"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO songs_bronze (title, artist, raw_lyrics, source_url)
            VALUES (?, ?, ?, ?)
        """, (title, artist, raw_lyrics, source_url))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # 이미 존재하는 곡
        cursor.execute("""
            SELECT id FROM songs_bronze WHERE title = ? AND artist = ?
        """, (title, artist))
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_bronze_unprocessed():
    """아직 Silver로 처리 안 된 Bronze 데이터 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.* FROM songs_bronze b
        LEFT JOIN songs_silver s ON b.id = s.bronze_id
        WHERE s.id IS NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ======================
# Silver 레이어 함수
# ======================

def insert_silver(bronze_id: int, clean_lyrics: str):
    """정제된 데이터 저장"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO songs_silver (bronze_id, clean_lyrics)
        VALUES (?, ?)
    """, (bronze_id, clean_lyrics))
    conn.commit()
    silver_id = cursor.lastrowid
    conn.close()
    return silver_id


def get_silver_unclassified():
    """아직 Gold로 분류 안 된 Silver 데이터 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, b.title, b.artist FROM songs_silver s
        JOIN songs_bronze b ON s.bronze_id = b.id
        LEFT JOIN songs_gold g ON s.id = g.silver_id
        WHERE g.id IS NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ======================
# Gold 레이어 함수
# ======================

def insert_gold(silver_id: int, category: str, confidence: float = None,
                 mood: str = "", mood_embedding: list = None, emotions: dict = None,
                 primary_emotion: str = "", emotional_arc: str = "",
                 tags: list = None, narrative: str = ""):
    """분류 결과 저장"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO songs_gold (silver_id, category, mood, mood_embedding, emotions,
                                primary_emotion, emotional_arc, tags, narrative, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (silver_id, category, mood,
          json.dumps(mood_embedding or [], ensure_ascii=False),
          json.dumps(emotions or {}, ensure_ascii=False),
          primary_emotion, emotional_arc,
          json.dumps(tags or [], ensure_ascii=False),
          narrative, confidence))
    conn.commit()
    gold_id = cursor.lastrowid
    conn.close()
    return gold_id


def get_all_mood_embeddings():
    """모든 곡의 mood 임베딩 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.id, g.mood, g.mood_embedding, g.category,
               b.title, b.artist
        FROM songs_gold g
        JOIN songs_silver s ON g.silver_id = s.id
        JOIN songs_bronze b ON s.bronze_id = b.id
        WHERE g.mood_embedding != '' AND g.mood_embedding != '[]'
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_songs_by_category(category: str = None):
    """카테고리별 곡 조회 (전체 정보 JOIN)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if category:
        cursor.execute("""
            SELECT g.id, g.category, g.mood, g.emotions,
                   g.primary_emotion, g.emotional_arc, g.tags, g.narrative,
                   g.confidence, g.classified_at,
                   s.clean_lyrics, b.title, b.artist
            FROM songs_gold g
            JOIN songs_silver s ON g.silver_id = s.id
            JOIN songs_bronze b ON s.bronze_id = b.id
            WHERE g.category = ?
            ORDER BY g.classified_at DESC
        """, (category,))
    else:
        cursor.execute("""
            SELECT g.id, g.category, g.mood, g.emotions,
                   g.primary_emotion, g.emotional_arc, g.tags, g.narrative,
                   g.confidence, g.classified_at,
                   s.clean_lyrics, b.title, b.artist
            FROM songs_gold g
            JOIN songs_silver s ON g.silver_id = s.id
            JOIN songs_bronze b ON s.bronze_id = b.id
            ORDER BY g.classified_at DESC
        """)
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_categories():
    """등록된 모든 카테고리 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM songs_gold")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


# ======================
# 플레이리스트 함수
# ======================

def create_playlist(name: str):
    """플레이리스트 생성"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def add_to_playlist(playlist_id: int, gold_id: int):
    """플레이리스트에 곡 추가"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO playlist_songs (playlist_id, gold_id)
            VALUES (?, ?)
        """, (playlist_id, gold_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_playlist_songs(playlist_id: int):
    """플레이리스트의 곡 목록 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.id, g.category, b.title, b.artist, s.clean_lyrics
        FROM playlist_songs ps
        JOIN songs_gold g ON ps.gold_id = g.id
        JOIN songs_silver s ON g.silver_id = s.id
        JOIN songs_bronze b ON s.bronze_id = b.id
        WHERE ps.playlist_id = ?
        ORDER BY ps.added_at
    """, (playlist_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_playlists():
    """모든 플레이리스트 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM playlists ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ======================
# 통계 함수
# ======================

def get_pipeline_stats():
    """파이프라인 현황 통계"""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    cursor.execute("SELECT COUNT(*) FROM songs_bronze")
    stats['bronze_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM songs_silver")
    stats['silver_count'] = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM songs_gold")
    stats['gold_count'] = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT category, COUNT(*) as count 
        FROM songs_gold 
        GROUP BY category
    """)
    stats['category_distribution'] = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return stats


if __name__ == "__main__":
    # 직접 실행하면 DB 초기화
    init_db()