# Gravity Mirage

Simulator that visually demostrates gravitational lensing caused by
black holes.

## Table of contents

- [Gravity Mirage](#gravity-mirage)
  - [Table of contents](#table-of-contents)
  - [Running and setting up the project](#running-and-setting-up-the-project)
    - [Using docker](#using-docker)
      - [Build the Docker image](#build-the-docker-image)
      - [Run the container](#run-the-container)
      - [Custom port mapping](#custom-port-mapping)
      - [Development mode with volume mounting](#development-mode-with-volume-mounting)
    - [Local development](#local-development)
      - [Setup locally](#setup-locally)
      - [Running the project](#running-the-project)
        - [Available command-line options](#available-command-line-options)
        - [Web preview (browser)](#web-preview-browser)
  - [Usage notes](#usage-notes)
  - [Performance and recommendations](#performance-and-recommendations)

## Running and setting up the project

### Using docker

The project includes a Dockerfile for containerized deployment. The Docker image uses a multi-stage build with `uv` for efficient dependency management.

> [!NOTE]
> The Dockerfile exposes port 8080 by default and runs the application
> as a non-root user for security.

#### Build the Docker image

```sh
docker build -t gravity-mirage .
```

#### Run the container

```sh
docker run -p 8080:8080 gravity-mirage
```

The web interface will be available at `http://localhost:8080`.

#### Custom port mapping

To run on a different host port (e.g., 3000):

```sh
docker run -p 3000:8080 gravity-mirage
```

Then access the application at `http://localhost:3000`.

#### Development mode with volume mounting

To mount the source code for development:

```sh
docker run -p 8080:8080 -v $(pwd):/app gravity-mirage
```

### Local development

#### Setup locally

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

1. Install required packages

    ```sh
    uv sync
    ```

#### Running the project

> [!TIP]
> You may personalize some of the details about the web server by
> checking some of the available
> [command-line options](#available-command-line-options)

Once you have done [the setup step](#setup-locally), you may run the
project by executing (command-line entrypoint):

```sh
uv run gravity-mirage
```

This will start the server on `http://127.0.0.1:2025` by default.

##### Available command-line options

- `--host HOST`: Host address to bind to (default: `0.0.0.0`)
- `--port PORT`: Port number to run on (default: `2025` or `PORT` environment variable)
- `--reload`: Enable auto-reload when code changes are detected (useful for development)

**Examples:**

```sh
# Run on a custom port
uv run gravity-mirage --port 8000

# Run with auto-reload enabled for development
uv run gravity-mirage --reload

# Run on all interfaces with custom port
uv run gravity-mirage --host 0.0.0.0 --port 3000
```

##### Web preview (browser)

The repository includes a small development web UI for uploading images and
previewing gravitational lensing. This UI is implemented with FastAPI and the
server is served with Uvicorn (not Flask). The app creates an `uploads/`
directory next to the repository root when needed and uses two rendering
methods:

- Weak-field: fast per-pixel angular deflection using Einstein's weak-field
  approximation (interactive preview).
- Geodesic: slower, more accurate numeric geodesic tracing (coarse radial
  integration, interpolated across the image).

## Usage notes

- Upload images from the left-hand panel; uploaded files are saved into
  `uploads/` next to the repo root.
- Click a thumbnail to set it as the active preview image or choose one from
  the dropdown in the preview panel. The preview image automatically updates
  when you change parameters (mass, scale, method).
- The UI requests generated PNG previews from the `/preview/{filename}`
  endpoint; no separate "Render" button is required.

## Performance and recommendations

- Use Weak-field mode for fast, interactive previews. Use Geodesic mode for
  higher fidelity at greater computational cost.
- Reduce the preview width (e.g., 256) to get faster responses from the
  geodesic renderer during iteration.
- This preview server is intended for development and testing. For production
  use add appropriate hardening (reverse proxy, auth, rate limiting,
  background workers, etc.).
