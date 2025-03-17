FROM nginx:latest

EXPOSE 80/tcp

COPY checks /usr/share/nginx/html/checks
COPY configs/nginx.conf /etc/nginx/conf.d/default.conf
