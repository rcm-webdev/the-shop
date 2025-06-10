/** @type {import('tailwindcss').Config} */
module.exports = {
    content: ["./views/**/*.ejs", "./public/**/*.js"],
    theme: {
      extend: {},
    },
    plugins: [require("daisyui")],
    daisyui: {
      themes: ["light", "dark", "pastel"], // You can add more themes or customize them
      darkTheme: "dark",
      base: true,
      styled: true,
      utils: true,
      prefix: "",
      logs: true,
    },
  };
  