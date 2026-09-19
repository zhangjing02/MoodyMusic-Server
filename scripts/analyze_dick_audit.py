import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
with open('scratch/dick_cowboy_audit_report.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

current_album = ""
for item in d:
    alb = item['album']
    tit = item['title']
    if alb != current_album:
        current_album = alb
        print(f"\n==================== 《{alb}》 ====================")
    m = item.get('kuwo_match')
    if m:
        live_tag = " [LIVE/CONCERT]" if m['is_live'] else ""
        print(f" • 《{tit}》 -> Kuwo: {m['artist']} - {m['title']} (Album: 《{m['album']}》, {m['duration']}s){live_tag}")
    else:
        print(f" • 《{tit}》 -> ❌ Kuwo 无迪克牛仔独立录音室版本")
