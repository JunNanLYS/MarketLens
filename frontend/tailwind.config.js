/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "var(--color-primary)",
          success: "var(--color-success)",
          warning: "var(--color-warning)",
          error: "var(--color-error)",
          info: "var(--color-info)",
        },
      },
    },
  },
  // 避免与 antd reset 冲突，跳过 preflight
  corePlugins: {
    preflight: false,
  },
  plugins: [],
};