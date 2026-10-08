import json, requests, subprocess

with open("reports/SUPERSTARS_AUDIO_REMEDIATION_LOG.json") as f:
    audio_log = json.load(f)
with open("reports/SUPERSTARS_LYRICS_REMEDIATION_LOG.json") as f:
    lyric_log = json.load(f)

success_audios = audio_log["success_items"]
success_lyrics = lyric_log["success_uploads"]

print("==================================================")
print(" 华语核心五大巨星全盘治理后深度验收")
print("==================================================")
print(f"成功置换音频母带: {len(success_audios)} 首")
print(f"成功清洗置换歌词: {len(success_lyrics)} 首\n")

print(">>> 1. 抽验重点核心关注曲目 (音频时长 + 歌词)...")
key_check_titles = ["晴天", "退后", "學不會", "可惜没如果", "傷信", "沒有人的方向", "稻香", "告白气球", "梦游"]

for tit in key_check_titles:
    # 找音频
    matched_audio = next((a for a in success_audios if a["title"] == tit), None)
    # 找歌词
    matched_lyric = next((l for l in success_lyrics if l["title"] == tit), None)
    
    print(f"\n【曲目: 《{tit}》】")
    if matched_audio:
        url = matched_audio["path"]
        r = requests.head(url, timeout=5)
        print(f"  音频 CDN: HTTP {r.status_code} | 时长: {matched_audio['duration']:.1f}s | 歌手: {matched_audio['artist']}")
        print(f"  URL: {url}")
    if matched_lyric:
        lrc_url = matched_lyric["lrc_path"]
        r_lrc = requests.get(lrc_url, timeout=5)
        print(f"  歌词 CDN: HTTP {r_lrc.status_code} | 字符数: {len(r_lrc.text)} | 行数: {len(r_lrc.text.splitlines())}")
        # 打印前 2 行歌词文本
        lines = [l for l in r_lrc.text.splitlines() if not l.startswith("[id:") and not l.startswith("[ar:")][:2]
        print(f"  歌词试看: {lines}")

print("\n>>> 2. 批量 CDN HTTP 状态全量扫描...")
audio_ok = 0
for a in success_audios:
    try:
        r = requests.head(a["path"], timeout=4)
        if r.status_code in [200, 206]: audio_ok += 1
    except: pass

lyric_ok = 0
for l in success_lyrics:
    try:
        r = requests.head(l["lrc_path"], timeout=4)
        if r.status_code == 200: lyric_ok += 1
    except: pass

print(f"音频母带 CDN HTTP 200/206 通过率: {audio_ok}/{len(success_audios)} ({audio_ok/len(success_audios)*100:.1f}%)")
print(f"歌词文件 CDN HTTP 200 通过率: {lyric_ok}/{len(success_lyrics)} ({lyric_ok/len(success_lyrics)*100:.1f}%)")

