FROM nginx:alpine
RUN echo '<h1>Hello from CI/CD</h1><p>Built with no source code.</p>' \
    > /usr/share/nginx/html/index.html
EXPOSE 80
