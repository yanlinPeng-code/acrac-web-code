#!/bin/bash
# Celery Worker 启动脚本 (Linux/Mac)

echo "========================================"
echo "启动 ACRAC Celery Worker"
echo "========================================"

# 激活虚拟环境（如果使用）
# source venv/bin/activate

# 设置Python路径
export PYTHONPATH=$(pwd)

# 启动Celery worker
celery -A app.config.celery_app worker \
    --loglevel=INFO \
    --concurrency=4 \
    --max-tasks-per-child=1000 \
    --time-limit=600 \
    --soft-time-limit=300
