import io
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from gravity_mirage.core.lensing import render_lensing_image
from gravity_mirage.utils.files import resolve_uploaded_file
from gravity_mirage.web.constants import ALLOWED_METHODS, PREVIEW_WIDTH

router = APIRouter(
    prefix="/preview",
)


@router.get("/{filename}", response_class=StreamingResponse)
async def preview(
    filename: str,
    mass: Annotated[float, Query(gt=0.0)] = 10.0,
    scale: Annotated[float, Query(gt=0.0)] = 100.0,
    width: Annotated[int, Query(gt=0)] = PREVIEW_WIDTH,
    method: Annotated[str, Query()] = "weak",
) -> StreamingResponse:
    """Generate and stream a PNG preview for the requested file."""
    clean_method = method.lower()
    if clean_method not in ALLOWED_METHODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported render method",
        )

    render_width = int(max(64, min(width, 2048)))
    path = resolve_uploaded_file(filename)

    try:
        png = await run_in_threadpool(
            render_lensing_image,
            path,
            float(mass),
            float(scale),
            render_width,
            clean_method,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        ) from exc

    return StreamingResponse(io.BytesIO(png), media_type="image/png")


__all__ = ["router"]
