import sys
import json
import re

sys.stdout.reconfigure(encoding='utf-8')
with open('scratch/dick_cowboy_full_audit.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

mismatches = [x for x in d if x['is_mismatch']]
print(f"Total mismatches: {len(mismatches)}")
for m in mismatches:
    path = m.get('path') or ''
    mat = re.search(r's_(\d+)\.mp3', path)
    sid = mat.group(1) if mat else str(m.get('id'))
    print(f"ID: {sid:6s} | 《{m['album']:15s}》 - 《{m['title']:12s}》 | {m['reason']}")
