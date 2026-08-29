/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#10151c",
        surface: "#161d26",
        "surface-2": "#1c2530",
        line: "#2a333f",
        "line-strong": "#3a4655",
        ink: "#c9d3de",
        "ink-dim": "#8593a3",
        "ink-faint": "#5b6875",
        accent: "#3fb6c4",
        "accent-dim": "#2b7f8a",
        dmg0: "#f5d76e",
        dmg1: "#e8894a",
        dmg2: "#d1495b",
        dmg3: "#8b1e3f",
      },
      fontFamily: {
        display: ['"Space Grotesk"', "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ['"Geist"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        1: "0 1px 2px rgba(4,8,14,0.4), 0 2px 8px rgba(4,8,14,0.3)",
        2: "0 4px 12px rgba(4,8,14,0.45), 0 12px 32px rgba(4,8,14,0.4)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        "in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
        drawer: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
      },
    },
  },
  plugins: [],
};
