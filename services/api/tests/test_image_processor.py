import io
from pathlib import Path

import pytest
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from app.services.image_processor import (
    AnimatedImageError,
    CorruptImageError,
    FileTooLargeError,
    PixelLimitExceededError,
    UnsupportedFormatError,
    process_and_normalize_image,
    stream_upload_to_temp_file,
)


def _make_image_bytes(
    fmt: str = "JPEG",
    size: tuple[int, int] = (100, 100),
    mode: str = "RGB",
    color="blue",
    exif: Image.Exif | None = None,
) -> bytes:
    buf = io.BytesIO()
    im = Image.new(mode, size, color=color)
    kwargs = {}
    if exif is not None:
        kwargs["exif"] = exif
    im.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def test_valid_jpeg(tmp_path: Path) -> None:
    source = tmp_path / "test.jpg"
    target = tmp_path / "out.jpg"
    source.write_bytes(_make_image_bytes("JPEG", (120, 180)))

    w, h, size = process_and_normalize_image(source, target)
    assert (w, h) == (120, 180)
    assert size > 0
    assert target.exists()

    with Image.open(target) as res:
        assert res.format == "JPEG"
        assert res.mode == "RGB"
        assert res.size == (120, 180)


def test_valid_png(tmp_path: Path) -> None:
    source = tmp_path / "test.png"
    target = tmp_path / "out.jpg"
    source.write_bytes(_make_image_bytes("PNG", (150, 150)))

    w, h, size = process_and_normalize_image(source, target)
    assert (w, h) == (150, 150)
    assert size > 0
    with Image.open(target) as res:
        assert res.format == "JPEG"
        assert res.mode == "RGB"


def test_valid_webp(tmp_path: Path) -> None:
    source = tmp_path / "test.webp"
    target = tmp_path / "out.jpg"
    source.write_bytes(_make_image_bytes("WEBP", (80, 120)))

    w, h, size = process_and_normalize_image(source, target)
    assert (w, h) == (80, 120)
    assert size > 0
    with Image.open(target) as res:
        assert res.format == "JPEG"
        assert res.mode == "RGB"


def test_exif_rotation(tmp_path: Path) -> None:
    # 200w x 100h with EXIF orientation 6 (90 deg CW) -> result should be 100w x 200h
    im = Image.new("RGB", (200, 100), color="red")
    exif = im.getexif()
    exif[0x0112] = 6  # Orientation 6
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)

    source = tmp_path / "rotated.jpg"
    target = tmp_path / "out.jpg"
    source.write_bytes(buf.getvalue())

    w, h, _ = process_and_normalize_image(source, target)
    assert (w, h) == (100, 200)

    with Image.open(target) as res:
        assert res.size == (100, 200)


def test_transparent_png_flattened_on_white(tmp_path: Path) -> None:
    # RGBA with 50% opacity red: (255, 0, 0, 128)
    im = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    im.save(buf, format="PNG")

    source = tmp_path / "alpha.png"
    target = tmp_path / "out.jpg"
    source.write_bytes(buf.getvalue())

    w, h, _ = process_and_normalize_image(source, target)
    assert (w, h) == (50, 50)

    with Image.open(target) as res:
        assert res.mode == "RGB"
        # Over white, red (255, 0, 0) at 50% alpha becomes pink (~255, 127, 127)
        r, g, b = res.getpixel((25, 25))
        assert r > 200
        assert 100 < g < 150
        assert 100 < b < 150


def test_grayscale_and_cmyk_conversion(tmp_path: Path) -> None:
    # 1. Grayscale
    source_gray = tmp_path / "gray.png"
    target_gray = tmp_path / "out_gray.jpg"
    source_gray.write_bytes(_make_image_bytes("PNG", (60, 60), mode="L", color=128))

    w, h, _ = process_and_normalize_image(source_gray, target_gray)
    assert (w, h) == (60, 60)
    with Image.open(target_gray) as res:
        assert res.mode == "RGB"

    # 2. CMYK
    source_cmyk = tmp_path / "cmyk.jpg"
    target_cmyk = tmp_path / "out_cmyk.jpg"
    im_cmyk = Image.new("CMYK", (70, 70), (0, 255, 255, 0))
    buf = io.BytesIO()
    im_cmyk.save(buf, format="JPEG")
    source_cmyk.write_bytes(buf.getvalue())

    w, h, _ = process_and_normalize_image(source_cmyk, target_cmyk)
    assert (w, h) == (70, 70)
    with Image.open(target_cmyk) as res:
        assert res.mode == "RGB"


