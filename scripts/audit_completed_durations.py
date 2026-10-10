import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('backend/scripts/remediate_progress.json', 'r', encoding='utf-8') as f:
    prog = json.load(f)

completed = prog.get('completed', [])
print(f'Total in completed: {len(completed)}')

conn = sqlite3.connect('backend/database/catalog_sync.db')
cur = conn.cursor()

short_tracks = []
good_tracks = []

for sid in completed:
    cur.execute('SELECT s.id, a.name, s.title, s.duration, s.file_path FROM songs s JOIN artists a ON s.artist_id = a.id WHERE s.id = ?', (sid,))
    row = cur.fetchone()
    if row:
        dur = row[3]
        if dur is None or dur <= 60:
            short_tracks.append(row)
        else:
            good_tracks.append(row)

print(f'\n✅ 确认完好长音频 (时效 > 60s): {len(good_tracks)} 首')
print(f'⚠️ 短音频或异常音轨 (时效 <= 60s): {len(short_tracks)} 首')
for r in short_tracks:
    print(f'  ID {r[0]}: [{r[1]}] 《{r[2]}》 -> {r[3]} 秒 ({r[4]})')
