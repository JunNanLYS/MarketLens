# MarketLens Design Language · 设计语言

> 本文件定义 MarketLens 前端 UI 的设计语言基线（Phase 1 文档）。
> 适用版本：2026-06-12 起。后续 Phase 2-5 的 UI 实施必须遵循此文件。
> 维护者：在产品方向/视觉方向调整时同步更新。

---

## 1. 品牌定位 (Brand Positioning)

**MarketLens 是一款单用户、本地优先的金融研究工具。**

它不是面向 C 端投资者的花哨 App，也不是机构级 Bloomberg 终端的简化版。它是一位"研究员的私人研究台"：用户每天打开它，是为了看自己的持仓、看 AI 给出的研判、看今天的新闻如何印证或证伪他的判断。

**视觉调性**：「Research Terminal · 金融研究终端」—— 融合 3 种设计参考：
- **Data-Dense Dashboard** 的信息密度骨架（让一屏看到尽可能多的有用信息）
- **Dimensional Layering** 的多级 elevation（让层级关系一眼可读）
- **Editorial Magazine** 的排版节奏（让"专业感"通过留白和字号表达）

**不做**：
- ❌ 不做 Glassmorphism —— `backdrop-filter` 在多列布局下掉帧
- ❌ 不做 Bento Grid —— 留白太奢侈，与"持仓总览 / 交易记录"等高密度场景冲突
- ❌ 不做 Neubrutalism —— 硬黑边 + 硬阴影与"金融专业稳重"调性冲突
- ❌ 不做浮夸动效 —— 用户每天打开，闪烁/弹跳会变成噪音

**目标情感**：冷静、克制、专业、可信。在信息密度中透出"私人书房"的呼吸感。

---

## 2. 设计原则 (Design Principles)

### 2.1 数据即主角
视觉装饰不抢信息焦点。所有"为了好看"的元素，必须让位给"为了看懂"的元素。
- KPI 数字比卡片背景更抢眼
- 涨/跌颜色比品牌主色更显眼
- 表格行高比卡片留白更重要

### 2.2 密度与呼吸并存
信息密度是骨架，杂志感留白是节奏。
- 表格行高 44px（紧凑）或 52px（宽松），根据信息量
- 卡片之间留 16-24px 间距，让眼睛能"换行"
- 标题与正文之间 8-12px，制造节拍感

### 2.3 状态可识别
颜色、图标、文字三重信号 —— 绝不仅靠颜色。
- P&L 涨：`success` 色 + ▲ 符号 + "涨"/正数前缀
- P&L 跌：`error` 色 + ▼ 符号
- 任务运行中：`info` 色 + `<Spin>` + "运行中"文字
- 错误：`error` 色 + 错误图标 + "重试"按钮
- 满足 WCAG 行 38 "color only" 反模式要求

### 2.4 主题一致性
暗色模式不是浅色的反相，是"冷峻模式"。
- 暗色背景阶梯 `#0A0E14 → #141A24 → #1A2230`（更冷、更 OLED-friendly）
- 暗色阴影用更深、扩散更大；加 `0 0 0 1px rgba(255,255,255,0.04)` 微亮高光
- 暗色文字不直接反相（避免纯白刺眼）：主文 `#E2E8F0` 而非 `#FFFFFF`

### 2.5 性能可感知
200ms 内必须有视觉反馈。
- Hover/press 反馈 ≤ 150ms
- 页面切换 ≤ 400ms
- 加载用 Skeleton 不用空白屏
- 滚动保持 60fps（避免 `box-shadow` 在大区域动画）
- 支持 `prefers-reduced-motion: reduce`（用户偏好优先）

---

## 3. 设计令牌 (Design Tokens)

> 所有 token 通过 CSS 变量定义在 [`frontend/src/styles/global.css`](frontend/src/styles/global.css)，由 [`frontend/src/theme/tokens.ts`](frontend/src/theme/tokens.ts) 单点对齐到 TS 层，再通过 [`tailwind.config.js`](frontend/tailwind.config.js) 映射到 Tailwind class。

### 3.1 Color 颜色

