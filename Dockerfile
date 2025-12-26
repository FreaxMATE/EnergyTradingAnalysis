# Use Nginx to serve static files
FROM nginx:alpine

# Copy static HTML files from docs directory to Nginx html directory
COPY docs /usr/share/nginx/html

# Expose port 80
EXPOSE 80