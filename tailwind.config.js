/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js"
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Admin theme colors
        'admin-primary': '#1e40af',
        'admin-secondary': '#3b82f6',
        'admin-accent': '#60a5fa',
        // Brand colors for campus selection
        brand: {
          royal: '#1d4ed8',
          emerald: '#10b981',
          slate: '#111827'
        }
      },
      boxShadow: {
        glow: '0 10px 25px rgba(29,78,216,.22)'
      },
      borderRadius: {
        '2xl': '1rem'
      },
      animation: {
        fadeUp: 'fadeUp .6s ease-out both',
        float: 'float 6s ease-in-out infinite'
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' }
        }
      }
    },
  },
  plugins: [],
}