**主色 (Brand)**

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--color-primary` | `#1E40AF` 皇家蓝 | `#3B82F6` 电光蓝 | 品牌主色、Button、链接 |
| `--color-primary-hover` | `#1D4ED8` | `#60A5FA` | 主色 hover |
| `--color-primary-soft` | `#DBEAFE` | `#172554` | 主色淡背景（hover/选中） |
| `--color-on-primary` | `#FFFFFF` | `#FFFFFF` | 主色上的文字 |

**强调色 (Accent)** — 画龙点睛用，主:强调比例 ≥ 8:2

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--color-accent` | `#EC4899` 玫红 | `#F472B6` | 强调、关键 CTA、Hero 高亮 |
| `--color-accent-hover` | `#DB2777` | `#F9A8D4` | 强调 hover |
| `--color-accent-soft` | `#FCE7F3` | `#500724` | 强调淡背景 |
| `--color-on-accent` | `#FFFFFF` | `#FFFFFF` | 强调色上的文字 |

**语义色 (Semantic)** — 涨跌、状态、提示

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--color-success` | `#059669` 深绿 | `#10B981` 翠绿 | 涨 / 正 P&L / 成功 |
| `--color-success-soft` | `#D1FAE5` | `#022C22` | 成功淡背景 |
| `--color-error` | `#DC2626` | `#EF4444` | 跌 / 负 P&L / 错误 |
| `--color-error-soft` | `#FEE2E2` | `#450A0A` | 错误淡背景 |
| `--color-warning` | `#D97706` 琥珀 | `#F59E0B` | 警告 / 待办 / 中性 |
| `--color-warning-soft` | `#FEF3C7` | `#451A03` | 警告淡背景 |
| `--color-info` | `#0369A1` | `#38BDF8` | 信息、链接（次级） |
| `--color-info-soft` | `#E0F2FE` | `#082F49` | 信息淡背景 |

**中性色 (Neutral)** — 背景、边框、文字

| Token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--color-bg-base` | `#FAFBFC` | `#0A0E14` | 页面底色（比纯白略冷） |
| `--color-bg-container` | `#FFFFFF` | `#141A24` | 卡片/弹窗底 |
| `--color-bg-elevated` | `#FFFFFF` | `#1A2230` | 浮层（Modal/Drawer） |
| `--color-bg-layout` | `#F4F6F9` | `#0E1218` | Sider 底色 |
| `--color-border` | `#E2E8F0` | `#1E2A3B` | 卡片边线 |
| `--color-border-strong` | `#CBD5E1` | `#334155` | 表格分隔/重要边线 |
| `--color-text-primary` | `#0F172A` | `#E2E8F0` | 正文 |
| `--color-text-secondary` | `#475569` | `#94A3B8` | 次要文字 |
| `--color-text-tertiary` | `#94A3B8` | `#64748B` | 占位/空值/禁用 |
| `--color-text-inverse` | `#FFFFFF` | `#0F172A` | 反色文字 |

### 3.2 Typography 排版

**字体**：`Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`

不引外部字体（CLAUDE.md 本地化原则）；系统字自动 fallback。

**字重**：
- `400` Regular — 正文
- `500` Medium — 强调文字
- `600` Semibold — 标题、按钮
- `700` Bold — Hero 数字

**字号阶梯 (8 级)**

| Token | 字号 / 行高 | 用途 |
|---|---|---|
| `--text-display` | 32px / 40px | 页面大标题（标的详情 Hero） |
| `--text-h1` | 24px / 32px | 卡片大标题 |
| `--text-h2` | 20px / 28px | Section 标题 |
| `--text-h3` | 16px / 24px | 卡片内标题 |
| `--text-body` | 14px / 22px | 正文（默认） |
| `--text-caption` | 12px / 18px | 辅助、表格头 |
| `--text-tiny` | 11px / 16px | 极小（仅 chip / badge） |
| `--text-metric` | 28px / 36px | KPI 数字（自动右对齐 + tabular-nums） |

**数字格式**：所有金额、数量、百分比必须 `font-variant-numeric: tabular-nums`（金融刚需 —— 0 和 8 等宽，避免跳动）。

**字距**：标题 `letter-spacing: -0.02em`，正文默认 `0`，全大写用 `0.05em`。

### 3.3 Spacing 间距（8px 基准，6 级）

