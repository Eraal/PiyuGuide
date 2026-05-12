/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js"
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
      colors: {
        // LSPU Brand palette
        lspu: {
          primary:   '#1d4ed8', // blue-700  — primary actions, active nav, topbar
          'primary-dark': '#1e3a8a', // blue-900 — hover states
          'primary-light': '#dbeafe', // blue-100 — hover fills, sidebar bg
          green:     '#16a34a', // green-600 — sessions / success
          'green-light': '#dcfce7', // green-100
          yellow:    '#ca8a04', // yellow-600 — pending / warning (sparse)
          'yellow-light': '#fef9c3', // yellow-100
          teal:      '#0d9488', // teal-600  — announcements accent
          'teal-light': '#ccfbf1', // teal-100
        },
        // Admin theme colors (preserved for admin templates)
        'admin-primary': '#1e40af',
        'admin-secondary': '#3b82f6',
        'admin-accent': '#60a5fa',
        // Legacy brand (campus selection page)
        brand: {
          royal:   '#1d4ed8',
          emerald: '#10b981',
          slate:   '#111827'
        }
      },
      boxShadow: {
        glow:  '0 10px 25px rgba(29,78,216,.22)',
        card:  '0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.05)',
        'card-hover': '0 4px 12px rgba(0,0,0,.10)',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      animation: {
        fadeUp:   'fadeUp .6s ease-out both',
        float:    'float 6s ease-in-out infinite',
        slideIn:  'slideIn .25s ease-out both',
      },
      keyframes: {
        fadeUp: {
          '0%':   { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%':      { transform: 'translateY(-10px)' }
        },
        slideIn: {
          '0%':   { opacity: '0', transform: 'translateX(-12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' }
        }
      }
    },
  },
  plugins: [],
}
