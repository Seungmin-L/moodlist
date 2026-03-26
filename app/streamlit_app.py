"""
Moodlist - 가사 기반 플레이리스트 분류 앱
"""

import streamlit as st
import sys
from pathlib import Path
import importlib

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import (
    get_pipeline_stats,
    get_songs_by_category,
    get_all_categories,
    get_connection
)
from pipeline.crawl import crawl_and_save
from pipeline.clean import process_bronze_to_silver
from pipeline.classify import process_silver_to_gold, CATEGORIES


def _load_crawl_module():
    import pipeline.crawl as crawl_module
    return importlib.reload(crawl_module)

# 페이지 설정
st.set_page_config(
    page_title="Moodlist",
    page_icon="🎵",
    layout="wide"
)

# 타이틀
st.title("🎵 Moodlist")
st.markdown("가사 기반으로 노래를 분류해서 플레이리스트를 만들어보세요!")

# 사이드바 - 파이프라인 현황
with st.sidebar:
    st.header("📊 파이프라인 현황")
    stats = get_pipeline_stats()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Bronze", stats['bronze_count'])
    col2.metric("Silver", stats['silver_count'])
    col3.metric("Gold", stats['gold_count'])
    
    if stats['category_distribution']:
        st.subheader("카테고리 분포")
        for cat, count in stats['category_distribution'].items():
            st.write(f"• {cat}: {count}곡")
    
    st.divider()
    
    # Ollama 상태 체크
    import requests
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            st.success("✅ Ollama 실행 중")
        else:
            st.error("❌ Ollama 응답 없음")
    except:
        st.error("❌ Ollama 미실행")
        st.caption("터미널에서 `ollama serve` 실행 필요")

# 메인 탭
tab1, tab2, tab3, tab4 = st.tabs(["🎤 곡 추가", "🎧 Spotify", "📋 분류 결과", "🔄 파이프라인"])

# =====================
# 탭 1: 곡 추가
# =====================
with tab1:
    st.header("곡 추가하기")
    
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("곡 제목", placeholder="예: 미쳤어")
    with col2:
        artist = st.text_input("아티스트 (필수)", placeholder="예: 손담비")
    
    # 검색 버튼
    if st.button("🔍 검색", type="secondary"):
        if not title or not artist:
            st.error("곡 제목과 아티스트를 모두 입력해주세요!")
        else:
            crawl = _load_crawl_module()
            
            with st.spinner("검색 중..."):
                results = crawl.search_song(title=title, artist=artist)
                
                # 번역/로마자 필터링
                filtered = crawl.filter_original_korean(results)
                if not filtered:
                    filtered = results
                
                if filtered:
                    st.session_state['search_results'] = filtered[:10]
                    st.session_state['selected_song'] = None
                else:
                    st.warning("검색 결과가 없습니다.")
                    st.session_state['search_results'] = []
    
    # 검색 결과 표시
    if 'search_results' in st.session_state and st.session_state['search_results']:
        st.subheader("검색 결과")
        st.caption("원하는 곡을 선택하세요")
        
        for i, song in enumerate(st.session_state['search_results']):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{song['title']}** - {song['artist']}")
            with col2:
                if st.button("선택", key=f"select_{i}"):
                    st.session_state['selected_song'] = song
        
        st.divider()
    
    # 선택된 곡 처리
    if 'selected_song' in st.session_state and st.session_state['selected_song']:
        song = st.session_state['selected_song']
        st.success(f"선택됨: **{song['title']}** - {song['artist']}")
        
        if st.button("🎵 가사 가져오기 + 분류", type="primary"):
            from pipeline.crawl import get_lyrics
            from db.database import insert_bronze
            
            with st.status("처리 중...", expanded=True) as status:
                # 1. 가사 가져오기
                st.write("🔍 가사 가져오는 중...")
                lyrics = get_lyrics(song_url=song['url'])
                
                if not lyrics:
                    st.error("가사를 가져올 수 없습니다.")
                    status.update(label="실패", state="error")
                else:
                    # Bronze에 저장
                    bronze_id = insert_bronze(
                        title=song['title'],
                        artist=song['artist'],
                        raw_lyrics=lyrics,
                        source_url=song['url']
                    )
                    st.write(f"✓ 가사 저장 완료")
                    
                    # 2. 정제
                    st.write("🧹 가사 정제 중...")
                    process_bronze_to_silver(bronze_id)
                    st.write("✓ 정제 완료")
                    
                    # 3. 분류
                    st.write("🤖 LLM 분류 중...")
                    classified = process_silver_to_gold()
                    
                    if classified:
                        item = classified[0]
                        st.write(f"✓ 분류 완료")
                        status.update(label="완료!", state="complete")
                        
                        # 결과 표시
                        st.success(f"**{item['title']}** - {item['artist']}")
                        st.info(f"📂 카테고리: **{item['category']}** (확신도: {item['confidence']:.0%})")
                        st.caption(f"💬 {item['reason']}")
                        
                        # 상태 초기화
                        st.session_state['search_results'] = []
                        st.session_state['selected_song'] = None
                    else:
                        status.update(label="분류 실패", state="error")