| Token | 值 | 用途 |
|---|---|---|
| `--space-1` | 4px | 标签内边距、icon 间距 |
| `--space-2` | 8px | 表单内边距、chip 间距 |
| `--space-3` | 12px | 卡片内边距（紧凑） |
| `--space-4` | 16px | 卡片内边距（标准）、卡片间距 |
| `--space-6` | 24px | Section 间距 |
| `--space-8` | 32px | 页面级间距 |

### 3.4 Radius 圆角（4 级）

| Token | 值 | 用途 |
|---|---|---|
| `--radius-sm` | 4px | chip / tag / input |
| `--radius-md` | 8px | button / 标准卡片 |
| `--radius-lg` | 12px | modal / drawer / 大卡片 |
| `--radius-xl` | 16px | Hero 卡片 / 大面板 |

### 3.5 Elevation 阴影（3 级，Dimensional Layering）

| Token | 阴影 | 用途 |
|---|---|---|
| `--elevation-1` | `0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 1px rgba(15, 23, 42, 0.02)` | 卡片 |
| `--elevation-2` | `0 4px 12px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04)` | 浮层（hover 卡片、dropdown） |
| `--elevation-3` | `0 12px 32px rgba(15, 23, 42, 0.08), 0 4px 8px rgba(15, 23, 42, 0.04)` | Modal、Drawer、CommandPalette |

**深色模式**：阴影更深、扩散更大（`rgba(0, 0, 0, 0.4)`），并叠加 `0 0 0 1px rgba(255, 255, 255, 0.04)` 微亮高光模拟深度。

### 3.6 Motion 动效

**时长（3 档）**

| Token | 值 | 曲线 | 用途 |
|---|---|---|---|
| `--motion-fast` | 150ms | `ease-out` | hover / 颜色变化 / 反馈 |
| `--motion-base` | 250ms | `cubic-bezier(0.2, 0, 0, 1)` | 卡片浮起 / 抽屉 / Tab 切换 |
| `--motion-slow` | 400ms | `cubic-bezier(0.16, 1, 0.3, 1)` | 页面切换 / Modal 进出 |

**关键 motion 模式**

| 模式 | 实现 | 适用 |
|---|---|---|
| **Card lift** | hover → `transform: translateY(-2px) + elevation-2` (250ms) | 可点击卡片 |
| **Press feedback** | active → `transform: scale(0.98)` (100ms) | Button / 可点击元素 |
| **Skeleton pulse** | `opacity: 0.4 → 0.8` 1.5s 循环 | 加载占位 |
| **Number flash** | 价格变动时数字背景色闪烁 1s | 实时行情 |

**无障碍**：`@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }`

### 3.7 Z-Index 层级

| Token | 值 | 用途 |
|---|---|---|
| `--z-base` | 0 | 默认 |
| `--z-dropdown` | 1000 | 下拉菜单 |
| `--z-sticky` | 1100 | 吸顶元素 |
| `--z-modal` | 1300 | Modal / Drawer |
| `--z-toast` | 1500 | 全局提示 |
| `--z-tooltip` | 1600 | Tooltip |

禁止使用 `z-index: 9999` 这类任意大值。

---

## 4. 组件库规范 (Component Specs)

> 所有组件必须满足：使用 token 化样式、覆盖所有 8 个状态（见 §5）、满足 §6 可访问性。

### 4.1 Button 按钮

**变体 (variant) × 颜色 (color) 矩阵**

| variant × color | primary | accent | neutral | success | error |
|---|---|---|---|---|---|
| **solid** 主操作 | `bg-primary text-on-primary` | `bg-accent text-on-accent` | `bg-bg-container text-text-primary border` | `bg-success text-white` | `bg-error text-white` |
| **soft** 次要 | `bg-primary-soft text-primary` | `bg-accent-soft text-accent` | `bg-bg-base text-text-primary` | `bg-success-soft text-success` | `bg-error-soft text-error` |
| **ghost** 第三级 | `text-primary border-primary` | `text-accent border-accent` | `text-text-secondary` | `text-success` | `text-error` |
| **link** 链接 | `text-primary` 下划线 hover | — | `text-text-secondary` | — | — |
| **danger** 危险 | — | — | — | — | `bg-error text-white` |

