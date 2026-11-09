from .auth.router import router as auth_router
from .users.router import router as users_router
from .health_profile.router import router as health_profile_router
from .daily_tracking.router import router as daily_tracking_router
from .dashboard.router import router as dashboard_router
from .health_planner.router import router as health_planner_router
from .ai_assistant.router import router as ai_assistant_router
from .weekly_review.router import router as weekly_review_router

routers = (auth_router, users_router, health_profile_router, daily_tracking_router, dashboard_router, health_planner_router, ai_assistant_router, weekly_review_router,)