def test_proportional_downscaling(tmp_path: Path) -> None:
    # 400x200 downscaled with max_dimension=200 -> 200x100
    source = tmp_path / "big.jpg"
    target = tmp_path / "out.jpg"
    source.write_bytes(_make_image_bytes("JPEG", (400, 200)))

    w, h, _ = process_and_normalize_image(source, target, max_dimension=200)
    assert (w, h) == (200, 100)

    with Image.open(target) as res:
        assert res.size == (200, 100)


def test_no_upscaling_small_image(tmp_path: Path) -> None:
    # 80x50 with max_dimension=1000 should stay 80x50
    source = tmp_path / "small.jpg"
    target = tmp_path / "out.jpg"
    source.write_bytes(_make_image_bytes("JPEG", (80, 50)))

    w, h, _ = process_and_normalize_image(source, target, max_dimension=1000)
    assert (w, h) == (80, 50)
    with Image.open(target) as res:
        assert res.size == (80, 50)


def test_metadata_stripped(tmp_path: Path) -> None:
    im = Image.new("RGB", (100, 100), color="green")
    exif = im.getexif()
    exif[0x010E] = "Test Image Description"
    exif[0x0112] = 1
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)

    source = tmp_path / "with_exif.jpg"
    target = tmp_path / "out.jpg"
    source.write_bytes(buf.getvalue())

    process_and_normalize_image(source, target)
    with Image.open(target) as res:
        saved_exif = res.getexif()
        assert len(saved_exif) == 0


def test_corrupt_image(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.jpg"
    target = tmp_path / "out.jpg"
    valid = _make_image_bytes("JPEG", (100, 100))
    # Truncate halfway
    source.write_bytes(valid[: len(valid) // 3])

    with pytest.raises(CorruptImageError):
        process_and_normalize_image(source, target)
    assert not target.exists()


def test_false_extension_rejected(tmp_path: Path) -> None:
    # Text file saved with .jpg extension
    source = tmp_path / "fake.jpg"
    target = tmp_path / "out.jpg"
    source.write_text("Hello World not an image")

    with pytest.raises(UnsupportedFormatError):
        process_and_normalize_image(source, target)
    assert not target.exists()


def test_unsupported_format_gif(tmp_path: Path) -> None:
    source = tmp_path / "test.gif"
    target = tmp_path / "out.jpg"
    im = Image.new("RGB", (50, 50), color="purple")
    buf = io.BytesIO()
    im.save(buf, format="GIF")
    source.write_bytes(buf.getvalue())

    with pytest.raises(UnsupportedFormatError) as exc_info:
        process_and_normalize_image(source, target)
    assert exc_info.value.status_code == 415
    assert not target.exists()


def test_animated_webp_rejected(tmp_path: Path) -> None:
    # Multiframe animated WebP
    im1 = Image.new("RGB", (50, 50), color="red")
    im2 = Image.new("RGB", (50, 50), color="blue")
    buf = io.BytesIO()
    im1.save(buf, format="WEBP", save_all=True, append_images=[im2])

    source = tmp_path / "animated.webp"
    target = tmp_path / "out.jpg"
    source.write_bytes(buf.getvalue())

    with pytest.raises(AnimatedImageError):
        process_and_normalize_image(source, target)
    assert not target.exists()


def test_pixel_count_limit(tmp_path: Path) -> None:
    source = tmp_path / "pixels.png"
    target = tmp_path / "out.jpg"
    # 200x200 = 40,000 pixels; limit set to 30,000
    source.write_bytes(_make_image_bytes("PNG", (200, 200)))

    with pytest.raises(PixelLimitExceededError) as exc_info:
        process_and_normalize_image(source, target, max_pixels=30000)
    assert exc_info.value.code == "PIXEL_LIMIT_EXCEEDED"
    assert not target.exists()


@pytest.mark.asyncio
async def test_stream_upload_chunk_byte_limit(tmp_path: Path) -> None:
    # 500 bytes payload with max_bytes=200
    payload = b"X" * 500
    headers = Headers({"content-type": "image/jpeg"})
    upload = UploadFile(
        file=io.BytesIO(payload),
        filename="test.jpg",
        headers=headers,
    )

    with pytest.raises(FileTooLargeError):
        await stream_upload_to_temp_file(
            upload_file=upload,
            temp_dir=tmp_path / "temp",
            max_bytes=200,
            chunk_size=64,
        )
