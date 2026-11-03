"""Cover photos for recipes: one WebP per recipe in the data volume, resized and stripped of metadata."""
import io
import os
import time

from PIL import Image, ImageOps, UnidentifiedImageError

from . import config, store

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SIDE = 1200
Image.MAX_IMAGE_PIXELS = 60_000_000  # refuse decompression bombs


class BadImage(ValueError):
    pass


def path_for(recipe_id: int):
    return config.DATA_DIR / "images" / f"{recipe_id}.webp"


def save_cover(recipe_id: int, data: bytes) -> dict:
    """Validate, orient, shrink and store an uploaded photo. Raises BadImage if it isn't a usable picture."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise BadImage("That photo is too large (15 MB max).")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise BadImage("That file isn't a picture I can read (try a JPEG or PNG).") from e
    img = ImageOps.exif_transpose(img)  # phone photos carry their rotation in metadata
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = background
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    dest = path_for(recipe_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    img.save(tmp, "WEBP", quality=82, method=6)  # re-encoding also drops EXIF/GPS
    os.replace(tmp, dest)
    return store.set_cover(recipe_id, int(time.time()))


def remove_cover(recipe_id: int) -> dict | None:
    path_for(recipe_id).unlink(missing_ok=True)
    return store.set_cover(recipe_id, None)
