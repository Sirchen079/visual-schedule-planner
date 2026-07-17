#!/usr/bin/env python3
"""生成「知时」应用图标:水滴 + 时钟融合,sea-glass 海玻璃质感。

用法(项目根目录):
    backend/.venv/Scripts/python.exe desktop/scripts/build-icon.py

输出(desktop/build/):
    icon-1024.png  主图源
    icon-256.png   托盘/常规用途
    icon.ico       多尺寸(16/24/32/48/64/128/256)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

SS = 4                     # 超采样倍数
BASE = 1024
S = BASE * SS              # 4096 工作画布
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "build")


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_rgb(c1, c2, t):
    return tuple(round(lerp(a, b, t)) for a, b in zip(c1, c2))


def vgradient(size, stops):
    """垂直多段渐变。stops=[(pos, (r,g,b)), ...],pos ∈ [0,1]。"""
    w, h = size
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / (h - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                tt = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
                px[0, y] = lerp_rgb(c0, c1, tt)
                break
        else:
            px[0, y] = stops[-1][1]
    return col.resize((w, h))


def radial_glow(size, center, radius, color, peak_alpha):
    """柔和径向光晕(RGBA 层)。透明区域预填同色,避免高斯模糊从透明黑渗色产生暗边。"""
    layer = Image.new("RGBA", size, color + (0,))
    d = ImageDraw.Draw(layer)
    steps = 48
    for i in range(steps, 0, -1):
        r = radius * i / steps
        a = round(peak_alpha * (1 - i / steps) ** 1.6)
        if a <= 0:
            continue
        d.ellipse(
            [center[0] - r, center[1] - r, center[0] + r, center[1] + r],
            fill=color + (a,),
        )
    return layer.filter(ImageFilter.GaussianBlur(radius / 10))


def teardrop_points(cx, cy, R, apex_k=2.02, bulge=0.10, n_arc=180, n_side=56):
    """对称水滴轮廓点列:顶点在上,圆弧在下(y 向下)。"""
    A = (cx, cy - apex_k * R)
    theta = math.acos(1.0 / apex_k)          # 切点相对中轴的夹角
    aL = -math.pi / 2 - theta
    TL = (cx + R * math.cos(aL), cy + R * math.sin(aL))

    # 左侧边:顶点 -> 左切点,三次贝塞尔,中部向外微微鼓起
    dx, dy = TL[0] - A[0], TL[1] - A[1]
    L = math.hypot(dx, dy)
    nx, ny = dy / L, -dx / L                 # 朝左的外法线
    c1 = (A[0] + dx * 0.16, A[1] + dy * 0.16)
    c2 = (TL[0] - dx * 0.16 + nx * bulge * R, TL[1] - dy * 0.16 + ny * bulge * R)
    left = []
    for i in range(1, n_side + 1):
        t = i / n_side
        mt = 1 - t
        x = mt**3 * A[0] + 3 * mt**2 * t * c1[0] + 3 * mt * t * t * c2[0] + t**3 * TL[0]
        y = mt**3 * A[1] + 3 * mt**2 * t * c1[1] + 3 * mt * t * t * c2[1] + t**3 * TL[1]
        left.append((x, y))

    # 底部圆弧:左切点 -> 右切点,经过正下方
    start = math.degrees(aL)                 # 约 -155°
    end = -90 + math.degrees(theta)          # 约 -25°
    arc = []
    for i in range(1, n_arc + 1):
        t = i / n_arc
        ang = math.radians(start + (end - 360 - start) * t)
        arc.append((cx + R * math.cos(ang), cy + R * math.sin(ang)))

    right = [(2 * cx - x, y) for (x, y) in reversed(left)]
    return [A] + left + arc + right


def render(size, small=False):
    """渲染 size×size 图标(RGBA)。small=True 时加粗笔画、省略细节,供小尺寸。"""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # --- 底板:squircle + 海玻璃渐变 ---
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=s * 0.225, fill=255
    )
    bg = vgradient(
        (s, s),
        [(0.0, (191, 236, 247)), (0.42, (96, 193, 222)), (1.0, (36, 134, 175))],
    ).convert("RGBA")
    img.paste(bg, (0, 0), mask)
    # 右下青绿晕染 + 左上环境光
    img.alpha_composite(radial_glow((s, s), (s * 0.86, s * 0.94), s * 0.78, (67, 191, 165), 105))
    img.alpha_composite(radial_glow((s, s), (s * 0.16, s * 0.08), s * 0.80, (255, 255, 255), 115))

    # --- 水滴几何 ---
    cx, cy, R = s / 2, s * 0.568, s * 0.228
    pts = teardrop_points(cx, cy, R)
    dmask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(dmask).polygon(pts, fill=255)

    # 水滴投影(先画,垫在水滴下)
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(
        [(x + s * 0.006, y + s * 0.014) for (x, y) in pts], fill=(14, 72, 98, 90)
    )
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s * 0.012)))

    # 水滴玻璃体:近白渐变
    fill = vgradient(
        (s, s),
        [(0.0, (255, 255, 255)), (0.55, (238, 250, 253)), (1.0, (206, 236, 246))],
    ).convert("RGBA")
    img.paste(fill, (0, 0), dmask)

    # 水滴内部:顶部高光 + 底部水色反光
    inner = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    inner.alpha_composite(
        radial_glow((s, s), (cx - R * 0.34, cy - R * 1.05), R * 1.05, (255, 255, 255), 150)
    )
    inner.alpha_composite(
        radial_glow((s, s), (cx + R * 0.30, cy + R * 0.72), R * 0.95, (94, 190, 220), 70)
    )
    img.paste(inner, (0, 0), Image.composite(inner.getchannel("A"), Image.new("L", (s, s), 0), dmask))

    # 水滴描边:外圈亮边 + 内圈深色细边(小尺寸加粗)
    rim = ImageDraw.Draw(img)
    closed = pts + [pts[0]]
    rim.line(closed, fill=(255, 255, 255, 200), width=max(2, round(s * (0.009 if small else 0.006))), joint="curve")
    rim.line(closed, fill=(23, 105, 143, 80), width=max(1, round(s * 0.003)), joint="curve")

    # --- 时钟指针(10:10,经典友好角度)---
    hand_w = max(2, round(s * (0.042 if small else 0.028)))
    hand_c = (18, 92, 118, 255)
    d = ImageDraw.Draw(img)

    def hand(angle_deg, length, width):
        a = math.radians(angle_deg)
        x2, y2 = cx + length * math.cos(a), cy + length * math.sin(a)
        d.line([cx, cy, x2, y2], fill=hand_c, width=width)
        r = width / 2
        d.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=hand_c)

    hand(-150, R * 0.46, hand_w)          # 时针指向 10
    hand(-30, R * 0.62, hand_w)           # 分针指向 2
    # 中心轴点:白环深心
    r0 = hand_w * 0.92
    d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], fill=(255, 255, 255, 255))
    r1 = hand_w * 0.55
    d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], fill=hand_c)

    # 刻度点(小尺寸省略)
    if not small:
        for ang in (-90, 0, 90, 180):
            a = math.radians(ang)
            tx, ty = cx + R * 0.78 * math.cos(a), cy + R * 0.78 * math.sin(a)
            tr = s * 0.0065
            d.ellipse([tx - tr, ty - tr, tx + tr, ty + tr], fill=(18, 92, 118, 120))

    # 左上角镜面高光(玻璃感);透明区预填白色防模糊暗边
    spec = Image.new("RGBA", (s, s), (255, 255, 255, 0))
    ImageDraw.Draw(spec).ellipse(
        [s * 0.10, s * 0.045, s * 0.52, s * 0.24], fill=(255, 255, 255, 95)
    )
    spec = spec.filter(ImageFilter.GaussianBlur(s * 0.02))
    img.alpha_composite(spec)

    # --- 按 squircle 重新裁剪,外圈细边 ---
    alpha = Image.composite(img.getchannel("A"), Image.new("L", (s, s), 0), mask)
    img.putalpha(alpha)
    edge = ImageDraw.Draw(img)
    edge.rounded_rectangle(
        [s * 0.004, s * 0.004, s * 0.996, s * 0.996],
        radius=s * 0.225,
        outline=(255, 255, 255, 90),
        width=max(1, round(s * 0.004)),
    )
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    master = render(S).resize((BASE, BASE), Image.LANCZOS)
    p1024 = os.path.join(OUT_DIR, "icon-1024.png")
    master.save(p1024)

    p256 = os.path.join(OUT_DIR, "icon-256.png")
    master.resize((256, 256), Image.LANCZOS).save(p256)

    # ICO:≤48 用加粗笔画的小尺寸变体,其余由主图降采样。
    # Pillow 的 ICO 保存不支持逐帧定制(sizes 参数会全部重采样同一图),
    # 而 ICO 容器格式很简单,手动拼装 PNG 帧以获得逐尺寸控制。
    import io
    import struct

    small_master = render(512, small=True)
    frames = []
    for sz in (16, 24, 32, 48):
        frames.append((sz, small_master.resize((sz, sz), Image.LANCZOS)))
    for sz in (64, 128, 256):
        frames.append((sz, master.resize((sz, sz), Image.LANCZOS)))

    blobs = []
    for sz, frame in frames:
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        blobs.append((sz, buf.getvalue()))

    ico_path = os.path.join(OUT_DIR, "icon.ico")
    with open(ico_path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(blobs)))
        offset = 6 + 16 * len(blobs)
        for sz, blob in blobs:
            f.write(
                struct.pack(
                    "<BBBBHHII",
                    0 if sz == 256 else sz,  # ICO 规范:256 记为 0
                    0 if sz == 256 else sz,
                    0,                        # 调色板色数(0=无)
                    0,                        # 保留
                    1,                        # 颜色平面
                    32,                       # 位深
                    len(blob),
                    offset,
                )
            )
            offset += len(blob)
        for _, blob in blobs:
            f.write(blob)

    print("written:", p1024, p256, ico_path, sep="\n  ")


if __name__ == "__main__":
    main()
