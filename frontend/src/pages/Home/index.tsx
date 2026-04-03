import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { addSong, getSongs } from "../../api/songs";
import type { Song } from "../../types";
import FadeInSection from "../../components/common/FadeInSection";
import AlbumArt from "../../components/common/AlbumArt";
import CategoryBadge from "../../components/common/CategoryBadge";
import SearchBar from "./SearchBar";
import styles from "./Home.module.css";

export default function Home() {
  const navigate = useNavigate();
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [recentSongs, setRecentSongs] = useState<Song[]>([]);
  const [artIndex, setArtIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getSongs()
      .then((songs) => setRecentSongs(songs.slice(0, 10)))
      .catch(() => {});
  }, []);

  // 5초마다 앨범아트 순환
  const songsWithArt = recentSongs.filter((s) => s.album_art_url);
  useEffect(() => {
    if (songsWithArt.length <= 1) return;
    timerRef.current = setInterval(() => {
      setArtIndex((prev) => (prev + 1) % songsWithArt.length);
    }, 5000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [songsWithArt.length]);

  const handleSearch = async (
    title: string,
    artist: string,
    spotifyId?: string,
    imageUrl?: string,
  ) => {
    setIsSearching(true);
    setSearchError(null);
    try {
      const result = await addSong({
        title,
        artist,
        ...(spotifyId ? { spotify_id: spotifyId } : {}),
        ...(imageUrl ? { image_url: imageUrl } : {}),
      });
      // 분류 완료 → 곡 상세 페이지로 이동
      navigate(`/song/${result.spotify_id}`);
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : "곡을 찾을 수 없습니다");
    } finally {
      setIsSearching(false);
    }
  };

  const currentArtSong = songsWithArt[artIndex] ?? null;

  return (
    <div className={styles.layout}>
      {/* ── 좌측: iPod + 검색 ──────────────────────────────── */}
      <div className={styles.left}>
        <FadeInSection>
          <div className={styles.hero}>
            {/* iPod */}
            <div className={styles.ipodBody}>
              <div className={styles.screen}>
                <div className={styles.screenTop}>
                  <span className={styles.screenBrand}>MOODLIST</span>
                  {currentArtSong && (
                    <span className={styles.screenNowPlaying}>NOW PLAYING</span>
                  )}
                </div>

                <div className={styles.screenContent}>
                  <AnimatePresence mode="wait">
                    {currentArtSong ? (
                      <motion.div
                        key={currentArtSong.spotify_id}
                        className={styles.screenArtWrap}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.6 }}
                      >
                        <img
                          src={currentArtSong.album_art_url!}
                          alt={currentArtSong.title}
                          className={styles.screenArt}
                        />
                        <p className={styles.screenTitle}>
                          {currentArtSong.title}
                        </p>
                        <p className={styles.screenArtist}>
                          {currentArtSong.artist}
                        </p>
                      </motion.div>
                    ) : (
                      <motion.div
                        key="idle"
                        className={styles.screenIdle}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <div className={styles.screenIdleIcon}>♪</div>
                        <p className={styles.screenIdleText}>
                          곡을 검색해 보세요
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {/* Click Wheel */}
              <div className={styles.clickWheel}>
                <span className={`${styles.wheelLabel} ${styles.wheelTop}`}>
                  MENU
                </span>
                <span className={`${styles.wheelLabel} ${styles.wheelLeft}`}>
                  ◀◀
                </span>
                <span className={`${styles.wheelLabel} ${styles.wheelRight}`}>
                  ▶▶
                </span>
                <span className={`${styles.wheelLabel} ${styles.wheelBottom}`}>
                  ▶❚❚
                </span>
                <div className={styles.wheelCenter} />
              </div>
            </div>

            <h1 className={styles.heroTitle}>
              지금 내 감정과 상황에
              <br />딱 맞는 노래를 찾는다면
            </h1>
            <p className={styles.heroSub}>
              곡명과 아티스트를 입력하면
              <br />
              가사를 분석해 감정과 상황을 분류합니다
            </p>
          </div>
        </FadeInSection>

        <FadeInSection delay={0.1}>
          <div className={styles.searchSection}>
            <SearchBar onSearch={handleSearch} isLoading={isSearching} />
          </div>
        </FadeInSection>

        {searchError && (
          <FadeInSection>
            <div className={styles.error}>{searchError}</div>
          </FadeInSection>
        )}
      </div>

      {/* ── 우측: 최근 분류된 곡 ─────────────────────────────── */}
      <div className={styles.right}>
        <FadeInSection delay={0.15}>
          <div className={styles.recentCard}>
            <div className={styles.recentHeader}>
              <h2 className={styles.sectionTitle}>최근 분류된 곡</h2>
            </div>

            <div className={styles.songList}>
              {recentSongs.map((song, i) => (
                <button
                  key={song.spotify_id}
                  className={styles.songRow}
                  onClick={() => navigate(`/song/${song.spotify_id}`)}
                >
                  <span className={styles.songNum}>{i + 1}</span>
                  <AlbumArt
                    artist={song.artist}
                    category={song.category}
                    imageUrl={song.album_art_url}
                    shape="rounded"
                    size={40}
                  />
                  <div className={styles.songInfo}>
                    <div className={styles.songTitleRow}>
                      <span className={styles.songTitle}>{song.title}</span>
                      {song.category && (
                        <CategoryBadge category={song.category} size="sm" />
                      )}
                    </div>
                    <span className={styles.songArtist}>{song.artist}</span>
                    {song.narrative && (
                      <span className={styles.songNarrative}>
                        {song.narrative}
                      </span>
                    )}
                  </div>
                </button>
              ))}

              {recentSongs.length === 0 && (
                <p className={styles.empty}>아직 분류된 곡이 없어요</p>
              )}
            </div>
          </div>
        </FadeInSection>
      </div>
    </div>
  );
}
