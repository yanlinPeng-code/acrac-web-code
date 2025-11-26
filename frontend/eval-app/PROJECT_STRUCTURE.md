# 评测平台前端项目结构

## 目录结构

```
src/
├── api/                    # API请求层
│   ├── config.ts          # API配置（URL、端点常量）
│   └── evaluation.ts      # 评测API请求函数
│
├── types/                  # 类型定义
│   └── evaluation.ts      # 评测相关类型定义
│
├── components/            # UI组件
│   ├── EvaluationParams/  # 评测参数配置组件
│   ├── SingleEvalResult/  # 单个接口评测结果组件
│   └── AllEvalResult/     # 所有接口评测结果组件
│
├── utils/                 # 工具函数
│   └── format.ts          # 数据格式化和转换工具
│
├── App.tsx               # 主应用组件
├── main.tsx              # 应用入口
└── styles.css            # 全局样式
```

## 层次说明

### 1. API层 (`api/`)
负责所有与后端的通信。

- **config.ts**: 统一管理所有API的配置
  - API基础URL
  - API路径常量
  - Endpoint类型定义
  - URL构造函数

- **evaluation.ts**: 封装评测相关的API调用
  - `evaluateSingleEndpoint()`: 评测单个接口
  - `evaluateAllEndpoints()`: 并发评测所有接口
  - `buildFormData()`: 构造请求FormData

### 2. 类型层 (`types/`)
统一管理TypeScript类型定义。

- **evaluation.ts**: 评测相关的所有类型
  - 请求参数类型
  - 响应数据类型
  - 组件Props类型
  - 枚举类型

### 3. 组件层 (`components/`)
拆分的UI组件，各司其职。

- **EvaluationParams/**: 评测参数配置表单
  - 根据endpoint动态显示/隐藏参数
  - 处理不同接口的特有参数

- **SingleEvalResult/**: 单个接口评测结果展示
  - 统计卡片
  - 明细表格
  - Tabs切换

- **AllEvalResult/**: 所有接口并发评测结果展示
  - 汇总统计
  - 各接口对比
  - CSV文件路径显示

### 4. 工具层 (`utils/`)
数据转换和工具函数。

- **format.ts**: 格式化工具
  - 百分比格式化
  - 推荐结果格式化
  - 场景命中格式化
  - 参数显示判断
  - 随机ID生成

### 5. 主应用 (`App.tsx`)
应用主入口，协调各个模块。

- 状态管理
- 业务逻辑编排
- 组件组合

## 数据流

```
用户操作 → App.tsx → API层 → 后端服务器
                 ↓
          状态更新 → UI组件 → 用户界面
                 ↓
          工具函数（格式化）
```

## 优势

1. **清晰的层次结构**: 各层职责分明，易于维护
2. **高内聚低耦合**: 每个模块独立，易于测试和复用
3. **类型安全**: 完整的TypeScript类型定义
4. **易于扩展**: 新增功能只需在对应层添加代码
5. **代码复用**: 工具函数和组件可在多处使用
