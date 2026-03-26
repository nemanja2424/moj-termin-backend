"""
Async Email Service - Koristi threading za slanje mejlova u pozadini
Omogućava bržem response na klijentskoj strani dok se mejlovi prate u pozadini
"""

import threading
from mailManager import send_confirmation_email, send_email_to_workers
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_confirmation_email_async(to_email, poruka, subject, html_poruka=None):
    """
    Šalje mejl asinkreno u posebnoj niti
    Odmah vraća True bez čekanja da mejl bude poslat
    
    Args:
        to_email: Email adresa primaoca
        poruka: Tekst poruke (plain text)
        subject: Naslov mejla
        html_poruka: HTML verzija poruke (opciono)
    
    Returns:
        bool: Uvek True jer se mejl šalje u pozadini
    """
    def send_email_in_background():
        try:
            result = send_confirmation_email(to_email, poruka, subject, html_poruka)
            if result:
                logger.info(f"✅ [ASYNC] Email uspešno poslat na: {to_email}")
            else:
                logger.error(f"❌ [ASYNC] Neuspešno slanje emaila na: {to_email}")
        except Exception as e:
            logger.error(f"❌ [ASYNC] Greška pri slanju emaila: {str(e)}")
    
    # Kreiraj nit i pousti je u pozadini (daemon=True znači da neće blokirati shutdown)
    thread = threading.Thread(target=send_email_in_background, daemon=True)
    thread.start()
    
    return True


def send_email_to_workers_async(vlasnikId, naslov, token, lokacija, preduzece, datum_i_vreme, zakazivac, stariPodaci=None):
    """
    Šalje mejlove zaposlenima asinkreno u posebnoj niti
    Odmah vraća True bez čekanja da mejlovi budu poslati
    
    Args:
        vlasnikId: ID vlasnika
        naslov: Naslov mejla
        token: Token zakazivanja
        lokacija: ID lokacije
        preduzece: Naziv preduzeća
        datum_i_vreme: Formatirani datum i vreme
        zakazivac: Ime/info o zakaživaču
        stariPodaci: Stari podaci za izmenu (opciono)
    
    Returns:
        bool: Uvek True jer se mejl šalje u pozadini
    """
    def send_emails_in_background():
        try:
            result = send_email_to_workers(vlasnikId, naslov, token, lokacija, preduzece, datum_i_vreme, zakazivac, stariPodaci)
            if result:
                logger.info(f"✅ [ASYNC] Mejlovi zaposlenima uspešno poslati za termin: {token}")
            else:
                logger.error(f"❌ [ASYNC] Neuspešno slanje mejlova zaposlenima za termin: {token}")
        except Exception as e:
            logger.error(f"❌ [ASYNC] Greška pri slanju mejlova zaposlenima: {str(e)}")
    
    # Kreiraj nit i pousti je u pozadini
    thread = threading.Thread(target=send_emails_in_background, daemon=True)
    thread.start()
    
    return True
