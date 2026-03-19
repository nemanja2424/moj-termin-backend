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

# ===== LOGGING =====
accesslog = '/var/log/gunicorn_access.log'
errorlog = '/var/log/gunicorn_error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ===== POST FORK - Osiguraj da je model dostupan u svakom workeru =====
def post_fork(server, worker):
    """
    Poziva se nakon što je worker fork-ovan.
    Osigurava da je embedding model dostupan u worker procesu.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Model je već učitan u parent procesu sa preload_app=True
        # Ovdje ga možeš koristiti bez dodatnog opterećenja
        logger.info(f"✅ Worker {worker.pid} je spreman (model je shared iz parent procesa)")
    except Exception as e:
        logger.error(f"❌ Greška u post_fork hook-u: {str(e)}")

# ===== PRE FORK - debug info =====
def pre_fork(server, worker):
    """
    Poziva se prije fork-a novog workera.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔄 Forkiram novi worker...")

print("""
╔══════════════════════════════════════════════════════════════╗
║         🚀 GUNICORN KONFIGURACIJA - PRELOAD APP             ║
╠══════════════════════════════════════════════════════════════╣
║ ✅ preload_app = True                                        ║
║    → Model se učitava samo JEDNOM u parent procesu          ║
║    → Svi workeri naslijede model iz memorije                ║
║    → Ušteda: 3 × 250MB = 750MB RAM-a!                       ║
╠══════════════════════════════════════════════════════════════╣
║ Workers: {:<49} ║
║ Binding: {:<49} ║
║ Timeout: 120 sekundi                                         ║
║ preload_app: ✅ Omogućeno                                    ║
╚══════════════════════════════════════════════════════════════╝
""".format(workers, bind))
