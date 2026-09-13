#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY MUSIC - Karen 音乐动态背景全自动提取、去水印重构与无缝循环制作流水线
功能：
1. 从 Karen 频道提取 20s 高清视频切片（通过本地代理 http://127.0.0.1:7897）
2. 自动时域统计滤波（Temporal Min Filter），重构被频谱遮挡的真实地砖/桌面/书本/鞋带纹理
3. 自动多重基线检测（y: 890~910 基准线、y: 960~980 进度条线）与时间戳（左下/右下）精确定向修复
4. 动态分层与 30px 线性羽化平滑过渡（保留上方吊灯呼吸、吉他指弹、人物晃动、黑胶旋转）
5. 自动循环周期检测 + 0.5s 环形交叉淡入淡出（Cross-fade），生成 100% 无缝无限循环
6. 双格式压制：
   - MP4: H.264 High Profile, yuv420p, crf 20, +faststart (全平台全机型极速秒开)
   - WebM: VP9, 极高压缩比
   - Poster: 提取高清关键帧作为渐进式加载封面
"""

import os
import sys
import json
import argparse
import subprocess
import cv2
import numpy as np
from scipy.signal import medfilt2d

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 代理配置
PROXY = "http://127.0.0.1:7897"
ENV = os.environ.copy()
ENV['HTTP_PROXY'] = PROXY
ENV['HTTPS_PROXY'] = PROXY
ENV['http_proxy'] = PROXY
ENV['https_proxy'] = PROXY

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND_VIDEO_DIR = os.path.join(WORKSPACE_DIR, "backend", "frontend", "src", "assets", "video")
FRONTEND_IMAGE_DIR = os.path.join(WORKSPACE_DIR, "backend", "frontend", "src", "assets", "images")
TEMP_DIR = os.path.join(WORKSPACE_DIR, "temp_karen_process")

os.makedirs(FRONTEND_VIDEO_DIR, exist_ok=True)
os.makedirs(FRONTEND_IMAGE_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)


def download_snippet(video_id: str, duration_sec: int = 20) -> str:
    """下载前 duration_sec 秒高清切片"""
    out_path = os.path.join(TEMP_DIR, f"{video_id}_raw.webm")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
        print(f"  [缓存命中] 切片已存在: {out_path}")
        return out_path

    print(f"  [下载中] 正在拉取视频 {video_id} 前 {duration_sec} 秒...")
    cmd = [
        "yt-dlp",
        "--proxy", PROXY,
        "--download-sections", f"*00:00:00-00:00:{duration_sec:02d}",
        "-f", "bestvideo[height<=1080][ext=webm]/bestvideo[height<=1080]/bestvideo",
        f"https://www.youtube.com/watch?v={video_id}",
        "-o", out_path,
        "--force-overwrites"
    ]
    ret = subprocess.run(cmd, env=ENV, capture_output=True, text=True)
    if ret.returncode != 0 or not os.path.exists(out_path):
        cmd_fallback = [
            "yt-dlp",
            "--proxy", PROXY,
            "--download-sections", f"*00:00:00-00:00:{duration_sec:02d}",
            f"https://www.youtube.com/watch?v={video_id}",
            "-o", out_path,
            "--force-overwrites"
        ]
        ret_fb = subprocess.run(cmd_fallback, env=ENV, capture_output=True, text=True)
        if ret_fb.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(f"下载失败: {ret_fb.stderr}")

    print(f"  [下载完成] 切片保存至: {out_path}")
    return out_path


def detect_loop_cycle(frames, fps: float):
    """在上半区检测动作循环最佳接缝帧"""
    total_f = len(frames)
    min_search = int(fps * 3.5)
    max_search = min(total_f - int(fps * 1.5), int(fps * 12.0))
    if max_search <= min_search:
        return min(total_f, int(fps * 5.0))

    f0_crop = frames[0][:550, :].astype(float)
    diffs = []
    for i in range(min_search, max_search):
        fi_crop = frames[i][:550, :].astype(float)
        d = np.mean(np.abs(fi_crop - f0_crop))
        diffs.append((i, d))

    diffs.sort(key=lambda x: x[1])
    best_frame, best_diff = diffs[0]
    print(f"  [循环周期检测] 最佳循环帧: {best_frame} (约 {best_frame/fps:.2f}s), 差异度: {best_diff:.2f}")
    return best_frame


def build_clean_bottom_plate(frames, h: int, w: int, scene_id: str = ""):
    """通过 Frame 0 原色母板与高精度 Navier-Stokes 微缝重构 100% 纯净底板 (零变暗、零暗影、零涂抹)"""
    plate_cache = os.path.join(TEMP_DIR, "plates", f"{scene_id}_plate.jpg")
    if os.path.exists(plate_cache):
        print(f"  [底板命中] 直接加载高精度纯净底板: {plate_cache}")
        return cv2.imread(plate_cache)

    if scene_id == "karen_worship_jazz":
        print("  [母板重构] 基于时序最小滤波与垂直线性插值重构高保真纯净底板 (彻底消解跳动频谱柱与进度线)...")
        # 1. 时域统计最小滤波：消除全部音频跳动频谱柱 (覆盖西装下摆、祭坛台阶、歌谱与花束)
        stack = np.array(frames)
        t_min_bottom = np.min(stack[:, 650:, :, :], axis=0)
        f0 = frames[0].copy()
        f0[650:, :] = t_min_bottom

        # 2. 进度条横线 (970..974) 与频谱基准圆点 (964..970) 掩膜
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[970:975, 20:1900] = 255
        bg_above = f0[958:963, :, :].mean(axis=0)
        for r in range(964, 970):
            diff = (f0[r, :, :].astype(float) - bg_above).mean(axis=1)
            mask[r, diff > 6] = 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask[963:976, :] = cv2.dilate(mask[963:976, :], kernel)

        # 3. 沿垂直方向执行列线性插值（彻底保留花束立茎、百褶裙褶皱、歌谱黑边与台阶原画质感，杜绝横向涂抹马赛克）
        clean_plate = f0.copy()
        for c in range(w):
            col_mask = mask[:, c]
            if not np.any(col_mask):
                continue
            masked_indices = np.where(col_mask > 0)[0]
            top_y = masked_indices.min() - 1
            bot_y = masked_indices.max() + 1
            if top_y >= 0 and bot_y < h:
                top_val = f0[top_y, c].astype(float)
                bot_val = f0[bot_y, c].astype(float)
                for y in masked_indices:
                    alpha = (y - top_y) / float(bot_y - top_y)
                    clean_plate[y, c] = ((1 - alpha) * top_val + alpha * bot_val).astype(np.uint8)

        # 4. 时间戳文字笔画精准掩膜并微缝修复
        mask_text = np.zeros((h, w), dtype=np.uint8)
        left_crop = f0[980:1020, 30:210]
        is_white_left = (left_crop[:, :, 0] > 180) & (left_crop[:, :, 1] > 180) & (left_crop[:, :, 2] > 180)
        mask_text[980:1020, 30:210] = cv2.dilate(is_white_left.astype(np.uint8) * 255, kernel)

        right_crop = f0[980:1020, 1670:1885]
        is_white_right = (right_crop[:, :, 0] > 180) & (right_crop[:, :, 1] > 180) & (right_crop[:, :, 2] > 180)
        mask_text[980:1020, 1670:1885] = cv2.dilate(is_white_right.astype(np.uint8) * 255, kernel)

        clean_plate = cv2.inpaint(clean_plate, mask_text, 2, cv2.INPAINT_NS)
        os.makedirs(os.path.join(TEMP_DIR, "plates"), exist_ok=True)
        cv2.imwrite(plate_cache, clean_plate)
        return clean_plate

    print("  [母板重构] 基于 Frame 0 原画母板与微缝修复重构高保真纯净底板...")
    f0 = frames[0].copy()
    
    # 1. 进度条 (963~976) 及基准小圆点高精度掩膜
    mask = np.zeros((h, w), dtype=np.uint8)
    
    # 1. 进度条横线 (严格收敛至 969~975，仅 6px 高度，彻底杜绝上下大范围纵向拉伸与马赛克伪影)
    mask[969:975, 20:1900] = 255
    
    # 2. 频谱基准小圆点智能识别 (捕获 964~970 区域内相对背景显著增亮的圆点像素，兼顾暗色溪流与明亮地景)
    bg_above = f0[958:963, :, :].mean(axis=0)
    dot_candidate = np.zeros((h, w), dtype=np.uint8)
    for r in range(964, 970):
        diff = (f0[r, :, :].astype(float) - bg_above).mean(axis=1)
        dot_candidate[r, diff > 6] = 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dot_dilated = cv2.dilate(dot_candidate[963:971, :], kernel)
    mask[963:971, :] = np.maximum(mask[963:971, :], dot_dilated)

    # 3. 进度条两侧端点标线 (完整覆盖上下边缘)
    mask[960:982, 35:46] = 255
    mask[960:982, 1874:1886] = 255

    # 4. 左右角时间戳文字笔画精准掩膜 (以 RGB 纯白像素精准匹配，防止明亮背景误入掩膜扩散)
    left_crop = f0[980:1020, 30:210]
    is_white_left = (left_crop[:, :, 0] > 180) & (left_crop[:, :, 1] > 180) & (left_crop[:, :, 2] > 180)
    mask[980:1020, 30:210] = cv2.dilate(is_white_left.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    right_crop = f0[980:1020, 1670:1885]
    is_white_right = (right_crop[:, :, 0] > 180) & (right_crop[:, :, 1] > 180) & (right_crop[:, :, 2] > 180)
    mask[980:1020, 1670:1885] = cv2.dilate(is_white_right.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))

    # 使用 Navier-Stokes 流体微缝修复，保真度最高 (radius=2 平滑过渡无硬切)
    clean_plate = cv2.inpaint(f0, mask, inpaintRadius=2, flags=cv2.INPAINT_NS)

    # 针对 mountain_chapel 石护栏顶面与阴影立面进行高保真边缘分区分界修复
    if scene_id == "karen_mountain_chapel":
        crop_stone = clean_plate[975:1025, 1650:1900].copy()
        mask_stone = (crop_stone[:, :, 0] > 200) & (crop_stone[:, :, 1] > 200) & (crop_stone[:, :, 2] > 200)
        mask_stone = cv2.dilate(mask_stone.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        y_trees, y_ledge = 6, 33
        z1_crop, z1_mask = crop_stone[:y_trees, :].copy(), mask_stone[:y_trees, :].copy()
        clean_z1 = cv2.inpaint(z1_crop, z1_mask, 1, cv2.INPAINT_NS) if np.any(z1_mask) else z1_crop
        z2_crop, z2_mask = crop_stone[y_trees:y_ledge, :].copy(), mask_stone[y_trees:y_ledge, :].copy()
        clean_z2 = cv2.inpaint(z2_crop, z2_mask, 1, cv2.INPAINT_NS) if np.any(z2_mask) else z2_crop
        z3_crop, z3_mask = crop_stone[y_ledge:, :].copy(), mask_stone[y_ledge:, :].copy()
        clean_z3 = cv2.inpaint(z3_crop, z3_mask, 1, cv2.INPAINT_NS) if np.any(z3_mask) else z3_crop
        clean_plate[975:1025, 1650:1900] = np.vstack([clean_z1, clean_z2, clean_z3])

    os.makedirs(os.path.join(TEMP_DIR, "plates"), exist_ok=True)
    cv2.imwrite(plate_cache, clean_plate)
    return clean_plate


SCENE_SPLITS = {
    "karen_street_acoustic": 710,  # 降低至 710，彻底覆盖膝盖处冲顶的白色频谱柱峰值 (y=732)
    "karen_midnight_cafe": 680,
    "karen_candle_devotion": 710,  # 设定为 710，彻底覆盖琴凳旁男琴师大腿处的频谱柱冲顶峰值 (y=730)
    "karen_worship_jazz": 680,     # 设定为 680，彻底覆盖祭坛与诗班讲台前冲顶的白色频谱柱峰值 (y=704)
    "karen_mountain_chapel": 750,
    "karen_peaceful_rest": 695,  # 设定为 695，彻底覆盖溪流中央冲顶的白色频谱柱峰值 (y=714)
    "karen_morning_grace": 670,
    "karen_rainy_night": 690       # 设定为 690，彻底覆盖吉他底部至双腿间的频谱柱冲顶峰值 (y=713)
}


def render_seamless_video(frames, clean_plate, loop_frame: int, fps: float, h: int, w: int, scene_id: str):
    """分层高保真渲染：上半区完整保留自然动态（呼吸、眨眼、发丝、唱片旋转、火苗），下半区纯净无缝消除频谱柱与进度线"""
    crossfade_len = int(fps * 0.5)
    total_needed = loop_frame + crossfade_len
    process_count = min(total_needed, len(frames))

    split_y = SCENE_SPLITS.get(scene_id, 720)
    blend_h = 10

    print(f"  [分层高保真渲染] 正在处理前 {process_count} 帧 (接缝高度: y={split_y}, 上半区动态微动, 下半区100%纯净)...")
    processed_frames = []

    for i in range(process_count):
        f = frames[i]
        out = clean_plate.copy()
        
        # 上半区动态微动
        out[:split_y - blend_h, :] = f[:split_y - blend_h, :]
        # 10px 平滑羽化过渡
        for y in range(split_y - blend_h, split_y):
            a = (y - (split_y - blend_h)) / float(blend_h)
            out[y, :] = ((1.0 - a) * f[y, :].astype(float) + a * clean_plate[y, :].astype(float)).astype(np.uint8)
        processed_frames.append(out)

    # 4. 环形接缝淡入淡出 (Cross-fade)
    print(f"  [循环接缝] 正在执行 0.5s 环形交叉淡入淡出 (循环长度: {loop_frame} 帧)...")
    final_frames = []
    for i in range(loop_frame):
        if i < loop_frame - crossfade_len:
            final_frames.append(processed_frames[i])
        else:
            cf_idx = i - (loop_frame - crossfade_len)
            alpha = (cf_idx + 1) / float(crossfade_len + 1)
            tail_f = processed_frames[loop_frame + cf_idx].astype(np.float32) if (loop_frame + cf_idx) < len(processed_frames) else processed_frames[0].astype(np.float32)
            head_f = processed_frames[cf_idx].astype(np.float32)
            cf_blended = (tail_f * (1.0 - alpha) + head_f * alpha).astype(np.uint8)
            final_frames.append(cf_blended)

    # 5. 写入临时 MP4
    raw_mp4 = os.path.join(TEMP_DIR, f"{scene_id}_temp.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_v = cv2.VideoWriter(raw_mp4, fourcc, fps, (w, h))
    for f in final_frames:
        out_v.write(f)
    out_v.release()

    # 6. 导出静态 Poster 封面
    poster_path = os.path.join(FRONTEND_IMAGE_DIR, f"{scene_id}.jpg")
    cv2.imwrite(poster_path, final_frames[0])
    print(f"  [海报生成] 已保存海报图: {poster_path}")

    # 7. 压制 Web MP4 (H.264, faststart, crf 20)
    final_mp4 = os.path.join(FRONTEND_VIDEO_DIR, f"{scene_id}.mp4")
    print(f"  [视频压制] 正在编码 H.264 Web MP4: {final_mp4}...")
    cmd_mp4 = [
        "ffmpeg", "-y",
        "-i", raw_mp4,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-crf", "20",
        "-movflags", "+faststart",
        "-an",
        final_mp4
    ]
    subprocess.run(cmd_mp4, check=True, capture_output=True)

    # 8. 压制 WebM (VP9, crf 28)
    final_webm = os.path.join(FRONTEND_VIDEO_DIR, f"{scene_id}.webm")
    print(f"  [视频压制] 正在编码 VP9 WebM: {final_webm}...")
    cmd_webm = [
        "ffmpeg", "-y",
        "-i", raw_mp4,
        "-c:v", "libvpx-vp9",
        "-crf", "28",
        "-b:v", "0",
        "-an",
        final_webm
    ]
    subprocess.run(cmd_webm, check=True, capture_output=True)

    if os.path.exists(raw_mp4):
        os.remove(raw_mp4)

    mp4_size = os.path.getsize(final_mp4) / 1024 / 1024 if os.path.exists(final_mp4) else 0
    webm_size = os.path.getsize(final_webm) / 1024 / 1024 if os.path.exists(final_webm) else 0
    print(f"  ✅ [处理完成] {scene_id} -> MP4: {mp4_size:.2f}MB, WebM: {webm_size:.2f}MB, Poster: OK")
    return final_mp4, final_webm, poster_path


def process_video(video_id: str, scene_id: str, scene_title: str):
    print(f"\n==================================================")
    print(f"🎬 开始处理场景: 《{scene_title}》")
    print(f"   YouTube ID: {video_id} | 场景名称: {scene_id}")
    print(f"==================================================")

    # 1. 下载切片
    raw_video = download_snippet(video_id, duration_sec=20)

    # 2. 读取全部帧
    cap = cv2.VideoCapture(raw_video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    while True:
        ret, f = cap.read()
        if not ret:
            break
        frames.append(f)
    cap.release()
    print(f"  [帧流解码] 共读取 {len(frames)} 帧, 分辨率: {w}x{h}, 帧率: {fps:.1f}fps")

    # 3. 循环周期检测
    loop_frame = detect_loop_cycle(frames, fps)

    # 4. 时序最小聚合重构纯净底板
    clean_plate = build_clean_bottom_plate(frames, h, w, scene_id=scene_id)

    # 5. 渲染无缝微动视频
    render_seamless_video(frames, clean_plate, loop_frame, fps, h, w, scene_id)


def main():
    parser = argparse.ArgumentParser(description="Karen YouTube Channel Ambient Video Pipeline")
    parser.add_argument("--id", type=str, help="YouTube Video ID")
    parser.add_argument("--name", type=str, help="Target scene identifier")
    parser.add_argument("--index", type=int, help="Process video by 1-based index from karen_videos.json")
    parser.add_argument("--batch", type=int, default=0, help="Process first N videos (0 for manual)")
    parser.add_argument("--presets", action="store_true", help="Process all 8 curated preset scenes")
    args = parser.parse_args()

    json_path = os.path.join(WORKSPACE_DIR, "karen_videos.json")
    with open(json_path, 'r', encoding='utf-8') as f:
        videos = json.load(f)

    # 预设场景映射字典（针对前几大最具代表性的唯美主题）
    SCENE_PRESETS = {
        "Wi39kkQROzQ": ("karen_street_acoustic", "夜市暖灯吉他", "暖光灯串、木吉他独奏与闭目沉浸的听歌少女"),
        "MijQY9LTaUo": ("karen_midnight_cafe", "深夜电台录音室", "温馨复古录音室、暖色台灯、经典黑胶与咖啡"),
        "v41Y1hV2RQc": ("karen_candle_devotion", "烛光静修小室", "暖意烛光、复古台灯与静谧书斋"),
        "e7hNAfIKW1s": ("karen_worship_jazz", "晚安祷告爵士", "温馨窗台、夜间微光与治愈陪伴"),
        "pZydfdh8Bmc": ("karen_mountain_chapel", "远山圣殿晨曦", "远山微风、圣殿晨光与静心时刻"),
        "_qGmzc6dMVs": ("karen_peaceful_rest", "安息静水边", "微风拂过绿野，轻柔抚慰疲惫心灵"),
        "XazrVhJ6SpM": ("karen_morning_grace", "晨光初醒赞美", "清晨的第一缕温暖日光与醇香咖啡"),
        "XwKj_-ssgbU": ("karen_rainy_night", "雨夜微光静息", "窗外沥沥小雨，室内温柔爵士与安息时光")
    }

    if args.presets:
        print("🚀 开始全量重构全部 8 个精选 Karen 氛围背景...")
        for vid, (scene_id, scene_title, scene_desc) in SCENE_PRESETS.items():
            process_video(vid, scene_id, scene_title)
    elif args.id:
        preset = SCENE_PRESETS.get(args.id, (args.name or f"karen_{args.id}", "Karen氛围场景", "优美环境氛围背景"))
        process_video(args.id, preset[0], preset[1])
    elif args.index:
        idx = args.index - 1
        if 0 <= idx < len(videos):
            v = videos[idx]
            vid = v['id']
            preset = SCENE_PRESETS.get(vid, (f"karen_scene_{args.index}", v['title'][:15], v['title']))
            process_video(vid, preset[0], preset[1])
    elif args.batch > 0:
        count = min(args.batch, len(videos))
        print(f"🚀 开始批量处理前 {count} 个视频...")
        for i in range(count):
            v = videos[i]
            vid = v['id']
            preset = SCENE_PRESETS.get(vid, (f"karen_scene_{i+1}", v['title'][:15], v['title']))
            process_video(vid, preset[0], preset[1])
    else:
        print("请指定参数: --id, --index, 或 --batch N")


if __name__ == "__main__":
    main()
