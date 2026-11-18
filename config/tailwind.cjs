module.exports = {
  content: [
    "./frontend/index.html",
    "./frontend/auth.js",
    "./frontend/app.js",
    "./frontend/finance.js",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
