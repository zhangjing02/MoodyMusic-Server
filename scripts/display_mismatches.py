#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('reports/AI_LISTENING_AUDIT_REPORT.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

mismatches = [x for x in data['ai_audit_details'] if x.get('status') in ('MISMATCH', 'AD_POLLUTION')]

print(f"Total Mismatched Tracks Detected: {len(mismatches)}")
print("=" * 80)
for idx, m in enumerate(mismatches, 1):
    print(f"[{idx:02d}] ID: {m['id']:<5} | [{m['artist']}] 《{m['album']}》 - 《{m['title']}》")
    print(f"     原因: {m['reason']}")
    print(f"     实唱: {m.get('whisper_heard', '')[:70]}...\n")
