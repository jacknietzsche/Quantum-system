/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        slate: {
          750: '#1e293b',
          850: '#0f172a',
          950: '#020617',
        },
      },
    },
  },
  plugins: [],
}
