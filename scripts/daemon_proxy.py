#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代理核心守护进程 (自动保活 127.0.0.1:7898)"""

import subprocess, time, sys

CMD = [
    "/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo",
    "-f", "/tmp/mihomo_7898.yaml",
    "-d", "/Users/apple/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev"
]

while True:
    try:
        proc = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
    except Exception as e:
        pass
    time.sleep(1)
