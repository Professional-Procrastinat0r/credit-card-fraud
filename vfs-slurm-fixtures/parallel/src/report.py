"""A PNG report with no optional plotting dependencies."""

import struct
import zlib

from expops.reporting import chart


@chart()
def report(metrics, ctx):
    total = metrics["summary"]["total"]["1"]
    width, height = 128, 16
    filled = int(abs(total)) % width
    row = b"\x00" + b"\x30\xb0\x60" * filled + b"\xe0\xe0\xe0" * (width - filled)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))
    (ctx.output_dir / "parallel.png").write_bytes(png)
