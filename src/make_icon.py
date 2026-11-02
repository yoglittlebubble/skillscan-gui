# -*- coding: utf-8 -*-
"""生成 SkillSpector 体检台的盾牌图标（PNG 预览 + 多尺寸 ICO）。"""

import math
import os

from PIL import Image, ImageDraw

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SS = 1024          # 超采样画布
TOP_COLOR = (74, 144, 226)
BOTTOM_COLOR = (23, 43, 92)


def qbez(p0, p1, p2, n=48):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def shield_path(size):
    """经典徽章盾形：上沿略弧、肩部圆、下摆收成尖。"""
    s = size

    def P(x, y):
        return (x * s, y * s)

    pts = []
    pts += qbez(P(0.50, 0.030), P(0.215, 0.030), P(0.080, 0.130))     # 上沿左半（圆肩）
    pts += qbez(P(0.080, 0.130), P(0.072, 0.290), P(0.092, 0.450))   # 左侧竖直微收
    pts += qbez(P(0.092, 0.450), P(0.120, 0.730), P(0.50, 0.975))    # 左摆收尖
    pts += qbez(P(0.50, 0.975), P(0.880, 0.730), P(0.908, 0.450))    # 右摆
    pts += qbez(P(0.908, 0.450), P(0.928, 0.290), P(0.920, 0.130))   # 右侧竖直微收
    pts += qbez(P(0.920, 0.130), P(0.785, 0.030), P(0.50, 0.030))    # 上沿右半（圆肩）
    return pts


def gradient(size, top, bottom):
    img = Image.new("RGB", (1, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        # 轻微缓动，让顶部亮区更集中
        t = t ** 0.85
        d.point((0, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img.resize((size, size))


def make_master(size=SS):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(shield_path(size), fill=255)

    img = gradient(size, TOP_COLOR, BOTTOM_COLOR).convert("RGBA")
    img.putalpha(mask)

    # 顶部柔光：随高度渐隐，避免出现生硬的亮带边界
    ramp = Image.new("L", (1, size))
    for y in range(size):
        t = min(1.0, y / (size * 0.55))
        ramp.putpixel((0, y), max(0, int(52 * (1 - t) ** 1.6)))
    gloss = ramp.resize((size, size))
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    img = Image.alpha_composite(img, Image.composite(white, Image.new("RGBA", (size, size), (0, 0, 0, 0)), gloss))

    # 内描边（深一点的轮廓，让边缘在浅色背景上不飘）
    edge = Image.new("L", (size, size), 0)
    ImageDraw.Draw(edge).polygon(shield_path(size), outline=255, width=max(2, size // 170))
    img = Image.alpha_composite(
        img, Image.composite(Image.new("RGBA", (size, size), (255, 255, 255, 90)),
                             Image.new("RGBA", (size, size), (0, 0, 0, 0)), edge)
    )

    # 对勾
    d = ImageDraw.Draw(img)
    lw = int(size * 0.115)
    pts = [
        (int(size * 0.285), int(size * 0.515)),
        (int(size * 0.435), int(size * 0.660)),
        (int(size * 0.735), int(size * 0.335)),
    ]
    d.line(pts, fill=(255, 255, 255, 255), width=lw, joint="curve")
    for p in (pts[0], pts[-1]):  # 圆头
        r = lw / 2 - 1
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(255, 255, 255, 255))
    return img


def main():
    master = make_master(SS)
    master.save(os.path.join(OUT_DIR, "icon_1024.png"))
    master.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT_DIR, "icon_256.png"))

    # 小尺寸单独降采样，避免细节糊掉
    sizes = [256, 128, 64, 48, 32, 24, 16]
    frames = [master.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[0].save(
        os.path.join(OUT_DIR, "icon.ico"),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print("ok:", os.path.join(OUT_DIR, "icon.ico"))


if __name__ == "__main__":
    main()
