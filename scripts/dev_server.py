#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MOODY Live Development Server (Port 8080)
Serves backend/frontend static files with zero cache lag.
Dynamically executes check_storage() in real-time on r2_stats.json requests.
"""

import http.server
import socketserver
import os
import sys
import json
import time
import threading

if sys.platform.startswith('win'):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
PORT = 8080

sys.path.insert(0, os.path.dirname(__file__))
from check_r2_storage import check_storage

class MoodyLiveRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def do_GET(self):
        # 拦截 R2 状态接口，0 延迟实时动态核算
        clean_path = self.path.split('?')[0]
        if clean_path.endswith('r2_stats.json'):
            try:
                stats = check_storage()
                content = json.dumps(stats, ensure_ascii=False, indent=2).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[LiveServer] Error computing live r2 stats: {e}", flush=True)

        super().do_GET()

    def end_headers(self):
        # 对开发环境静态资源禁用强缓存，确保热更新即时生效
        clean_path = self.path.split('?')[0]
        if clean_path.endswith(('.html', '.js', '.css', '.json')):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        # 减少刷屏日志，仅记录非 200 或重要请求
        if args and str(args[1]) not in ['200', '304']:
            super().log_message(format, *args)

def background_pulse():
    """后台低频心跳刷新磁盘快照（15秒一次）"""
    while True:
        time.sleep(15)
        try:
            check_storage()
        except Exception:
            pass

def main():
    socketserver.TCPServer.allow_reuse_address = True
    
    # 启动后台心跳盘点
    pulse_thread = threading.Thread(target=background_pulse, daemon=True)
    pulse_thread.start()

    with socketserver.TCPServer(("", PORT), MoodyLiveRequestHandler) as httpd:
        print(f"🚀 [MOODY Live Server] 正在监听 http://127.0.0.1:{PORT}")
        print(f"📁 根目录: {FRONTEND_DIR}")
        print(f"⚡ R2 实时动态计算引擎: 已就绪 (点击刷新秒级更新)")
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止。")

if __name__ == '__main__':
    main()
