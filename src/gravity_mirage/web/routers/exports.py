import io
import uuid
from pathlib import Path
from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image

from gravity_mirage.core.lensing import compute_lensed_array_from_src_arr
from gravity_mirage.web.constants import ALLOWED_METHODS, EXPORT_FOLDER, PREVIEW_WIDTH
from gravity_mirage.web.utils.files import list_exported_images, resolve_uploaded_file
from gravity_mirage.web.workers import JOB_QUEUE, JOBS

router = APIRouter(
    prefix="/exports",
    tags=["exports"],
)


@router.get("/gif/{filename}")
async def export_gif(
    filename: str,
    mass: Annotated[float, Query(gt=0.0)] = 10.0,
    scale: Annotated[float, Query(gt=0.0)] = 100.0,
    width: Annotated[int, Query(gt=0)] = PREVIEW_WIDTH,
    method: Annotated[str, Query()] = "weak",
    frames: Annotated[int, Query(ge=2, le=200)] = 24,
) -> StreamingResponse:
    """
    Generate an animated GIF that scrolls the image right-to-left.

    The scrolling is implemented by rolling the resized source image horizontally
    across the requested number of frames and routerlying the lensing renderer
    to each frame.
    """
    clean_method = method.lower()
    if clean_method not in ALLOWED_METHODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported render method",
        )

    path = resolve_uploaded_file(filename)

    def _build_gif_bytes():
        with Image.open(path) as src_image:
            src = src_image.convert("RGB")
            w0, h0 = src.size
            aspect = h0 / max(w0, 1)
            out_w = max(1, int(width))
            out_h = max(1, int(out_w * aspect))
            src_small = src.resize((out_w, out_h), Image.Resampling.BILINEAR)
            src_arr0 = np.array(src_small)

        frames_list = []
        # for each frame, roll the image left by a fraction of the width
        for i in range(frames):
            shift = round(i * (out_w / frames))
            rolled = np.roll(src_arr0, -shift, axis=1)
            result_arr = compute_lensed_array_from_src_arr(
                rolled,
                mass=mass,
                scale_rs=scale,
                method=clean_method,
            )
            frames_list.append(Image.fromarray(result_arr))

        bio = io.BytesIO()
        # Save as animated GIF
        frames_list[0].save(
            bio,
            format="GIF",
            save_all=True,
            routerend_images=frames_list[1:],
            loop=0,
            # Use 20 frames per second => 50 ms per frame
            duration=50,
            optimize=False,
        )
        bio.seek(0)
        return bio.getvalue()

    try:
        gif_bytes = await run_in_threadpool(_build_gif_bytes)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        ) from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{Path(filename).stem}-scroll.gif"',
    }
    return StreamingResponse(
        io.BytesIO(gif_bytes),
        media_type="image/gif",
        headers=headers,
    )


@router.post("/gif/async/{filename}")
async def export_gif_async(
    filename: str,
    mass: Annotated[float, Query(gt=0.0)] = 10.0,
    scale: Annotated[float, Query(gt=0.0)] = 100.0,
    width: Annotated[int, Query(gt=0)] = PREVIEW_WIDTH,
    method: Annotated[str, Query()] = "weak",
    frames: Annotated[int, Query(ge=2, le=200)] = 24,
) -> dict:
    """Queue a GIF export job and return a job id for polling."""
    clean_method = method.lower()
    if clean_method not in ALLOWED_METHODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported render method",
        )

    path = resolve_uploaded_file(filename)

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "progress": 0,
        "path": str(path),
        "mass": float(mass),
        "scale": float(scale),
        "width": int(width),
        "method": clean_method,
        "frames": int(frames),
    }
    JOB_QUEUE.put(JOBS[job_id])
    return {"job_id": job_id, "status": "queued"}


@router.get("/gif/status/{job_id}")
async def export_gif_status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
    }


@router.get("/gif/result/{job_id}")
async def export_gif_result(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.get("status") != "done":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job not ready",
        )
    result_name = job.get("result")
    if not result_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Result missing",
        )
    result_path = EXPORT_FOLDER / result_name
    return FileResponse(result_path, media_type="image/gif", filename=result_name)


@router.get("/list")
async def exports_list() -> dict:
    """Return a JSON listing of files in the exports folder."""
    return {"exports": list_exported_images()}


@router.get("/{filename:path}")
async def export_file(filename: str) -> FileResponse:
    """Serve files from the repository's `exports/` directory (generated GIFs)."""
    # Ensure we don't allow path traversal outside the exports directory.
    export_base = EXPORT_FOLDER.resolve()
    target = (export_base / Path(filename).name).resolve()
    try:
        target.relative_to(export_base)
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
    return FileResponse(target, media_type="image/gif")


__all__ = ["router"]
