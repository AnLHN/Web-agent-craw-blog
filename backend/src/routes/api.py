from fastapi import APIRouter

from src.controllers.article_import_controller import router as article_import_router
from src.controllers.chat_controller import router as chat_router
from src.controllers.llm_controller import router as llm_router
from src.controllers.search_controller import router as search_router

api_router = APIRouter()
api_router.include_router(article_import_router, tags=["article-import"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(llm_router, tags=["llm"])
