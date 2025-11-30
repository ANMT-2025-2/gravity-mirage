from fastapi import APIRouter

from gravity_mirage.web.routers.delete import router as delete_router
from gravity_mirage.web.routers.preview import router as preview_router

api_router = APIRouter()

api_router.include_router(
    preview_router,
)

api_router.include_router(
    delete_router,
)

__all__ = ["api_router"]
