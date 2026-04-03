"""
Phase 2 전체 곡 재분류 스크립트
- 표준 감정 사전(20개)으로 GPT 재분류
- emotion_vector(20차원) 생성
- Spotify audio features 수집
- 확장 임베딩(Phase 1) 유지
"""
import json
import sys
import time
import array
import re
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import ssl as _ssl
from dotenv import load_dotenv
import oracledb

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

DSN = os.getenv("ORACLE_DSN", "").replace("ssl_server_dn_match=yes", "ssl_server_dn_match=no")

# 표준 감정 사전 (20개, 순서 고정)
STANDARD_EMOTIONS = [
    "그리움", "슬픔", "미련", "체념", "분노", "후련함", "자신감", "결단",
    "설렘", "사랑", "불안", "혼란", "상실감", "행복", "기대", "상처",
    "외로움", "실망", "갈망", "안타까움"
]


def get_connection():
    ssl_ctx = _ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = _ssl.CERT_NONE
    conn = oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=DSN, tcp_connect_timeout=15, ssl_context=ssl_ctx,
    )
    def _clob_handler(cursor, metadata):
        if metadata.type_code is oracledb.DB_TYPE_CLOB:
            return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
    conn.outputtypehandler = _clob_handler
    return conn


def emotions_to_vector(emotions: dict) -> list:
    """emotions dict를 20차원 표준 감정 벡터로 변환"""
    vec = [0.0] * len(STANDARD_EMOTIONS)
    for emo_name, score in emotions.items():
        if emo_name in STANDARD_EMOTIONS:
            idx = STANDARD_EMOTIONS.index(emo_name)
            vec[idx] = float(score)
    return vec


def get_audio_features(sp, spotify_id: str) -> dict:
    """Spotify audio features 수집"""
    try:
        features = sp.audio_features([spotify_id])
        if features and features[0]:
            f = features[0]
            return {
                "valence": f.get("valence"),
                "energy": f.get("energy"),
                "danceability": f.get("danceability"),
                "tempo": f.get("tempo"),
                "acousticness": f.get("acousticness"),
            }
    except Exception as e:
        print(f"    audio features 실패: {e}")
    return {}


