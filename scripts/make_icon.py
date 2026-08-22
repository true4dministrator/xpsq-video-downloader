#!/usr/bin/env python3
"""生成应用图标 resources/app.ico（纯标准库，PNG-in-ICO）。"""
import struct
import zlib
from pathlib import Path


def make_png(size: int, bg=(59, 130, 246, 255), fg=(255, 255, 255, 255)) -> bytes:
    """蓝底圆角方块 + 白色播放三角。"""
    import math
    rows = []
    r = size * 0.22
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            # 圆角判断
            corner = min(x, size - 1 - x, y, size - 1 - y)
            if corner < r:
                # 圆角外的角点透明度渐变
                cx = r - corner
                dx = min(x - 0, size - 1 - x, y - 0, size - 1 - y)
                if dx < r and (corner < r):
                    # 简化：四角做圆
                    pass
            # 播放三角：以中心为原点
            cx0, cy0 = size / 2, size / 2
            tx = (x - cx0) / size
            ty = (y - cy0) / size
            # 三角形顶点：(0,-0.28) (0.30,0) (0,-0.28) -> (0, -0.26) (0.28, 0) (0, 0.26)
            def in_tri(px, py):
                v0, v1, v2 = (0, -0.26), (0.28, 0), (0, 0.26)
                def sign(a, b, c):
                    return (a[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (a[1] - c[1])
                d1 = sign((px, py), v0, v1)
                d2 = sign((px, py), v1, v2)
                d3 = sign((px, py), v2, v0)
                neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
                pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
                return not (neg and pos)
            in_t = in_tri(tx, ty)
            # 圆角
            rad = size * 0.22
            dx0 = max(rad - x, 0)
            dy0 = max(rad - y, 0)
            dx1 = max(rad - (size - 1 - x), 0)
            dy1 = max(rad - (size - 1 - y), 0)
            in_corner = (dx0 * dx0 + dy0 * dy0 > rad * rad) or \
                        (dx1 * dx1 + dy0 * dy0 > rad * rad) or \
                        (dx0 * dx0 + dy1 * dy1 > rad * rad) or \
                        (dx1 * dx1 + dy1 * dy1 > rad * rad)
            if in_corner:
                row += bytes((0, 0, 0, 0))
            elif in_t:
                row += bytes(fg)
            else:
                row += bytes(bg)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def make_ico(png_data: bytes, size: int) -> bytes:
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
                        0, 0, 1, 32, len(png_data), 22)
    return header + entry + png_data


def main() -> None:
    out_dir = Path(__file__).parent.parent / "resources"
    out_dir.mkdir(exist_ok=True)
    size = 256
    png = make_png(size)
    (out_dir / "app.ico").write_bytes(make_ico(png, size))
    (out_dir / "app.png").write_bytes(png)
    print("icon generated:", out_dir / "app.ico")


if __name__ == "__main__":
    main()