# =====================
# 탭 2: Spotify
# =====================
with tab2:
    st.header("Spotify 플레이리스트")
    
    from pipeline.spotify import (
        is_logged_in, get_spotify_client_oauth, get_current_user,
        get_playlist_info, get_playlist_tracks, get_my_playlists,
        create_playlist, add_tracks_to_playlist, search_track
    )
    
    # 로그인 상태 확인
    logged_in = is_logged_in()
    
    if logged_in:
        try:
            user = get_current_user()
            st.success(f"✅ 로그인됨: **{user['display_name']}**")
        except:
            logged_in = False
    
    if not logged_in:
        st.warning("🔒 비공개 플레이리스트 접근 및 플레이리스트 생성을 위해 로그인하세요")
        if st.button("🔐 Spotify 로그인"):
            try:
                sp = get_spotify_client_oauth()
                user = sp.current_user()
                st.success(f"✅ 로그인 성공: {user['display_name']}")
                st.rerun()
            except Exception as e:
                st.error(f"로그인 실패: {e}")
    
    st.divider()
    
    # 플레이리스트 입력
    col1, col2 = st.columns([3, 1])
    with col1:
        playlist_url = st.text_input(
            "플레이리스트 URL",
            placeholder="https://open.spotify.com/playlist/...",
            key="spotify_url_input"
        )
    with col2:
        st.write("")  # 정렬용
        st.write("")
        load_btn = st.button("📥 불러오기")
    
    if load_btn and playlist_url:
        try:
            with st.spinner("플레이리스트 정보 가져오는 중..."):
                info = get_playlist_info(playlist_url, use_oauth=logged_in)
                tracks = get_playlist_tracks(playlist_url, use_oauth=logged_in)
            
            st.session_state['spotify_info'] = info
            st.session_state['spotify_tracks'] = tracks
            st.session_state['spotify_selected'] = set(range(len(tracks)))  # 기본 전체 선택
            st.session_state['spotify_failed'] = []
            
        except Exception as e:
            st.error(f"오류: {e}")
    
    # 플레이리스트 정보 표시
    if 'spotify_info' in st.session_state and st.session_state.get('spotify_info'):
        info = st.session_state['spotify_info']
        tracks = st.session_state['spotify_tracks']
        
        col1, col2 = st.columns([1, 3])
        with col1:
            if info.get('image'):
                st.image(info['image'], width=150)
        with col2:
            st.subheader(info['name'])
            st.caption(f"총 {info['total']}곡")
        
        st.divider()
        
        # 선택 관리 - 초기화
        if 'spotify_selected' not in st.session_state:
            st.session_state['spotify_selected'] = set(range(len(tracks)))
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("✅ 전체 선택"):
                for i in range(len(tracks)):
                    st.session_state[f"sp_track_{i}"] = True
                st.session_state['spotify_selected'] = set(range(len(tracks)))
                st.rerun()
        with col2:
            if st.button("❌ 전체 해제"):
                for i in range(len(tracks)):
                    st.session_state[f"sp_track_{i}"] = False
                st.session_state['spotify_selected'] = set()
                st.rerun()
        
        selected = st.session_state['spotify_selected']
        
        with col3:
            st.write(f"**{len(selected)}곡 선택됨**")
        
        # 곡 목록
        st.subheader("곡 목록")
        
        new_selected = set()
        for i, track in enumerate(tracks):
            # 체크박스 기본값 설정
            default_val = st.session_state.get(f"sp_track_{i}", i in selected)
            
            checked = st.checkbox(
                f"**{track['title']}** - {track['artist']}",
                value=default_val,
                key=f"sp_track_{i}"
            )
            if checked:
                new_selected.add(i)
        
        st.session_state['spotify_selected'] = new_selected
        selected = new_selected
        
        st.divider()
        
        # 가사 가져오기 + 분류
        if selected and st.button("🎵 선택한 곡 가사 가져오기 + 분류", type="primary"):
            crawl = _load_crawl_module()
            from db.database import insert_bronze
            
            progress = st.progress(0)
            status_text = st.empty()
            
            success_list = []
            fail_list = []
            
            selected_list = sorted(list(selected))
            
            for idx, i in enumerate(selected_list):
                track = tracks[i]
                progress.progress((idx + 1) / len(selected_list))
                status_text.write(f"처리 중: {track['title']} - {track['artist']}")
                
                try:
                    # 아티스트명 정리 (쉼표 → 띄어쓰기)
                    import re
                    clean_artist = re.sub(r"\s*,\s*", " ", track["artist"]).strip()

                    if not clean_artist:
                        fail_list.append({
                            "track": track,
                            "reason": "아티스트 정보가 없어 artist-first 검색 불가"
                        })
                        continue

                    # artist-first exact 검색만 사용
                    results = crawl.search_song(
                        title=track["title"],
                        artist=clean_artist,
                        limit=20,
                    )
                    filtered = crawl.filter_original_korean(results)
                    if not filtered:
                        filtered = results
                    
                    if not filtered:
                        fail_list.append({
                            "track": track,
                            "reason": "아티스트 기준 제목 exact 매칭 실패"
                        })
                        continue
                    
                    # 3. 가사 가져오기
                    best = filtered[0]
                    lyrics = crawl.get_lyrics(song_url=best['url'])
                    
                    if not lyrics:
                        fail_list.append({
                            "track": track,
                            "reason": "가사를 가져올 수 없음"
                        })
                        continue
                    
                    # 4. Bronze 저장
                    bronze_id = insert_bronze(
                        title=best['title'],
                        artist=best['artist'],
                        raw_lyrics=lyrics,
                        source_url=best['url']
                    )
                    
                    # 5. 정제
                    process_bronze_to_silver(bronze_id)
                    
                    success_list.append({
                        "track": track,
                        "genius_title": best['title'],
                        "genius_artist": best['artist'],
                        "used_korean_search": False
                    })
                    
                except Exception as e:
                    fail_list.append({
                        "track": track,
                        "reason": str(e)
                    })
                    continue
            
            # 5. 전체 분류
            status_text.write("🤖 LLM 분류 중...")
            classified = process_silver_to_gold()
            
            progress.progress(1.0)
            status_text.empty()
            
            # 결과 표시
            st.success(f"✅ 완료! 성공: {len(success_list)}곡, 실패: {len(fail_list)}곡")
            
            # 분류 결과
            if classified:
                st.subheader("📊 분류 결과")
                
                # 카테고리별로 그룹핑
                by_category = {}
                for item in classified:
                    cat = item['category']
                    if cat not in by_category:
                        by_category[cat] = []
                    by_category[cat].append(item)
                
                for cat, items in by_category.items():
                    with st.expander(f"**{cat}** ({len(items)}곡)", expanded=True):
                        for item in items:
                            st.write(f"• {item['title']} - {item['artist']}")
                
                st.session_state['classified_by_category'] = by_category
            
            # 실패 목록
            if fail_list:
                with st.expander(f"❌ 실패한 곡 ({len(fail_list)}곡)", expanded=False):
                    for fail in fail_list:
                        st.write(f"• **{fail['track']['title']}** - {fail['track']['artist']}")
                        st.caption(f"  ↳ {fail['reason']}")
        
        # Spotify 플레이리스트 생성
        st.divider()
        st.subheader("🎧 Spotify 플레이리스트 생성")
        
        if not logged_in:
            st.info("플레이리스트 생성을 위해 위에서 Spotify 로그인을 해주세요.")
        elif 'classified_by_category' in st.session_state:
            by_category = st.session_state['classified_by_category']
            
            selected_category = st.selectbox(
                "카테고리 선택",
                list(by_category.keys())
            )
            
            playlist_name = st.text_input(
                "플레이리스트 이름",
                value=f"Moodlist - {selected_category}"
            )
            
            if st.button("🎵 Spotify에 플레이리스트 생성"):
                items = by_category[selected_category]
                
                with st.spinner("플레이리스트 생성 중..."):
                    try:
                        # 플레이리스트 생성
                        result = create_playlist(
                            name=playlist_name,
                            description=f"Moodlist에서 자동 생성된 {selected_category} 플레이리스트"
                        )
                        
                        # 곡 검색해서 추가
                        track_uris = []
                        not_found = []
                        
                        for item in items:
                            found = search_track(item['title'], item['artist'])
                            if found:
                                track_uris.append(found['uri'])
                            else:
                                not_found.append(item)
                        
                        if track_uris:
                            add_tracks_to_playlist(result['id'], track_uris)
                        
                        st.success(f"✅ 플레이리스트 생성 완료!")
                        st.markdown(f"[🔗 Spotify에서 열기]({result['url']})")
                        
                        if not_found:
                            st.warning(f"⚠️ {len(not_found)}곡은 Spotify에서 찾지 못함")
                            for item in not_found:
                                st.caption(f"  • {item['title']} - {item['artist']}")
                    
                    except Exception as e:
                        st.error(f"오류: {e}")
        else:
            st.info("먼저 곡을 분류해주세요.")

