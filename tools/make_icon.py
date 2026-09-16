# -*- coding: utf-8 -*-
"""工程化重绘独立产品图标（IMP-002）。

设计：靛蓝圆角底 + 白色叠放配置卡片 + 青绿切换开关。
与 ChatGPT 的云/螺旋符号完全不同，独立可辨识，小尺寸清晰。

这是根据文字描述做的矢量式程序化重绘，不读取/不编辑任何输入照片。
输出：
  assets/codex-config-manager.ico   （多尺寸 16/24/32/48/64/128/256）
  assets/icon.png                   （512，供文档/界面引用）
  outputs/icon.png                  （512，交付物）
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "outputs")
os.makedirs(ASSETS, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# ---- 配色（与界面主题一致） ----
INDIGO_TOP = (99, 102, 241)     # #6366F1
INDIGO_BOT = (67, 56, 202)      # #4338CA
WHITE = (255, 255, 255)
CARD_SHADOW = (15, 23, 42)      # #0F172A
ROW = (203, 213, 225)           # #CBD5E1 (配置行)
ROW_ACTIVE = (99, 102, 241)     # 选中行用靛蓝
TEAL_TRACK = (153, 246, 228)    # #99F6E4
TEAL_KNOB = (20, 184, 166)      # #14B8A6

SS = 1024  # 超采样基准


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_mask(size, radius, fill=255):
    """生成圆角矩形 alpha 蒙版。"""
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=fill)
    return m


def draw_master():
    img = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 背景：靛蓝垂直渐变 + 圆角
    bg = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    bgd = ImageDraw.Draw(bg)
    for y in range(SS):
        t = y / (SS - 1)
        bgd.line([(0, y), (SS, y)], fill=lerp(INDIGO_TOP, INDIGO_BOT, t) + (255,))
    mask = rounded_mask(SS, int(SS * 0.22))
    img = Image.composite(bg, img, mask)

    # 顶部高光（左上柔光）
    hl = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    hld = ImageDraw.Draw(hl)
    hld.ellipse([-SS * 0.15, -SS * 0.25, SS * 0.7, SS * 0.55],
                fill=(255, 255, 255, 46))
    img = Image.alpha_composite(img, hl)

    d = ImageDraw.Draw(img)
    R = int(SS * 0.07)

    def card(x0, y0, x1, y1, fill=WHITE, alpha=255, shadow=True):
        if shadow:
            sh = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
            sd = ImageDraw.Draw(sh)
            sd.rounded_rectangle([x0 + 18, y0 + 34, x1 + 18, y1 + 34],
                                 radius=R, fill=CARD_SHADOW + (60,))
            img.alpha_composite(sh)
        d.rounded_rectangle([x0, y0, x1, y1], radius=R,
                            fill=fill + (alpha,))

    # 叠放的两张白色配置卡片（前卡略大、偏右下）
    card(286, 250, 724, 612, shadow=True)          # 后卡
    card(300, 322, 792, 720, shadow=True)          # 前卡（主）

    # 前卡上的配置行
    def row(x0, y, w, h=22, color=ROW):
        d.rounded_rectangle([x0, y, x0 + w, y + h], radius=h // 2, fill=color + (255,))
    row(372, 392, 300)
    row(372, 446, 220, color=ROW_ACTIVE)           # 选中行（靛蓝）
    row(372, 500, 330)

    # 青绿切换开关（前卡底部）
    sx0, sy0, sx1, sy1 = 372, 582, 632, 672
    d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=(sy1 - sy0) // 2,
                        fill=TEAL_TRACK + (255,))
    kr = (sy1 - sy0) // 2 - 10
    kx = sx1 - kr - 10
    ky = (sy0 + sy1) // 2
    d.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=TEAL_KNOB + (255,))
    return img


def main():
    master = draw_master()
    # 多尺寸 ICO
    sizes = [256, 128, 64, 48, 32, 24, 16]
    frames = []
    for s in sizes:
        f = master.resize((s, s), Image.LANCZOS)
        frames.append(f.convert("RGBA"))
    ico = os.path.join(ASSETS, "codex-config-manager.ico")
    base = master.resize((512, 512), Image.LANCZOS).convert("RGBA")
    base.save(ico, sizes=[(s, s) for s in sizes])
    # PNG 交付
    png512 = master.resize((512, 512), Image.LANCZOS).convert("RGBA")
    png512.save(os.path.join(ASSETS, "icon.png"))
    png512.save(os.path.join(OUT, "icon.png"))
    print("OK icon generated")
    print("ico:", ico, os.path.getsize(ico), "bytes")
    print("png:", os.path.join(OUT, "icon.png"), os.path.getsize(os.path.join(OUT, "icon.png")), "bytes")
    print("sizes:", sizes)


if __name__ == "__main__":
    main()
