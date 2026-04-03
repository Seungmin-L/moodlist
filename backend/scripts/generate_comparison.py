"""
Before vs After 비교 리포트 생성
두 스냅샷의 DB 데이터를 비교하여 변경 사항을 정리
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


def load_before_data():
    """before 스냅샷 MD에서 곡별 데이터 파싱"""
    path = REPO_ROOT / "docs" / "pipeline-improvement" / "snapshot_before.md"
    text = path.read_text(encoding="utf-8")
    songs = {}
    current_song = None
    in_table = False

    for line in text.split("\n"):
        if line.startswith("#### ") and " - " in line:
            parts = line[5:].strip()
            # title - artist
            current_song = {"_raw_header": parts}
            in_table = False
        elif current_song and line.startswith("| spotify_id |"):
            sid = line.split("|")[2].strip().strip("`")
            current_song["spotify_id"] = sid
        elif current_song and line.startswith("| category |"):
            current_song["category"] = line.split("|")[2].strip().strip("*")
        elif current_song and line.startswith("| mood |"):
            current_song["mood"] = line.split("|")[2].strip()
        elif current_song and line.startswith("| primary_emotion |"):
            current_song["primary_emotion"] = line.split("|")[2].strip()
        elif current_song and line.startswith("| emotional_arc |"):
            current_song["emotional_arc"] = line.split("|")[2].strip()
        elif current_song and line.startswith("| narrative |"):
            current_song["narrative"] = line.split("|")[2].strip()

            # song is complete, save it
            if "spotify_id" in current_song:
                songs[current_song["spotify_id"]] = current_song
            current_song = None

    return songs


def run():
    # Load before data from snapshot file
    before = load_before_data()

    # Load after data from live DB
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT spotify_id, title, artist, category, mood, primary_emotion,
               emotional_arc, emotions, tags, narrative, confidence, mood_embedding
        FROM songs
        WHERE status = 'classified'
        ORDER BY category, title
    """)
    cols = [c[0].lower() for c in cursor.description]
    after_rows = []
    for row in cursor.fetchall():
        d = dict(zip(cols, row))
        emb = d.get("mood_embedding")
        d["_vec"] = list(emb) if emb is not None else []
        for field in ["emotions", "tags"]:
            val = d.get(field)
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except Exception:
                    pass
        after_rows.append(d)

    after = {r["spotify_id"]: r for r in after_rows}

    lines = []
    lines.append("# Phase 0+1 Before vs After 비교 리포트\n")

    # ============================================================
    # 1. 카테고리 분포 비교
    # ============================================================
    lines.append("## 1. 카테고리 분포 비교\n")

    before_cats = Counter(s.get("category", "") for s in before.values())
    after_cats = Counter(s.get("category", "") for s in after.values())

    all_cats = sorted(set(list(before_cats.keys()) + list(after_cats.keys())))
    lines.append("| 카테고리 | Before | After | 변화 |")
    lines.append("|----------|--------|-------|------|")
    for cat in all_cats:
        b = before_cats.get(cat, 0)
        a = after_cats.get(cat, 0)
        diff = a - b
        diff_str = f"+{diff}" if diff > 0 else str(diff) if diff != 0 else "-"
        lines.append(f"| {cat} | {b} | {a} | {diff_str} |")
    lines.append("")

    # ============================================================
    # 2. 카테고리가 변경된 곡 목록
    # ============================================================
    lines.append("## 2. 카테고리가 변경된 곡\n")

    changed = []
    for sid, after_song in after.items():
        before_song = before.get(sid)
        if before_song and before_song.get("category") != after_song.get("category"):
            changed.append((after_song["title"], after_song["artist"],
                          before_song.get("category", ""), after_song.get("category", ""),
                          before_song.get("mood", ""), after_song.get("mood", "")))

    if changed:
        lines.append(f"**{len(changed)}곡의 카테고리가 변경됨**\n")
        lines.append("| 곡 | 아티스트 | Before category | After category | Before mood | After mood |")
        lines.append("|-----|---------|----------------|---------------|-------------|------------|")
        for title, artist, b_cat, a_cat, b_mood, a_mood in changed:
            lines.append(f"| {title} | {artist} | {b_cat} | **{a_cat}** | {b_mood} | {a_mood} |")
    else:
        lines.append("변경 없음")
    lines.append("")

    # ============================================================
    # 3. Mood 텍스트 변경 목록
    # ============================================================
    lines.append("## 3. Mood 텍스트가 변경된 곡\n")

    mood_changed = []
    for sid, after_song in after.items():
        before_song = before.get(sid)
        if before_song and before_song.get("mood") != after_song.get("mood"):
            mood_changed.append((after_song["title"], after_song["artist"],
                               before_song.get("mood", ""), after_song.get("mood", "")))

    if mood_changed:
        lines.append(f"**{len(mood_changed)}곡의 mood가 변경됨**\n")
        lines.append("| 곡 | 아티스트 | Before mood | After mood |")
        lines.append("|-----|---------|-------------|------------|")
        for title, artist, b_mood, a_mood in mood_changed:
            lines.append(f"| {title} | {artist} | {b_mood} | {a_mood} |")
    else:
        lines.append("변경 없음")
    lines.append("")

    # ============================================================
    # 4. Mood 중복 개선 확인
    # ============================================================
    lines.append("## 4. Mood 텍스트 중복 개선\n")

    before_moods = Counter(s.get("mood", "") for s in before.values())
    after_moods = Counter(s.get("mood", "") for s in after.values())

    lines.append("| 지표 | Before | After |")
    lines.append("|------|--------|-------|")
    lines.append(f"| 고유 mood 수 | {len(before_moods)} | {len(after_moods)} |")

    before_dupes = [(m, c) for m, c in before_moods.most_common() if c > 1]
    after_dupes = [(m, c) for m, c in after_moods.most_common() if c > 1]
    lines.append(f"| 중복 mood 수 | {len(before_dupes)} | {len(after_dupes)} |")
    lines.append("")

    if before_dupes:
        lines.append("### Before 중복 mood")
        for m, c in before_dupes:
            lines.append(f"- \"{m}\" x{c}")
        lines.append("")

    if after_dupes:
        lines.append("### After 중복 mood")
        for m, c in after_dupes:
            lines.append(f"- \"{m}\" x{c}")
        lines.append("")

    # ============================================================
    # 5. 임베딩 품질 비교 (After만 - before는 벡터가 변경되어 직접 비교 불가)
    # ============================================================
    lines.append("## 5. After 임베딩 품질 측정\n")

    # 카테고리별 내부 거리
    by_cat = {}
    for s in after_rows:
        by_cat.setdefault(s["category"], []).append(s)

    lines.append("### 카테고리별 내부 평균 거리 (낮으면 같은 카테고리끼리 뭉침)\n")
    lines.append("| 카테고리 | 곡 수 | 평균 거리 | 거리=0 쌍 |")
    lines.append("|----------|-------|----------|----------|")

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
        lines.append(f"| {cat} | {len(songs)} | {avg_d:.4f} | {zero_pairs} |")
    lines.append("")

    # 크로스 카테고리 침범율
    lines.append("### 크로스 카테고리 침범율\n")
    lines.append("각 곡의 유사곡 TOP5 중 다른 카테고리 비율\n")

    invasion = {}
    for s in after_rows:
        dists_list = []
        for other in after_rows:
            if other["spotify_id"] == s["spotify_id"]:
                continue
            d = cosine_dist(s["_vec"], other["_vec"])
            dists_list.append((d, other))
        dists_list.sort(key=lambda x: x[0])
        top5 = dists_list[:5]
        diff_cat = sum(1 for _, o in top5 if o["category"] != s["category"])
        cat = s["category"]
        if cat not in invasion:
            invasion[cat] = {"total": 0, "invaded": 0}
        invasion[cat]["total"] += 1
        invasion[cat]["invaded"] += diff_cat

    lines.append("| 카테고리 | Before 침범율 | After 침범율 |")
    lines.append("|----------|-------------|-------------|")
    before_invasion = {"이별": "36%", "짝사랑": "58%", "사랑": "55%", "썸": "63%", "갈등": "87%", "자기자신": "60%", "기타": "90%"}
    for cat in sorted(invasion.keys(), key=lambda c: -invasion[c]["total"]):
        stats = invasion[cat]
        rate = stats["invaded"] / (stats["total"] * 5) * 100
        b_rate = before_invasion.get(cat, "N/A")
        lines.append(f"| {cat} | {b_rate} | {rate:.0f}% |")
    lines.append("")

    # 분리도
    lines.append("### 임베딩 분리도\n")

    import random
    random.seed(42)
    same_dists = []
    diff_dists = []
    for _ in range(300):
        i, j = random.sample(range(len(after_rows)), 2)
        d = cosine_dist(after_rows[i]["_vec"], after_rows[j]["_vec"])
        if after_rows[i]["category"] == after_rows[j]["category"]:
            same_dists.append(d)
        else:
            diff_dists.append(d)

    if same_dists and diff_dists:
        same_avg = sum(same_dists) / len(same_dists)
        diff_avg = sum(diff_dists) / len(diff_dists)
        lines.append(f"| 지표 | Before | After |")
        lines.append(f"|------|--------|-------|")
        lines.append(f"| 같은 카테고리 평균 거리 | 0.6228 | {same_avg:.4f} |")
        lines.append(f"| 다른 카테고리 평균 거리 | 0.7234 | {diff_avg:.4f} |")
        lines.append(f"| **분리도** (차이) | **0.1006** | **{diff_avg - same_avg:.4f}** |")
    lines.append("")

    # ============================================================
    # 6. 유사곡 추천 샘플 비교
    # ============================================================
    lines.append("## 6. 유사곡 추천 샘플 (After)\n")

    # 진단에서 문제가 있었던 곡들로 확인
    check_songs = ["Lxxk 2 U", "Good bye-bye", "So Cool", "Kick It", "Crazy"]
    for check_title in check_songs:
        song = next((s for s in after_rows if s["title"] == check_title), None)
        if not song:
            continue

        dists_list = []
        for other in after_rows:
            if other["spotify_id"] == song["spotify_id"]:
                continue
            d = cosine_dist(song["_vec"], other["_vec"])
            dists_list.append((d, other))
        dists_list.sort(key=lambda x: x[0])

        lines.append(f"### {song['title']} ({song['artist']}) - [{song['category']}] {song['mood']}\n")
        lines.append("| # | 유사곡 | 아티스트 | category | mood | 거리 |")
        lines.append("|---|--------|----------|----------|------|------|")
        for k, (d, o) in enumerate(dists_list[:5]):
            match = "O" if o["category"] == song["category"] else "X"
            lines.append(f"| {k+1} | {o['title']} | {o['artist']} | {o['category']} ({match}) | {o['mood']} | {d:.4f} |")
        lines.append("")

    # ============================================================
    # 7. 전체 곡 Before/After 비교 테이블
    # ============================================================
    lines.append("## 7. 전체 곡 Before/After 비교\n")
    lines.append("| 곡 | 아티스트 | Before category | After category | Before mood | After mood | 변경 |")
    lines.append("|-----|---------|----------------|---------------|-------------|------------|------|")

    for sid, a in sorted(after.items(), key=lambda x: x[1]["title"]):
        b = before.get(sid, {})
        b_cat = b.get("category", "N/A")
        a_cat = a.get("category", "")
        b_mood = b.get("mood", "N/A")
        a_mood = a.get("mood", "")
        cat_changed = b_cat != a_cat
        mood_changed_flag = b_mood != a_mood
        change_marker = ""
        if cat_changed:
            change_marker += "CAT "
        if mood_changed_flag:
            change_marker += "MOOD"
        if not change_marker:
            change_marker = "-"
        lines.append(f"| {a['title']} | {a['artist']} | {b_cat} | {a_cat} | {b_mood} | {a_mood} | {change_marker} |")
    lines.append("")

    conn.close()

    output_path = REPO_ROOT / "docs" / "pipeline-improvement" / "comparison_before_after.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {output_path}")


if __name__ == "__main__":
    run()
