import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: "#1b201b",
          900: "#2a3028",
          850: "#30372d",
          800: "#384033",
          750: "#1d2b49",
          700: "#27375c",
        },
        vault: {
          950: "#1b201b",
          900: "#2a3028",
          850: "#30372d",
          800: "#1e293b",
          700: "#334155",
        },
        electric: {
          400: "#fde047",
          500: "#eab308",
          600: "#ca8a04",
        },
        fire: {
          400: "#f87171",
          500: "#ef4444",
          600: "#dc2626",
        },
        water: {
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
        },
        grass: {
          400: "#4ade80",
          500: "#22c55e",
          600: "#16a34a",
        },
        psychic: {
          400: "#c084fc",
          500: "#a855f7",
          600: "#9333ea",
        },
        gold: {
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
        },
      },
      aspectRatio: {
        card: "2.5 / 3.5",
      },
      boxShadow: {
        slab: "0 1px 3px 0 rgba(0, 0, 0, 0.4), 0 1px 2px -1px rgba(0, 0, 0, 0.4)",
        "slab-hover":
          "0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)",
      },
    },
  },
  plugins: [],
};

export default config;