# =====================
# 탭 3: 분류 결과
# =====================
with tab3:
    st.header("분류된 곡 목록")
    
    # 카테고리 필터
    all_cats = get_all_categories()
    
    if not all_cats:
        st.info("아직 분류된 곡이 없습니다. '곡 추가' 탭에서 곡을 추가해보세요!")
    else:
        selected_cat = st.selectbox(
            "카테고리 선택",
            ["전체"] + all_cats
        )
        
        # 곡 목록 가져오기
        if selected_cat == "전체":
            songs = get_songs_by_category()
        else:
            songs = get_songs_by_category(selected_cat)
        
        if songs:
            for song in songs:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    col1.write(f"**{song['title']}**")
                    col2.write(song['artist'])
                    col3.write(f"`{song['category']}`")
                st.divider()
        else:
            st.info("해당 카테고리에 곡이 없습니다.")

# =====================
# 탭 4: 파이프라인
# =====================
with tab4:
    st.header("파이프라인 관리")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Bronze → Silver")
        st.caption("미정제 가사 처리")
        if st.button("정제 실행"):
            with st.spinner("정제 중..."):
                result = process_bronze_to_silver()
                if result:
                    st.success(f"{len(result)}곡 정제 완료!")
                else:
                    st.info("정제할 데이터가 없습니다.")
    
    with col2:
        st.subheader("Silver → Gold")
        st.caption("미분류 가사 처리")
        if st.button("분류 실행"):
            with st.spinner("분류 중..."):
                result = process_silver_to_gold()
                if result:
                    st.success(f"{len(result)}곡 분류 완료!")
                else:
                    st.info("분류할 데이터가 없습니다.")
    
    with col3:
        st.subheader("전체 파이프라인")
        st.caption("정제 + 분류 한번에")
        if st.button("전체 실행"):
            with st.spinner("처리 중..."):
                clean_result = process_bronze_to_silver()
                classify_result = process_silver_to_gold()
                st.success(f"정제: {len(clean_result) if clean_result else 0}곡, 분류: {len(classify_result) if classify_result else 0}곡")
    
    st.divider()
    
    # 데이터 미리보기
    st.subheader("📂 데이터 미리보기")
    
    preview_tab = st.radio("테이블 선택", ["Bronze", "Silver", "Gold"], horizontal=True)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    if preview_tab == "Bronze":
        cursor.execute("SELECT id, title, artist, substr(raw_lyrics, 1, 100) as lyrics_preview, crawled_at FROM songs_bronze ORDER BY id DESC LIMIT 10")
    elif preview_tab == "Silver":
        cursor.execute("""
            SELECT s.id, b.title, b.artist, substr(s.clean_lyrics, 1, 100) as lyrics_preview, s.processed_at 
            FROM songs_silver s 
            JOIN songs_bronze b ON s.bronze_id = b.id 
            ORDER BY s.id DESC LIMIT 10
        """)
    else:
        cursor.execute("""
            SELECT g.id, b.title, b.artist, g.category, g.confidence, g.classified_at 
            FROM songs_gold g 
            JOIN songs_silver s ON g.silver_id = s.id 
            JOIN songs_bronze b ON s.bronze_id = b.id 
            ORDER BY g.id DESC LIMIT 10
        """)
    
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()
    
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows, columns=columns)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("데이터가 없습니다.")
