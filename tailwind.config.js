/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef6ff', 100: '#d9eaff', 200: '#bcdaff', 300: '#8ec2ff',
          400: '#599fff', 500: '#2f7bff', 600: '#1a5cf5', 700: '#1549e1',
          800: '#173cb6', 900: '#19388f', 950: '#142355',
        },
      },
    },
  },
  plugins: [],
}