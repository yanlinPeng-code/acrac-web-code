#!/usr/bin/env python3
"""
部署初始化脚本
在部署前后端时执行，依次初始化：
1. PostgreSQL 数据库（创建表结构并导入数据）
2. Milvus 向量数据库（创建集合并生成 embeddings）

用法：
    python backend/scripts/deploy_init.py --csv-file path/to/ACR_final.csv

选项：
    --csv-file: CSV 数据文件路径（必需）
    --force-rebuild-pg: 强制重建 PostgreSQL 数据库（删除现有表）
    --force-rebuild-milvus: 强制重建 Milvus 集合（删除现有数据）
    --skip-pg: 跳过 PostgreSQL 初始化
    --skip-milvus: 跳过 Milvus 初始化
"""

import sys
import os
import argparse
import logging
import asyncio
import subprocess
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("deploy_init")


def init_postgresql(csv_file: str, force_rebuild: bool = False) -> bool:
    """初始化 PostgreSQL 数据库

    Args:
        csv_file: CSV 数据文件路径
        force_rebuild: 是否强制重建数据库

    Returns:
        bool: 初始化是否成功
    """
    logger.info("=" * 60)
    logger.info("开始初始化 PostgreSQL 数据库")
    logger.info("=" * 60)

    try:
        script_path = Path(__file__).parent / "build_acrac_from_csv_siliconflow.py"

        # 构建命令
        action = "rebuild" if force_rebuild else "build"
        cmd = [
            sys.executable,
            str(script_path),
            action,
            "--csv-file", csv_file
        ]

        logger.info(f"执行命令: {' '.join(cmd)}")

        # 执行脚本
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        # 输出执行结果
        if result.stdout:
            logger.info("PostgreSQL 初始化输出:")
            for line in result.stdout.splitlines():
                logger.info(f"  {line}")

        if result.stderr:
            logger.warning("PostgreSQL 初始化警告/错误:")
            for line in result.stderr.splitlines():
                logger.warning(f"  {line}")

        if result.returncode != 0:
            logger.error(f"PostgreSQL 初始化失败，返回码: {result.returncode}")
            return False

        logger.info("PostgreSQL 数据库初始化成功")
        return True

    except Exception as e:
        logger.error(f"PostgreSQL 初始化过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False


async def init_milvus_async(force_rebuild: bool = False) -> bool:
    """异步初始化 Milvus 向量数据库

    Args:
        force_rebuild: 是否强制重建集合

    Returns:
        bool: 初始化是否成功
    """
    logger.info("=" * 60)
    logger.info("开始初始化 Milvus 向量数据库")
    logger.info("=" * 60)

    try:
        # 导入 Milvus 构建模块
        sys.path.insert(0, str(Path(__file__).parents[1]))
        from scripts.build_milvus_script import main_build_milvus

        # 执行 Milvus 初始化
        success = await main_build_milvus(
            collection_name="scenarios",
            recreate=force_rebuild
        )

        if success:
            logger.info("Milvus 向量数据库初始化成功")
        else:
            logger.error("Milvus 向量数据库初始化失败")

        return success

    except Exception as e:
        logger.error(f"Milvus 初始化过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def init_milvus(force_rebuild: bool = False) -> bool:
    """初始化 Milvus 向量数据库（同步接口）"""
    return asyncio.run(init_milvus_async(force_rebuild))


def main():
    parser = argparse.ArgumentParser(
        description="部署初始化脚本：初始化 PostgreSQL 和 Milvus 数据库"
    )
    parser.add_argument(
        "--csv-file",
        required=True,
        help="CSV 数据文件路径"
    )
    parser.add_argument(
        "--force-rebuild-pg",
        action="store_true",
        help="强制重建 PostgreSQL 数据库（删除现有表）"
    )
    parser.add_argument(
        "--force-rebuild-milvus",
        action="store_true",
        help="强制重建 Milvus 集合（删除现有数据）"
    )
    parser.add_argument(
        "--skip-pg",
        action="store_true",
        help="跳过 PostgreSQL 初始化"
    )
    parser.add_argument(
        "--skip-milvus",
        action="store_true",
        help="跳过 Milvus 初始化"
    )

    args = parser.parse_args()

    # 检查 CSV 文件是否存在
    if not os.path.exists(args.csv_file):
        logger.error(f"CSV 文件不存在: {args.csv_file}")
        return 1

    logger.info("开始部署初始化流程")
    logger.info(f"CSV 文件: {args.csv_file}")
    logger.info(f"强制重建 PostgreSQL: {args.force_rebuild_pg}")
    logger.info(f"强制重建 Milvus: {args.force_rebuild_milvus}")
    logger.info(f"跳过 PostgreSQL: {args.skip_pg}")
    logger.info(f"跳过 Milvus: {args.skip_milvus}")

    success = True

    # 步骤 1: 初始化 PostgreSQL
    if not args.skip_pg:
        pg_success = init_postgresql(args.csv_file, args.force_rebuild_pg)
        if not pg_success:
            logger.error("PostgreSQL 初始化失败，终止部署流程")
            return 1
    else:
        logger.info("跳过 PostgreSQL 初始化")

    # 步骤 2: 初始化 Milvus
    if not args.skip_milvus:
        milvus_success = init_milvus(args.force_rebuild_milvus)
        if not milvus_success:
            logger.error("Milvus 初始化失败，但 PostgreSQL 已成功初始化")
            logger.warning("请手动检查 Milvus 配置并重试")
            return 1
    else:
        logger.info("跳过 Milvus 初始化")

    logger.info("=" * 60)
    logger.info("部署初始化流程全部完成")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
