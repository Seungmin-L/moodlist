"""
Silver → Gold LLM 분류 모듈

- OpenAI GPT-4o-mini 사용
- category (고정 5개) + mood (자유 생성) + emotions 구조
"""

import os
import sys
import json
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from db.database import (
    get_silver_unclassified,
    insert_gold,
    get_connection,
    get_all_mood_embeddings
)

# OpenAI 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"


def get_mood_embedding(mood: str) -> list:
    """mood 텍스트의 임베딩 벡터 생성"""
    if not mood:
        return []
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=mood
    )
    return response.data[0].embedding


def _cosine_similarity(a: list, b: list) -> float:
    """두 벡터의 코사인 유사도"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_similar_songs(gold_id: int, top_k: int = 10) -> list:
    """특정 곡과 mood가 비슷한 곡 찾기"""
    all_songs = get_all_mood_embeddings()

    target = None
    others = []
    for song in all_songs:
        emb = json.loads(song['mood_embedding']) if isinstance(song['mood_embedding'], str) else song['mood_embedding']
        if song['id'] == gold_id:
            target = emb
        else:
            others.append({**song, '_embedding': emb})

    if not target:
        return []

    for song in others:
        song['similarity'] = _cosine_similarity(target, song['_embedding'])

    others.sort(key=lambda x: x['similarity'], reverse=True)
    return [{k: v for k, v in s.items() if k != '_embedding'} for s in others[:top_k]]


def group_songs_by_mood(threshold: float = 0.82) -> list:
    """mood 유사도 기반으로 곡들을 그룹핑"""
    all_songs = get_all_mood_embeddings()

    songs = []
    for song in all_songs:
        emb = json.loads(song['mood_embedding']) if isinstance(song['mood_embedding'], str) else song['mood_embedding']
        songs.append({**song, '_embedding': emb})

    groups = []
    used = set()

    for i, song in enumerate(songs):
        if i in used:
            continue

        group = [song]
        used.add(i)

        for j, other in enumerate(songs):
            if j in used:
                continue
            sim = _cosine_similarity(song['_embedding'], other['_embedding'])
            if sim >= threshold:
                group.append(other)
                used.add(j)

        # 그룹 대표 mood는 첫 번째 곡의 mood
        groups.append({
            'mood': song['mood'],
            'category': song['category'],
            'songs': [{k: v for k, v in s.items() if k != '_embedding'} for s in group]
        })

    return groups

SYSTEM_PROMPT = """당신은 한국 노래 가사의 상황과 감정을 분석하는 전문가입니다.

## 분류 체계

### category (대주제) - 반드시 아래 5개 중 하나
- 사랑: 연애, 호감, 관계에 대한 노래
- 이별: 헤어짐, 관계의 끝
- 자기자신: 자존감, 성장, 다짐, 위로
- 일상: 친구, 가족, 일상의 감정
- 기타: 위에 해당 안 됨

### mood (분위기/무드) - 자유롭게 생성
이 곡을 어떤 기분일 때 들을지를 짧은 한국어 구문으로 표현.
예: "후련한 이별", "슬픈 미련", "분노 폭발", "쿨하게 놓아줌", "달달한 설렘", "혼자만의 위로" 등
정해진 목록 없이 곡의 분위기에 맞게 자유롭게 만들어라.

### emotions (감정 점수)
0.0~1.0 사이 점수, 0.3 이상만 포함.
감정명도 자유롭게 사용 가능.

## 분석 규칙
1. 가사 전체 흐름을 읽어라 (시작 → 끝)
2. 반전이 있으면 마지막 감정이 primary_emotion
3. emotions 점수는 독립적 (합이 1.0 안 넘어도 됨)
4. 0.3 이상인 감정만 emotions에 포함
5. tags는 주제 키워드 2~4개
6. 반드시 JSON만 출력하고, 다른 텍스트는 절대 포함하지 마"""


def classify_lyrics(lyrics: str, title: str = "", artist: str = "") -> dict:
    """가사를 분석하고 감정 + 무드 반환"""

    user_prompt = f"""아래 곡을 분석하고 JSON만 출력하세요.

- 제목: {title}
- 아티스트: {artist}

## 가사
{lyrics[:3000]}

