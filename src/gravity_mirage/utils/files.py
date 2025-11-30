from pathlib import Path

from fastapi import HTTPException, status

from gravity_mirage.web.constants import (
    ALLOWED_EXTENSIONS,
    EXPORT_FOLDER,
    UPLOAD_FOLDER,
)


def resolve_uploaded_file(filename: str) -> Path:
    """Ensure the requested filename lives inside the uploads folder."""
    clean_name = Path(filename).name
    target = (UPLOAD_FOLDER / clean_name).resolve()
    base = UPLOAD_FOLDER.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        ) from exc
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return target


def resolve_export_file(filename: str) -> Path:
    """Ensure the requested filename lives inside the exports folder."""
    clean_name = Path(filename).name
    target = (EXPORT_FOLDER / clean_name).resolve()
    base = EXPORT_FOLDER.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        ) from exc
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return target


def allocate_image_path(extension: str) -> Path:
    """Pick the next sequential image<N> filename."""
    max_index = 0
    for existing in UPLOAD_FOLDER.iterdir():
        if existing.is_file() and existing.stem.startswith("image"):
            suffix = existing.stem[5:]
            if suffix.isdigit():
                max_index = max(max_index, int(suffix))
    return UPLOAD_FOLDER / f"image{max_index + 1}{extension}"


def allocate_export_path(extension: str = ".gif") -> Path:
    """Pick the next sequential image<N> filename for the exports folder."""
    max_index = 0
    for existing in EXPORT_FOLDER.iterdir():
        if existing.is_file() and existing.stem.startswith("image"):
            suffix = existing.stem[5:]
            if suffix.isdigit():
                max_index = max(max_index, int(suffix))
    return EXPORT_FOLDER / f"image{max_index + 1}{extension}"


def sanitize_extension(extension: str | None) -> str:
    """Normalize and validate the user-provided extension."""
    if not extension:
        return ".png"
    extension = extension.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return ".png"
    return extension


def list_exported_images() -> list[str]:
    """Return the filenames that currently exist in the exports directory."""
    return sorted([f.name for f in EXPORT_FOLDER.iterdir() if f.is_file()])


def list_uploaded_images() -> list[str]:
    """Return the filenames that currently exist in the upload directory."""
    return sorted([f.name for f in UPLOAD_FOLDER.iterdir() if f.is_file()])
