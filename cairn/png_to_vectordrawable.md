# 位图设计资产向 Android 矢量图标（VectorDrawable）高保真自动转换与镂空修复流水线

## 1. 背景与核心痛点

在 Android 与跨平台移动开发中，UI 设计资产经常以透明背景的单色/描边 PNG 位图形式交付：
1. **手绘 Canvas 的局限**：在代码中用 Canvas/Path 纯手绘还原复杂拟物或手绘风格图标，极易造成比例失调、圆角丢失和线条走形（如信封变成方形叉号、吉他琴身失真）。
2. **位图 PNG 的局限**：无法无损缩放、放大存在毛刺、多分辨率适配包体积大，且无法无缝适配动态主题着色（`tint`）。
3. **传统转换工具的核心踩坑**：
   - 透明白线 PNG 直接输入矢量化引擎时无法识别前景。
   - 转换至 Android `VectorDrawable` XML 后，**内折线/镂空区域全部变成实心色块**。
   - 追踪算法容易在边缘产生孤立噪点。

---

## 2. 完整转换与修复流水线

```
[透明白线 PNG]
       ↓ (Pillow 提取白色笔画 Alpha 掩码)
[高反差纯黑底白线 BMP/PNG]
       ↓ (Potrace 贝塞尔平滑轮廓追踪)
[SVG 复合矢量路径 (fill-rule="evenodd")]
       ↓ (坐标缩放到 24dp Viewport + 噪点子路径清洗)
[Android VectorDrawable XML]
       ↓ (注入 android:fillType="evenOdd" 修复镂空)
[100% 像素级高保真原生矢量图标]
```

---

## 3. 核心步骤与关键避坑点

### 步骤 1：前景笔画提取与反差预处理 (Python / Pillow)
由于图标笔画通常为白色且带透明 Alpha 通道，直接矢量化会导致边缘丢失。先通过像素掩码将其转换为纯黑底（背景）、纯白线条（前景）的高反差图像：
```python
from PIL import Image
import numpy as np

img = Image.open("icon.png").convert("RGBA")
arr = np.array(img)
# 提取有效笔画像素
mask = (arr[:,:,0] > 180) & (arr[:,:,1] > 180) & (arr[:,:,2] > 180) & (arr[:,:,3] > 40)
bw = Image.new("RGB", img.size, (0, 0, 0))
white = Image.new("RGB", img.size, (255, 255, 255))
bw.paste(white, mask=Image.fromarray(mask.astype('uint8') * 255))
bw.save("icon_bw.png")
```

### 步骤 2：贝塞尔样条追踪 (Potrace)
使用 `potrace` 进行贝塞尔曲线追踪，指定 `blackOnWhite: false`（白色像素为笔画）：
```javascript
const potrace = require('potrace');
potrace.trace('icon_bw.png', {
  blackOnWhite: false,
  threshold: 128,
  turdSize: 3,
  optTolerance: 0.2,
  color: '#FFFFFF',
  background: 'transparent'
}, (err, svg) => { /* 处理 SVG 路径 */ });
```

### 步骤 3：⭐ 关键突破点 —— 修复实心色块 (`android:fillType="evenOdd"`)
- **现象**：生成的 VectorDrawable 渲染后，原本镂空的信封内折线、吉他琴孔/琴颈内部变成了**实心色块**。
- **根因**：SVG 默认使用 `fill-rule="evenodd"` 计算奇偶内外环绕裁切；而 Android `VectorDrawable` 的默认 `android:fillType` 是 `nonZero`。如果复合路径的绕向一致，Android 会将镂空内部当成实心填充。
- **解法**：在 VectorDrawable 的 `<path>` 标签中必须显式声明：
  ```xml
  <path
      android:fillType="evenOdd"
      android:fillColor="#FFFFFFFF"
      android:strokeColor="@android:color/transparent"
      android:pathData="..." />
  ```

### 步骤 4：坐标映射与孤立噪点过滤
1. **坐标缩放**：将源图片尺寸（如 256×256）等比缩放至 Android 标准 Viewport（`24×24`，缩放因子 `24.0 / 256.0`）。
2. **噪点清理**：位图边缘若存在抗锯齿散点，矢量化后会生成极短的孤立子路径（`len < 200` 且位于边角），通过正则拆分 `M` 指令过滤非主体子路径，保证图标干净无杂点。

---

## 4. 收益与适用场景

- **收益**：
  1. **零走样还原**：100% 保留原设计稿所有圆角、折线与曲线细节。
  2. **矢量轻量**：每个图标仅约 3KB，支持任意密度屏幕无损清晰渲染。
  3. **完美着色**：支持 Jetpack Compose `Icon(..., tint = ...)` 及 Android 动态着色。
- **适用场景**：
  - 只有设计切图 PNG，但缺少原始 Figma/Sketch/SVG 矢量源文件的移动端项目。
  - 需要在 Android 中实现主题变色、状态切换的复杂线框/手绘风格图标。
