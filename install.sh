#!/usr/bin/env bash

curl -sL https://deb.nodesource.com/setup_8.x -o nodesource_setup.sh
sudo bash nodesource_setup.sh
sudo apt install nodejs
sudo npm install -g purgecss postcss-cli autoprefixer cssnano
cat static/css/* > static/css-min/sum.css && cp static/css-min/sum{,-lean}.css && purgecss --css static/css-min/sum-lean.css --content templates/**/* templates/*.html -o static/css-min/ && postcss static/css-min/sum-lean.css -u autoprefixer -u cssnano --no-map --verbose -o static/css-min/sum-min.css