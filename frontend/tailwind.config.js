/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // 预留给后续 antd 主题 token 同步
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#1677ff",
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
