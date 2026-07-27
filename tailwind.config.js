/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./templates/**/*.html'],
  theme: {
    extend: {
      colors: {
        /* Calm "Sakinah" palette — muted pine (was vivid/clashing greens). */
        'gov-green': {
          50: '#eff4f1',
          100: '#e1ece7',
          200: '#c4d9d0',
          300: '#9ec2b3',
          400: '#6fa48f',
          500: '#4c8a72',
          600: '#3d7961',
          700: '#356a54',
          800: '#2a5646',
          900: '#1f4135',
          950: '#12271f',
        },
        /* Warm greige neutrals (was cold blue-grays). */
        'gov-gray': {
          50: '#f6f5f1',
          100: '#efede7',
          200: '#e3e1d9',
          300: '#cfcdc3',
          400: '#a8a79c',
          500: '#797a70',
          600: '#5b5c53',
          700: '#42433c',
          800: '#2b2c27',
          900: '#1a1b17',
        },
        /* Muted semantics + sand accent, separate from the brand hue. */
        'gov-sand': '#b49a6a',
        'gov-ok': '#4e9c7f',
        'gov-warn': '#c08a3e',
        'gov-crit': '#b4675c',
      },
      fontFamily: {
        'sans': ['Inter', 'Noto Sans Arabic', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
