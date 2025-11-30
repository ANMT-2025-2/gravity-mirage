from __future__ import annotations

import threading
from importlib.metadata import version
from os import getenv
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import DictLoader, Environment, select_autoescape

from gravity_mirage.web.constants import INDEX_TEMPLATE, PREVIEW_WIDTH, UPLOAD_FOLDER
from gravity_mirage.web.routers import api_router
from gravity_mirage.web.utils.files import list_exported_images, list_uploaded_images
from gravity_mirage.web.workers.gif import worker as worker_gif

app = FastAPI(
    title="Gravity Mirage Web",
    version=version("gravity_mirage"),
)

# Add middleware to compress responses larger than 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# Start worker thread
_worker_thread = threading.Thread(target=worker_gif, daemon=True)
_worker_thread.start()


template_env = Environment(
    loader=DictLoader({"index.html": INDEX_TEMPLATE}),
    autoescape=select_autoescape(["html", "xml"]),
)
index_template = template_env.get_template("index.html")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Render the landing page with the upload + preview UI."""
    images = list_uploaded_images()
    exports = list_exported_images()

    # Prefer a gif placed in ./img/ (repo asset) for the full-page background;
    # fall back to an uploaded copy in the uploads/ folder if present.
    img_dir = Path.cwd() / "img"
    img_file = img_dir / "nasa-black-hole-visualization.gif"
    if img_file.exists():
        background_image_url = f"/api/img/{img_file.name}"
    else:
        bg_file = UPLOAD_FOLDER / "nasa-black-hole-visualization.gif"
        background_image_url = f"/uploads/{bg_file.name}" if bg_file.exists() else ""

    html = index_template.render(
        images=images,
        exports=exports,
        first_image=images[0] if images else "",
        preview_width=PREVIEW_WIDTH,
        background_image_url=background_image_url,
    )
    return HTMLResponse(html)


app.include_router(
    api_router,
)


def run(
    *,
    port: int | None = None,
    host: str | None = None,
    reload: bool = False,
) -> None:
    """
    Start the web server for the Gravity Mirage API.

    This function serves as the entry point for running the web application using uvicorn.
    It handles port and host configuration, with support for environment variable overrides.

    Args:
        port: The port number to run the server on (keyword-only).
            Defaults to the PORT provided (if specified), environment variable if set, otherwise 2025.
        host: The host address to bind the server to (keyword-only).
            Defaults to '127.0.0.1' if not specified.
        reload: Enable auto-reload when code changes are detected (keyword-only).
            Defaults to False.

    Returns:
        None

    Example:
        >>> run()  # Runs on 127.0.0.1:2025
        >>> run(port=8000, host='0.0.0.0')  # Runs on 0.0.0.0:8000
        >>> run(reload=True)  # Runs with auto-reload enabled

    """
    env_port = getenv("PORT")
    if env_port and not port:
        port = int(env_port)
    if port is None:
        port = 2025

    if not host:
        host = "127.0.0.1"

    import uvicorn  # noqa: PLC0415

    uvicorn.run("gravity_mirage.web:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
