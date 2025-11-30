"""Gravity Mirage: Simulador de lensing gravitacional."""

from gravity_mirage.core.physics import SchwarzschildBlackHole
from gravity_mirage.core.ray_tracer import GravitationalRayTracer
from gravity_mirage.web import app as web_app
from gravity_mirage.web import run as start_api


def main() -> None:
    """
    Main entry point for the gravity-mirage CLI.

    Parses command-line arguments and starts the web server.
    """
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        "gravity-mirage",
        description="Gravity Mirage: Gravitational lensing simulator",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to run the web server on (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to run the web server on (default: 2025 or PORT env var)",
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for the web server",
    )

    args = parser.parse_args()

    return start_api(
        port=args.port,
        host=args.host,
        reload=args.reload,
    )


__all__ = ["GravitationalRayTracer", "SchwarzschildBlackHole", "main", "web_app"]