**尺寸**：`sm` 28px / `md` 36px / `lg` 44px（默认 md）

**圆角**：`--radius-md` (8px)

**图标**：`size === "sm"` 时 14px / 其他 16px；图标与文字间距 8px。

**禁用**：opacity 0.4 + `cursor: not-allowed`，不使用灰度滤镜。

### 4.2 Card 卡片

```
┌──────────────────────────────────────┐
│  标题 (H3)            [操作区]        │  ← header padding: 16px 20px
├──────────────────────────────────────┤
│                                      │
│  内容区                              │  ← body padding: 20px
│                                      │
└──────────────────────────────────────┘
```

- 圆角：`--radius-lg` (12px)
- 阴影：`--elevation-1`
- 边框：`1px solid var(--color-border)`
- 背景：`var(--color-bg-container)`
- 可点击卡片：hover → `translateY(-2px) + elevation-2` + 边框变 `--color-border-strong`
- 不可点击卡片：去掉 hover 效果

### 4.3 Input / Select 输入

- 高度：36px（默认）/ 28px（sm）/ 44px（lg）
- 圆角：`--radius-sm` (4px)
- 边框：默认 `--color-border`，focus `--color-primary` 2px
- 背景：`--color-bg-container`
- 文字：`--text-body`，占位符 `--color-text-tertiary`
- Focus ring：`outline: 2px solid var(--color-primary); outline-offset: 2px;`（3px 环）

### 4.4 Table 数据表

- **表头**：背景 `var(--color-bg-container)`，文字 `--color-text-secondary`，字号 caption (12px)，字重 600
- **行高**：44px（compact）或 52px（normal）
- **斑马纹**：奇行 `bg-container` / 偶行 `bg-base`（微差 0.5%）
- **数字列**：右对齐 + `font-variant-numeric: tabular-nums`
- **悬浮行**：背景 `var(--color-primary-soft)` @ 50% 透明度
- **边框**：`1px solid var(--color-border)` 仅横线（无竖线，减少视觉噪音）
- **空态**：用 antd `<Empty />` 组件，居中 + 描述文案

### 4.5 Tag / Badge 标签徽章

**变体**

| 变体 | 背景 | 文字 | 边框 | 用途 |
|---|---|---|---|---|
| `success` | `--color-success-soft` | `--color-success` | 无 | 涨 / 成功 |
| `error` | `--color-error-soft` | `--color-error` | 无 | 跌 / 错误 |
| `warning` | `--color-warning-soft` | `--color-warning` | 无 | 警告 |
| `info` | `--color-info-soft` | `--color-info` | 无 | 信息 |
| `neutral` | `--color-bg-base` | `--color-text-secondary` | 无 | 中性 |
| `accent` | `--color-accent-soft` | `--color-accent` | 无 | 强调 |

- 圆角：`--radius-sm` (4px)
- 内边距：2px 8px
- 字号：caption (12px)
- **必须配图标**（WCAG 颜色非唯一信号）：右侧 12px icon

### 4.6 PnL 数字 (盈利亏损)

**渲染规则**

```tsx
function PnlDisplay({ value, showPercent }: { value: number; showPercent?: number }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-text-tertiary">—</span>;
  }
  if (value === 0) {
    return <span className="text-text-secondary">0.00</span>;
  }
  const isUp = value > 0;
  return (
    <span className={isUp ? "text-success" : "text-error"}>
      {isUp ? "▲" : "▼"} {formatNumber(Math.abs(value))}
      {showPercent !== undefined && ` (${isUp ? "+" : "-"}${formatPercent(Math.abs(showPercent))})`}
    </span>
  );
}
```

- 涨：`▲` + `--color-success`
- 跌：`▼` + `--color-error`
- 平：0.00 + `--color-text-secondary`
- 空：`—` + `--color-text-tertiary`
- 数字 `font-variant-numeric: tabular-nums`

### 4.7 KPI 数字卡

```
┌──────────────┐
│ 总市值         │  ← label: caption 12px secondary
│ ¥ 123,456.78  │  ← value: metric 28px primary right-aligned
│ ▲ +1.23%     │  ← delta: success/error 12px
└──────────────┘
```

