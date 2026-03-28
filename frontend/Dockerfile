# Use the lightweight Nginx Alpine image
FROM nginx:alpine

# Create the directory expected by your custom nginx.conf
RUN mkdir -p /var/www/rogue-merchant

# Copy the static HTML file to the serving directory
COPY index.html /var/www/rogue-merchant/

# Replace the default Nginx config with your custom proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 for web traffic
EXPOSE 80
