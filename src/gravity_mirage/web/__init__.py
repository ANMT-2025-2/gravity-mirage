from __future__ import annotations

import io
import queue as _queue
import threading
import uuid
from importlib.metadata import version
from os import getenv
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)
from jinja2 import DictLoader, Environment, select_autoescape
from PIL import Image

from gravity_mirage.physics import SchwarzschildBlackHole
from gravity_mirage.ray_tracer import GravitationalRayTracer
from gravity_mirage.utils.files import (
    allocate_export_path,
    allocate_image_path,
    list_exported_images,
    list_uploaded_images,
    resolve_export_file,
    resolve_uploaded_file,
    sanitize_extension,
)
from gravity_mirage.web.constants import (
    ALLOWED_METHODS,
    CHUNK_SIZE,
    EXPORT_FOLDER,
    PREVIEW_WIDTH,
    UPLOAD_FOLDER,
)

app = FastAPI(
    title="Gravity Mirage Web",
    version=version("gravity_mirage"),
)

# Simple in-memory job queue for GIF exports. This is intentionally lightweight
# and suitable for development. Jobs are stored in `JOBS` and processed by a
# background worker thread that writes the generated GIF to `exports/`.
JOB_QUEUE: _queue.Queue = _queue.Queue()
JOBS: dict[str, dict[str, Any]] = {}


