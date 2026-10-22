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
        brand: v("brand"),
        review: v("review"),
        "st-ok": v("st-ok"),
        "st-warn": v("st-warn"),
        "st-bad": v("st-bad"),
        "st-unknown": v("st-unknown"),
        // FEMA five-level damage scale (ColorBrewer YlOrRd with a grey base),
        // data colours, identical in both themes. Keep in sync with FEMA_HEX
        // in src/lib/ops.ts.
        "f-none": "#9e9e9e",
        "f-aff": "#fecc5c",
        "f-min": "#fd8d3c",
        "f-maj": "#f03b20",
        "f-des": "#bd0026",
        warn: v("warn-bg"),
        "warn-ink": v("warn-ink"),
        // xView2 four-level damage ramp (semantic, theme-independent).
        // Keep in sync with DAMAGE[] in src/lib/damage.ts.
        dmg0: "#3fa06d",
        dmg1: "#efb036",
        dmg2: "#e56a2b",
        dmg3: "#a81b38",
      },
      fontFamily: {
        // Marcellus: the Groma wordmark and document titles only (Roman
        // inscriptional capitals, the brand's surveyor lineage).
        display: ['"Marcellus"', '"Trajan Pro"', "Optima", "Georgia", "serif"],
        // Public Sans: the US Web Design System typeface, the register the
        // government users of this tool already read every day.
        sans: ['"Public Sans Variable"', '"Public Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        // IBM Plex Mono: every figure in a column, grid references, times.
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
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
