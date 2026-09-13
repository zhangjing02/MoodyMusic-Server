import os
import sys
import json
import sqlite3
import subprocess
import boto3
from botocore.config import Config

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))
import r2_safety_guard

DB_PATH = os.path.join(BASE_DIR, "database", "catalog_sync.db")
CONFIG_PATH = os.path.join(BASE_DIR, "r2_config.json")
OPTIMIZED_DIR = os.path.join(BASE_DIR, "downloads_optimized")
LOG_PATH = os.path.join(BASE_DIR, "reports", "MULTI_BUCKET_EXECUTION_LOG.md")
os.makedirs(OPTIMIZED_DIR, exist_ok=True)

# 9.50 GB Hard Circuit Breaker (95% of 10GB free tier)
MAX_SAFE_BYTES = int(9.50 * 1024 * 1024 * 1024)

def load_r2_clients():
    r2_safety_guard.assert_write_allowed()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    
    clients = {}
    for key, b_info in cfg["buckets"].items():
        s3 = boto3.client(
            service_name="s3",
            endpoint_url=b_info["endpoint_url"],
            aws_access_key_id=b_info["access_key_id"],
            aws_secret_access_key=b_info["secret_access_key"],
            region_name="auto",
            config=Config(s3={"addressing_style": "path"}, connect_timeout=15, read_timeout=30, retries={'max_attempts': 3})
        )
        clients[key] = {
            "s3": s3,
            "info": b_info
        }
    return clients

def get_bucket_live_size(s3_client, bucket_name: str) -> tuple[int, int]:
    """Query R2 bucket live physical size and object count"""
    total_bytes = 0
    total_count = 0
    continuation_token = None
    
    while True:
        kwargs = {"Bucket": bucket_name, "MaxKeys": 1000}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
            
        resp = s3_client.list_objects_v2(**kwargs)
        if "Contents" in resp:
            for obj in resp["Contents"]:
                total_bytes += obj["Size"]
                total_count += 1
                
        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break
            
    return total_bytes, total_count

