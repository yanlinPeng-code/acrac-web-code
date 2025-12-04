# VChart 可视化组件安装说明

## 概述

项目中新增了 `VChartComparison` 组件，用于展示四个接口的数据对比。该组件使用了字节跳动的 VChart 图表库，提供了更丰富的可视化效果。

## 功能特性

VChart 可视化组件提供了以下图表：

1. **准确率对比柱状图** - 展示各接口的 Top1 和 Top3 准确率
2. **命中数对比柱状图** - 展示各接口的命中数统计
3. **响应时间折线图** - 展示各接口的平均响应时间趋势
4. **综合性能雷达图** - 多维度展示接口的综合性能
5. **接口详细表现卡片** - 展示每个接口的详细指标

## 安装依赖

在 `frontend/eval-app` 目录下执行以下命令安装 VChart 相关依赖：

```bash
npm install @visactor/react-vchart @visactor/vchart
```

或者使用 yarn：

```bash
yarn add @visactor/react-vchart @visactor/vchart
```

或者使用 pnpm：

```bash
pnpm add @visactor/react-vchart @visactor/vchart
```

## 依赖说明

- `@visactor/vchart` - VChart 核心库，提供图表渲染功能
- `@visactor/react-vchart` - VChart 的 React 封装，提供 React 组件

## 使用方式

安装完成后，组件会自动在"接口评测结果对比"卡片中显示两个选项卡：

1. **数据表格** - 传统的表格展示方式
2. **可视化图表** - 使用 VChart 的高级可视化图表

用户可以通过点击不同的选项卡在表格和图表展示方式之间切换。

## 组件位置

- 组件文件：`src/components/VChartComparison/index.tsx`
- 集成位置：`src/components/AllEvalResult/index.tsx`

## 图表类型

### 1. 准确率对比柱状图 (Bar Chart)
展示各接口的 Top1 和 Top3 准确率，使用分组柱状图进行对比。

### 2. 命中数对比柱状图 (Bar Chart)
展示各接口的 Top1 和 Top3 命中数，便于了解具体的命中情况。

### 3. 响应时间折线图 (Line Chart)
使用折线图展示各接口的平均响应时间，配有数据点标注。

### 4. 综合性能雷达图 (Radar Chart)
在一个雷达图中同时展示：
- Top1 准确率
- Top3 准确率
- 响应速度（标准化处理）

便于直观对比各接口的综合表现。

### 5. 接口详细表现卡片
为每个接口提供详细的统计卡片，包括所有关键指标。

## 自定义配置

如果需要自定义图表样式或行为，可以修改 `VChartComparison/index.tsx` 中的图表配置对象：

- `accuracyBarSpec` - 准确率柱状图配置
- `hitCountBarSpec` - 命中数柱状图配置
- `responseTimeLineSpec` - 响应时间折线图配置
- `radarSpec` - 雷达图配置

详细的配置选项请参考 [VChart 官方文档](https://www.visactor.io/vchart)。

## 故障排除

### 问题：组件无法渲染或报错

**解决方案：**
1. 确保已正确安装依赖：`npm install`
2. 检查 `@visactor/react-vchart` 和 `@visactor/vchart` 是否在 package.json 中
3. 重启开发服务器：`npm run dev`

### 问题：图表显示不正常

**解决方案：**
1. 检查数据格式是否正确
2. 打开浏览器控制台查看错误信息
3. 确保 endpoint_summary 数据包含所有必需字段

## 更多资源

- [VChart 官方文档](https://www.visactor.io/vchart)
- [VChart React 使用指南](https://www.visactor.io/vchart/guide/tutorial_docs/Cross-terminal_and_Developer_Ecology/react)
- [VChart 示例库](https://www.visactor.io/vchart/example)
