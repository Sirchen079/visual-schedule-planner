"""生成 desktop/build/icon.ico 与 icon-256.png。

用 Pillow 绘制「知时」应用图标：紫色渐变圆角背景 + 白色时钟（10:10 姿势），
呼应项目 favicon 的紫色 (#863bff) 与「知时」的时间主题。

用法：python desktop/scripts/build-icon.py
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "desktop" / "build"
BUILD.mkdir(parents=True, exist_ok=True)

SIZE = 1024

# 紫色渐变（呼应 favicon #863bff）
GRAD_TOP = (0xA0, 0x60, 0xFF)
GRAD_BOT = (0x55, 0x1C, 0xD8)
WHITE = (255, 255, 255, 255)


def _gradient_bg() -> Image.Image:
    """圆角矩形 + 垂直紫色渐变 + 左上柔光。"""
    # 垂直渐变：1 像素宽条逐行填色，再水平拉伸（避免逐像素填 1024×1024 过慢）
    bar = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(int(GRAD_TOP[i] + (GRAD_BOT[i] - GRAD_TOP[i]) * t) for i in range(3))
        bar.putpixel((0, y), color)
    grad = bar.resize((SIZE, SIZE))

    # 圆角 mask
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=224, fill=255)

    bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bg.paste(grad, (0, 0), mask)

    # 左上柔光（椭圆 + 高斯模糊，提升质感）
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [-SIZE * 0.25, -SIZE * 0.25, SIZE * 0.55, SIZE * 0.55], fill=(255, 255, 255, 70)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(SIZE * 0.08))
    return Image.alpha_composite(bg, glow)


def _draw_hand(draw, cx, cy, angle_deg, length, width, fill):
    """从中心画一根钟表指针（0°=12 点方向，顺时针为正）。"""
    a = math.radians(angle_deg - 90)
    x2 = cx + math.cos(a) * length
    y2 = cy + math.sin(a) * length
    draw.line([(cx, cy), (x2, y2)], fill=fill, width=width)
    r = width // 2
    draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=fill)  # 端点圆头


def _draw_clock_icon() -> Image.Image:
    img = _gradient_bg()
    draw = ImageDraw.Draw(img)

    cx = cy = SIZE // 2
    radius = int(SIZE * 0.30)

    # 外圆环
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        outline=WHITE, width=int(SIZE * 0.028),
    )

    # 12 / 3 / 6 / 9 点刻度（短粗线）
    tick_len = int(SIZE * 0.055)
    tick_w = int(SIZE * 0.022)
    inner = radius - tick_len
    for ang in (0, 90, 180, 270):
        a = math.radians(ang - 90)
        x1, y1 = cx + math.cos(a) * inner, cy + math.sin(a) * inner
        x2, y2 = cx + math.cos(a) * radius, cy + math.sin(a) * radius
        draw.line([(x1, y1), (x2, y2)], fill=WHITE, width=tick_w)

    # 指针：10:10 姿势（视觉对称、正面积极）
    _draw_hand(draw, cx, cy, angle_deg=300, length=int(radius * 0.52),
               width=int(SIZE * 0.038), fill=WHITE)  # 时针 → 10
    _draw_hand(draw, cx, cy, angle_deg=60, length=int(radius * 0.78),
               width=int(SIZE * 0.026), fill=WHITE)  # 分针 → 2

    # 中心轴
    cr = int(SIZE * 0.022)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=WHITE)
    return img


def main() -> None:
    img = _draw_clock_icon()
    img.save(BUILD / "icon-1024.png")
    img.resize((256, 256), Image.LANCZOS).save(BUILD / "icon-256.png")
    img.save(
        BUILD / "icon.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"图标已生成于 {BUILD}（紫色渐变 + 白色时钟 10:10）")


if __name__ == "__main__":
    main()