def compress_to_160k_cbr(src_path: str, dst_path: str) -> bool:
    """Use FFmpeg to transcode to 160kbps CBR MP3, 44.1kHz, with Xing header and EBU R128 loudness normalization"""
    cmd = [
        "ffmpeg", "-y", "-i", src_path,
        "-vn",
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "libmp3lame",
        "-b:a", "160k",
        "-ar", "44100",
        "-write_xing", "1",
        dst_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0 and os.path.exists(dst_path) and os.path.getsize(dst_path) > 1000

def verify_audio_qa(src_path: str, dst_path: str) -> tuple[bool, str]:
    """Use FFprobe to verify sample rate, bitrate, and duration"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=sample_rate,bit_rate,duration:format=duration,bit_rate",
            "-of", "json", dst_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            return False, f"FFprobe failed: {res.stderr}"
        
        info = json.loads(res.stdout)
        streams = info.get("streams", [])
        if not streams:
            return False, "No audio stream found"
            
        stream = streams[0]
        sample_rate = int(stream.get("sample_rate", 0))
        bit_rate = int(stream.get("bit_rate", 0)) if stream.get("bit_rate") else int(info.get("format", {}).get("bit_rate", 0))
        duration = float(stream.get("duration", 0)) if stream.get("duration") else float(info.get("format", {}).get("duration", 0))
        
        if sample_rate != 44100:
            return False, f"Invalid sample_rate: {sample_rate} (expected 44100)"
            
        bit_rate_kbps = bit_rate // 1000
        if not (150 <= bit_rate_kbps <= 170):
            return False, f"Unexpected bitrate: {bit_rate_kbps} kbps"
            
        src_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", src_path]
        src_res = subprocess.run(src_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if src_res.returncode == 0:
            src_info = json.loads(src_res.stdout)
            src_duration = float(src_info.get("format", {}).get("duration", 0))
            if abs(src_duration - duration) > 2.0:
                return False, f"Duration mismatch: src={src_duration:.1f}s, dst={duration:.1f}s"
                
        return True, f"QA PASS: {sample_rate}Hz, {bit_rate_kbps}kbps, {duration:.1f}s"
    except Exception as e:
        return False, str(e)

def log_execution_event(event_text: str):
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(event_text + "\n")

def process_and_upload_batch(target_bucket_key: str, song_ids: list[int]):
    clients = load_r2_clients()
    if target_bucket_key not in clients:
        raise ValueError(f"Unknown bucket key: {target_bucket_key}")
        
    s3_info = clients[target_bucket_key]["info"]
    s3 = clients[target_bucket_key]["s3"]
    bucket_name = s3_info["name"]
    public_domain = s3_info.get("public_domain", "")
    
    print("=" * 80)
    print(f"🔍 [容量核验] 正在实时查询目标存储桶: {bucket_name} ...")
    current_bytes, current_count = get_bucket_live_size(s3, bucket_name)
    current_gb = current_bytes / (1024 ** 3)
    usage_pct = (current_bytes / (10 * 1024 ** 3)) * 100
    print(f"📊 当前物理占用: {current_gb:.4f} GB / 10.00 GB ({usage_pct:.2f}%) | 对象总数: {current_count}")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ",".join("?" for _ in song_ids)
    c.execute(f"""
        SELECT song_id, artist_name, album_title, song_title, local_mp3, local_lrc, file_size
        FROM tracks_sync_state
        WHERE song_id IN ({placeholders})
    """, song_ids)
    tracks = c.fetchall()
    conn.close()
    
    estimated_batch_bytes = len(tracks) * int(5.5 * 1024 * 1024)
    expected_final_bytes = current_bytes + estimated_batch_bytes
    print(f"📦 本批待处理曲目: {len(tracks)} 首 | 预估新增: {estimated_batch_bytes / (1024**2):.1f} MB")
    print(f"🎯 预计最终占用: {expected_final_bytes / (1024**3):.4f} GB")
    
    # 🚨 95% Safety Circuit Breaker Check
    if expected_final_bytes >= MAX_SAFE_BYTES:
        alert_msg = f"🚨 [熔断报警] 目标桶 {bucket_name} 预计占用 {expected_final_bytes/(1024**3):.4f} GB，突破 95% (9.50 GB) 安全红线！立即终止！"
        print(alert_msg)
        log_execution_event(f"- ⚠️ **{alert_msg}**")
        return False
        
    print(f"✅ [容量校验通过] 处于安全容量区间内 (安全上限 9.50 GB)，开始转码与核验...")
    print("=" * 80)
    
    success_count = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    for idx, r in enumerate(tracks, 1):
        song_id, artist, album, title, local_mp3, local_lrc, orig_size = r
        if not local_mp3 or not os.path.exists(local_mp3):
            print(f"⚠️ [{idx}/{len(tracks)}] 本地音频缺失: {title} ({local_mp3})")
            continue
            
        opt_mp3 = os.path.join(OPTIMIZED_DIR, f"s_{song_id}.mp3")
        
        # 1. 压缩转码
        if not compress_to_160k_cbr(local_mp3, opt_mp3):
            print(f"❌ [{idx}/{len(tracks)}] FFmpeg 转码失败: 《{title}》 - {artist}")
            continue
            
        # 2. 抽检质检
        passed, qa_msg = verify_audio_qa(local_mp3, opt_mp3)
        if not passed:
            print(f"⚠️ [{idx}/{len(tracks)}] 质检不合规: 《{title}》 | {qa_msg}")
            continue
            
        opt_size = os.path.getsize(opt_mp3)
        r2_key = f"music/{artist}/{album}/s_{song_id}.mp3"
        r2_lrc_key = f"music/{artist}/{album}/s_{song_id}.lrc"
        
        # 3. 路径格式
        if target_bucket_key == "account_01":
            final_file_path = r2_key
            final_lrc_path = r2_lrc_key
            status_tag = "R2_UPLOADED"
        elif target_bucket_key == "account_02":
            final_file_path = f"{public_domain}/{r2_key}"
            final_lrc_path = f"{public_domain}/{r2_lrc_key}"
            status_tag = "R2_UPLOADED_BUCKET2"
        elif target_bucket_key == "account_03":
            final_file_path = f"{public_domain}/{r2_key}"
            final_lrc_path = f"{public_domain}/{r2_lrc_key}"
            status_tag = "R2_UPLOADED_BUCKET3"
        else:
            final_file_path = f"{public_domain}/{r2_key}"
            final_lrc_path = f"{public_domain}/{r2_lrc_key}"
            status_tag = f"R2_UPLOADED_{target_bucket_key.upper()}"
            
        # 4. 上传 R2
        try:
            with open(opt_mp3, "rb") as f_mp3:
                s3.put_object(
                    Bucket=bucket_name,
                    Key=r2_key,
                    Body=f_mp3,
                    ContentType="audio/mpeg"
                )
                
            if local_lrc and os.path.exists(local_lrc):
                with open(local_lrc, "rb") as f_lrc:
                    s3.put_object(
                        Bucket=bucket_name,
                        Key=r2_lrc_key,
                        Body=f_lrc,
                        ContentType="text/plain; charset=utf-8"
                    )
            
            # 5. 更新 DB
            c.execute("""
                UPDATE tracks_sync_state
                SET status = ?,
                    is_compressed = 1,
                    bitrate_kbps = 160,
                    file_size = ?,
                    r2_mp3_key = ?,
                    r2_lrc_key = ?,
                    qa_status = 'VERIFIED_160K_CBR',
                    compressed_at = CURRENT_TIMESTAMP,
                    uploaded_at = CURRENT_TIMESTAMP
                WHERE song_id = ?
            """, (status_tag, opt_size, final_file_path, final_lrc_path, song_id))
            conn.commit()
            
            success_count += 1
            savings_pct = (1 - (opt_size / orig_size)) * 100 if orig_size else 0
            print(f"✅ [{idx}/{len(tracks)}] 上传成功: 《{title}》 - {artist} ({album}) | {opt_size/(1024**2):.2f}MB (瘦身 {savings_pct:.1f}%) -> {bucket_name}")
        except Exception as upload_err:
            print(f"❌ [{idx}/{len(tracks)}] 上传 R2 失败: 《{title}》 | {upload_err}")
            
    conn.close()
    print("=" * 80)
    print(f"🎉 批次处理完毕: 成功 {success_count}/{len(tracks)} 首入库！")
    return success_count
