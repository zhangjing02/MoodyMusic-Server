#!/usr/bin/env python3
"""
全曲库华语歌手地毯式立体化双轨正交审计与自动治理调度中枢
(orchestrate_full_catalog_dual_pipeline.py)
=============================================================================
功能：
1. 从线上获取全量 185 位歌手名单，按战略重要性与曲库规模编排优先级战役序列；
2. 支持全流程断点续传：自动跳过已 100% 闭环达标的歌手；
3. 对队列中每位歌手依次实施闭环作业：
   - Step 1: 立体化双轨正交审计 (Stage 1 初筛 + Stage 2 正交反向平反)
   - Step 2: 自动化分流治理 (正版歌词清洗推流 + 官方 Topic 母带置换 + 404 断链重构点亮)
   - Step 3: 全盘终极连通性回归验收 (HTTP 200 流探测)
4. 输出全曲库总推进进度大盘 (CATALOG_ORCHESTRATION_PROGRESS.json)。
"""

import os, sys, json, time, subprocess, requests
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = REPORTS_DIR / "CATALOG_ORCHESTRATION_PROGRESS.json"

# 已确认 100% 满格闭环历史歌手 (免重跑)
PREVIOUSLY_COMPLETED = {
    "黄品源", "五月天", "王菲", "周杰伦", "孙燕姿", "陈奕迅", "林俊杰", "张学友", "Beyond"
}

# 核心战略优先级梯队
PRIORITY_ORDER = [
    # 首发梯队
    "周华健", "莫文蔚", "齐秦", "苏打绿", "任贤齐",
    # 华语巨量典藏梯队
    "谭咏麟", "邓丽君", "容祖儿", "张国荣", "张信哲", "罗大佑", "李玟", "庾澄庆", "苏慧伦", "黄小琥",
    # 华语中坚大碟梯队
    "王力宏", "梁静茹", "张惠妹", "刘若英", "范晓萱", "JOLIN蔡依林", "杨丞琳", "刘德华", "萧煌奇", "薛之谦", "品冠", "刀郎", "游鸿明", "高胜美",
    # 摇滚、民谣、乐队与经典流行
    "张宇", "陈小春", "谢霆锋", "范玮琪", "张震岳", "李宗盛", "李克勤", "杨千嬅", "杨乃文", "林宥嘉", "林忆莲", "林志炫",
    "窦唯", "新裤子", "羽·泉", "痛仰乐队", "老狼", "李健", "朴树", "草东没有派对", "告五人", "落日飞车", "旅行团乐队"
]

def get_all_remote_artists() -> list:
    try:
        r = requests.get("https://m-api.changgepd.ccwu.cc/api/skeleton", timeout=15)
        artists = r.json().get("data", {}).get("artists", [])
        return [a["name"] for a in artists]
    except Exception as e:
        print(f"⚠️ 拉取全量歌手列表失败: {e}")
        return []

def is_artist_fully_completed(artist: str) -> bool:
    if artist in PREVIOUSLY_COMPLETED:
        return True
    rem_file = REPORTS_DIR / f"REMEDIATION_{artist}_LOG.json"
    if rem_file.exists():
        try:
            with open(rem_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            # 如果断链数为 0 且验证通过数 == 总曲目数
            if len(d.get("broken_songs", [])) == 0 and d.get("verified_healthy", 0) == d.get("total_songs", 0):
                return True
        except:
            pass
    return False

def run_step(cmd: list, desc: str) -> bool:
    print(f"\n>>> 启动任务: {desc}...")
    print(f"    命令: {' '.join(cmd)}")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in iter(p.stdout.readline, ''):
        if line:
            print(f"    {line.rstrip()}")
    p.stdout.close()
    p.wait()
    return p.returncode == 0

def main():
    print("=" * 70)
    print(" 全曲库华语歌手地毯式立体化双轨正交审计与自动治理调度中枢")
    print("=" * 70)
    
    remote_artists = get_all_remote_artists()
    print(f"线上总计发现 {len(remote_artists)} 位歌手/乐队资产。")
    
    # 构建完整作业队列
    work_queue = []
    seen = set()
    
    # 1. 优先加入已编排的重点梯队
    for a in PRIORITY_ORDER:
        if a in remote_artists and a not in seen:
            work_queue.append(a)
            seen.add(a)
            
    # 2. 加入其余全部歌手
    for a in remote_artists:
        if a not in seen:
            work_queue.append(a)
            seen.add(a)
            
    print(f"完整调度流水线已编排总队列: {len(work_queue)} 位歌手。")
    
    # 逐一推进
    for idx, artist in enumerate(work_queue, 1):
        print("\n" + "#" * 70)
        print(f"【调度中枢】第 [{idx}/{len(work_queue)}] 战役: 【{artist}】")
        print("#" * 70)
        
        if is_artist_fully_completed(artist):
            print(f"🎉 歌手【{artist}】已达到 100% 满格健康，自动跳过。")
            continue
            
        # Step 1: 审计
        audit_cmd = ["python3", str(BASE_DIR / "scripts" / "audit_superstars_dual_pipeline.py"), "--artist", artist]
        audit_ok = run_step(audit_cmd, f"【{artist}】立体化双轨正交审计")
        if not audit_ok:
            print(f"❌ 【{artist}】审计执行异常，继续保持排查...")
            
        # Step 2: 治理与回归验证
        remedy_cmd = ["python3", str(BASE_DIR / "scripts" / "remediate_artist_pipeline.py"), "--artist", artist]
        remedy_ok = run_step(remedy_cmd, f"【{artist}】自动化治理与终极回归验收")
        if remedy_ok:
            print(f"🌟 恭喜！歌手【{artist}】已成功闭环治理！")
        else:
            print(f"⚠️ 歌手【{artist}】治理环节存在需人工复核项。")
            
        # 更新大盘进度文件
        progress = {
            "current_index": idx,
            "current_artist": artist,
            "total_queue": len(work_queue),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
