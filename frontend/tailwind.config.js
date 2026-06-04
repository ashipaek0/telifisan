/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface: {
          50: 'var(--s-50)', 100: 'var(--s-100)', 200: 'var(--s-200)',
          300: 'var(--s-300)', 400: 'var(--s-400)', 500: 'var(--s-500)',
          600: 'var(--s-600)', 700: 'var(--s-700)', 800: 'var(--s-800)',
          900: 'var(--s-900)', 950: 'var(--s-950)',
        },
        accent: {
          400: 'var(--a-400)', 500: 'var(--a-500)', 600: 'var(--a-600)', 700: 'var(--a-700)',
        },
      },
    },
  },
  plugins: [],
};
