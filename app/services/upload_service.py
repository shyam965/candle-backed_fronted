"""Image upload validation, storage and deletion (FR-118–FR-122, D-12, D-35)."""

from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from anyio import to_thread
from starlette.datastructures import FormData, UploadFile

from app.core.errors import PayloadTooLarge, ValidationFailed

log = logging.getLogger("akrf.uploads")

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9]{1,10})?$")
TYPE_MESSAGE = "Only JPG, PNG and WebP images are allowed"


@dataclass(frozen=True)
class ImageUpload:
    data: bytes
    extension: str
    content_type: str


def detect_image(data: bytes) -> tuple[str, str] | None:
    """Identify JPEG / PNG / WebP from magic bytes; the client-declared type is never trusted."""
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


def _is_real_file(value: object) -> bool:
    # Browsers submit an empty part (no filename, no bytes) when no file is chosen.
    return isinstance(value, UploadFile) and bool(value.filename or (value.size or 0) > 0)


async def extract_image(form: FormData, max_bytes: int, *, field: str = "image") -> ImageUpload | None:
    """Return the single uploaded image from `form`, None if none was chosen, or raise 400/413."""
    files = [(key, value) for key, value in form.multi_items() if _is_real_file(value)]
    if any(key != field for key, _ in files):
        raise ValidationFailed("Unexpected file field. Upload the image in the image field.", field=field)
    if len(files) > 1:
        raise ValidationFailed("Only one image file is allowed", field=field)
    if not files:
        return None
    upload: UploadFile = files[0][1]  # type: ignore[assignment]
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLarge(f"Image must be under {max_bytes // (1024 * 1024)} MB", field=field)
    kind = detect_image(data)
    if kind is None:
        raise ValidationFailed(TYPE_MESSAGE, field=field)
    return ImageUpload(data=data, extension=kind[0], content_type=kind[1])


class UploadStore:
    """Files live in UPLOAD_DIR and are referenced in the DB as `/uploads/<name>` (FR-121, FR-122)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def ensure_dir(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path | None:
        if not SAFE_NAME.match(name):
            return None
        return self.directory / name

    async def save(self, image: ImageUpload) -> str:
        self.ensure_dir()

        def _write() -> str:
            for _ in range(5):
                name = f"{int(time.time() * 1000)}-{secrets.randbelow(1_000_000_001)}{image.extension}"
                try:
                    with open(self.directory / name, "xb") as handle:
                        handle.write(image.data)
                except FileExistsError:
                    continue
                return name
            raise RuntimeError("could not allocate a unique upload filename")

        name = await to_thread.run_sync(_write)
        return f"/uploads/{name}"

    async def delete(self, stored: str | None) -> None:
        """Delete a stored `/uploads/<name>` file; missing files are ignored (BE §7.4)."""
        if not isinstance(stored, str) or not stored.startswith("/uploads/"):
            return
        path = self.path_for(stored.rsplit("/", 1)[-1])
        if path is None:
            return
        try:
            await to_thread.run_sync(lambda: path.unlink(missing_ok=True))
        except OSError as exc:
            log.warning("Image delete error: %s", exc)
