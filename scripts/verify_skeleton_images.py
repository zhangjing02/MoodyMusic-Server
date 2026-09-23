# -*- coding: utf-8 -*-
import json
import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open(r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\configs\four_new_artists_skeleton.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=== 验证封面与头像可访问性 ===")
failed = 0
total = 0
for art in data:
    av = art.get('avatar_url')
    r = requests.head(av, timeout=5)
    print(f"艺人 [{art['artist_name']}] 头像: HTTP {r.status_code}")
    for alb in art['albums']:
        total += 1
        cv = alb.get('cover_url')
        if not cv:
            print(f"  ❌ 缺失封面: 《{alb['title']}》")
            failed += 1
            continue
        try:
            rc = requests.head(cv, timeout=5)
            if rc.status_code != 200:
                print(f"  ⚠️ 封面 HTTP {rc.status_code}: 《{alb['title']}》 ({cv})")
                failed += 1
        except Exception as e:
            print(f"  ⚠️ 封面请求失败: 《{alb['title']}》: {e}")
            failed += 1

print(f"总检验封面数: {total}, 失败数: {failed}")
