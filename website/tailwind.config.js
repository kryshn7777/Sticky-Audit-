/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'neo-bg': '#F4F4F0',
        'neo-yellow': '#FFF200',
        'neo-blue': '#00E5FF',
        'neo-pink': '#FF3366',
        'neo-green': '#00FF66',
        'neo-orange': '#FF6600',
        'brand-dark': '#000000',
        'sticky-yellow': '#fdf6b1',
        'sticky-green': '#dcfce7',
        'sticky-blue': '#e0f2fe',
        'sticky-pink': '#fae8ff',
        'sticky-purple': '#f3e8ff',
      },
      fontFamily: {
        sans: ['Space Grotesk', 'sans-serif'],
        handwriting: ['Kalam', 'cursive'],
      },
      borderWidth: {
        '3': '3px',
      },
      boxShadow: {
        'neo': '6px 6px 0px rgba(0, 0, 0, 1)',
        'neo-sm': '4px 4px 0px rgba(0, 0, 0, 1)',
        'neo-lg': '10px 10px 0px rgba(0, 0, 0, 1)',
      }
    },
  },
  plugins: [],
}
