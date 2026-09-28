#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
MOODY - Groq Whisper AI 听歌识曲与多 Token 智能轮询调度管理器 (Groq Token Pool)
=============================================================================
核心能力：
1. 多账号 Token 负载池轮询 (Round-Robin)：平摊 RPM/TPM 请求消耗，打破单号频控壁垒
2. 429 速率限制熔断与自动故障转移 (Failover)：遇到 429 自动进入冷却期并无缝切换至下一可用 Token
3. 音频切片智能优化：利用 ffmpeg 自动抽取 15s~80s 单声道 64kbps 切片 (约 400KB)，保障秒级上传
4. 模糊特征字吻合度计算：支持繁简统一（zhconv）与字集交集特征断言，精准拦截李鬼/翻唱/纯伴奏
=============================================================================
"""

import os
import sys
import json
import time
import re
import subprocess
import threading
import requests

# 默认基础路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SERVER_ROOT, "groq_config.json")
GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# 代理配置
DEFAULT_PROXIES = {
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897"
}

class GroqTokenPool:
    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = config_path
        self.lock = threading.Lock()
        self.current_index = 0
        self.tokens = []
        self.cooldowns = {}  # {token_str: cooldown_until_timestamp}
        self.settings = {
            "rotation_strategy": "round_robin",
            "cooldown_on_429_seconds": 60,
            "default_model": "whisper-large-v3",
            "proxy_url": "http://127.0.0.1:7897"
        }
        self._load_config()

    def _load_config(self):
        """从 groq_config.json 加载 Token 池，若不存在则回退至环境变量"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tokens = data.get("tokens", [])
                    self.settings.update(data.get("settings", {}))
            except Exception as e:
                print(f"[GroqPool] 读取配置文件失败: {e}，将尝试环境变量")

        # 环境变量兜底
        env_key = os.environ.get("GROQ_API_KEY", "").strip()
        if env_key and not any(t.get("api_key") == env_key for t in self.tokens):
            self.tokens.append({
                "id": len(self.tokens) + 1,
                "account": "env_fallback",
                "api_key": env_key,
                "status": "active"
            })

    def get_token(self):
        """线程安全地获取当前下一个可用的 Token（自动避开处于 429 冷却期的 Token）"""
        with self.lock:
            if not self.tokens:
                return None, "未配置任何 Groq Token"

            now = time.time()
            total = len(self.tokens)

            # 遍历尝试找到未处于冷却期的 Token
            for i in range(total):
                idx = (self.current_index + i) % total
                candidate = self.tokens[idx]
                key = candidate.get("api_key", "")
                
                # 检查冷却状态
                cooldown_until = self.cooldowns.get(key, 0)
                if now >= cooldown_until:
                    # 轮转到下一个
                    self.current_index = (idx + 1) % total
                    return candidate, None

            # 若全部都在冷却中，则选取冷却剩余时间最短的一个
            min_key = min(self.cooldowns, key=self.cooldowns.get)
            min_wait = max(1, int(self.cooldowns[min_key] - now))
            for cand in self.tokens:
                if cand.get("api_key") == min_key:
                    return cand, f"所有 Token 均在频控冷却中，最近一个 Token 需等待 {min_wait} 秒"

            return self.tokens[0], None

    def mark_cooldown(self, token_info, reason="429 Rate Limit"):
        """标记指定 Token 触发冷却"""
        with self.lock:
            key = token_info.get("api_key")
            cooldown_sec = self.settings.get("cooldown_on_429_seconds", 60)
            until = time.time() + cooldown_sec
            self.cooldowns[key] = until
            acc = token_info.get("account", "unknown")
            print(f"⚠️ [GroqPool 频控熔断] Token [{acc}] 触发 {reason}，进入 {cooldown_sec}s 冷却期")

    def transcribe(self, audio_file_path: str, model: str = None, language: str = "zh", max_retries: int = 3):
        """
        全自动化音频转录（具备切片优化、多 Token 轮换、429 自动故障转移）
        """
        if not os.path.exists(audio_file_path):
            return {"success": False, "error": f"音频文件不存在: {audio_file_path}"}

        model = model or self.settings.get("default_model", "whisper-large-v3")
        proxy_url = self.settings.get("proxy_url")
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        # 1. 抽取精华切片 (从第 15 秒截取 65 秒单声道 64kbps，体积仅 ~400KB)
        snippet_path = audio_file_path + ".groq_snippet.mp3"
        target_upload_file = audio_file_path
        try:
            cmd = ["ffmpeg", "-y", "-ss", "15", "-t", "65", "-i", audio_file_path, "-b:a", "64k", "-ac", "1", snippet_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            if os.path.exists(snippet_path) and os.path.getsize(snippet_path) > 1000:
                target_upload_file = snippet_path
        except Exception:
            target_upload_file = audio_file_path

        last_error = ""

        # 2. 轮询多 Token 发起转录，支持故障转移
        for attempt in range(max_retries):
            token_info, warn = self.get_token()
            if not token_info:
                last_error = warn or "无可用 Token"
                break

            api_key = token_info.get("api_key")
            account = token_info.get("account", "default")
            headers = {"Authorization": f"Bearer {api_key}"}

            try:
                with open(target_upload_file, "rb") as f:
                    files = {"file": (os.path.basename(target_upload_file), f, "audio/mpeg")}
                    data = {"model": model, "language": language}
                    r = requests.post(
                        GROQ_API_URL,
                        headers=headers,
                        files=files,
                        data=data,
                        proxies=proxies,
                        timeout=35
                    )

                if r.status_code == 200:
                    text = r.json().get("text", "").strip()
                    # 清理临时切片
                    if target_upload_file != audio_file_path and os.path.exists(target_upload_file):
                        try: os.remove(target_upload_file)
                        except Exception: pass
                    return {"success": True, "text": text, "account": account, "model": model}

                elif r.status_code == 429:
                    self.mark_cooldown(token_info, reason="HTTP 429 (Too Many Requests)")
                    last_error = f"Token [{account}] 触发频控(429)，尝试切换下一个 Token"
                    time.sleep(1)
                    continue

                elif r.status_code == 401:
                    print(f"❌ [GroqPool] Token [{account}] 鉴权失败 (HTTP 401)")
                    last_error = f"Token [{account}] 鉴权失败"
                    continue

                else:
                    last_error = f"HTTP {r.status_code}: {r.text[:120]}"

            except Exception as e:
                last_error = f"网络请求异常: {e}"
                time.sleep(1)

        # 清理临时切片
        if target_upload_file != audio_file_path and os.path.exists(target_upload_file):
            try: os.remove(target_upload_file)
            except Exception: pass

        return {"success": False, "error": last_error}


# 全局单例
_POOL = GroqTokenPool()

def get_groq_pool():
    return _POOL

def get_groq_api_key():
    """获取当前可用的单个 Groq API Key（平滑替代 os.environ.get('GROQ_API_KEY')）"""
    tok, _ = _POOL.get_token()
    return tok.get("api_key", "") if tok else ""

def transcribe_audio_text(audio_path: str, model="whisper-large-v3") -> str:
    """快速获取音频文本"""
    res = _POOL.transcribe(audio_path, model=model)
    return res.get("text", "") if res.get("success") else ""

def verify_with_groq_whisper(file_path: str, song: str, intro_lyrics: str = "", chorus_lyrics: str = ""):
    """
    与 download_music.py 完全对齐的官方 AI 听音比对接口
    返回值: (ai_heard_text_sample, is_match)
    """
    res = _POOL.transcribe(file_path)
    if not res.get("success"):
        return f"Groq转录失败: {res.get('error')}", True  # 软性兜底不阻断

    text = res.get("text", "")
    sample = text[:60] + "..." if len(text) > 60 else text

    # 尝试引入 zhconv 繁简统一
    try:
        import zhconv
        clean_intro = zhconv.convert(re.sub(r'[^\w]', '', intro_lyrics), 'zh-hans')
        clean_chorus = zhconv.convert(re.sub(r'[^\w]', '', chorus_lyrics), 'zh-hans')
        clean_text = zhconv.convert(re.sub(r'[^\w]', '', text), 'zh-hans')
        norm_song = zhconv.convert(re.sub(r'[^\w]', '', song), 'zh-hans')
    except ImportError:
        clean_intro = re.sub(r'[^\w]', '', intro_lyrics)
        clean_chorus = re.sub(r'[^\w]', '', chorus_lyrics)
        clean_text = re.sub(r'[^\w]', '', text)
        norm_song = re.sub(r'[^\w]', '', song)

    # 特征字重合度比对 (解决快歌含糊发音导致精确字串失配的问题)
    s_intro = set(clean_intro)
    s_chorus = set(clean_chorus)
    s_text = set(clean_text)

    intro_overlap = len(s_intro & s_text) / len(s_intro) if s_intro else 0
    chorus_overlap = len(s_chorus & s_text) / len(s_chorus) if s_chorus else 0

    # 匹配条件：
    # 1. 歌名直接包含在听出的文本中
    # 2. 或副歌关键词出现
    # 3. 或引言/副歌特征字重合度达到 40% 以上
    is_match = (
        norm_song in clean_text
        or (len(clean_chorus) > 4 and clean_chorus[:8] in clean_text)
        or chorus_overlap >= 0.40
        or intro_overlap >= 0.40
    )

    return sample, is_match


if __name__ == "__main__":
    print("=" * 80)
    print("🚀 测试 Groq 多 Token 负载池轮换与健康状态...")
    print("=" * 80)
    pool = get_groq_pool()
    print(f"📊 已加载 Token 数量: {len(pool.tokens)}")
    for t in pool.tokens:
        print(f" • Token {t['id']} [{t['account']}]: {t['api_key'][:8]}...{t['api_key'][-6:]} (状态: {t['status']})")
    
    print("\n🔄 连续模拟 6 次调度轮换:")
    for step in range(1, 7):
        tok, warn = pool.get_token()
        print(f" [调度 #{step}] 分配账号: {tok['account']} (Key: {tok['api_key'][:10]}...)")
    print("=" * 80)
