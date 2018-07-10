module.exports = {
  plugins: [
    require('cssnano')({
        preset: ['advanced', {
            autoprefixer: {
                exclude: true
            }
        }]
    })
  ]
}