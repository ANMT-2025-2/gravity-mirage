from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, status
from fastapi.responses import RedirectResponse

from gravity_mirage.utils.files import resolve_export_file, resolve_uploaded_file

router = APIRouter(
    prefix="/delete",
)


@router.post("/upload")
async def delete(filename: Annotated[str, Form()]) -> RedirectResponse:
    """Remove an uploaded asset."""
    try:
        path = resolve_uploaded_file(filename)
    except HTTPException:
        return RedirectResponse(
            "/",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    path.unlink(missing_ok=True)
    return RedirectResponse(
        "/",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/export")
async def delete_export(filename: Annotated[str, Form()]) -> RedirectResponse:
    """Remove an exported GIF."""
    try:
        path = resolve_export_file(filename)
    except HTTPException:
        return RedirectResponse(
            "/",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    path.unlink(missing_ok=True)
    return RedirectResponse(
        "/",
        status_code=status.HTTP_303_SEE_OTHER,
    )


__all__ = ["router"]
