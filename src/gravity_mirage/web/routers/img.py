from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(
    prefix="/img",
)


@router.get("/{filename:path}")
async def img_file(filename: str) -> FileResponse:
    """
    Serve files from the repository's ./img/ directory (for repo assets).

    This lets the template reference `/img/milky-way.gif`
    without requiring the user to re-upload the asset into uploads/.
    """
    # Ensure we don't allow path traversal outside the img directory.
    img_base = (Path.cwd() / "img").resolve()
    target = (img_base / Path(filename).name).resolve()
    try:
        target.relative_to(img_base)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        ) from e
    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return FileResponse(target)


__all__ = ["router"]