def run():
    from openai import OpenAI
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials

    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    ))

    MODEL = "gpt-4o-mini"
    EMBEDDING_MODEL = "text-embedding-3-small"

    # SYSTEM_PROMPT 읽기
    classify_path = Path(__file__).parent.parent / "pipeline" / "classify.py"
    source = classify_path.read_text(encoding="utf-8")
    p_start = source.index('SYSTEM_PROMPT = """') + len('SYSTEM_PROMPT = """')
    p_end = source.index('"""', p_start)
    SYSTEM_PROMPT = source[p_start:p_end]

    def clean_lyrics(raw_lyrics: str) -> str:
        if not raw_lyrics:
            return ""
        text = raw_lyrics
        text = re.sub(r'\d*Embed$', '', text)
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'You might also like', '', text, flags=re.IGNORECASE)
        text = re.sub(r'See .+ Live.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Get tickets as low as \$\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [line.strip() for line in text.split('\n')]
        return '\n'.join(lines).strip()

    def classify_lyrics(lyrics, title, artist):
        user_prompt = f"""아래 곡을 분석하고 JSON만 출력하세요.

- 제목: {title}
- 아티스트: {artist}

## 가사
{lyrics[:3000]}

## 응답 형식 (JSON만, 다른 텍스트 금지)
{{
  "category": "대주제 (관심/짝사랑/썸/사랑/권태기/갈등/이별/자기자신/일상/기타)",
  "mood": "이 곡의 분위기를 짧은 구문으로 자유롭게 표현",
  "emotions": {{"감정명": 점수}},
  "primary_emotion": "가장 강한 감정 (표준 20개 중 하나)",
  "emotional_arc": "시작감정 -> 끝감정",
  "tags": ["키워드1", "키워드2"],
  "narrative": "가사의 핵심 상황과 화자의 심정을 2~3문장으로",
  "key_lyrics": "분류 근거가 된 핵심 가사 1~2줄 인용",
  "reasoning": "이렇게 분류한 이유를 한 줄로",
  "confidence": 0.0~1.0
}}"""
        response = openai_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3, max_tokens=800
        )
        content = response.choices[0].message.content.strip()
        if "```" in content:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
            if match:
                content = match.group(1).strip()
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group()
        result = json.loads(content)
        VALID_CATS = {"관심", "짝사랑", "썸", "사랑", "권태기", "갈등", "이별", "자기자신", "일상", "기타"}
        if result.get("category") not in VALID_CATS:
            result["category"] = "기타"
        if not isinstance(result.get("emotions"), dict):
            result["emotions"] = {}
        if not isinstance(result.get("tags"), list):
            result["tags"] = []
        result.setdefault("mood", "")
        result.setdefault("primary_emotion", "")
        result.setdefault("emotional_arc", "")
        result.setdefault("narrative", "")
        result.setdefault("confidence", 0.5)
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
        return result

    def get_mood_embedding(mood, result=None):
        if not mood:
            return []
        if result:
            text = (
                f"[{result.get('category', '')}] {mood}"
                f" | {result.get('primary_emotion', '')}"
                f" | {result.get('emotional_arc', '')}"
                f" | {result.get('narrative', '')}"
            )
        else:
            text = mood
        response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return response.data[0].embedding

    # DB 연결
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT spotify_id, title, artist, lyrics
        FROM songs
        WHERE status = 'classified' AND lyrics IS NOT NULL
        ORDER BY title
    """)
    cols = [c[0].lower() for c in cursor.description]
    songs = [dict(zip(cols, row)) for row in cursor.fetchall()]

    print(f"Phase 2 재분류 대상: {len(songs)}곡\n")

    success = 0
    failed = 0

    for i, song in enumerate(songs):
        sid = song["spotify_id"]
        title = song["title"]
        artist = song["artist"]
        lyrics = song["lyrics"] or ""

        print(f"[{i+1}/{len(songs)}] {title} - {artist}")

        try:
            cleaned = clean_lyrics(lyrics)
            if not cleaned:
                print(f"  -> 가사 없음, 스킵")
                continue

            # 1. GPT 재분류 (표준 감정 사전 적용)
            result = classify_lyrics(cleaned, title, artist)

            # 2. emotion_vector 생성
            emo_vec = emotions_to_vector(result.get("emotions", {}))

            # 3. 확장 임베딩 (Phase 1 유지)
            embedding = get_mood_embedding(result.get("mood", ""), result)

            # 4. Spotify audio features
            audio = get_audio_features(sp, sid)

            # 5. DB 업데이트
            emotions_json = json.dumps(result.get("emotions", {}), ensure_ascii=False)
            tags_json = json.dumps(result.get("tags", []), ensure_ascii=False)
            emb_array = array.array('d', embedding) if embedding else None
            emo_vec_array = array.array('d', emo_vec)

            cursor.execute("""
                UPDATE songs SET
                    category = :1,
                    mood = :2,
                    emotions = :3,
                    primary_emotion = :4,
                    emotional_arc = :5,
                    tags = :6,
                    narrative = :7,
                    confidence = :8,
                    mood_embedding = :9,
                    emotion_vector = :10,
                    valence = :11,
                    energy = :12,
                    danceability = :13,
                    tempo = :14,
                    acousticness = :15,
                    status = 'classified',
                    classified_at = CURRENT_TIMESTAMP
                WHERE spotify_id = :16
            """, [
                result.get("category", "기타"),
                result.get("mood", ""),
                emotions_json,
                result.get("primary_emotion", ""),
                result.get("emotional_arc", ""),
                tags_json,
                result.get("narrative", ""),
                result.get("confidence", 0.5),
                emb_array,
                emo_vec_array,
                audio.get("valence"),
                audio.get("energy"),
                audio.get("danceability"),
                audio.get("tempo"),
                audio.get("acousticness"),
                sid
            ])
            conn.commit()

            emo_str = ", ".join(f"{k}:{v}" for k, v in result["emotions"].items())
            af_str = f"v={audio.get('valence', '?')}, e={audio.get('energy', '?')}" if audio else "no audio"
            print(f"  -> [{result['category']}] {result['mood']} | {result['primary_emotion']}")
            print(f"     emotions: {emo_str}")
            print(f"     audio: {af_str}")
            success += 1

            time.sleep(0.5)

        except Exception as e:
            print(f"  -> 실패: {e}")
            failed += 1
            conn.rollback()

    conn.close()
    print(f"\n완료: {success}곡 성공, {failed}곡 실패")


if __name__ == "__main__":
    run()
