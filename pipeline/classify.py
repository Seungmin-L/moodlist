"""
Silver → Gold LLM 분류 모듈

Ollama (로컬 LLM)를 이용해 가사를 분류하고 Gold 레이어에 저장

사용 전 준비:
1. brew install ollama
2. ollama serve (백그라운드 실행)
3. ollama pull llama3.1:8b
"""

import os
import sys
import json
import requests
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import (
    get_silver_unclassified,
    insert_gold,
    get_connection
)


# Ollama 설정
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "ministral-3:8b"  # 또는 llama3.1:70b

# 분류 카테고리
CATEGORIES = [
    "이별",
    "사랑",
    "설렘",
    "호감",
    "썸",
    "짝사랑",
    "그리움",
    "자기위로",
    "힐링",
    "희망",
    "응원",
    "우울/슬픔",
    "분노",
    "이별 후회",
    "이별 슬픔",
]

CATEGORY_DESCRIPTIONS = """
- 이별: 헤어짐, 관계의 끝, 이별 통보
- 사랑: 사랑 고백, 행복한 연애, 사랑하는 감정
- 설렘: 두근거림, 떨리는 마음, 연애 초기 감정
- 호감: 관심, 끌림, 좋아하기 시작하는 감정
- 썸: 연인 전 단계, 밀당, 애매한 관계
- 짝사랑: 일방적 사랑, 혼자 좋아함, 고백 못함
- 그리움: 누군가를 그리워함, 추억, 보고 싶음
- 자기위로: 자기 자신을 위로, 스스로 다독임
- 힐링: 치유, 평화로움, 마음의 안정
- 희망: 희망적인 메시지, 미래에 대한 기대
- 응원: 응원, 격려, 힘내라는 메시지
- 우울/슬픔: 우울한 감정, 슬픔, 눈물
- 분노: 화남, 배신감, 억울함
- 이별 후회: 이별 후 후회, 돌아가고 싶음
- 이별 슬픔: 이별 후 슬픔, 상실감, 허전함
"""


def check_ollama_running():
    """Ollama 서버 실행 확인"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False


def classify_lyrics(lyrics: str, title: str = "", artist: str = "") -> dict:
    """
    가사를 분류하고 카테고리 + 확신도 반환
    Returns: {"category": ..., "confidence": ..., "reason": ...}
    """
    if not check_ollama_running():
        print("⚠️  Ollama가 실행되지 않았습니다. 'ollama serve' 실행 필요")
        return {"category": "기타", "confidence": 0.0, "reason": "Ollama 미실행"}
    
    prompt = f"""다음 노래 가사를 분석하고 가장 적절한 카테고리 하나를 선택해주세요.

## 카테고리
{CATEGORY_DESCRIPTIONS}

## 곡 정보
- 제목: {title}
- 아티스트: {artist}

## 가사
{lyrics[:2000]}

## 응답 형식
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요.
{{
    "category": "카테고리명",
    "confidence": 0.0-1.0 사이 확신도,
    "reason": "분류 이유 (한 줄)"
}}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 200
                }
            },
            timeout=60
        )
        
        response.raise_for_status()
        content = response.json().get("response", "").strip()
        
        # JSON 추출 (혹시 ```json 으로 감싸져 있을 경우)
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        result = json.loads(content)
        
        # 카테고리 검증
        if result.get("category") not in CATEGORIES:
            # 가장 유사한 카테고리 찾기
            for cat in CATEGORIES:
                if cat in result.get("category", ""):
                    result["category"] = cat
                    break
            else:
                result["category"] = "기타"
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"JSON 파싱 실패: {e}")
        print(f"응답 내용: {content}")
        return {"category": "기타", "confidence": 0.0, "reason": "파싱 실패"}
    except Exception as e:
        print(f"분류 실패: {e}")
        return {"category": "기타", "confidence": 0.0, "reason": str(e)}


def process_silver_to_gold(silver_id: int = None):
    """
    Silver 데이터를 분류해서 Gold에 저장
    silver_id 지정하면 해당 곡만, 없으면 미처리 전체
    """
    if silver_id:
        # 특정 곡만 처리
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.clean_lyrics, b.title, b.artist
            FROM songs_silver s
            JOIN songs_bronze b ON s.bronze_id = b.id
            WHERE s.id = ?
        """, (silver_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            print(f"Silver ID {silver_id} 를 찾을 수 없음")
            return []
        
        unclassified = [dict(row)]
    else:
        # 미처리 전체
        unclassified = get_silver_unclassified()
    
    if not unclassified:
        print("분류할 데이터가 없습니다.")
        return []
    
    classified = []
    
    for row in unclassified:
        sid = row['id']
        title = row['title']
        artist = row['artist']
        lyrics = row['clean_lyrics']
        
        print(f"분류 중: {title} - {artist}")
        
        # LLM 분류
        result = classify_lyrics(lyrics, title, artist)
        
        category = result.get("category", "기타")
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "")
        
        # Gold에 저장
        gold_id = insert_gold(sid, category, confidence)
        
        classified.append({
            "gold_id": gold_id,
            "silver_id": sid,
            "title": title,
            "artist": artist,
            "category": category,
            "confidence": confidence,
            "reason": reason
        })
        
        print(f"  ✓ {category} (확신도: {confidence:.0%}) - {reason}")
    
    print(f"\n총 {len(classified)}곡 분류 완료")
    return classified


def show_classification_results():
    """분류 결과 요약 출력"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT g.category, COUNT(*) as count
        FROM songs_gold g
        GROUP BY g.category
        ORDER BY count DESC
    """)
    
    print("\n📊 분류 결과 요약")
    print("-" * 30)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}곡")
    
    cursor.execute("""
        SELECT g.category, b.title, b.artist, g.confidence
        FROM songs_gold g
        JOIN songs_silver s ON g.silver_id = s.id
        JOIN songs_bronze b ON s.bronze_id = b.id
        ORDER BY g.category, g.classified_at DESC
    """)
    
    print("\n📋 전체 목록")
    print("-" * 50)
    current_category = None
    for row in cursor.fetchall():
        cat, title, artist, conf = row
        if cat != current_category:
            current_category = cat
            print(f"\n[{cat}]")
        print(f"  • {title} - {artist} ({conf:.0%})")
    
    conn.close()


# ======================
# CLI
# ======================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Silver → Gold 가사 분류")
    parser.add_argument("--all", action="store_true", help="미분류 전체 처리")
    parser.add_argument("--id", type=int, help="특정 Silver ID만 분류")
    parser.add_argument("--results", action="store_true", help="분류 결과 보기")
    parser.add_argument("--status", action="store_true", help="현재 상태 확인")
    parser.add_argument("--categories", action="store_true", help="카테고리 목록 보기")
    
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
    
    elif args.categories:
        print("\n📂 사용 가능한 카테고리")
        print(CATEGORY_DESCRIPTIONS)
    
    elif args.results:
        show_classification_results()
    
    elif args.all or args.id:
        process_silver_to_gold(args.id)
    
    else:
        print("사용법:")
        print("  python classify.py --all          # 미분류 전체 처리")
        print("  python classify.py --id 1         # Silver ID 1만 분류")
        print("  python classify.py --results      # 분류 결과 보기")
        print("  python classify.py --status       # 파이프라인 현황")
        print("  python classify.py --categories   # 카테고리 목록")