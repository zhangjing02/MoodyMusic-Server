import os
import sys
import json
import time
import requests
import sqlite3
import subprocess
import difflib
import re
import zhconv

sys.stdout.reconfigure(encoding='utf-8')

GROQ_KEY = os.environ.get('GROQ_API_KEY')
GROQ_API_URL = 'https://api.groq.com/openai/v1/audio/transcriptions'
TMP_DIR = r'G:\music-backup\tmp'
os.makedirs(TMP_DIR, exist_ok=True)

STAGE1_FILE = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\stage1_audit_result.json'
with open(STAGE1_FILE, 'r', encoding='utf-8') as f:
    stage1_data = json.load(f)

identical_groups = stage1_data.get('identical_hash_groups', [])
print(f"Loaded {len(identical_groups)} identical hash groups.")

def normalize_text(text):
    if not text:
        return ""
    # Convert traditional to simplified
    try:
        s = zhconv.convert(text, 'zh-cn')
    except Exception:
        s = text
    # Keep only Chinese characters and alphanumeric
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', s.lower())
    # Strip common hallucination patterns
    hallucinations = ['作词李宗盛', '作曲李宗盛', '词曲李宗盛', '作词', '作曲', '编曲', '演唱', '字幕提供', '李宗盛']
    for h in hallucinations:
        cleaned = cleaned.replace(h, '')
    return cleaned

def clean_title(t):
    return t.split('(')[0].split('（')[0].split('[')[0].strip().lower()

def is_same_song_variants(songs):
    base_titles = [clean_title(s['title']) for s in songs]
    return len(set(base_titles)) == 1

def call_whisper_api(clip_path):
    try:
        with open(clip_path, 'rb') as f:
            resp = requests.post(
                GROQ_API_URL,
                headers={'Authorization': f'Bearer {GROQ_KEY}'},
                files={'file': ('clip.mp3', f, 'audio/mpeg')},
                data={'model': 'whisper-large-v3', 'temperature': '0.0'},
                timeout=25
            )
        if resp.status_code == 200:
            txt = resp.json().get('text', '').strip()
            # If transcript is empty or musical notes only
            txt_clean = txt.replace('🎵', '').replace('♪', '').strip()
            return txt_clean
        else:
            print(f"  [Groq API Status {resp.status_code}]: {resp.text}", flush=True)
            return None
    except Exception as e:
        print(f"  [Whisper API Error]: {e}", flush=True)
        return None

def transcribe_audio(url):
    tmp_src = os.path.join(TMP_DIR, "audit_src.mp3")
    tmp_clip = os.path.join(TMP_DIR, "audit_clip.mp3")
    
    if os.path.exists(tmp_src): os.remove(tmp_src)
    if os.path.exists(tmp_clip): os.remove(tmp_clip)
    
    try:
        # Download first 2.5MB
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-2500000'}, timeout=12)
        if r.status_code not in [200, 206]:
            return None
        with open(tmp_src, 'wb') as f:
            f.write(r.content)
            
        # Try Window 1: ss=35, t=25 (verse)
        cmd = ['ffmpeg', '-y', '-ss', '35', '-t', '25', '-i', tmp_src, '-ac', '1', '-ar', '16000', '-b:a', '64k', tmp_clip]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        
        t1 = call_whisper_api(tmp_clip)
        if t1 and len(t1) >= 6:
            if os.path.exists(tmp_src): os.remove(tmp_src)
            if os.path.exists(tmp_clip): os.remove(tmp_clip)
            return t1
            
        # If Window 1 is instrumental, try Window 2: ss=65, t=25 (chorus)
        if os.path.exists(tmp_clip): os.remove(tmp_clip)
        cmd2 = ['ffmpeg', '-y', '-ss', '65', '-t', '25', '-i', tmp_src, '-ac', '1', '-ar', '16000', '-b:a', '64k', tmp_clip]
        subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        
        t2 = call_whisper_api(tmp_clip)
        if os.path.exists(tmp_src): os.remove(tmp_src)
        if os.path.exists(tmp_clip): os.remove(tmp_clip)
        return t2 or t1
        
    except Exception as e:
        if os.path.exists(tmp_src): os.remove(tmp_src)
        if os.path.exists(tmp_clip): os.remove(tmp_clip)
        return None

