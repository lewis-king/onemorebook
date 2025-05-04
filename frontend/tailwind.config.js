/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'comic': ['"Comic Neue"', 'Comic Sans MS', 'cursive'],
        'rounded': ['Varela Round', 'sans-serif'],
      },
      colors: {
        'kiddy': {
          primary: '#FF6B6B',
          secondary: '#4ECDC4',
          accent: '#FFE66D',
          background: '#F7F9FC',
        }
      },
      animation: {
        'float': 'float 6s ease-in-out infinite',
        'page-turn': 'pageTurn 0.5s ease-in-out',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        pageTurn: {
          '0%': { transform: 'rotateY(0deg)' },
          '100%': { transform: 'rotateY(-10deg)' },
        }
      }
    },
  },
  plugins: [],
}