"""
ACRO 应用主入口
"""

from app.config.app_config import create_app
from app.config.config import settings

app=create_app()

@app.get("/")
def read_root():
    """根路径"""
    return {
        "message": "Welcome to ACRO API",
        "version": settings.VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION
    }



if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        reload=settings.DEBUG,
        log_level="info"
    )
