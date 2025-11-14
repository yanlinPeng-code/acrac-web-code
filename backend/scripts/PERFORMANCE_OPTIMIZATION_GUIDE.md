# 数据库性能优化指南

## 📋 优化清单

### 1️⃣ 创建性能索引

#### 执行索引创建脚本
```bash
# Windows PowerShell
python scripts/add_performance_indexes.py create

# 查看索引统计
python scripts/add_performance_indexes.py stats

# 回滚索引（如果需要）
python scripts/add_performance_indexes.py drop
```

#### 创建的索引列表

**ClinicalScenario表索引**：
- `idx_clinical_scenarios_active_id` - is_active + id 复合索引（WHERE优化）
- `idx_clinical_scenarios_description_zh_gin` - 全文搜索GIN索引（LIKE优化）
- `idx_clinical_scenarios_patient_population` - 患者人群过滤
- `idx_clinical_scenarios_gender` - 性别过滤
- `idx_clinical_scenarios_pregnancy_status` - 妊娠状态过滤
- `idx_clinical_scenarios_symptom_category` - 症状分类过滤
- `idx_clinical_scenarios_embedding_ivfflat` - 向量搜索IVFFlat索引（10-100倍性能提升）

**ClinicalRecommendation表索引**：
- `idx_clinical_recommendations_scenario_id` - 场景关联查询
- `idx_clinical_recommendations_rating` - 评分过滤
- `idx_clinical_recommendations_active_scenario` - 活跃场景复合索引

### 2️⃣ PostgreSQL配置优化

编辑 `postgresql.conf`（通常位于 `C:\Program Files\PostgreSQL\{version}\data\`）：

```ini
# ========== 内存配置 ==========
shared_buffers = 2GB                    # 共享缓冲区（建议为系统内存的25%）
effective_cache_size = 4GB              # 操作系统缓存（建议为系统内存的50%）
work_mem = 64MB                         # 单个查询排序/哈希内存
maintenance_work_mem = 512MB            # 索引创建/VACUUM内存

# ========== 连接配置 ==========
max_connections = 200                   # 最大连接数（确保 >= 应用连接池最大值）

# ========== 查询优化 ==========
random_page_cost = 1.1                  # SSD存储建议值
effective_io_concurrency = 200          # 并发I/O数量
default_statistics_target = 100         # 统计信息采样量

# ========== WAL配置 ==========
wal_buffers = 16MB
checkpoint_completion_target = 0.9
max_wal_size = 2GB
min_wal_size = 1GB

# ========== 向量扩展优化 ==========
# pgvector IVFFlat索引参数
ivfflat.probes = 10                     # 查询时探测的聚类数（越大越准确但越慢）
```

重启PostgreSQL服务：
```powershell
# Windows
Restart-Service postgresql-x64-{version}

# 或使用pg_ctl
pg_ctl restart -D "C:\Program Files\PostgreSQL\{version}\data"
```

### 3️⃣ 查询优化验证

#### 查看查询执行计划
```sql
-- 查看向量搜索性能
EXPLAIN ANALYZE
SELECT id, description_zh, 
       embedding <=> '[0.1,0.2,...]' as distance
FROM clinical_scenarios
WHERE embedding IS NOT NULL
ORDER BY distance
LIMIT 30;

-- 查看文本搜索性能
EXPLAIN ANALYZE
SELECT * FROM clinical_scenarios
WHERE is_active = true
AND description_zh LIKE '%乳房%'
LIMIT 30;
```

#### 监控索引使用率
```sql
-- 查看索引扫描次数
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;

-- 查看未使用的索引
SELECT 
    schemaname,
    tablename,
    indexname
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexname NOT LIKE 'pg_%'
AND schemaname = 'public';
```

### 4️⃣ 性能测试对比

#### 测试向量搜索性能
```python
import time
import asyncio
from app.service.rag_v1.retrieval_service import RetrievalService

async def benchmark_vector_search():
    # 执行10次向量搜索
    times = []
    for i in range(10):
        start = time.time()
        results = await retrieval_service._semantic_vector_search(
            query_text="乳房肿块疼痛",
            top_p=30,
            top_k=10
        )
        elapsed = time.time() - start
        times.append(elapsed)
    
    print(f"平均耗时: {sum(times)/len(times):.3f}秒")
    print(f"最快: {min(times):.3f}秒")
    print(f"最慢: {max(times):.3f}秒")

# 运行测试
asyncio.run(benchmark_vector_search())
```

### 5️⃣ 预期性能提升

| 查询类型 | 优化前 | 优化后 | 提升 |
|---------|--------|--------|------|
| **向量搜索**（1000条数据） | 200-500ms | 20-50ms | **10倍** |
| **向量搜索**（10000条数据） | 2-5秒 | 50-200ms | **20倍** |
| **文本LIKE搜索** | 100-300ms | 10-30ms | **10倍** |
| **复合条件过滤** | 50-150ms | 5-15ms | **10倍** |
| **并发查询吞吐量** | 50 QPS | 200+ QPS | **4倍** |

### 6️⃣ 维护建议

#### 定期维护任务
```sql
-- 每周执行一次VACUUM ANALYZE（自动释放空间并更新统计信息）
VACUUM ANALYZE clinical_scenarios;
VACUUM ANALYZE clinical_recommendations;

-- 每月检查表膨胀
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('clinical_scenarios', 'clinical_recommendations')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

#### 监控告警阈值
- 连接池使用率 > 80% → 考虑增加连接数
- 查询平均响应时间 > 500ms → 检查慢查询
- 缓存命中率 < 95% → 调整shared_buffers
- 索引膨胀率 > 30% → 执行REINDEX

### 7️⃣ 故障排查

#### 如果性能没有提升：
```sql
-- 1. 检查索引是否被使用
SET enable_seqscan = off;  -- 强制使用索引（测试用）

-- 2. 查看实际执行计划
EXPLAIN (ANALYZE, BUFFERS) 
SELECT * FROM clinical_scenarios WHERE ...;

-- 3. 检查表统计信息是否过期
SELECT 
    schemaname,
    tablename,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE tablename = 'clinical_scenarios';

-- 4. 手动更新统计信息
ANALYZE clinical_scenarios;
```

#### 如果向量搜索仍然慢：
```sql
-- 调整IVFFlat探测参数（在会话中临时调整）
SET ivfflat.probes = 5;  -- 降低精度提升速度
-- 或
SET ivfflat.probes = 20; -- 提高精度但降低速度

-- 重建向量索引（如果数据量变化很大）
REINDEX INDEX CONCURRENTLY idx_clinical_scenarios_embedding_ivfflat;
```

## ✅ 检查清单

执行优化后，请确认：
- [ ] 所有索引创建成功（无错误）
- [ ] PostgreSQL配置已更新并重启
- [ ] 查看执行计划确认索引被使用
- [ ] 性能测试对比显示提升
- [ ] 监控连接池和查询性能
- [ ] 设置定期维护任务

## 🚨 注意事项

1. **备份数据**：执行优化前务必备份数据库
2. **索引创建时间**：使用CONCURRENTLY避免锁表，但需要更长时间
3. **磁盘空间**：索引会占用额外空间，确保有足够磁盘空间
4. **内存配置**：根据实际服务器内存调整参数
5. **逐步优化**：一次改一个参数，观察效果再继续

## 📞 问题反馈

如遇到问题，请收集以下信息：
- PostgreSQL版本
- 数据量（clinical_scenarios表行数）
- 执行计划（EXPLAIN ANALYZE结果）
- 服务器配置（CPU、内存、磁盘类型）
- 错误日志
