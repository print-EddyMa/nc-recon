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
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
      },
    },
  },
  plugins: [],
};
