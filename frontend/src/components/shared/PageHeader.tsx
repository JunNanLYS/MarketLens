import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
}

// 统一页面头：标题 + 副标题 + 右侧操作区。
// 符合 DESIGN.md §3.2 字号阶梯：标题 24/32、副标题 13/20 secondary。
// 用于 7 page 顶部，建立统一的视觉锚点。
export function PageHeader({ title, subtitle, extra }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-title-block">
        <h1 className="page-header-title">{title}</h1>
        {subtitle && <span className="page-header-subtitle">{subtitle}</span>}
      </div>
      {extra && <div className="page-header-extra">{extra}</div>}
    </header>
  );
}
