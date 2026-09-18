# -*- coding: utf-8 -*-
import sys, os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

file_path = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\MoodyMusicForAndroid\app\src\main\java\com\example\moodymusicforandroid\ui\theme_detail\ThemeDetailScreen.kt'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# find header (imports)
import_lines = []
for l in lines:
    if l.startswith('/**') and '现代颂歌' in l:
        break
    import_lines.append(l)

# Add new imports
new_imports = """import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.moodymusicforandroid.data.model.ThemeStoryDto
import com.example.moodymusicforandroid.data.model.TimelineSectionDto
import com.example.moodymusicforandroid.ui.theme_detail.ThemeDetailViewModel
import com.example.moodymusicforandroid.ui.theme_detail.ThemeDetailUiState
"""

# Find where Scaffold starts
scaffold_idx = -1
for i, l in enumerate(lines):
    if 'val story = remember(themeId)' in l:
        scaffold_idx = i
        break

# Find where LazyColumn starts
lazy_idx = -1
for i in range(scaffold_idx, len(lines)):
    if 'LazyColumn(' in lines[i]:
        lazy_idx = i
        break

print(f"Header lines: {len(import_lines)}, Scaffold line: {scaffold_idx}, LazyColumn line: {lazy_idx}")