- 背景：`--color-bg-container`
- 内边距：`16px 20px`
- 圆角：`--radius-lg` (12px)
- 边框：可选 `1px solid var(--color-border)`
- 可点击：hover 浮起

### 4.8 Sider 侧栏

- 宽度：240px（展开）/ 64px（折叠）
- 背景：`--color-bg-layout`
- 边框：`1px solid var(--color-border)` 仅右侧
- 菜单项高度：40px
- 菜单项圆角：`--radius-sm` (6px)
- 菜单项 padding：8px 12px
- 菜单项 hover：`--color-primary-soft` 背景
- 菜单项 selected：`--color-primary-soft` 背景 + `--color-primary` 文字 + 左侧 3px primary 强调条
- 折叠态：仅图标，文字在 Tooltip 中显示

### 4.9 CommandPalette 命令面板

- 位置：屏幕居中，顶部 15%
- 最大宽：640px
- 圆角：`--radius-lg` (12px)
- 阴影：`--elevation-3`
- 背景：`--color-bg-elevated`
- 输入框：底部 1px 边框，focus 时变 `--color-accent`
- 列表项高度：48px
- 列表项圆角：`--radius-sm` (6px)
- 列表项 selected：`--color-primary-soft` 背景 + `--color-text-primary` 文字
- 列表项 hover：`--color-bg-base` 背景
- 键盘提示：右下角小字 `↑↓ 选择  ↵ 确认  ESC 关闭`

### 4.10 Modal 模态框 / Drawer 抽屉

- Modal 圆角：`--radius-lg` (12px)
- Modal 阴影：`--elevation-3`
- Modal 背景：`--color-bg-elevated`
- Modal 标题：H3 字号，左对齐
- Modal 关闭按钮：右上角，icon-only，必须有 `aria-label="关闭"`
- Modal 入场动画：400ms scale 0.95 → 1 + opacity 0 → 1
- Drawer 宽度：480px（标准）/ 720px（宽）
- Drawer 入场动画：400ms translateX 100% → 0

### 4.11 Empty 空状态

- 居中布局，垂直 padding 48px
- 图标：64px × 64px，浅色 `--color-text-tertiary` / 深色略亮
- 标题：H3 字号
- 描述：caption 字号 secondary
- 可选 CTA 按钮（不超过 1 个）

### 4.12 Skeleton 骨架屏

- 背景色：浅色 `#F1F5F9` / 深色 `#1E2A3B`
- 动画：`opacity 0.4 → 0.8` 1.5s ease-in-out infinite
- 圆角：与对应组件一致（卡片 12px、文本行 4px）
- 替代 `<Spin />` 用于"整页加载"，保留 `<Spin />` 用于"局部操作"

### 4.13 QueryErrorState 错误状态

```
┌──────────────────────────────────────┐
│         ⚠ (icon)                      │
│    加载失败                            │  ← H3
│    网络连接异常，请稍后重试              │  ← caption secondary
│         [ 重试 ]                       │  ← 按钮
└──────────────────────────────────────┘
```

- 图标：48px，`--color-error`
- 居中布局，padding 48px
- "重试"按钮：`variant="solid"` `color="primary"`
- 不同 HTTP 状态码文案：
  - 401: "API Key 无效，请检查配置"
  - 404: "资源不存在"
  - 422: "参数无效"
  - 500: "服务器异常"
  - 502/503/504: "后端服务暂不可用"
  - timeout: "请求超时"
  - network: "网络连接失败"

---

## 5. 状态体系 (State System)

每个组件必须覆盖以下 8 个状态：

| 状态 | 视觉表现 | 说明 |
|---|---|---|
| **default** | 基础样式 | 组件初始状态 |
| **hover** | 颜色/阴影变化、轻微位移 | 鼠标进入（`@media (hover: hover)` 限定） |
| **active / press** | scale 0.98 或 inset shadow | 按下瞬间反馈 |
| **focus** | outline 2-3px primary, offset 2px | 键盘聚焦（必须可见） |
| **disabled** | opacity 0.4 + `cursor: not-allowed` | 不可交互 |
| **loading** | 内部用 Skeleton 或 `<Spin />` | 异步加载中 |
| **error** | 红色边框 + 错误文案 | 校验失败 / 接口失败 |
| **empty** | Empty 组件 | 无数据 |

