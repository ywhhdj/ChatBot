/**@type{import('tailwindcss').Config}*/
module.exports = {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}",], theme: {
    extend: {
      colors: {
        primary: '#1890ff',// 扩展主题色 
      }
    },
  },
  plugins: [],
}