## 응답 형식 (JSON만, 다른 텍스트 금지)
{{
  "category": "대주제 (사랑/이별/자기자신/일상/기타)",
  "mood": "이 곡의 분위기를 짧은 구문으로 자유롭게 표현",
  "emotions": {{"감정명": 점수}},
  "primary_emotion": "가장 강한 감정",
  "emotional_arc": "시작감정 → 끝감정",
  "tags": ["키워드1", "키워드2"],
  "narrative": "가사의 핵심 상황과 화자의 심정을 2~3문장으로",
  "key_lyrics": "분류 근거가 된 핵심 가사 1~2줄 인용",
  "reasoning": "이렇게 분류한 이유를 한 줄로",
  "confidence": 0.0~1.0
}}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )

        content = response.choices[0].message.content.strip()

        # ```json``` 블록 추출
        if "```" in content:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
            if match:
                content = match.group(1).strip()

        # { } 로 감싸진 JSON 찾기
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group()

        result = json.loads(content)
        result = _validate_result(result)

        return result

    except json.JSONDecodeError as e:
        repaired = _try_repair_json(content)
        if repaired:
            return _validate_result(repaired)
        print(f"JSON 파싱 실패: {e}")
        print(f"응답 내용: {content[:200]}")
        return _empty_result("파싱 실패")
    except Exception as e:
        print(f"분류 실패: {e}")
        return _empty_result(str(e))


def _try_repair_json(content: str) -> dict | None:
    """잘린 JSON 복구 시도"""
    idx = content.find('{')
    if idx == -1:
        return None
    content = content[idx:]

    for suffix in ['"}', ']}', '}', '"]}', '"}]}']:
        try:
            return json.loads(content + suffix)
        except json.JSONDecodeError:
            continue

    last_comma = content.rfind(',')
    if last_comma > 0:
        truncated = content[:last_comma] + '}'
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass

    return None


def _empty_result(reason: str) -> dict:
    """빈 결과 반환"""
    return {
        "category": "기타",
        "mood": "",
        "emotions": {},
        "primary_emotion": "미분류",
        "emotional_arc": "",
        "tags": [],
        "narrative": reason,
        "key_lyrics": "",
        "reasoning": "",
        "confidence": 0.0
    }


def _validate_result(result: dict) -> dict:
    """결과 검증 및 정규화"""

    defaults = {
        "category": "기타",
        "mood": "",
        "emotions": {},
        "primary_emotion": "미분류",
        "emotional_arc": "",
        "tags": [],
        "narrative": "",
        "key_lyrics": "",
        "reasoning": "",
        "confidence": 0.5
    }

    for key, default in defaults.items():
        if key not in result:
            result[key] = default

    # category 검증
    valid_categories = {"사랑", "이별", "자기자신", "일상", "기타"}
    if result["category"] not in valid_categories:
        result["category"] = "기타"

    if not isinstance(result["emotions"], dict):
        result["emotions"] = {}

    for emotion, score in list(result["emotions"].items()):
        if not isinstance(score, (int, float)):
            result["emotions"][emotion] = 0.0
        else:
            result["emotions"][emotion] = max(0.0, min(1.0, float(score)))

    if not result["primary_emotion"] and result["emotions"]:
        result["primary_emotion"] = max(result["emotions"], key=result["emotions"].get)

    if not isinstance(result["tags"], list):
        result["tags"] = []

    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.5))))

    return result


def process_silver_to_gold(silver_id: int = None):
    """Silver 데이터를 분류해서 Gold에 저장"""
    if silver_id:
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

        result = classify_lyrics(lyrics, title, artist)

        category = result.get("category", "기타")
        mood = result.get("mood", "")
        emotions = result.get("emotions", {})
        primary_emotion = result.get("primary_emotion", "")
        confidence = result.get("confidence", 0.0)
        narrative = result.get("narrative", "")
        key_lyrics = result.get("key_lyrics", "")
        reasoning = result.get("reasoning", "")
        tags = result.get("tags", [])
        emotional_arc = result.get("emotional_arc", "")

        # mood 임베딩 생성
        mood_embedding = get_mood_embedding(mood)

        gold_id = insert_gold(
            sid, category, confidence,
            mood=mood, mood_embedding=mood_embedding, emotions=emotions,
            primary_emotion=primary_emotion, emotional_arc=emotional_arc,
            tags=tags, narrative=narrative
        )

        classified.append({
            "gold_id": gold_id,
            "silver_id": sid,
            "title": title,
            "artist": artist,
            "category": category,
            "mood": mood,
            "emotions": emotions,
            "primary_emotion": primary_emotion,
            "confidence": confidence,
            "narrative": narrative,
            "key_lyrics": key_lyrics,
            "reasoning": reasoning,
            "tags": tags,
            "emotional_arc": emotional_arc,
        })

        print(f"  ✓ [{category}] {mood} ({primary_emotion}, {confidence:.0%})")
        print(f"    📝 {narrative}")
        print(f"    🎵 \"{key_lyrics}\"")
        print(f"    💡 {reasoning}")

    print(f"\n총 {len(classified)}곡 분류 완료")
    return classified
