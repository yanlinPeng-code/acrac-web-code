#!/bin/bash
# Backend Entrypoint Script
# 在容器启动时自动初始化数据库

set -e

echo "=========================================="
echo "ACRAC Backend Starting..."
echo "=========================================="

# 等待 PostgreSQL 和 Milvus 服务启动
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:-postgres}" 2>/dev/null; do
    echo -n "."
    sleep 2
done
echo ""
echo "✓ PostgreSQL is ready"

echo "Waiting for Milvus to be ready..."
# 使用本地服务器上的 bisheng-milvus-standalone 容器
MILVUS_HOST="localhost"
MILVUS_PORT="19530"
until timeout 2 bash -c "cat < /dev/null > /dev/tcp/${MILVUS_HOST}/${MILVUS_PORT}" 2>/dev/null; do
    echo -n "."
    sleep 2
done
echo ""
echo "✓ Milvus is ready"

# 检查是否需要初始化数据库
CSV_FILE="${CSV_FILE:-origin_data/ACR_final.csv}"

if [ -f "$CSV_FILE" ]; then
    echo ""
    echo "=========================================="
    echo "Database Initialization"
    echo "=========================================="
    echo "CSV file found: $CSV_FILE"
    echo "Starting database initialization..."

    # 运行初始化脚本
    if python scripts/deploy_init.py --csv-file "$CSV_FILE"; then
        echo "✓ Database initialization completed successfully"
    else
        echo "⚠ Database initialization failed or skipped"
        echo "This is normal if data already exists"
    fi
else
    echo ""
    echo "⚠ CSV file not found: $CSV_FILE"
    echo "Skipping database initialization"
    echo "To initialize database later, run:"
    echo "  python scripts/deploy_init.py --csv-file <path-to-csv>"
fi

echo ""
echo "=========================================="
echo "Starting Application Server..."
echo "=========================================="

# 启动应用
exec "$@"
