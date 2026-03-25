# Gunicorn configuration
workers = 3
bind = '127.0.0.1:5000'
worker_class = 'sync'
timeout = 120
graceful_timeout = 30
keepalive = 5
preload_app = True