/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      // ═══════ Color tokens（DESIGN.md §3.1）═══════
      colors: {
        // 透明 / 继承
        transparent: "transparent",
        current: "currentColor",
        inherit: "inherit",

        // 主色 (Brand)
        primary: {
          DEFAULT: "var(--color-primary)",
          hover: "var(--color-primary-hover)",
          soft: "var(--color-primary-soft)",
        },

        // 强调色 (Accent)
        accent: {
          DEFAULT: "var(--color-accent)",
          hover: "var(--color-accent-hover)",
          soft: "var(--color-accent-soft)",
        },

        // 语义色 (Semantic)
        success: {
          DEFAULT: "var(--color-success)",
          soft: "var(--color-success-soft)",
        },
        error: {
          DEFAULT: "var(--color-error)",
          soft: "var(--color-error-soft)",
        },
        warning: {
          DEFAULT: "var(--color-warning)",
          soft: "var(--color-warning-soft)",
        },
        info: {
          DEFAULT: "var(--color-info)",
          soft: "var(--color-info-soft)",
        },

        // 中性色 (Neutral) - 替换 Tailwind 内置 gray
        bg: {
          base: "var(--color-bg-base)",
          container: "var(--color-bg-container)",
          elevated: "var(--color-bg-elevated)",
          layout: "var(--color-bg-layout)",
        },
        border: {
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
        },
        text: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          tertiary: "var(--color-text-tertiary)",
          inverse: "var(--color-text-inverse)",
        },

        // 兼容别名：保留 brand.* 别名，避免旧代码大面积报错
        brand: {
          DEFAULT: "var(--color-primary)",
          hover: "var(--color-primary-hover)",
          soft: "var(--color-primary-soft)",
          success: "var(--color-success)",
          warning: "var(--color-warning)",
          error: "var(--color-error)",
          info: "var(--color-info)",
        },
      },

      // ═══════ Border Radius（DESIGN.md §3.4）═══════
      borderRadius: {
        none: "0",
        sm: "4px",
        DEFAULT: "8px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        full: "9999px",
      },

      // ═══════ Box Shadow（DESIGN.md §3.5）═══════
      boxShadow: {
        none: "none",
        sm: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 1px rgba(15, 23, 42, 0.02)",
        DEFAULT: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 1px rgba(15, 23, 42, 0.02)",
        md: "0 4px 12px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04)",
        lg: "0 12px 32px rgba(15, 23, 42, 0.08), 0 4px 8px rgba(15, 23, 42, 0.04)",
        xl: "0 20px 50px rgba(15, 23, 42, 0.12), 0 8px 16px rgba(15, 23, 42, 0.06)",
        "inner-card": "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 1px rgba(15, 23, 42, 0.02)",
      },

      // ═══════ Font Family（DESIGN.md §3.2）═══════
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "Roboto Mono",
          "SF Mono",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },

      // ═══════ Font Size（DESIGN.md §3.2 字号阶梯）═══════
      fontSize: {
        xs: ["11px", { lineHeight: "16px" }],
        sm: ["12px", { lineHeight: "18px" }],
        base: ["14px", { lineHeight: "22px" }],
        lg: ["16px", { lineHeight: "24px" }],
        xl: ["20px", { lineHeight: "28px" }],
        "2xl": ["24px", { lineHeight: "32px" }],
        "3xl": ["32px", { lineHeight: "40px" }],
        metric: ["28px", { lineHeight: "36px" }],
      },

      // ═══════ Spacing（DESIGN.md §3.3 8px 基准）═══════
      spacing: {
        "space-1": "4px",
        "space-2": "8px",
        "space-3": "12px",
        "space-4": "16px",
        "space-6": "24px",
        "space-8": "32px",
      },

      // ═══════ Animation Duration（DESIGN.md §3.6）═══════
      transitionDuration: {
        fast: "150ms",
        base: "250ms",
        slow: "400ms",
      },

      // ═══════ Z-Index（DESIGN.md §3.7）═══════
      zIndex: {
        base: "0",
        dropdown: "1000",
        sticky: "1100",
        modal: "1300",
        toast: "1500",
        tooltip: "1600",
      },
    },
  },
  // 避免与 antd reset 冲突，跳过 preflight
  corePlugins: {
    preflight: false,
  },
  plugins: [],
};
