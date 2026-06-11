import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  delay?: number;
}

// 卡片/列表项进出场动画；用户偏好减少动态效果时直接回退为静态容器。
export function MotionCard({ children, delay = 0 }: Props) {
  const shouldReduceMotion = useReducedMotion();

  if (shouldReduceMotion) {
    return <div>{children}</div>;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.18, delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
