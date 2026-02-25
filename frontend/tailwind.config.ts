import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        vault: {
          black: "#0d0f11",
          DEFAULT: "#0d0f11",
        },
        charcoal: {
          DEFAULT: "#1a1d22",
          light: "#1e2228",
        },
        "wet-stone": {
          DEFAULT: "#252930",
          light: "#2c3038",
        },
        "slate-border": "#2f343b",
        bone: {
          DEFAULT: "#c8c2b8",
          muted: "#8a857d",
          dim: "#5a5650",
        },
        "cold-teal": {
          DEFAULT: "#2dd4a8",
          dim: "#1a7d64",
          glow: "rgba(45, 212, 168, 0.15)",
        },
        "clinical-cyan": {
          DEFAULT: "#22d3ee",
          dim: "#0e7490",
        },
        "dried-blood": {
          DEFAULT: "#8b2500",
          bright: "#c43b2e",
          dim: "#5c1a00",
        },
      },
      fontFamily: {
        heading: ["Rajdhani", "sans-serif"],
        body: ["IBM Plex Sans", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
      boxShadow: {
        vault: "0 2px 8px rgba(0, 0, 0, 0.4)",
        "vault-lg": "0 4px 16px rgba(0, 0, 0, 0.5)",
        "teal-glow": "0 0 12px rgba(45, 212, 168, 0.15)",
        "teal-glow-lg": "0 0 20px rgba(45, 212, 168, 0.25)",
        "cyan-glow": "0 0 12px rgba(34, 211, 238, 0.15)",
        "blood-glow": "0 0 12px rgba(139, 37, 0, 0.3)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-out forwards",
        "slide-in": "slideIn 0.3s ease-out forwards",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
