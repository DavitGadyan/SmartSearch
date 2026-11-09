from fastapi import APIRouter

from app.api.v1 import agent, analytics, events, experiments, products, recommendations, search, users

api_router = APIRouter()
api_router.include_router(agent.router)
api_router.include_router(search.router)
api_router.include_router(products.router)
api_router.include_router(recommendations.router)
api_router.include_router(events.router)
api_router.include_router(experiments.router)
api_router.include_router(analytics.router)
api_router.include_router(users.router)
