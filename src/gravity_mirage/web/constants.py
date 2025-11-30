from pathlib import Path

# Directory used to persist uploaded assets.
UPLOAD_FOLDER = Path.cwd() / "uploads"
"""Directory used to persist uploaded assets"""
UPLOAD_FOLDER.mkdir(
    parents=True,
    exist_ok=True,
)

# Directory for exported GIFs
EXPORT_FOLDER = Path.cwd() / "exports"
"""Directory for exported GIFs"""
EXPORT_FOLDER.mkdir(
    parents=True,
    exist_ok=True,
)

ALLOWED_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tiff",
    ".webp",
)

ALLOWED_METHODS = (
    "weak",
    "geodesic",
)

PREVIEW_WIDTH = 512
CHUNK_SIZE = 1 << 20  # 1 MiB chunks while streaming uploads to disk.

__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_METHODS",
    "CHUNK_SIZE",
    "EXPORT_FOLDER",
    "PREVIEW_WIDTH",
    "UPLOAD_FOLDER",
]
