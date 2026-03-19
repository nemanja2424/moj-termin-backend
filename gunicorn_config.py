"""
Gunicorn konfiguracija za Moj Termin Backend
Učitava embedding model samo jednom sa preload_app = True
"""

import os
import logging

# ===== OSNOVNE KONFIGURACIJE =====
# Za test verziju, koristi 2-3 workera ovisno od dostupnog RAM-a
# Preporuka: 2 workera za osjetljive sisteme, 3 za veće
workers = int(os.getenv('GUNICORN_WORKERS', 3))
worker_class = 'sync'
worker_connections = 1000
backlog = 2048

# ===== PRELOAD APP - KLJUČNO! =====
# Sa preload_app = True, app se učitava PRIJE fork-a workera
# Ovo znači da se embedding model učita samo JEDNOM u parent procesu
# Svi workeri naslijede model iz memorije - UŠTEDA 750MB RAM-a!
preload_app = True

# ===== BINDING =====
# Za VPS: 0.0.0.0:5000 ili 0.0.0.0:5001 (production)
# Za lokalnu upotrebu: 127.0.0.1:5001 (systemd service)
bind = os.getenv('GUNICORN_BIND', '127.0.0.1:5001')

# ===== TIMEOUTS =====
timeout = 120
graceful_timeout = 30
keepalive = 5
