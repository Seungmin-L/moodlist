"""
Bronze → Silver 가사 정제 모듈

Genius에서 가져온 raw_lyrics를 정제해서 Silver 레이어에 저장
"""

import re
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import (
    get_bronze_unprocessed,
    insert_silver,
    get_connection
)


def clean_lyrics(raw_lyrics: str) -> str:
    """
    가사 정제
    - 섹션 헤더 제거 ([Verse], [Chorus] 등)
    - Genius 관련 텍스트 제거
    - 빈 줄 정리
    - 앞뒤 공백 제거
    """
    if not raw_lyrics:
        return ""
    
    text = raw_lyrics
    
    # 1. 맨 앞의 숫자 + "Embed" 제거 (Genius 특유 패턴)
    # 예: "123Embed" 또는 끝에 "123Embed"
    text = re.sub(r'\d*Embed$', '', text)
    
    # 2. 섹션 헤더 제거 [Verse], [Chorus], [Intro] 등
    text = re.sub(r'\[.*?\]', '', text)
    
    # 3. 괄호 안 부가 설명 제거 (선택적)
    # 예: (x2), (반복) 등 - 필요하면 주석 해제
    # text = re.sub(r'\(x?\d+\)', '', text)
    # text = re.sub(r'\(반복\)', '', text)
    
    # 4. "You might also like" 제거 (Genius 삽입 텍스트)
    text = re.sub(r'You might also like', '', text, flags=re.IGNORECASE)
    
    # 5. "See [아티스트] Live" 제거
    text = re.sub(r'See .+ Live.*', '', text, flags=re.IGNORECASE)
    
    # 6. "Get tickets as low as $XX" 제거
    text = re.sub(r'Get tickets as low as \$\d+', '', text, flags=re.IGNORECASE)
    
    # 7. 여러 개의 빈 줄을 하나로
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 8. 각 줄 앞뒤 공백 제거
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    # 9. 전체 앞뒤 공백 제거
    text = text.strip()
    
    return text


def process_bronze_to_silver(bronze_id: int = None):
    """
    Bronze 데이터를 정제해서 Silver에 저장
    bronze_id 지정하면 해당 곡만, 없으면 미처리 전체
    """
    if bronze_id:
        # 특정 곡만 처리
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM songs_bronze WHERE id = ?", (bronze_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"Bronze ID {bronze_id} 를 찾을 수 없음")
            return []
        
        unprocessed = [dict(row)]
    else:
        # 미처리 전체
        unprocessed = get_bronze_unprocessed()
    
    if not unprocessed:
        print("처리할 데이터가 없습니다.")
        return []
    
    processed = []
    
    for row in unprocessed:
        bronze_id = row['id']
        title = row['title']
        artist = row['artist']
        raw_lyrics = row['raw_lyrics']
        
        print(f"정제 중: {title} - {artist}")
        
        # 가사 정제
        clean = clean_lyrics(raw_lyrics)
        
        if not clean:
            print(f"  ✗ 정제 후 빈 가사")
            continue
        
        # Silver에 저장
        silver_id = insert_silver(bronze_id, clean)
        
        processed.append({
            "silver_id": silver_id,
            "bronze_id": bronze_id,
            "title": title,
            "artist": artist
        })
        
        print(f"  ✓ Silver 저장 완료 (ID: {silver_id})")
    
    print(f"\n총 {len(processed)}곡 정제 완료")
    return processed


def get_silver_preview(silver_id: int, max_lines: int = 10):
    """
    Silver 데이터 미리보기
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.clean_lyrics, b.title, b.artist
        FROM songs_silver s
        JOIN songs_bronze b ON s.bronze_id = b.id
        WHERE s.id = ?
    """, (silver_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print(f"Silver ID {silver_id} 를 찾을 수 없음")
        return
    
    lyrics, title, artist = row
    lines = lyrics.split('\n')[:max_lines]
    
    print(f"\n{'='*50}")
    print(f"🎵 {title} - {artist}")
    print('='*50)
    print('\n'.join(lines))
    if len(lyrics.split('\n')) > max_lines:
        print(f"... ({len(lyrics.split(chr(10)))}줄 중 {max_lines}줄만 표시)")
    print('='*50)


# ======================
# CLI
# ======================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Bronze → Silver 가사 정제")
    parser.add_argument("--all", action="store_true", help="미처리 전체 정제")
    parser.add_argument("--id", type=int, help="특정 Bronze ID만 정제")
    parser.add_argument("--preview", type=int, help="Silver ID 미리보기")
    parser.add_argument("--status", action="store_true", help="현재 상태 확인")
    
    args = parser.parse_args()
    
    if args.status:
        from db.database import get_pipeline_stats
        stats = get_pipeline_stats()
        print("\n📊 파이프라인 현황")
        print(f"  Bronze: {stats['bronze_count']}곡")
        print(f"  Silver: {stats['silver_count']}곡")
        print(f"  Gold: {stats['gold_count']}곡")
        if stats['category_distribution']:
            print(f"  카테고리: {stats['category_distribution']}")
    
    elif args.preview:
        get_silver_preview(args.preview)
    
    elif args.all or args.id:
        process_bronze_to_silver(args.id)
    
    else:
        print("사용법:")
        print("  python clean.py --all          # 미처리 전체 정제")
        print("  python clean.py --id 1         # Bronze ID 1만 정제")
        print("  python clean.py --preview 1    # Silver ID 1 미리보기")
        print("  python clean.py --status       # 파이프라인 현황")