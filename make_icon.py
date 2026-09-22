"""
cat_timer.ico 生成スクリプト
5.png をカバー表示（正方形いっぱいに拡大・はみ出し分を中央クロップ）
"""
from PIL import Image
import os

SRC     = os.path.join(os.path.dirname(__file__), "5.png")
OUT_ICO = os.path.join(os.path.dirname(__file__), "cat_timer.ico")
OUT_PNG = os.path.join(os.path.dirname(__file__), "icon_preview.png")

BG = (26, 26, 46)  # #1a1a2e

src = Image.open(SRC).convert("RGBA")

# 非透明領域のバウンディングボックスでトリム
bbox = src.getbbox()
if bbox:
    src = src.crop(bbox)

side = 512
w, h = src.size

# カバー表示: 正方形に収まるよう短辺(高さ)を基準に拡大し、長辺をセンタークロップ
scale = side / min(w, h)
cover_w = int(w * scale)
cover_h = int(h * scale)
covered = src.resize((cover_w, cover_h), Image.LANCZOS)

# 中央 512×512 クロップ
cx = (cover_w - side) // 2
cy = (cover_h - side) // 2
cropped = covered.crop((cx, cy, cx + side, cy + side))

# ダーク背景 RGB キャンバスにアルファ合成
final = Image.new("RGB", (side, side), BG)
r, g, b, a = cropped.split()
final.paste(Image.merge("RGB", (r, g, b)), (0, 0), mask=a)

sizes  = [256, 128, 64, 48, 32, 16]
layers = [final.resize((s, s), Image.LANCZOS) for s in sizes]

layers[0].save(
    OUT_ICO,
    format="ICO",
    sizes=[(s, s) for s in sizes],
    append_images=layers[1:],
)
layers[0].save(OUT_PNG)

print(f"元サイズ: {w}×{h} → カバー拡大 {cover_w}×{cover_h} → 中央クロップ {side}×{side}")
print(f"ico → {OUT_ICO}")
print(f"preview → {OUT_PNG}")
