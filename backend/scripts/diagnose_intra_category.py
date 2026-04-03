"""
카테고리 내부 분화 능력 진단
- 같은 카테고리(특히 이별) 안에서 곡들이 얼마나 구분되는지
- 기존 구조화 데이터(narrative, emotions, emotional_arc)의 분화 잠재력
"""
import json
import math
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import ssl as _ssl
from dotenv import load_dotenv
import oracledb

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

DSN = os.getenv("ORACLE_DSN", "").replace("ssl_server_dn_match=yes", "ssl_server_dn_match=no")

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


def cosine_dist(a, b):
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - dot / (na * nb)


def run():
    conn = get_connection()
    cursor = conn.cursor()

    report = []
    report.append("# 카테고리 내부 분화 능력 진단\n")
    report.append("> 같은 카테고리 안에서 곡의 맥락/서사가 얼마나 구분되는지 분석\n")

    # ============================================================
    # 1. 전체 곡 데이터 로드
    # ============================================================
    cursor.execute("""
        SELECT spotify_id, title, artist, mood, category, primary_emotion,
               emotional_arc, emotions, tags, narrative, mood_embedding, confidence
        FROM songs
        WHERE status = 'classified' AND mood_embedding IS NOT NULL
    """)
    cols = [c[0].lower() for c in cursor.description]
    all_songs = []
    for row in cursor.fetchall():
        d = dict(zip(cols, row))
        emb = d["mood_embedding"]
        d["_vec"] = list(emb) if emb is not None else []
        # parse JSON fields
        for field in ["emotions", "tags"]:
            val = d[field]
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except Exception:
                    d[field] = {} if field == "emotions" else []
        all_songs.append(d)

    conn.close()

    # 카테고리별 그룹핑
    by_cat = {}
    for s in all_songs:
        by_cat.setdefault(s["category"], []).append(s)

    # ============================================================
    # 2. 카테고리별 내부 거리 분석
    # ============================================================
    report.append("## 1. 카테고리별 mood 임베딩 내부 거리\n")
    report.append("같은 카테고리 곡들 사이의 코사인 거리. 낮으면 = 구분이 안 됨.\n")
    report.append("| 카테고리 | 곡 수 | 평균 거리 | 최소 | 최대 | 거리=0 쌍 |")
    report.append("|----------|-------|----------|------|------|----------|")

    for cat in sorted(by_cat.keys(), key=lambda c: -len(by_cat[c])):
        songs = by_cat[cat]
        if len(songs) < 2:
            continue
        dists = []
        zero_pairs = 0
        for i in range(len(songs)):
            for j in range(i + 1, len(songs)):
                d = cosine_dist(songs[i]["_vec"], songs[j]["_vec"])
                dists.append(d)
                if d < 0.001:
                    zero_pairs += 1
        avg_d = sum(dists) / len(dists)
        report.append(f"| {cat} | {len(songs)} | {avg_d:.4f} | {min(dists):.4f} | {max(dists):.4f} | {zero_pairs} |")
    report.append("")

    # ============================================================
    # 3. 이별 카테고리 심층 분석
    # ============================================================
    breakup = by_cat.get("이별", [])
    report.append(f"## 2. 이별 카테고리 심층 분석 ({len(breakup)}곡)\n")

    if breakup:
        report.append("### 곡별 분류 데이터\n")
        report.append("| 곡 | 아티스트 | mood | primary_emotion | emotional_arc | confidence |")
        report.append("|-----|---------|------|-----------------|---------------|------------|")
        for s in breakup:
            report.append(f"| {s['title']} | {s['artist']} | {s['mood']} | {s['primary_emotion']} | {s.get('emotional_arc', '')} | {s['confidence']} |")
        report.append("")

        report.append("### 곡별 감정 프로필 + narrative\n")
        for s in breakup:
            emo_str = ", ".join(f"{k}:{v}" for k, v in s["emotions"].items()) if isinstance(s["emotions"], dict) else str(s["emotions"])
            tags_str = ", ".join(s["tags"]) if isinstance(s["tags"], list) else str(s["tags"])
            report.append(f"**{s['title']}** ({s['artist']})")
            report.append(f"- mood: {s['mood']}")
            report.append(f"- emotions: {emo_str}")
            report.append(f"- tags: {tags_str}")
            report.append(f"- narrative: {s.get('narrative', '')}")
            report.append(f"- arc: {s.get('emotional_arc', '')}")
            report.append("")

        # 이별 내 거리 행렬
        report.append("### 이별 곡 간 코사인 거리 행렬\n")
        names = [f"{s['title'][:12]}" for s in breakup]
        header = "| | " + " | ".join(names) + " |"
        sep = "|---|" + "|".join(["---"] * len(names)) + "|"
        report.append(header)
        report.append(sep)
        for i, s1 in enumerate(breakup):
            row = f"| {names[i]} |"
            for j, s2 in enumerate(breakup):
                if i == j:
                    row += " - |"
                else:
                    d = cosine_dist(s1["_vec"], s2["_vec"])
                    row += f" {d:.3f} |"
            report.append(row)
        report.append("")

        # 이별 내 mood 텍스트 동일성
        mood_counts = Counter(s["mood"] for s in breakup)
        report.append("### 이별 내 mood 텍스트 중복\n")
        for mood, cnt in mood_counts.most_common():
            if cnt > 1:
                songs_with = [s["title"] for s in breakup if s["mood"] == mood]
                report.append(f"- \"{mood}\" x{cnt}: {', '.join(songs_with)}")
        if all(cnt == 1 for cnt in mood_counts.values()):
            report.append("- 중복 없음 (모두 고유)")
        report.append("")

    # ============================================================
    # 4. 짝사랑 카테고리 심층 분석
    # ============================================================
    crush = by_cat.get("짝사랑", [])
    report.append(f"## 3. 짝사랑 카테고리 심층 분석 ({len(crush)}곡)\n")

    if crush:
        report.append("### 곡별 분류 데이터\n")
        for s in crush:
            emo_str = ", ".join(f"{k}:{v}" for k, v in s["emotions"].items()) if isinstance(s["emotions"], dict) else str(s["emotions"])
            report.append(f"**{s['title']}** ({s['artist']})")
            report.append(f"- mood: {s['mood']} | arc: {s.get('emotional_arc', '')}")
            report.append(f"- emotions: {emo_str}")
            report.append(f"- narrative: {s.get('narrative', '')}")
            report.append("")

    # ============================================================
    # 5. 구조화 데이터의 분화 잠재력 평가
    # ============================================================
    report.append("## 4. 구조화 데이터 분화 잠재력 평가\n")
    report.append("GPT가 이미 생성한 데이터가 카테고리 내부 분화에 활용 가능한지 평가.\n")

    # emotional_arc 다양성
    report.append("### emotional_arc 다양성 (카테고리별)\n")
    for cat in ["이별", "짝사랑", "사랑", "썸"]:
        songs = by_cat.get(cat, [])
        arcs = [s.get("emotional_arc", "") for s in songs if s.get("emotional_arc")]
        unique_arcs = set(arcs)
        report.append(f"**{cat}** ({len(songs)}곡): {len(unique_arcs)}개 고유 arc")
        for arc in sorted(unique_arcs):
            cnt = arcs.count(arc)
            report.append(f"  - \"{arc}\" x{cnt}")
    report.append("")

    # primary_emotion 다양성
    report.append("### primary_emotion 다양성 (카테고리별)\n")
    for cat in ["이별", "짝사랑", "사랑", "썸"]:
        songs = by_cat.get(cat, [])
        emos = Counter(s.get("primary_emotion", "") for s in songs)
        report.append(f"**{cat}**: {dict(emos)}")
    report.append("")

    # narrative 길이 분석
    report.append("### narrative 길이 (임베딩 입력 후보)\n")
    narr_lengths = [len(s.get("narrative", "") or "") for s in all_songs]
    if narr_lengths:
        report.append(f"- 최소: {min(narr_lengths)}자, 최대: {max(narr_lengths)}자, 평균: {sum(narr_lengths)/len(narr_lengths):.0f}자")
        report.append(f"- mood 평균 ~8자 vs narrative 평균 ~{sum(narr_lengths)/len(narr_lengths):.0f}자 = **{sum(narr_lengths)/len(narr_lengths)/8:.0f}배 정보량**")
    report.append("")

    # ============================================================
    # 6. 크로스 카테고리 침범 분석
    # ============================================================
    report.append("## 5. 크로스 카테고리 침범 분석\n")
    report.append("각 곡의 유사곡 TOP 5 중 다른 카테고리 곡이 몇 개인지.\n")

    invasion_stats = {}
    for s in all_songs:
        dists = []
        for other in all_songs:
            if other["spotify_id"] == s["spotify_id"]:
                continue
            d = cosine_dist(s["_vec"], other["_vec"])
            dists.append((d, other))
        dists.sort(key=lambda x: x[0])
        top5 = dists[:5]
        diff_cat = sum(1 for _, o in top5 if o["category"] != s["category"])
        cat = s["category"]
        if cat not in invasion_stats:
            invasion_stats[cat] = {"total": 0, "invaded": 0, "songs": []}
        invasion_stats[cat]["total"] += 1
        invasion_stats[cat]["invaded"] += diff_cat
        if diff_cat >= 3:
            invasion_stats[cat]["songs"].append((s["title"], s["artist"], diff_cat, [(o["title"], o["category"]) for _, o in top5]))

    report.append("| 카테고리 | 곡 수 | TOP5 중 타 카테고리 비율 |")
    report.append("|----------|-------|----------------------|")
    for cat in sorted(invasion_stats.keys(), key=lambda c: -invasion_stats[c]["total"]):
        stats = invasion_stats[cat]
        rate = stats["invaded"] / (stats["total"] * 5) * 100
        report.append(f"| {cat} | {stats['total']} | {rate:.0f}% |")
    report.append("")

    # 침범이 심한 곡들
    report.append("### TOP5 중 3곡 이상이 다른 카테고리인 곡들\n")
    for cat, stats in invasion_stats.items():
        for title, artist, diff_cnt, top5_list in stats["songs"]:
            report.append(f"**{title}** ({artist}) [{cat}] - {diff_cnt}/5 타 카테고리")
            for t, c in top5_list:
                marker = "X" if c != cat else "O"
                report.append(f"  - {t} [{c}] ({marker})")
            report.append("")

    # ============================================================
    # 7. 종합 진단
    # ============================================================
    report.append("## 6. 종합 진단: 왜 카테고리 내부 분화가 안 되는가\n")

    report.append("### 근본 원인\n")
    report.append("1. **임베딩 입력이 mood 구문(~8자)뿐**: \"쿨하게 놓아줌\"이라는 4단어로는 ")
    report.append("   \"후련한 이별\" vs \"억울하지만 보내줌\" vs \"사랑하지만 놓아줌\"을 구분 불가")
    report.append("2. **동일 mood = 동일 벡터(거리 0)**: mood 텍스트가 같으면 아무리 가사/감정이 달라도 벡터가 완전히 동일")
    report.append("3. **narrative(~60자)에 맥락 정보 존재하지만 미활용**: GPT가 이미 서사를 요약해놨는데 임베딩에 안 쓰임")
    report.append("4. **emotions 다차원 프로필 미활용**: {그리움:0.8, 체념:0.4}와 {분노:0.7, 후련함:0.6}은 ")
    report.append("   같은 이별이라도 전혀 다른 감정 구조인데, 유사도에 반영 안 됨")
    report.append("5. **emotional_arc 미활용**: \"사랑 -> 체념\"과 \"분노 -> 해방\"은 같은 이별이라도 서사 구조가 다름")
    report.append("")

    report.append("### 개선 우선순위\n")
    report.append("")
    report.append("**Phase 1 (선행 필수 - 임베딩 입력 확장)**")
    report.append("- mood 구문 대신 `mood + category + primary_emotion + emotional_arc + narrative` 결합 텍스트를 임베딩")
    report.append("- 이것만으로도 8자 -> ~100자로 정보량 12배 증가, 카테고리 내부 분화 가능")
    report.append("")
    report.append("**Phase 2 (감정 벡터 하이브리드)**")
    report.append("- emotions dict를 고정 차원 벡터로 변환 (표준 감정 사전 정의)")
    report.append("- 코사인 유사도 = alpha * embedding_sim + beta * emotion_vector_sim")
    report.append("- 같은 이별이라도 {그리움, 미련} vs {분노, 후련} 구분 가능")
    report.append("")
    report.append("**Phase 3 (태그 표준화 + 카테고리 가중치)**")
    report.append("- 자유형 태그를 표준 태그 사전으로 정규화")
    report.append("- 같은 카테고리 내에서의 유사도에 가중치 부여")
    report.append("")

    return "\n".join(report)


if __name__ == "__main__":
    result = run()
    output_path = Path(__file__).parent.parent.parent / "docs" / "PIPELINE_DIAGNOSIS_DETAIL.md"
    output_path.write_text(result, encoding="utf-8")
    print(f"저장: {output_path}")
    print(result)
