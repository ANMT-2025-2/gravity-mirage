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
                            <form method="post" action="/delete/upload" onsubmit="return confirm('Delete {{ image }}?');">
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
                            <form method="post" action="/delete/export" onsubmit="return confirm('Delete export {{ image }}?');">
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
                                <form method="post" action="/delete/export" onsubmit="return confirm('Delete export ${name}?');">
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


__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_METHODS",
    "CHUNK_SIZE",
    "EXPORT_FOLDER",
    "INDEX_TEMPLATE",
    "PREVIEW_WIDTH",
    "UPLOAD_FOLDER",
]
