/**@type{import('tailwindcss').Config}*/
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "var(--bg-color)",
        surface: "var(--surface-color)",
        primary: "var(--primary-color)",
        text: "var(--text-color)",
        primaryBg: "var(--primary-bg-color)",
      },
    },
  },
} satisfies Config;
