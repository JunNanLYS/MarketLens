# MarketLens 前端 UI 升级计划 (r15)

> 计划日期:2026-06-11
> 背景:第 12 轮 React 迁移完成,7 页面全部落地;目前 antd 默认主题 + 标准管理后台骨架,缺少"专业金融研究终端"的质感。本轮目标是从"可用的 React + antd"升级到"看起来像专业金融工具"。
> 范围:**仅 `frontend/`**,不动后端 API、数据库、scheduler。
> 关联审查:第 13 轮补登 UI 维度(普通感/品牌缺失/数字呈现单调)→ 本计划落地。

---

## 总体路径(从轻到重,推荐按序推进)

| 阶段 | 主题 | 估时 | 优先级 | 关键收益 |
| --- | --- | --- | --- | --- |
| **P0** | 品牌重塑 + 暗色模式 | 0.5 d | 高 | 一眼可辨的视觉语言;夜间盯盘可用 |
| **P1** | 信息架构 + 数字呈现 | 1 d | 高 | 跨页 KPI;数字有"心跳";趋势可见 |
| **P2** | 详情页/工作流增强 | 1.5 d | 中 | 三栏研究工作区;键盘可达性 |
| **合计** |  | **3 d** |  |  |

> 实施节奏建议:P0 与 P1 连续做(都改 layout 基础),P2 单独 PR(动 AssetDetail 主页面)。

---

## P0 品牌重塑 + 暗色模式

### P0-1 antd 主题 token 重做
- **文件**:`frontend/src/main.tsx`(`ConfigProvider.theme.token`)
- **任务**:
  - [ ] 定义完整 token 集合:`colorPrimary` / `colorSuccess` / `colorWarning` / `colorError`,统一色相
    - 建议:深空蓝 `#0F2D5C` / 翡翠 `#16A34A` / 琥珀 `#D97706` / 玫瑰 `#DC2626`(用 oklch 微调亮度统一)
  - [ ] `borderRadius`(8 px)/ `fontFamily`(系统字 + 等距数字)/ `controlHeight` token
  - [ ] 全局 CSS:`font-variant-numeric: tabular-nums`(数字对齐)
- **验收**:启动后无 antd 默认蓝泄漏;数字纵向对齐
- **估时**:2 h

### P0-2 暗色模式
- **新建**:`frontend/src/store/preferences.ts`(zustand store)
- **新建**:`frontend/src/components/layout/ThemeToggle.tsx`
- **任务**:
  - [ ] zustand store:`theme: 'light' | 'dark' | 'system'`,localStorage 持久化
  - [ ] `ConfigProvider` 集成 `theme.darkAlgorithm`(`algorithm` 数组根据当前模式动态切换)
  - [ ] `<html data-theme="dark">` 配合 CSS 变量,覆盖 echarts / 滚动条等 antd 之外元素
  - [ ] 切换无闪烁:初始化时 inline script 同步读 localStorage
- **验收**:切换 < 100 ms,刷新保留偏好,7 页面风格一致
- **估时**:2 h

### P0-3 Tailwind 整合闭环
- **文件**:`frontend/tailwind.config.js`、`frontend/src/styles/global.css`、`frontend/postcss.config.js`
- **任务**:
  - [ ] 确认 `content` 覆盖 `src/**/*.{ts,tsx}`
  - [ ] `global.css` 注入 `@tailwind base/components/utilities`
  - [ ] 与 antd `reset.css` 加载顺序确认(antd reset 在前,避免 Tailwind preflight 覆盖)
  - [ ] 主题色用 CSS 变量穿透,与 P0-1 共享
- **验收**:`flex`/`grid`/`space-x-*` 等类生效,无 antd 冲突
- **估时**:1 h

### P0-4 品牌收尾
- **任务**:
  - [ ] `frontend/index.html`:title 改为 `MarketLens — 你的本地金融研究终端`
  - [ ] `frontend/public/favicon.svg`:替换为有 logo 感的图标(放大镜 + K 线元素)
  - [ ] 全局 loading 文案统一:`加载市场数据中…`
- **估时**:1 h

**P0 验收总则**:`npm run dev` 启动后,浅色 / 暗色各点一遍 7 页面,色板/字体/圆角一致;`npm run lint` / `npm run type-check` 通过。

---

## P1 信息架构 + 数字呈现

### P1-1 顶部全局 KPI Bar
- **新建**:`frontend/src/components/layout/KpiBar.tsx`
- **修改**:`frontend/src/components/layout/AppLayout.tsx`(Header 内嵌入)
- **任务**:
  - [ ] 4 个核心指标:**总市值 / 今日已实现盈亏 / 未实现 P&L / 数据源健康**
  - [ ] 数据源:复用 `portfolio` service + `data-sources/status` API
  - [ ] TanStack Query 30 s staleTime 与全局一致
  - [ ] 响应式:窄屏降级为横向滚动
- **验收**:7 页面顶部一致可见;数据延迟 ≤ 30 s;加载有 skeleton
- **估时**:3 h

### P1-2 数字 tween 动画
- **修改**:`frontend/src/components/shared/NumberFormat.tsx`
- **任务**:
  - [ ] 用 `framer-motion` 的 `animate` 把数字从 0 tween 到目标值(初次加载)
  - [ ] 持续变动场景(quote 刷新)加 0.3 s 脉冲高亮(背景色闪一下)
  - [ ] `prefers-reduced-motion` 检测:开启时降级为硬切
- **验收**:刷新数字时平滑过渡,无视觉跳动
- **估时**:2 h

