from pathlib import Path

import numpy as np
from PIL import Image

from gravity_mirage.core.lensing import compute_lensed_array_from_src_arr
from gravity_mirage.utils.files import allocate_export_path
from gravity_mirage.web.constants import PREVIEW_WIDTH
from gravity_mirage.web.workers import JOB_QUEUE, JOBS


def worker() -> None:
    """
    Worker function that processes GIF generation jobs from the job queue.

    This function runs in an infinite loop, continuously fetching jobs from JOB_QUEUE
    and processing them sequentially. For each job, it:
    1. Loads the source image from the specified path
    2. Resizes it to the requested output dimensions while maintaining aspect ratio
    3. Generates multiple frames by horizontally shifting the source image
    4. Applies gravitational lensing effects to each frame using the specified parameters
    5. Saves all frames as an animated GIF with the configured frame rate

    The worker updates job status and progress throughout processing and handles
    errors gracefully. It terminates when None is received from the queue.

    Job Parameters:
        - id (str): Unique identifier for the job
        - path (str): File system path to the source image
        - width (int, optional): Output width in pixels. Defaults to PREVIEW_WIDTH
        - frames (int, optional): Number of frames to generate. Defaults to 24
        - mass (float, optional): Mass parameter for lensing effect. Defaults to 10.0
        - scale (float, optional): Scale factor for Schwarzschild radius. Defaults to 100.0
        - method (str, optional): Lensing method ('weak' or other). Defaults to 'weak'

    Side Effects:
        - Updates JOBS dictionary with status, progress, result, or error information
        - Creates GIF files in the export directory
        - Marks tasks as done in JOB_QUEUE

    Returns:
        None

    Raises:
        Does not raise exceptions; errors are caught and stored in the job's error field.

    """
    while True:
        job = JOB_QUEUE.get()
        if job is None:
            break
        job_id = job["id"]
        try:
            JOBS[job_id]["status"] = "processing"
            JOBS[job_id]["progress"] = 0

            path = Path(job["path"]).resolve()
            with Image.open(path) as src_image:
                src = src_image.convert("RGB")
                w0, h0 = src.size
                aspect = h0 / max(w0, 1)
                out_w = max(1, int(job.get("width", PREVIEW_WIDTH)))
                out_h = max(1, int(out_w * aspect))
                src_small = src.resize((out_w, out_h), Image.Resampling.BILINEAR)
                src_arr0 = np.array(src_small)

            frames = int(job.get("frames", 24))
            frames_list: list[Image.Image] = []
            for i in range(frames):
                # update a coarse progress indicator
                JOBS[job_id]["progress"] = int((i / frames) * 100)
                shift = round(i * (out_w / frames))
                rolled = np.roll(src_arr0, -shift, axis=1)
                result_arr = compute_lensed_array_from_src_arr(
                    rolled,
                    mass=job.get("mass", 10.0),
                    scale_rs=job.get("scale", 100.0),
                    method=job.get("method", "weak"),
                )
                frames_list.append(Image.fromarray(result_arr))

            # Allocate the next sequential export filename (image1.gif, image2.gif, ...)
            out_file = allocate_export_path(".gif")

            # Save with 20 frames per second (50 ms per frame)
            frames_list[0].save(
                out_file,
                format="GIF",
                save_all=True,
                append_images=frames_list[1:],
                loop=0,
                duration=50,
                optimize=False,
            )
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["result"] = str(out_file.name)
            JOBS[job_id]["progress"] = 100
        except (OSError, ValueError, RuntimeError) as exc:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(exc)
        finally:
            JOB_QUEUE.task_done()


__all__ = ["worker"]
