# -*- coding: utf-8 -*-
import json, re, sys, os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

src_path = 'MoodyMusicForAndroid/app/src/main/java/com/example/moodymusicforandroid/ui/theme_detail/ThemeDetailScreen.kt'
with open(src_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Let's write a robust parser for the Kotlin ThemeStory definitions
stories = {}

# We know the themeIds:
# pop_piano_theme, jonathan_lee_theme, lofi_chill_theme, white_snake_flute_theme, bach_cello_theme, butterfly_lovers_deep_dive, snow_cafe_theme

# Let's define them directly as high-precision structured JSON
