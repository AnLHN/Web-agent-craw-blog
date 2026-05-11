from fastapi import APIRouter

from src.controllers.search_controller import router as search_router

api_router = APIRouter()
api_router.include_router(search_router, tags=["search"])