def _gif_worker() -> None:
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
            frames_list = []
            for i in range(frames):
                # update a coarse progress indicator
                JOBS[job_id]["progress"] = int((i / frames) * 100)
                shift = round(i * (out_w / frames))
                rolled = np.roll(src_arr0, -shift, axis=1)
                result_arr = _compute_lensed_array_from_src_arr(
                    rolled,
                    mass=job.get("mass", 10.0),
                    scale_Rs=job.get("scale", 100.0),
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


# Start worker thread
_worker_thread = threading.Thread(target=_gif_worker, daemon=True)
_worker_thread.start()


INDEX_TEMPLATE = """
<!doctype html>
<html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>Gravity Mirage — Upload & Preview</title>
        <style>
            :root {
                --bg:#0f1720;
                --panel:#0b1220;
                --muted:#9aa6b2;
                --accent:#6ee7b7;
                --card:#141c2c;
            }
            * { box-sizing:border-box; }
            body {
                margin:0;
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
                     /* Background color fallback; a full-page background element is
                         inserted by the template when a GIF is available. */
                     background-color:#071025;
                color:#e6eef6;
                min-height:100vh;
                display:flex;
                align-items:flex-start;
                justify-content:flex-start;
                padding:24px;
            }
            .app {
                display:grid;
                grid-template-columns: minmax(320px, 400px) minmax(640px, 1400px);
                gap:28px;
                width:100%;
                max-width:1900px;
            }
            .sidebar, .main {
                background:rgba(255,255,255,0.02);
                border-radius:12px;
                padding:20px;
                box-shadow:0 6px 24px rgba(2,6,23,0.55);
            }
            h1, h2 {
                margin:0 0 12px 0;
                text-align:center;
                font-size:1.25rem;
            }
            .uploader form {
                display:flex;
                gap:10px;
                align-items:center;
                width:100%;
            }
            .control-button {
                display:inline-flex;
                align-items:center;
                justify-content:center;
                padding:10px 16px;
                border-radius:8px;
                /* match the thumbnail/card background so uploader buttons blend */
                background:var(--card);
                border:1px solid rgba(255,255,255,0.06);
                color:inherit;
                font-weight:600;
                cursor:pointer;
                min-height:36px;
                box-shadow:0 2px 6px rgba(2,6,23,0.45);
            }
            .control-button:disabled {
                opacity:0.55;
                cursor:not-allowed;
            }
            .uploads-list ul {
                list-style:none;
                padding:0;
                margin:0;
                display:flex;
                flex-wrap:wrap;
                gap:12px;
                justify-content:center;
            }
            .uploads-list li {
                position:relative;
                width:160px;
            }
            .uploads-list button.thumb {
                width:100%;
                border:none;
                background:var(--card);
                padding:10px;
                border-radius:10px;
                color:inherit;
                cursor:pointer;
                display:flex;
                flex-direction:column;
                gap:8px;
            }
            .uploads-list img {
                width:100%;
                height:96px;
                object-fit:cover;
                border-radius:6px;
                border:1px solid rgba(255,255,255,0.08);
            }
            .uploads-list form {
                position:absolute;
                top:8px;
                right:8px;
            }
            .uploads-list form button {
                width:24px;
                height:24px;
                border-radius:50%;
                border:none;
                background:#d9534f;
                color:white;
                cursor:pointer;
                font-size:12px;
            }
            .uploads-list li.empty {
                width:auto;
                color:var(--muted);
                font-size:14px;
            }
            .controls {
                /* Two-column grid so we can pair controls visually:
                   Row 1: Image | Mass
                   Row 2: Method | Scale
                */
                display:grid;
                grid-template-columns: 1fr 1fr;
                gap:18px;
                align-items:center;
                background:rgba(255,255,255,0.03);
                padding:16px;
                border-radius:12px;
                margin-bottom:16px;
            }
            .controls label {
                font-size:13px;
                /* make labels white so they match the control text */
                color:#ffffff;
                margin-bottom:6px;
                display:block;
            }
            .controls select,
            .controls input[type=range] {
                /* let controls expand to fill the column but keep a reasonable
                   maximum so very wide viewports don't create oversized inputs */
                width:100%;
                max-width:420px;
                padding:6px;
                border-radius:6px;
                border:1px solid rgba(255,255,255,0.08);
                background-color:#111827;
                /* make the control text explicitly white for visibility */
                color:#ffffff;
            }
            .value {
                color:#ffffff;
                font-weight:600;
                text-align:center;
                width:100%;
            }
            /* Left-aligned variant for numeric readouts beneath sliders */
            .value.value-left {
                text-align:left;
            }
            .preview-card {
                background:rgba(255,255,255,0.02);
                border-radius:12px;
                padding:16px;
                /* allow the card to size to its contents (the preview image)
                   so the preview container can match the image dimensions */
                height:auto;
                min-height:0;
                display:flex;
                flex-direction:column;
                gap:12px;
                align-items:center;
            }
            /* center the preview image inside its container */
            #previewContainer {
                display:flex;
                align-items:center;
                justify-content:center;
                width:auto;
                /* don't force a fixed height; let the container wrap the image */
                flex:0 0 auto;
                min-height:0;
                padding:8px 0;
            }
            #previewImg {
                display:block;
                width:auto;
                height:auto;
                max-width:100%;
                max-height:70vh; /* keep image from exceeding viewport height */
            }
            .small {
                /* match the h2 size so the preview label is equally prominent */
                font-size:1.25rem;
                font-weight:600;
                color:#ffffff;
                white-space:nowrap;
                overflow:hidden;
                text-overflow:ellipsis;
            }
            /* full-page background element used when a GIF is uploaded */
            .page-bg {
                position:fixed;
                inset:0;
                z-index:-1;
                background-color:#071025;
                background-repeat:no-repeat;
                background-position:center;
                background-size:cover;
            }
        </style>
    </head>
    <body data-first-image="{{ first_image }}">
                <div class="app">
                    {%- if background_image_url %}
                    <div class="page-bg" style="background-image: url('{{ background_image_url }}');"></div>
                    {%- endif %}
            <aside class="sidebar">
                <h1>Uploads</h1>
                <div style="width:100%;"><hr style="border:none; border-top:1px solid rgba(255,255,255,0.06); margin:8px 0 12px 0;" /></div>
                <div class="uploads-list">
                    <ul>
                        {% for image in images %}
                        <li>
                            <form method="post" action="/delete" onsubmit="return confirm('Delete {{ image }}?');">
                                <input type="hidden" name="filename" value="{{ image }}" />
                                <button type="submit" aria-label="Delete {{ image }}">✖</button>
                            </form>
                            <button type="button" class="thumb" onclick="setPreview('{{ image }}')">
                                <strong>{{ image }}</strong>
                                <img src="/uploads/{{ image }}" alt="{{ image }}" loading="lazy" />
                            </button>
                        </li>
                        {% else %}
                        <li class="empty">Upload an image to get started.</li>
                        {% endfor %}
                    </ul>
                </div>
                <div style="width:100%;"><hr style="border:none; border-top:1px solid rgba(255,255,255,0.06); margin:8px 0 12px 0;" /></div>
                <div style="display:flex; align-items:center; gap:8px; margin-top:18px; justify-content:center;">
                    <h1 style="margin:0;">Exports</h1>
                    <button id="refreshExportsBtn" class="control-button" type="button" style="padding:6px 10px;">Refresh</button>
                </div>
                <div style="width:100%;">
                    <hr style="border:none; border-top:1px solid rgba(255,255,255,0.06); margin:12px 0;" />
                </div>
                <div class="uploads-list exports-list">
                    <ul>
                        {% for image in exports %}
                        <li>
                            <a class="download-btn" href="/exports/{{ image }}" download aria-label="Download {{ image }}" style="position:absolute; top:8px; left:8px; width:24px; height:24px; border-radius:50%; background:#0b4dd8; color:white; display:inline-flex; align-items:center; justify-content:center; text-decoration:none;">↓</a>
                            <form method="post" action="/delete_export" onsubmit="return confirm('Delete export {{ image }}?');">
                                <input type="hidden" name="filename" value="{{ image }}" />
                                <button type="submit" aria-label="Delete {{ image }}">✖</button>
                            </form>
                            <button type="button" class="thumb" onclick="openExport('{{ image }}')">
                                <strong>{{ image }}</strong>
                                <img src="/exports/{{ image }}" alt="{{ image }}" loading="lazy" />
                            </button>
                        </li>
                        {% else %}
                        <li class="empty">No exports yet.</li>
                        {% endfor %}
                    </ul>
                </div>
                <div style="width:100%;"><hr style="border:none; border-top:1px solid rgba(255,255,255,0.06); margin:8px 0 12px 0;" /></div>
                <div class="uploader" style="margin-top:14px; text-align:center;">
                    <form method="post" action="/upload" enctype="multipart/form-data">
                        <label for="fileInput" class="control-button" style="cursor:pointer;">
                            Choose file
                            <input id="fileInput" name="file" type="file" style="display:none;" />
                        </label>
                        <span id="fileName" class="small" style="margin-left:10px;">No file chosen</span>
                        <button id="uploadSubmit" type="submit" class="control-button" style="margin-left:12px;" disabled>Upload</button>
                    </form>
                </div>
            </aside>
            <main class="main">
                <h2>Black hole parameters</h2>
                <section class="controls">
                    <div>
                        <label for="imageSelect">Image</label>
                        <select id="imageSelect" {% if not images %}disabled{% endif %}>
                            {% for image in images %}
                            <option value="{{ image }}">{{ image }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label for="methodSelect">Method</label>
                        <select id="methodSelect">
                            <option value="weak">Weak-field (fast)</option>
                            <option value="geodesic">Geodesic (accurate)</option>
                        </select>
                    </div>
                    <div>
                        <label for="massSlider">Mass (M☉)</label>
                        <input id="massSlider" type="range" min="1" max="1000000" step="1" value="10" />
                        <div class="value value-left" id="massValue">10</div>
                    </div>
                    <div>
                        <label for="scaleSlider">Scale (Rs across radius)</label>
                        <input id="scaleSlider" type="range" min="1" max="20" step="1" value="5" />
                        <div class="value value-left" id="scaleValue">5</div>
                    </div>
                    <div style="display:flex; gap:10px; width:100%; justify-content:left; align-items:center;">
                        <div style="display:flex; flex-direction:column; align-items:center; text-align:center;">
                            <label for="framesInput">Frames (GIF)</label>
                            <div style="font-size:12px; color:#ffffff; margin-top:4px;">(2-2000)</div>
                        </div>
                        <input id="framesInput" type="number" min="2" max="2000" step="1" value="24" />
                        <button id="exportGifBtn" class="control-button" type="button" disabled>Export GIF</button>
                        <a id="downloadLink" style="display:none; align-self:center;" download>Download GIF</a>
                        <div id="gifSpinner" style="display:none; color:#ffffff; font-weight:600;">Generating... <span id="gifProgressText"></span></div>
                    </div>
                </section>
                <section class="preview-card">
                    <div class="small">Preview </div>
                    <div id="previewContainer">
                        <img id="previewImg" src="" alt="Gravitational lensing preview" />
                    </div>
                </section>
            </main>
        </div>
        <script>
            (function(){
                const doc = document;
                const body = doc.body;
                const imageSelect = doc.getElementById('imageSelect');
                const previewImg = doc.getElementById('previewImg');
                const massSlider = doc.getElementById('massSlider');
                const massValue = doc.getElementById('massValue');
                const scaleSlider = doc.getElementById('scaleSlider');
                const scaleValue = doc.getElementById('scaleValue');
                const methodSelect = doc.getElementById('methodSelect');
                const framesInput = doc.getElementById('framesInput');
                const framesValue = doc.getElementById('framesValue');
                const exportGifBtn = doc.getElementById('exportGifBtn');
                const downloadLink = doc.getElementById('downloadLink');
                const fileInput = doc.getElementById('fileInput');
                const fileName = doc.getElementById('fileName');
                const uploadSubmit = doc.getElementById('uploadSubmit');
                const defaultWidth = {{ preview_width }};
                let debounceTimer = null;

                function buildPreviewUrl(name){
                    if(!name) return '';
                    const mass = massSlider ? (massSlider.value || 10) : 10;
                    const scale = scaleSlider ? (scaleSlider.value || 5) : 5;
                    const method = methodSelect ? methodSelect.value : 'weak';
                    return `/preview/${encodeURIComponent(name)}?mass=${encodeURIComponent(mass)}&scale=${encodeURIComponent(scale)}&width=${encodeURIComponent(defaultWidth)}&method=${encodeURIComponent(method)}`;
                }

                function setPreview(name){
                    if(!name || !previewImg) return;
                    if(imageSelect) imageSelect.value = name;
                    previewImg.src = buildPreviewUrl(name);
                }

                function scheduleRender(){
                    if(debounceTimer) clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(() => {
                        if(imageSelect && imageSelect.value){
                            setPreview(imageSelect.value);
                        }
                    }, 250);
                }

                function wireSlider(slider, output){
                    if(!slider || !output) return;
                    const sync = () => { output.textContent = slider.value; };
                    sync();
                    slider.addEventListener('input', () => {
                        sync();
                        scheduleRender();
                    });
                }

                if(framesInput && framesValue){
                    const syncFrames = () => { framesValue.textContent = framesInput.value; };
                    syncFrames();
                    framesInput.addEventListener('input', () => syncFrames());
                }

                if(imageSelect){
                    imageSelect.addEventListener('change', () => setPreview(imageSelect.value));
                }
                function updateExportButton(){
                    if(!exportGifBtn) return;
                    exportGifBtn.disabled = !(imageSelect && imageSelect.value);
                }
                updateExportButton();
                if(imageSelect){
                    imageSelect.addEventListener('change', updateExportButton);
                }
                wireSlider(massSlider, massValue);
                wireSlider(scaleSlider, scaleValue);

                if(methodSelect){
                    methodSelect.addEventListener('change', () => {
                        if(imageSelect && imageSelect.value){
                            setPreview(imageSelect.value);
                        }
                    });
                }

                if(fileInput){
                    const defaultText = ((navigator.language || '').toLowerCase().startsWith('es'))
                        ? 'Ningún archivo seleccionado'
                        : 'No file chosen';
                    if(fileName){
                        fileName.textContent = defaultText;
                    }
                    if(uploadSubmit){
                        uploadSubmit.disabled = true;
                    }
                    fileInput.addEventListener('change', () => {
                        const hasFile = fileInput.files && fileInput.files.length > 0;
                        if(fileName){
                            fileName.textContent = hasFile ? fileInput.files[0].name : defaultText;
                        }
                        if(uploadSubmit){
                            uploadSubmit.disabled = !hasFile;
                        }
                    });
                }

                function openExport(name){
                    if(!name) return;
                    window.open(`/exports/${encodeURIComponent(name)}`, '_blank');
                }

                async function refreshExports(){
                    try{
                        const resp = await fetch('/exports_list');
                        if(!resp.ok) throw new Error('Failed to fetch');
                        const data = await resp.json();
                        const list = data.exports || [];
                        const container = doc.querySelector('.exports-list ul');
                        if(!container) return;
                        if(list.length === 0){
                            container.innerHTML = '<li class="empty">No exports yet.</li>';
                            return;
                        }
                        const items = list.map(name => `
                            <li>
                                <a class="download-btn" href="/exports/${name}" download aria-label="Download ${name}" style="position:absolute; top:8px; left:8px; width:24px; height:24px; border-radius:50%; background:#0b4dd8; color:white; display:inline-flex; align-items:center; justify-content:center; text-decoration:none;">↓</a>
                                <form method="post" action="/delete_export" onsubmit="return confirm('Delete export ${name}?');">
                                    <input type="hidden" name="filename" value="${name}" />
                                    <button type="submit" aria-label="Delete ${name}">✖</button>
                                </form>
                                <button type="button" class="thumb" onclick="openExport('${name}')">
                                    <strong>${name}</strong>
                                    <img src="/exports/${name}" alt="${name}" loading="lazy" />
                                </button>
                            </li>
                        `).join('');
                        container.innerHTML = items;
                    }catch(err){
                        console.error('refreshExports', err);
                    }
                }

                const refreshExportsBtn = doc.getElementById('refreshExportsBtn');
                if(refreshExportsBtn){
                    refreshExportsBtn.addEventListener('click', refreshExports);
                }

                async function exportGif(){
                    if(!imageSelect || !imageSelect.value) return;
                    const name = imageSelect.value;
                    const mass = massSlider ? (massSlider.value || 10) : 10;
                    const scale = scaleSlider ? (scaleSlider.value || 5) : 5;
                    const method = methodSelect ? methodSelect.value : 'weak';
                    const frames = framesInput ? Math.max(2, Math.min(200, parseInt(framesInput.value || '24'))) : 24;

                    exportGifBtn.disabled = true;
                    downloadLink.style.display = 'none';
                    const spinner = doc.getElementById('gifSpinner');
                    const progressText = doc.getElementById('gifProgressText');
                    if(spinner) spinner.style.display = 'inline-block';
                    if(progressText) progressText.textContent = '';

                    try{
                        const qs = `?mass=${encodeURIComponent(mass)}&scale=${encodeURIComponent(scale)}&width=${encodeURIComponent(defaultWidth)}&method=${encodeURIComponent(method)}&frames=${encodeURIComponent(frames)}`;
                        const resp = await fetch(`/export_gif_async/${encodeURIComponent(name)}${qs}`, { method: 'POST' });
                        if(!resp.ok){
                            throw new Error('Queue failed');
                        }
                        const data = await resp.json();
                        const jobId = data.job_id;

                        // Poll status
                        let done = false;
                        while(!done){
                            await new Promise(r => setTimeout(r, 1000));
                            const st = await fetch(`/export_gif_status/${encodeURIComponent(jobId)}`);
                            if(!st.ok) throw new Error('Status error');
                            const js = await st.json();
                            const status = js.status;
                            const progress = js.progress || 0;
                            if(progressText) progressText.textContent = `${progress}%`;
                            if(status === 'done'){
                                done = true;
                                // Do NOT auto-download the generated GIF. Refresh the
                                // exports list so the user can manually download via
                                // the per-export download button next to each preview.
                                try{ if(typeof refreshExports === 'function') await refreshExports(); }catch(e){/*ignore*/}
                                if(progressText) progressText.textContent = '100%';
                            } else if(status === 'error'){
                                throw new Error(js.error || 'Job error');
                            }
                        }
                    }catch(err){
                        alert('Failed to generate GIF: ' + err.message);
                        console.error(err);
                    }finally{
                        exportGifBtn.disabled = false;
                        const spinner = doc.getElementById('gifSpinner');
                        if(spinner) spinner.style.display = 'none';
                    }
                }

                if(exportGifBtn){
                    exportGifBtn.addEventListener('click', exportGif);
                }

                window.setPreview = setPreview;

                const initial = body ? body.getAttribute('data-first-image') : '';
                if(initial){
                    setPreview(initial);
                } else if(imageSelect && imageSelect.value){
                    setPreview(imageSelect.value);
                }
            })();
        </script>
    </body>
</html>
"""

template_env = Environment(
    loader=DictLoader({"index.html": INDEX_TEMPLATE}),
    autoescape=select_autoescape(["html", "xml"]),
)
index_template = template_env.get_template("index.html")


def render_lensing_image(
    src_path: Path,
    mass: float = 10.0,
    scale_Rs: float = 100.0,
    out_width: int = PREVIEW_WIDTH,
    method: str = "weak",
) -> bytes:
    """Render a PNG preview that visualizes gravitational lensing."""
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    with Image.open(src_path) as src_image:
        src = src_image.convert("RGB")
        w0, h0 = src.size
        aspect = h0 / max(w0, 1)
        out_w = max(1, int(out_width))
        out_h = max(1, int(out_w * aspect))
        src_small = src.resize((out_w, out_h), Image.Resampling.BILINEAR)
        src_arr = np.array(src_small)

    bh = SchwarzschildBlackHole(mass=mass)
    cx = out_w / 2.0
    cy = out_h / 2.0
    ys, xs = np.mgrid[0:out_h, 0:out_w]
    dx = xs - cx
    dy = ys - cy
    r = np.sqrt(dx**2 + dy**2)
    max_r = max(np.max(r), 1.0)

    Rs = bh.schwarzschild_radius
    meters_per_pixel = (scale_Rs * Rs) / max_r
    b = r * meters_per_pixel

    if method == "weak":
        with np.errstate(divide="ignore", invalid="ignore"):
            alpha = np.vectorize(bh.deflection_angle_weak_field)(b)
    else:
        tracer = GravitationalRayTracer(bh)
        bins = min(128, max(8, int(max_r)))
        radii = np.linspace(0, max_r, bins)
        alpha_bins = np.zeros_like(radii)
        r0 = max(1e4 * Rs, 1e6)

        for i, rb in enumerate(radii):
            b_phys = rb * meters_per_pixel
            dr0 = -1.0
            dtheta0 = 0.0
            dphi0 = b_phys / (r0**2 + 1e-30)
            try:
                # Allow integration long enough for the photon to escape back
                # to large radius. The tracer now supports stopping at the
                # escape event, so a large lambda_max is acceptable.
                sol = tracer.trace_photon_geodesic(
                    (r0, np.pi / 2.0, 0.0),
                    (dr0, dtheta0, dphi0),
                    lambda_max=max(1e3, float(r0) * 2.0),
                )
                y = getattr(sol, "y", None)
                if y is not None and y.shape[1] > 0:
                    phi_final = y[3, -1]
                    alpha_bins[i] = float(abs(phi_final) - np.pi)
                else:
                    alpha_bins[i] = 0.0
            except Exception:
                alpha_bins[i] = 0.0

        alpha = np.interp(r.flatten(), radii, alpha_bins).reshape(r.shape)

    captured = ~np.isfinite(alpha)
    theta = np.arctan2(dy, dx)
    theta_src = theta + alpha
    src_x = cx + r * np.cos(theta_src)
    src_y = cy + r * np.sin(theta_src)
    src_xi = np.clip(np.rint(src_x).astype(int), 0, out_w - 1)
    src_yi = np.clip(np.rint(src_y).astype(int), 0, out_h - 1)

    result = np.empty_like(src_arr)
    result[:, :, 0] = src_arr[src_yi, src_xi, 0]
    result[:, :, 1] = src_arr[src_yi, src_xi, 1]
    result[:, :, 2] = src_arr[src_yi, src_xi, 2]

    Rs_pixels = Rs / meters_per_pixel
    mask_disk = (r <= Rs_pixels) | captured
    result[mask_disk] = 0

    out_img = Image.fromarray(result)
    bio = io.BytesIO()
    out_img.save(bio, format="PNG")
    bio.seek(0)
    return bio.getvalue()


def _compute_lensed_array_from_src_arr(
    src_arr: np.ndarray,
    mass: float = 10.0,
    scale_Rs: float = 100.0,
    method: str = "weak",
) -> np.ndarray:
    """
    Compute a lensed RGB image array from an already-resized source array.

    src_arr: HxWx3 uint8 RGB array
    returns: HxWx3 uint8 RGB array with lensing applied
    """
    out_h, out_w = src_arr.shape[0], src_arr.shape[1]

    bh = SchwarzschildBlackHole(mass=mass)
    cx = out_w / 2.0
    cy = out_h / 2.0
    ys, xs = np.mgrid[0:out_h, 0:out_w]
    dx = xs - cx
    dy = ys - cy
    r = np.sqrt(dx**2 + dy**2)
    max_r = max(np.max(r), 1.0)

    Rs = bh.schwarzschild_radius
    meters_per_pixel = (scale_Rs * Rs) / max_r
    b = r * meters_per_pixel

    if method == "weak":
        with np.errstate(divide="ignore", invalid="ignore"):
            alpha = np.vectorize(bh.deflection_angle_weak_field)(b)
    else:
        tracer = GravitationalRayTracer(bh)
        bins = min(128, max(8, int(max_r)))
        radii = np.linspace(0, max_r, bins)
        alpha_bins = np.zeros_like(radii)
        r0 = max(1e4 * Rs, 1e6)

        for i, rb in enumerate(radii):
            b_phys = rb * meters_per_pixel
            dr0 = -1.0
            dtheta0 = 0.0
            dphi0 = b_phys / (r0**2 + 1e-30)
            try:
                sol = tracer.trace_photon_geodesic(
                    (r0, np.pi / 2.0, 0.0),
                    (dr0, dtheta0, dphi0),
                    lambda_max=max(1e3, float(r0) * 2.0),
                )
                y = getattr(sol, "y", None)
                if y is not None and y.shape[1] > 0:
                    phi_final = y[3, -1]
                    alpha_bins[i] = float(abs(phi_final) - np.pi)
                else:
                    alpha_bins[i] = 0.0
            except (ValueError, RuntimeError):
                alpha_bins[i] = 0.0

        alpha = np.interp(r.flatten(), radii, alpha_bins).reshape(r.shape)

    captured = ~np.isfinite(alpha)
    theta = np.arctan2(dy, dx)
    theta_src = theta + alpha
    src_x = cx + r * np.cos(theta_src)
    src_y = cy + r * np.sin(theta_src)
    src_xi = np.clip(np.rint(src_x).astype(int), 0, out_w - 1)
    src_yi = np.clip(np.rint(src_y).astype(int), 0, out_h - 1)

    result = np.empty_like(src_arr)
    result[:, :, 0] = src_arr[src_yi, src_xi, 0]
    result[:, :, 1] = src_arr[src_yi, src_xi, 1]
    result[:, :, 2] = src_arr[src_yi, src_xi, 2]

    Rs_pixels = Rs / meters_per_pixel
    mask_disk = (r <= Rs_pixels) | captured
    result[mask_disk] = 0

    return result


@app.get("/export_gif/{filename}")
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
    across the requested number of frames and applying the lensing renderer
    to each frame.
    """
    clean_method = method.lower()
    if clean_method not in ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail="Unsupported render method")

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
            result_arr = _compute_lensed_array_from_src_arr(
                rolled,
                mass=mass,
                scale_Rs=scale,
                method=clean_method,
            )
            frames_list.append(Image.fromarray(result_arr))

        bio = io.BytesIO()
        # Save as animated GIF
        frames_list[0].save(
            bio,
            format="GIF",
            save_all=True,
            append_images=frames_list[1:],
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
        raise HTTPException(status_code=404, detail="Image not found") from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{Path(filename).stem}-scroll.gif"',
    }
    return StreamingResponse(
        io.BytesIO(gif_bytes),
        media_type="image/gif",
        headers=headers,
    )


@app.post("/export_gif_async/{filename}")
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
        raise HTTPException(status_code=400, detail="Unsupported render method")

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


@app.get("/export_gif_status/{job_id}")
async def export_gif_status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job.get("status", "unknown"),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
    }


@app.get("/export_gif_result/{job_id}")
async def export_gif_result(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "done":
        raise HTTPException(status_code=409, detail="Job not ready")
    result_name = job.get("result")
    if not result_name:
        raise HTTPException(status_code=500, detail="Result missing")
    result_path = EXPORT_FOLDER / result_name
    return FileResponse(result_path, media_type="image/gif", filename=result_name)


@app.get("/exports_list")
async def exports_list() -> dict:
    """Return a JSON listing of files in the exports folder."""
    return {"exports": list_exported_images()}


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
        background_image_url = f"/img/{img_file.name}"
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


@app.post("/upload")
async def upload(file: Annotated[UploadFile, File()]) -> RedirectResponse:
    """Persist an uploaded file and redirect back to the UI."""
    if file is None or not file.filename:
        return RedirectResponse("/", status_code=303)

    ext = sanitize_extension(Path(file.filename).suffix)
    dest = allocate_image_path(ext)

    with dest.open("wb") as buffer:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            buffer.write(chunk)
    await file.close()
    return RedirectResponse("/", status_code=303)


@app.get("/uploads/{filename:path}")
async def uploaded_file(filename: str) -> FileResponse:
    """Serve original uploaded assets."""
    path = resolve_uploaded_file(filename)
    return FileResponse(path)


@app.get("/img/{filename:path}")
async def img_file(filename: str) -> FileResponse:
    """
    Serve files from the repository's ./img/ directory (for repo assets).

    This lets the template reference `/img/nasa-black-hole-visualization.gif`
    without requiring the user to re-upload the asset into uploads/.
    """
    # Ensure we don't allow path traversal outside the img directory.
    img_base = (Path.cwd() / "img").resolve()
    target = (img_base / Path(filename).name).resolve()
    try:
        target.relative_to(img_base)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="File not found") from e
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/exports/{filename:path}")
async def export_file(filename: str) -> FileResponse:
    """Serve files from the repository's `exports/` directory (generated GIFs)."""
    # Ensure we don't allow path traversal outside the exports directory.
    export_base = EXPORT_FOLDER.resolve()
    target = (export_base / Path(filename).name).resolve()
    try:
        target.relative_to(export_base)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="File not found") from e
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target, media_type="image/gif")


@app.post("/delete")
async def delete(filename: Annotated[str, Form()]) -> RedirectResponse:
    """Remove an uploaded asset."""
    try:
        path = resolve_uploaded_file(filename)
    except HTTPException:
        return RedirectResponse("/", status_code=303)
    path.unlink(missing_ok=True)
    return RedirectResponse("/", status_code=303)


@app.post("/delete_export")
async def delete_export(filename: Annotated[str, Form()]) -> RedirectResponse:
    """Remove an exported GIF."""
    try:
        path = resolve_export_file(filename)
    except HTTPException:
        return RedirectResponse("/", status_code=303)
    path.unlink(missing_ok=True)
    return RedirectResponse("/", status_code=303)


@app.get("/preview/{filename}", response_class=StreamingResponse)
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
        raise HTTPException(status_code=400, detail="Unsupported render method")

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
        raise HTTPException(status_code=404, detail="Image not found") from exc

    return StreamingResponse(io.BytesIO(png), media_type="image/png")


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

    import uvicorn

    uvicorn.run("gravity_mirage.web:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
