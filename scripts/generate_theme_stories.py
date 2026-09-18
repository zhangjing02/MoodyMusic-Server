# -*- coding: utf-8 -*-
import os, sys, re, json

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

src_path = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\MoodyMusicForAndroid\app\src\main\java\com\example\moodymusicforandroid\ui\theme_detail\ThemeDetailScreen.kt'
with open(src_path, 'r', encoding='utf-8') as f:
    code = f.read()

# Split by `"theme_id" -> ThemeStory(` and `else -> ThemeStory(`
sections = re.split(r'(\"[a-zA-Z0-9_]+\"|else)\s*->\s*ThemeStory\(', code)
# sections will have: [before, id1, body1, id2, body2, ...]

print("Found section tokens:", len(sections))

stories = {}
for i in range(1, len(sections), 2):
    raw_id = sections[i].strip('"')
    if raw_id == 'else':
        theme_id = 'snow_cafe_theme'
    else:
        theme_id = raw_id
    
    body = sections[i+1]
    # find closing )
    # Note: we can parse fields using regex
    def get_str(field):
        m = re.search(r'\b' + field + r'\s*=\s*\"(.*?)(?<!\\)\"', body, re.DOTALL)
        if m:
            s = m.group(1)
            # handle escapes
            return s.replace('\\n', '\n').replace('\\"', '"')
        return ""

    def get_list(field):
        m = re.search(r'\b' + field + r'\s*=\s*listOf\((.*?)\)', body, re.DOTALL)
        if m:
            items_str = m.group(1)
            # find all quoted strings
            items = re.findall(r'\"(.*?)(?<!\\)\"', items_str, re.DOTALL)
            return [it.replace('\\n', '\n').replace('\\"', '"') for it in items]
        return []

    def get_bool(field, default=False):
        m = re.search(r'\b' + field + r'\s*=\s*(true|false)', body)
        if m:
            return m.group(1) == 'true'
        return default

    def get_float(field, default=1.6):
        m = re.search(r'\b' + field + r'\s*=\s*([0-9\.\/f]+)', body)
        if m:
            raw = m.group(1).replace('f', '')
            if '/' in raw:
                parts = raw.split('/')
                try: return float(parts[0]) / float(parts[1])
                except: return default
            try: return float(raw)
            except: return default
        return default

    # Timeline sections
    timeline_sections = []
    t_matches = re.finditer(r'TimelineSection\((.*?)\)', body, re.DOTALL)
    for tm in t_matches:
        tb = tm.group(1)
        def get_t_str(tf):
            m = re.search(r'\b' + tf + r'\s*=\s*\"(.*?)(?<!\\)\"', tb, re.DOTALL)
            if m:
                return m.group(1).replace('\\n', '\n').replace('\\"', '"')
            return ""
        timeline_sections.append({
            'timeLabel': get_t_str('timeLabel'),
            'title': get_t_str('title'),
            'sceneStory': get_t_str('sceneStory'),
            'emotion': get_t_str('emotion'),
            'technique': get_t_str('technique'),
            'performerNote': get_t_str('performerNote')
        })

    hero_url_map = {
        'white_snake_flute_theme': 'https://m-api.changgepd.ccwu.cc/storage/covers/albums/white_snake_flute_cover.jpg',
        'bach_cello_theme': 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/hero/bach_cello_hero.jpg',
        'butterfly_lovers_deep_dive': 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/albums/butterfly_lovers_cover_clean.jpg',
        'jonathan_lee_theme': 'https://m-api.changgepd.ccwu.cc/storage/covers/albums/album_jonathan_lee.jpg',
        'pop_piano_theme': 'https://m-api.changgepd.ccwu.cc/storage/covers/albums/pop_piano_cover.jpg',
        'lofi_chill_theme': 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/albums/lofi_chill_cover.jpg',
        'snow_cafe_theme': 'https://pub-9ea7ff16135d47238c0229f1aa54ecc4.r2.dev/covers/hero/snow_cafe_hero.jpg'
    }

    story = {
        'themeId': theme_id,
        'issueTag': get_str('issueTag'),
        'categoryTag': get_str('categoryTag'),
        'headline': get_str('headline'),
        'subtitle': get_str('subtitle'),
        'authorDate': get_str('authorDate'),
        'heroUrl': hero_url_map.get(theme_id, ''),
        'bodyParagraphs': get_list('bodyParagraphs'),
        'quoteEn': get_str('quoteEn'),
        'quoteZh': get_str('quoteZh'),
        'scenariosTitle': get_str('scenariosTitle') or '🎧 适用场景',
        'scenarios': get_list('scenarios'),
        'benefitsTitle': get_str('benefitsTitle') or '✨ 专题亮点',
        'benefits': get_list('benefits'),
        'aboutTitle': get_str('aboutTitle') or '👉 关于作品与演绎者',
        'aboutDesc': get_str('aboutDesc'),
        'aboutMotto': get_str('aboutMotto'),
        'footerSign': get_str('footerSign'),
        'playPillTextActive': get_str('playPillTextActive') or '演奏中',
        'playPillTextIdle': get_str('playPillTextIdle') or '开始播放',
        'isSquareCover': get_bool('isSquareCover', False),
        'posterAspectRatio': get_float('posterAspectRatio', 1.6),
        'timelineTitle': get_str('timelineTitle'),
        'timelineSections': timeline_sections
    }
    stories[theme_id] = story
    print(f"Parsed story [{theme_id}]: {story['headline']}, paragraphs: {len(story['bodyParagraphs'])}, timeline: {len(timeline_sections)}")

out_json = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\scripts\default_theme_stories.json'
with open(out_json, 'w', encoding='utf-8') as f:
    json.dump(stories, f, ensure_ascii=False, indent=2)

print(f"Saved {len(stories)} stories to {out_json} successfully!")