### P1-3 Sparkline 嵌入表格
- **新建**:`frontend/src/components/shared/Sparkline.tsx`
- **应用**:Portfolio / TrackedAssets 表格的"近 30 日"列
- **任务**:
  - [ ] 包装 `echarts-for-react`,`opts={{ height: 24, animation: false }}`
  - [ ] 数据从既有 kline 端点取近 N 个收盘点
  - [ ] 配色与 P0-1 主题 token 联动(浅 / 深色自动切换)
  - [ ] 100+ 行时抽样渲染(每 5 行 1 个)或 IntersectionObserver 懒加载
- **验收**:不抢戏,趋势一眼能看;性能不掉帧
- **估时**:3 h

### P1-4 P&L 配色中性化(色弱友好)
- **修改**:`frontend/src/components/shared/PnlDisplay.tsx`
- **任务**:
  - [ ] 保留 ▲/▼ 形状(已有),加文字标签"盈利 / 亏损"
  - [ ] 检查 WCAG 对比度:正/负/零 三态对比度 ≥ 4.5:1
  - [ ] 加 `aria-label="盈利" / "亏损" / "持平"` 给屏幕阅读器
- **验收**:8% 男性色弱可独立识别
- **估时**:1 h

**P1 验收总则**:打开任一持仓详情 → 数字平滑增长,KPI Bar 一致显示;Portfolio 表格里每行有 mini 趋势。

---

## P2 详情页 / 工作流增强

### P2-1 可拖拽三栏布局
- **修改**:`frontend/src/pages/AssetDetail/index.tsx`
- **依赖**:新增 `react-resizable-panels`
- **任务**:
  - [ ] 三栏:左 基本面(财务/资金流) / 中 图表(K线+技术指标) / 右 AI 报告(可折叠抽屉)
  - [ ] 宽度持久化到 localStorage(`marketlens:layout:asset:<symbol>`)
  - [ ] 拖拽把手设 `aria-label="拖拽以调整宽度"`,Tab 键可达
  - [ ] 窄屏(< 1024 px)降级为单列 + tabs
- **验收**:刷新后保留布局;键盘可达;窄屏可用
- **估时**:4 h

### P2-2 Command Palette
- **新建**:`frontend/src/components/shared/CommandPalette.tsx`
- **依赖**:新增 `cmdk`(或自研)
- **任务**:
  - [ ] `Cmd/Ctrl+K` 唤起,`Esc` 关闭
  - [ ] 命令注册表(可扩展):页面跳转 / 资产搜索(调 `symbols` 端点)/ 触发定时任务(调 `tasks/trigger/{name}`)
  - [ ] 搜索响应 < 100 ms(本地 fuse.js 索引 + 后端兜底)
  - [ ] 最近使用命令置顶
- **验收**:键盘可达,模糊搜索精准
- **估时**:4 h

### P2-3 采集事件时间轴
- **新建**:`frontend/src/components/shared/CollectionTimeline.tsx`
- **应用**:AssetDetail 新增 tab"采集历史"
- **任务**:
  - [ ] 调 `run_logs` 端点(已存在),按 `affected_assets` 过滤当前 symbol
  - [ ] antd `Timeline` 组件包装,按时间倒序
  - [ ] 失败事件标红 + 错误摘要展开
- **验收**:可见 evidence-driven 流程;失败可点击查看
- **估时**:3 h

**P2 验收总则**:AssetDetail 拖拽布局持久化;`Cmd+K` 跳页 / 搜资产 / 触任务三件套均可用;时间轴 tab 可看采集历史。

---

## 实施细节(预备)

### 新增 npm 依赖
```bash
cd frontend
npm install react-resizable-panels cmdk fuse.js
```

### 不需要新增的(已装)
- `framer-motion` `echarts` `echarts-for-react` `zustand` `antd` `@ant-design/icons` `tailwindcss` `dayjs`

### 涉及文件清单(预估)
- 新建:5 个(`preferences.ts` / `ThemeToggle.tsx` / `KpiBar.tsx` / `Sparkline.tsx` / `CommandPalette.tsx` / `CollectionTimeline.tsx` = 6 个)
- 修改:6 个(`main.tsx` / `AppLayout.tsx` / `index.html` / `NumberFormat.tsx` / `PnlDisplay.tsx` / `AssetDetail/index.tsx` / `global.css` / `tailwind.config.js`)

---

## 不在范围(本次)

- 不动后端 API / 数据库 / scheduler
- 不做 i18n(已锁定 zh-CN)
- 不做移动端适配(本地工具,桌面优先)
- 不重写 antd 组件库,仅调 token

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 暗色模式 antd 组件色板不一致 | 中 | 官方 `darkAlgorithm` 优先;小范围 CSS 变量 patch |
| 数字 tween 在快速刷新下掉帧 | 低 | `useReducedMotion` 降级;只在"变化"时动画 |
| Sparkline 100+ 行表格性能 | 中 | 抽样渲染 + IntersectionObserver 懒加载 |
| 拖拽布局影响键盘可达性 | 中 | 拖拽把手 `aria-label`;Tab 序保留 |
| Tailwind preflight 与 antd reset 冲突 | 中 | 加载顺序测试;必要时 `corePlugins.preflight: false` |

---

## 验收总则(三阶段共用)

1. **静态检查**:`npm run lint` / `npm run type-check` / `npm run build` 全通过
2. **冒烟测试**:dev 模式 7 页面逐页点击,无 console error
3. **截图对比**:桌面 1280×800,浅 / 暗色各一份,与迁移前(第 12 轮)对比
4. **可用性**:`prefers-reduced-motion` 尊重;键盘 Tab 序合理;暗色对比度 ≥ 4.5:1

---

## 完成后

- 在根 `ISSUES.md` 登记:"UI 维度已升级"链接到本计划
- 若有新发现(主题 bug / 性能问题),追加到本计划底部"实施记录"段
- 不归档(本计划是 roadmap,不是 issue tracker;与 `ISSUES.md` 角色不同)
