/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './*.html',
    './pages/**/*.html',
    './assets/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        'sc-green':  '#0c6b55',
        'sc-green2': '#0a5b49',
        'sc-gold':   '#c69b5a',
        'sc-ink':    '#102c2d',
        'sc-muted':  '#667977',
        'sc-line':   '#dfe7e3',
        'sc-soft':   '#f6f9f7',
        'sc-soft2':  '#eef5f2',
        'sc-red':    '#cd5a52',
        'sc-amber':  '#c38c34',
      },
      fontFamily: {
        arabic: ['"IBM Plex Sans Arabic"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card:    '0 4px 24px rgba(12,107,85,0.07)',
        'card-lg': '0 15px 40px rgba(23,69,55,0.08)',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}