**键盘导航**：所有可交互组件必须支持 `Tab` 聚焦 + `Enter`/`Space` 触发。
**Focus ring**：永远不要 `outline: none` 不带替代方案。

---

## 6. 可访问性 (Accessibility · WCAG AA)

### 6.1 颜色对比度

| 元素 | 最小对比度 | 验证方式 |
|---|---|---|
| 正文文字 | 4.5:1 | `color: var(--color-text-primary)` on `var(--color-bg-base)` |
| 大文字（≥18pt / 14pt bold） | 3:1 | 同上 |
| UI 组件（按钮、输入框边框） | 3:1 | `var(--color-border)` on `var(--color-bg-container)` |
| 非文字（icon、装饰图） | 3:1 | 装饰性元素可豁免，但功能性元素必须满足 |

**验证工具**：WebAIM Contrast Checker / Lighthouse。

### 6.2 触摸目标

- 最小尺寸：44px × 44px（WCAG 2.5.5）
- 间距：相邻可点击元素最小 8px
- 桌面端可豁免，但移动端必须满足

### 6.3 Focus 指示

- Focus ring 宽度：3px
- Focus ring 颜色：`--color-primary`
- Focus ring offset：2px
- 永远不删除 `outline` 不给替代

### 6.4 Motion 减弱

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 6.5 语义化

- 标题层级严格 h1 → h2 → h3 不跳级
- 按钮用 `<button>`，链接用 `<a>`，不要互相替代
- 表单 `<label>` 与 `<input>` 通过 `htmlFor` / `id` 关联
- 图标按钮必须有 `aria-label`
- 装饰性图片 `alt=""`，信息性图片 `alt="描述"`

### 6.6 颜色之外

- 状态信息：颜色 + 图标 + 文字 三重信号
- P&L 涨：绿色 + ▲ 符号 + "涨"字 / 正号
- 任务运行中：蓝色 + spinner + "运行中"文字
- 错误：红色 + ⚠ 图标 + "失败"文字
- 不能"只靠颜色"传达信息（WCAG 1.4.1）

---

## 7. 实施规范 (Implementation Rules)

### 7.1 命名约定

**Token 使用**
- CSS 变量：`var(--color-primary)`（CSS 原生）
- Tailwind class：`text-primary` / `bg-primary` / `border-border`（已映射到 token）
- TS：import from `@/theme/tokens.ts`

**禁止**：
- ❌ `text-blue-500`（Tailwind 内置色，硬编码，与主题脱节）
- ❌ `text-gray-400` / `text-gray-500`（现状有，Phase 2 改）
- ❌ `#1E40AF` 直接出现在 JSX 中（应走 token）
- ❌ `color: "red"` / `color: "green"` 给 antd Tag（应走 token + 图标）

### 7.2 什么时候用 antd 默认 vs 自定义 token

| 场景 | 策略 |
|---|---|
| 主 Button / 链接 / 品牌色相关 | 用 `ConfigProvider` 注入 token，让 antd 用我们的色 |
| 简单布局组件（Space / Row / Col） | 用 antd 默认 |
| Tag / Badge 颜色 | 不用 antd 颜色，**自定义 `<StatusTag>`** |
| PnL 数字 | **自定义 `<PnlDisplay>`** |
| 错误态 | **统一用 `<QueryErrorState>`** |
| KPI 数字 | **自定义 `<KpiCard>`**（后续 Phase 引入） |

### 7.3 暗色模式

- 通过 `<html data-theme="dark">` 切换
- CSS 变量根据 `data-theme` 切换值
- 不在组件里写 `if (isDark) { ... }` 分支
- 不使用 antd `theme="dark"` prop（受 antd ConfigProvider 全局管理）
- antd `theme="light"` 是 antd 5 的浅色默认——**`Sider` 上的 `theme="light"` 是错误的硬编码**，应删除

### 7.4 现状问题对照表（需要 Phase 2-5 修复）

