import { useMemo } from "react";
import ReactECharts from "echarts-for-react";

interface Props {
  /** 收盘价序列（最新在末尾） */
  data: number[];
  /** 是否为下跌趋势（红色），默认根据首尾值自动判断 */
  isDown?: boolean;
  /** 高度，默认 24 */
  height?: number;
  className?: string;
}

/**
 * 迷你趋势图组件：
 * - 24px 高度迷你 sparkline，嵌入表格单元格
 * - 配色跟随主题 CSS 变量（浅色/深色自动切换）
 * - 动画关闭（避免表格渲染抖动）
 */
export function Sparkline({ data, isDown: isDownProp, height = 24, className }: Props) {
  const isDown = isDownProp ?? (data.length >= 2 && data[data.length - 1] < data[0]);

  // 抽样当数据点 > 50 时
  const sampledData = useMemo(() => {
    if (data.length <= 50) return data;
    const step = Math.ceil(data.length / 50);
    return data.filter((_, i) => i % step === 0 || i === data.length - 1);
  }, [data]);

  const option = useMemo(
    () => ({
      animation: false,
      grid: { left: 0, right: 0, top: 1, bottom: 1 },
      xAxis: { show: false, type: "category" as const, boundaryGap: false },
      yAxis: { show: false, type: "value" as const },
      series: [
        {
          type: "line" as const,
          data: sampledData,
          showSymbol: false,
          lineStyle: {
            width: 1.5,
            color: isDown
              ? "var(--sparkline-down-color)"
              : "var(--sparkline-color)",
          },
          areaStyle: {
            color: isDown
              ? "var(--sparkline-down-area)"
              : "var(--sparkline-area)",
          },
        },
      ],
      tooltip: { show: false },
    }),
    [sampledData, isDown],
  );

  return (
    <ReactECharts
      option={option}
      style={{ height, width: "100%" }}
      opts={{ renderer: "svg" }}
      className={className}
      notMerge
      lazyUpdate
    />
  );
}