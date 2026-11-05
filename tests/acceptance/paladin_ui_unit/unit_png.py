import binascii
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def chunk(kind, data):
    return (
        struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data))
    )


def encode(width, height, rgba):
    assert width in (375, 1280) and height == 800
    row = b"\0" + bytes(rgba) * width
    return (
        SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def decode_unit_rgba(raw):
    assert len(raw) <= 8 * 1024 * 1024 and raw.startswith(SIGNATURE)
    offset, compressed, dimensions, ended = 8, [], None, False
    while offset < len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        data = raw[offset + 8 : offset + 8 + length]
        assert len(data) == length
        crc = raw[offset + 8 + length : offset + 12 + length]
        assert len(crc) == 4 and struct.unpack(">I", crc)[0] == binascii.crc32(kind + data)
        offset += length + 12
        if kind == b"IHDR":
            assert dimensions is None and len(data) == 13
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            assert width in (375, 1280) and height == 800
            assert (depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0)
            dimensions = width, height
        elif kind == b"IDAT":
            assert dimensions is not None
            compressed.append(data)
        elif kind == b"IEND":
            assert data == b"" and offset == len(raw)
            ended = True
        else:
            raise AssertionError("Unexpected deterministic unit PNG chunk")
    assert ended and dimensions is not None
    width, height = dimensions
    expected = height * (1 + width * 4)
    decoder = zlib.decompressobj()
    rows = decoder.decompress(b"".join(compressed), expected + 1)
    assert len(rows) == expected and decoder.eof
    assert not decoder.unused_data and not decoder.unconsumed_tail
    pixels = bytearray()
    stride = width * 4 + 1
    for offset in range(0, expected, stride):
        assert rows[offset] == 0
        pixels.extend(rows[offset + 1 : offset + stride])
    return width, height, bytes(pixels)


def verify_identical_metric(baseline, current, observation):
    left, right = decode_unit_rgba(baseline), decode_unit_rgba(current)
    assert left == right
    assert observation["mismatched_pixels"] == observation["exact_changed_pixels"] == 0
    assert observation["diff_ratio"] == 0
