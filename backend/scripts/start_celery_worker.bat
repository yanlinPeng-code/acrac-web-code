@echo off
REM Celery Worker 启动脚本 (Windows)

echo ========================================
echo 启动 ACRAC Celery Worker
echo ========================================

REM 激活虚拟环境（如果使用）
REM call venv\Scripts\activate

REM 设置Python路径
set PYTHONPATH=%CD%

REM 启动Celery worker
celery -A app.config.celery_app worker ^
    --loglevel=INFO ^
    --concurrency=4 ^
    --pool=solo ^
    --max-tasks-per-child=1000

pause
