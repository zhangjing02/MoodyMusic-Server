-- 1. 确保 user_profiles 拥有展示音信页面所需字段与密码哈希
ALTER TABLE user_profiles ADD COLUMN nickname TEXT DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN bio TEXT DEFAULT '在音信里听风的声音';
ALTER TABLE user_profiles ADD COLUMN password_hash TEXT DEFAULT '';
ALTER TABLE user_profiles ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP;

-- 1.1 邮箱验证码表
CREATE TABLE IF NOT EXISTS email_verification_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL,
  code TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'login',
  expires_at INTEGER NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  used_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_email_verification_codes_lookup 
ON email_verification_codes (email, code, used_at);

-- 2. 用户收藏歌曲表
CREATE TABLE IF NOT EXISTS user_favorite_songs (
  user_id INTEGER NOT NULL,
  song_id INTEGER NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, song_id),
  FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_fav_songs_user ON user_favorite_songs(user_id);

-- 3. 用户收藏专辑表 (驱动音信页 FavoriteAlbumsSection)
CREATE TABLE IF NOT EXISTS user_favorite_albums (
  user_id INTEGER NOT NULL,
  album_id TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, album_id),
  FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_fav_albums_user ON user_favorite_albums(user_id);

-- 4. 用户关注歌手表 (驱动音信页 FollowedArtistsSection)
CREATE TABLE IF NOT EXISTS user_followed_artists (
  user_id INTEGER NOT NULL,
  artist_id TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, artist_id),
  FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_followed_artists_user ON user_followed_artists(user_id);

-- 5. 用户最近播放历史表 (预留扩展)
CREATE TABLE IF NOT EXISTS user_play_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  song_id INTEGER NOT NULL,
  played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_play_history_user ON user_play_history(user_id, played_at DESC);
