/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#EAF6F1",
          100: "#CFEBE0",
          200: "#A0D7C2",
          300: "#6FC0A2",
          400: "#3D9E80",
          500: "#0F7D63",
          600: "#0C6551",
          700: "#0A5142",
          800: "#083F34",
          900: "#062E26",
        },
        bronze: {
          50: "#FBF4E9",
          100: "#F1E1C4",
          200: "#E3C593",
          300: "#D2A85F",
          400: "#BE8F3F",
          500: "#A8752D",
          600: "#8B5F24",
          700: "#6E4B1E",
        },
        surface: {
          page: "var(--surface-page)",
          canvas: "var(--surface-canvas)",
          card: "var(--surface-card)",
          sunken: "var(--surface-sunken)",
        },
        loko: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
          disabled: "var(--text-disabled)",
          "on-brand": "var(--text-on-brand)",
          link: "var(--text-link)",
        },
        "brand-token": {
          DEFAULT: "var(--brand-primary)",
          hover: "var(--brand-primary-hover)",
          active: "var(--brand-primary-active)",
          tint: "var(--brand-primary-tint)",
        },
        "success-s": {
          bg: "var(--success-bg)",
          fg: "var(--success-fg)",
          border: "var(--success-border)",
        },
        "warning-s": {
          bg: "var(--warning-bg)",
          fg: "var(--warning-fg)",
          border: "var(--warning-border)",
        },
        "error-s": {
          bg: "var(--error-bg)",
          fg: "var(--error-fg)",
          border: "var(--error-border)",
        },
        "info-s": {
          bg: "var(--info-bg)",
          fg: "var(--info-fg)",
          border: "var(--info-border)",
        },
      },
      fontFamily: {
        sans: ["Geist", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "SF Mono", "monospace"],
      },
      borderRadius: {
        xs: "4px",
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "24px",
        pill: "999px",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
    },
  },
  plugins: [],
};
