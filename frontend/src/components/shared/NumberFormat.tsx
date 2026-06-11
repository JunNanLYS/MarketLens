import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { formatWithUnit } from "@/utils/format";

interface Props {
  value: number | null | undefined;
  /** 是否在值变化时显示脉冲高亮（用于实时刷新的数字） */
  pulse?: boolean;
  className?: string;
}

/**
 * 数字格式化组件：
 * - 初次加载时从 0 tween 到目标值
 * - 值变化时可选脉冲高亮（pulse）
 * - prefers-reduced-motion 时降级为硬切
 */
export function NumberFormat({ value, pulse = false, className }: Props) {
  const prefersReducedMotion = useReducedMotion();
  const [displayValue, setDisplayValue] = useState<number | null>(null);
  const prevValueRef = useRef<number | null | undefined>(undefined);
  const isFirstRender = useRef(true);
  const [isPulsing, setIsPulsing] = useState(false);

  // 初次 tween：从 0 渐变到目标值
  useEffect(() => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      setDisplayValue(null);
      return;
    }
    if (isFirstRender.current) {
      isFirstRender.current = false;
      if (prefersReducedMotion) {
        setDisplayValue(value);
        return;
      }
      // 简单 tween：300ms 内从 0 渐变到目标值
      const duration = 300;
      const start = performance.now();
      let rafId: number;
      const animate = (now: number) => {
        const progress = Math.min((now - start) / duration, 1);
        // easeOutCubic
        const eased = 1 - Math.pow(1 - progress, 3);
        setDisplayValue(value * eased);
        if (progress < 1) {
          rafId = requestAnimationFrame(animate);
        } else {
          setDisplayValue(value);
        }
      };
      rafId = requestAnimationFrame(animate);
      return () => cancelAnimationFrame(rafId);
    }
    // 非首次：直接设值
    setDisplayValue(value);
  }, [value, prefersReducedMotion]);

  // 脉冲高亮：值变化时短暂闪一下背景色
  useEffect(() => {
    if (!pulse || prefersReducedMotion) return;
    if (prevValueRef.current !== undefined && prevValueRef.current !== value && value !== null && value !== undefined) {
      setIsPulsing(true);
      const timer = setTimeout(() => setIsPulsing(false), 300);
      return () => clearTimeout(timer);
    }
    prevValueRef.current = value;
  }, [value, pulse, prefersReducedMotion]);

  if (displayValue === null || displayValue === undefined) {
    return <span className={`tabular-nums ${className ?? ""}`}>-</span>;
  }

  return (
    <span
      className={`tabular-nums ${isPulsing ? "number-pulse" : ""} ${className ?? ""}`}
    >
      {formatWithUnit(displayValue)}
    </span>
  );
}