| 现状问题 | 修复方案 | 引用文件 |
|---|---|---|
| Sider `theme="light"` 写死 | 删除 prop，让 ConfigProvider 接管 | [`frontend/src/components/layout/AppLayout.tsx:24`](frontend/src/components/layout/AppLayout.tsx) |
| PnlDisplay 用 `text-gray-400` | 改为 `text-text-tertiary` token | [`frontend/src/components/shared/PnlDisplay.tsx:23`](frontend/src/components/shared/PnlDisplay.tsx) |
| StatusTag 用 antd 内置色 | 改为 token + 配 icon | [`frontend/src/components/shared/StatusTag.tsx:13`](frontend/src/components/shared/StatusTag.tsx) |
| AssetDetail `h-[calc(100vh-200px)]` | 改 `flex-1 min-h-0` | [`frontend/src/pages/AssetDetail/index.tsx`](frontend/src/pages/AssetDetail/index.tsx) |
| CommandPalette 选中色 `#fff` 硬编码 | 改 `--color-on-primary` | [`frontend/src/styles/global.css:192`](frontend/src/styles/global.css) |
| 7 page 错误态不统一 | 全部替换为 `<QueryErrorState>` | 4 个 page 待替换（AiReports/TaskStatus/TrackedAssets/NewsList） |

### 7.5 验证清单 (Pre-Delivery Checklist)

每次 PR 提交前，对所有改动文件跑以下检查：

- [ ] 视觉：所有 token 化样式生效，无硬编码颜色/尺寸
- [ ] 交互：hover / press / focus / disabled 4 态全部生效
- [ ] 明暗：light + dark 模式都目视检查
- [ ] 布局：1280 / 1024 / 768 三种宽度不破图
- [ ] 可访问性：focus ring 可见、对比度 ≥ 4.5、键盘可达、aria-label 完备
- [ ] 性能：滚动 60fps（避免 box-shadow 动画大区域）
- [ ] Reduced motion：开启后无动效
- [ ] 无 console 警告

### 7.6 验证命令

```bash
# 前端静态检查
cd frontend && npm run lint && npm run type-check && npm run build

# 后端回归（前端改动不应破坏后端测试，但跑一遍兜底）
uv run pytest tests/ -v

# 启动 dev server 浏览器目视
uv run python scripts/launcher.py
# 或分别启动
cd frontend && npm run dev  # http://localhost:5173
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 附录 A：相关文件索引

| 文件 | 职责 |
|---|---|
| [`frontend/src/styles/global.css`](frontend/src/styles/global.css) | CSS 变量定义、antd 主题覆盖、全局样式 |
| [`frontend/src/theme/tokens.ts`](frontend/src/theme/tokens.ts) | TS 端 token 单点 |
| [`frontend/tailwind.config.js`](frontend/tailwind.config.js) | Tailwind 与 token 映射 |
| [`frontend/src/main.tsx`](frontend/src/main.tsx) | ConfigProvider / Theme 注入 |
| [`frontend/src/store/preferences.ts`](frontend/src/store/preferences.ts) | zustand 主题偏好持久化 |
| [`frontend/src/components/layout/AppLayout.tsx`](frontend/src/components/layout/AppLayout.tsx) | 全局 Layout 框架 |
| [`frontend/src/components/shared/`](frontend/src/components/shared/) | 共享组件库（10 个） |
| [`frontend/src/pages/`](frontend/src/pages/) | 7 个业务页面 |

## 附录 B：参考资源

- **本设计语言灵感来源**：`C:\Users\18906\.claude\skills\ui-ux-pro-max-0.1.0\assets\data\`
  - `colors.csv` — 100+ 产品类型配色方案
  - `styles.csv` — 70+ 视觉风格定义
  - `typography.csv` — 60+ 字体配对方案
  - `ux-guidelines.csv` — 250+ UX 反模式与最佳实践
  - `charts.csv` — 25+ 图表类型选择指南
- **WCAG 2.1 规范**：https://www.w3.org/WAI/WCAG21/quickref/
- **Inter 字体**（如未来引入）：https://rsms.me/inter/

## 附录 C：版本历史

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-06-12 | 初版。研究终端方向，皇家蓝 + 玫红配色，Inter 排版，3 级 elevation。Phase 1 文档化。 |