def fetch_lrc_text(lrc_url):
    if not lrc_url or not lrc_url.startswith('http'):
        return ""
    try:
        r = requests.get(lrc_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
        if r.status_code == 200:
            lines = []
            for line in r.text.splitlines():
                if ']' in line:
                    txt = line.split(']', 1)[1].strip()
                    if txt and not any(tag in txt for tag in ['作词', '作曲', '编曲', '制作人', '原唱', '词:', '曲:']):
                        lines.append(txt)
            return " ".join(lines)
    except Exception:
        pass
    return ""

def score_match(transcript, lrc_text):
    t_clean = normalize_text(transcript)
    l_clean = normalize_text(lrc_text)
    
    if not t_clean or not l_clean or len(t_clean) < 4:
        return 0.0
        
    # 1. Bigram overlap
    t_bi = set(t_clean[i:i+2] for i in range(len(t_clean)-1))
    l_bi = set(l_clean[i:i+2] for i in range(len(l_clean)-1))
    bigram_score = len(t_bi & l_bi) / max(1, len(t_bi))
    
    # 2. SequenceMatcher best chunk
    # Find longest matching block
    sm = difflib.SequenceMatcher(None, t_clean, l_clean)
    match = sm.find_longest_match(0, len(t_clean), 0, len(l_clean))
    lcs_score = match.size / len(t_clean)
    
    return max(bigram_score, lcs_score)

audit_results = []
cross_song_mismatches = []
variant_duplicates = []

print("=" * 80)
print(f"Starting Stage 2 Double-Check (v2 Enhanced) on {len(identical_groups)} Groups...")
print("=" * 80, flush=True)

for idx, g in enumerate(identical_groups, 1):
    album_id, album_title, artist_name, file_size = g['group_key']
    songs = g['songs']
    is_variant = is_same_song_variants(songs)
    
    cat_label = "VARIANT_DUPLICATE" if is_variant else "CROSS_SONG_MISMATCH"
    print(f"\n[{idx}/{len(identical_groups)}] [{cat_label}] {artist_name} - 《{album_title}》 (ID: {album_id})")
    print(f"   Tracks: {' | '.join([s['title'] for s in songs])}", flush=True)
    
    first_url = songs[0]['file_path']
    transcript = transcribe_audio(first_url)
    clean_t = normalize_text(transcript)
    print(f"   🗣️ [Whisper]: {transcript or '[Instrumental/None]'}", flush=True)
    
    best_match_song = None
    best_score = 0.0
    
    for s in songs:
        lrc = fetch_lrc_text(s.get('lrc_path'))
        score = score_match(transcript, lrc)
        s['match_score'] = round(score, 3)
        if score > best_score:
            best_score = score
            best_match_song = s
            
    verdict_info = {
        'group_index': idx,
        'album_id': album_id,
        'album_title': album_title,
        'artist_name': artist_name,
        'file_size': file_size,
        'category': cat_label,
        'transcript': transcript,
        'songs': []
    }
    
    if best_score >= 0.28 and best_match_song:
        print(f"   🎯 [GENUINE OWNER]: 《{best_match_song['title']}》 (Score: {best_score}) -> KEEP!", flush=True)
        for s in songs:
            if s['id'] == best_match_song['id']:
                status = "GENUINE_KEEP"
            else:
                status = "IMPOSTOR_TO_FIX"
                print(f"   🚨 [IMPOSTOR TO FIX]: 《{s['title']}》 (ID: {s['id']}) was wrongly populated with 《{best_match_song['title']}》!", flush=True)
            verdict_info['songs'].append({
                'id': s['id'],
                'title': s['title'],
                'file_path': s['file_path'],
                'status': status,
                'match_score': s.get('match_score', 0.0)
            })
    else:
        status_label = "ALIEN_POLLUTION_TO_FIX" if (transcript and len(clean_t) >= 8) else "UNCERTAIN_REVIEW"
        print(f"   ⚠️ [NO CLEAN MATCH]: Best score {best_score}. Verdict: {status_label}", flush=True)
        for s in songs:
            verdict_info['songs'].append({
                'id': s['id'],
                'title': s['title'],
                'file_path': s['file_path'],
                'status': status_label,
                'match_score': s.get('match_score', 0.0)
            })
            
    audit_results.append(verdict_info)
    if is_variant:
        variant_duplicates.append(verdict_info)
    else:
        cross_song_mismatches.append(verdict_info)
        
    time.sleep(1.8)

out_report = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\stage2_double_check_report.json'
with open(out_report, 'w', encoding='utf-8') as f:
    json.dump({
        'total_groups': len(identical_groups),
        'cross_song_mismatches': cross_song_mismatches,
        'variant_duplicates': variant_duplicates
    }, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 80)
print("STAGE 2 AUDIT V2 COMPLETE!")
print(f"Total Groups Audited: {len(identical_groups)}")
print(f"  🚨 Cross-Song Mismatches: {len(cross_song_mismatches)} groups")
print(f"  ⚠️ Variant Duplicates: {len(variant_duplicates)} groups")
print(f"Report saved to: {out_report}")
print("=" * 80, flush=True)
