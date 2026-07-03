/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
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
      },
      fontFamily: {
        sans: ["Geist", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "SF Mono", "monospace"],
      },
      borderRadius: {
        xl: "16px",
      },
    },
  },
  plugins: [],
};
