/** @type {import('tailwindcss').Config} */

// Colours are CSS custom properties (space-separated R G B) defined in index.css
// for the light theme, overridden for dark. `<alpha-value>` keeps `bg-x/60` etc.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: v("canvas"),
        surface: v("surface"),
        "surface-2": v("surface-2"),
        line: v("line"),
        "line-strong": v("line-strong"),
        ink: v("ink"),
        "ink-dim": v("ink-dim"),
        "ink-faint": v("ink-faint"),
        accent: v("accent"),
        "accent-soft": v("accent-soft"),
        "accent-ink": v("accent-ink"),
        meter: v("meter"),
        // xView2 four-level damage ramp (semantic, theme-independent).
        // Keep in sync with DAMAGE[] in src/lib/damage.ts.
        dmg0: "#3fa06d",
        dmg1: "#efb036",
        dmg2: "#e56a2b",
        dmg3: "#a81b38",
      },
      fontFamily: {
        // Serif display — the register US government statistical / hazard
        // products use (Census, BLS, USWDS default). Reads as an official
        // instrument, not a generated landing page. Body + figures stay sans.
        display: ['"Source Serif 4"', "Georgia", "ui-serif", "serif"],
        sans: ['"Geist"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        1: "0 1px 2px rgb(var(--shadow) / 0.10), 0 1px 3px rgb(var(--shadow) / 0.08)",
        2: "0 4px 12px rgb(var(--shadow) / 0.14), 0 12px 32px rgb(var(--shadow) / 0.12)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        "in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
        drawer: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.005em" }],
        // restrained display steps (see --text-display in index.css)
        display: ["var(--text-display)", { lineHeight: "1.12", letterSpacing: "-0.006em" }],
        "display-s": ["var(--text-display-s)", { lineHeight: "1.16", letterSpacing: "-0.004em" }],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
        xl: "14px",
      },
    },
  },
  plugins: [],
};
