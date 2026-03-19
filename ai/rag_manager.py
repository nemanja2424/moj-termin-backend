"""
RAG Manager - Retrieval Augmented Generation sistem za Moj Termin
Pronalazi relevantne dokumente iz baze i prosleđuje LLM-u kao kontekst
"""

import json
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from pgvector.sqlalchemy import Vector
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Globalni model - učitava se samo jednom pri pokretanju
_model = None
_model_lock = threading.Lock()

def get_model():
    """Vrati cache-irani model"""
    global _model
    if _model is None:
        # Koristi optimizovani multilingual paraphrase model - bolji za srpski
        _model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        logger.info("✅ Paraphrase multilingual model učitan (384 dimenzije - optimizovan za srpski)")
    return _model

def preload_model():
    """Force-loadaj model pri pokretanju app-a"""
    logger.info("🔄 Pre-učitavam embedding model pri pokretanju...")
    get_model()
    logger.info("✅ Model je spreman za upite")


class EmbeddingTypes:
    """
    Enum za tipove embedding-a (označava nivo pristupa - ko može vidjeti)
    """
    VLASNIK = 1    # Vlasnik - vidi sve podatke
    ZAPOSLEN = 2   # Zaposlenik - vidi samo svoju firmu i termine
    KLIJENT = 3    # Klijent - vidi samo firme i slobodne termine (bez detalja)


class RAGManager:
    """
    Manages RAG (Retrieval Augmented Generation) operations
    - Generiše embeddings
    - Pronalazi relevantne dokumente
    - Formatira kontekst za LLM
    """
    
    def __init__(self, db):
        """
        Inicijalizuj RAG sistem
        
        Args:
            db: SQLAlchemy database objekat
        """
        self.db = db
        # Koristi globalni cache-irani model
        self.model = get_model()
        logger.info("✅ RAG Manager inicijalizovan (koristi cache-irani model)")
    
    def generate_embedding(self, tekst):
        """
        Generiši embedding za tekst
        
        Args:
            tekst (str): Tekst za embedding
            
        Returns:
            list: Vektor od 384 dimenzije
        """
        embedding = self.model.encode(tekst)
        return embedding.tolist()
    
    def retrieve_documents(self, user_id, pitanje, vlasnik_id_for_klijent=None, k=6):
        """
        Pronađi relevantne dokumente iz embeddings tabele - NOVA LOGIKA
        
        Automatski detektuje tip korisnika iz baze:
        - Ako zaposlen_u = 0 → VLASNIK (tip_id = 1)
        - Ako zaposlen_u > 0 → ZAPOSLENIK (tip_id = 2)
        - Ako vlasnik_id_for_klijent → KLIJENT (tip_id = 3)
        
        Args:
            user_id (int): ID korisnika koji pita
            pitanje (str): Pitanje korisnika
            vlasnik_id_for_klijent (int): ID vlasnika (SAMO za klijenta)
            k (int): Broj rezultata (default 6)
            
        Returns:
            list: Lista relevantnih dokumenata
        """
        try:
            # 1. Generiši embedding za pitanje
            logger.info(f"🔍 Generisem embedding za pitanje: '{pitanje[:50]}...'")
            query_embedding = self.generate_embedding(pitanje)
            embedding_str = f'[{",".join(str(x) for x in query_embedding)}]'
            
            # 2. Odredi tip korisnika iz baze
            if vlasnik_id_for_klijent:
                # KLIJENT - korisnik koji zakazuje kod vlasnika
                tip_korisnika = 'klijent'
                user_id_for_query = vlasnik_id_for_klijent
                tip_id = EmbeddingTypes.KLIJENT
                logger.info(f"👤 TIP: KLIJENT - vlasnik_id={vlasnik_id_for_klijent}")
            else:
                # Proveri iz users tabele da li je vlasnik ili zaposlenik
                user_query = text("SELECT zaposlen_u FROM users WHERE id = :id")
                user_result = self.db.session.execute(user_query, {'id': int(user_id)}).fetchone()
                
                if not user_result:
                    logger.error(f"❌ Korisnik sa ID {user_id} nije pronađen!")
                    return []
                
                zaposlen_u = user_result[0]
                
                if zaposlen_u == 0:
                    # VLASNIK
                    tip_korisnika = 'vlasnik'
                    user_id_for_query = user_id
                    tip_id = EmbeddingTypes.VLASNIK
                    logger.info(f"👑 TIP: VLASNIK - user_id={user_id}")
                else:
                    # ZAPOSLENIK
                    tip_korisnika = 'zaposlen'
                    user_id_for_query = user_id
                    firma_id = zaposlen_u
                    tip_id = EmbeddingTypes.ZAPOSLEN
                    logger.info(f"👤 TIP: ZAPOSLENIK - user_id={user_id}, firma_id={firma_id}")
            
            # 3. SQL pretraga sa psycopg2 raw connection
            conn = self.db.engine.raw_connection()
            try:
                cursor = conn.cursor()
                
                if tip_korisnika == 'vlasnik':
                    # VLASNIK: Samo tip 1 (VLASNIK)
                    query_sql = """
                        SELECT e.id, e.tekst, e.tip_id, e.embedding <-> %s::vector as distance
                        FROM embeddings e
                        WHERE e.user_id = %s
                          AND e.tip_id = %s
                        ORDER BY e.embedding <-> %s::vector
                        LIMIT %s
                    """
                    cursor.execute(query_sql, (
                        embedding_str,
                        int(user_id_for_query),
                        int(EmbeddingTypes.VLASNIK),
                        embedding_str,
                        int(k)
                    ))
                    logger.info(f"   SQL: Pretraživam dokumenta za VLASNIKA")
                    
                elif tip_korisnika == 'zaposlen':
                    # ZAPOSLENIK: Samo tip 2 (ZAPOSLEN) sa filtriranjem po firma_id
                    query_sql = """
                        SELECT e.id, e.tekst, e.tip_id, e.embedding <-> %s::vector as distance
                        FROM embeddings e
                        WHERE e.user_id = %s
                          AND e.tip_id = %s
                          AND e.firma_id = %s
                        ORDER BY e.embedding <-> %s::vector
                        LIMIT %s
                    """
                    cursor.execute(query_sql, (
                        embedding_str,
                        int(user_id_for_query),
                        int(EmbeddingTypes.ZAPOSLEN),
                        int(firma_id),
                        embedding_str,
                        int(k)
                    ))
                    logger.info(f"   SQL: Pretraživam dokumente za ZAPOSLENIKA sa firma_id={firma_id}")
                    
                elif tip_korisnika == 'klijent':
                    # KLIJENT: Samo tip 3 (KLIJENT)
                    query_sql = """
                        SELECT e.id, e.tekst, e.tip_id, e.embedding <-> %s::vector as distance
                        FROM embeddings e
                        WHERE e.user_id = %s
                          AND e.tip_id = %s
                        ORDER BY e.embedding <-> %s::vector
                        LIMIT %s
                    """
                    cursor.execute(query_sql, (
                        embedding_str,
                        int(user_id_for_query),
                        int(EmbeddingTypes.KLIJENT),
                        embedding_str,
                        int(k)
                    ))
                    logger.info(f"   SQL: Pretraživam dokumente za KLIJENTA")
                
                results = cursor.fetchall()
                cursor.close()
            finally:
                conn.close()
            
            logger.info(f"✅ Pronađeno {len(results)} relevantnih dokumenata")
            
            # 4. Ekstraktuj rezultate
            documents = []
            for row in results:
                doc_id, tekst, tip_id, distance = row
                documents.append({
                    'id': doc_id,
                    'tekst': tekst,
                    'tip_id': tip_id,
                    'distance': float(distance)
                })
                # Ispis sa tekstom
                logger.info(f"   📄 Doc {doc_id} (tip {tip_id}): relevance={distance:.3f}")
                logger.info(f"      >>> {tekst}")
            
            return documents
            
        except Exception as e:
            logger.error(f"❌ Greška pri retrieval-u: {str(e)}")
            self.db.session.rollback()
            return []
    
    def format_context(self, documents):
        """
        Formatiraj dokumente u tekstualni kontekst za LLM
        
        Args:
            documents (list): Lista dokumenata sa retrieve_documents()
            
        Returns:
            str: Formatiran kontekst za LLM
        """
        if not documents:
            return "Nema dostupnih podataka."
        
        kontekst = "=== RELEVANTNI PODACI ===\n\n"
        
        for i, doc in enumerate(documents, 1):
            tekst = doc['tekst']
            tip_id = doc['tip_id']
            
            # Detektuj vrstu dokumenta od teksta
            if "Zakazivanje" in tekst:
                label = "📅 ZAKAZIVANJE/TERMIN"
            elif "Vlasnik:" in tekst:
                label = "👑 VLASNIK"
            elif "Firma:" in tekst:
                label = "🏢 FIRMA"
            elif "Zaposlenik:" in tekst:
                label = "👤 ZAPOSLENIK"
            elif "Preduzeće:" in tekst:
                label = "🏢 PREDUZEĆE"
            else:
                label = f"📋 TIP {tip_id}"
            
            kontekst += f"{i}. {label}\n"
            kontekst += f"{tekst}\n"
            kontekst += f"(Relevantnost: {doc['distance']:.2f})\n\n"
        
        kontekst += "=== KRAJ RELEVANTNIH PODATAKA ===\n"
        
        logger.info(f"📝 Kontekst formatiran: {len(kontekst)} karaktera")
        return kontekst
    
    # ============================================================
    # TIP 1 - VLASNIK (tip_id=1)
    # ============================================================
    
    def format_vlasnik_tip1_for_embedding(self, user_data):
        """
        Formatiraj podatke VLASNIKA za embedding (TIP 1 - Red 1)
        CHUNK OPTIMIZATION: Kompaktan, fokusiran tekst
        
        Args:
            user_data (dict): {username, email, brTel, paket, ime_preduzeca}
            
        Returns:
            str: Formatiran tekst (kompaktan)
        """
        username = user_data.get('username', 'N/A')
        ime_preduzeca = user_data.get('ime_preduzeca', 'N/A')
        email = user_data.get('email', 'N/A')
        brTel = user_data.get('brTel', 'N/A')
        paket = user_data.get('paket', 'N/A')
        
        # Kompaktan format - fokusirano na ključne informacije
        tekst = f"Vlasnik: {username} | Preduzeće: {ime_preduzeca} | Email: {email} | Telefon: {brTel} | Paket: {paket}"
        return tekst.strip()
    
    # ============================================================
    # ZAJEDNIČKE FUNKCIJE - koriste se za sve tipove
    # ============================================================
    
    def format_firma_for_embedding(self, firma_data):
        """
        Formatiraj podatke FIRME za embedding (koristi se za TIP 1, 2, 3)
        CHUNK OPTIMIZATION: Kompaktan, fokusiran tekst
        
        Args:
            firma_data (dict): {ime, adresa, overlapLimit}
            
        Returns:
            str: Formatiran tekst (kompaktan)
        """
        ime = firma_data.get('ime', 'N/A')
        adresa = firma_data.get('adresa', 'N/A')
        overlapLimit = firma_data.get('overlapLimit', 'N/A')
        
        # Kompaktan format - samo ključne informacije
        tekst = f"Firma: {ime} | Adresa: {adresa} | Kapacitet: {overlapLimit}"
        return tekst.strip()
    
    def format_termin_tip1_for_embedding(self, termin_data, firma_ime=None):
        """
        Formatiraj podatke TERMINA za embedding - VLASNIK/ZAPOSLEN
        CHUNK OPTIMIZATION: Kompaktan, fokusiran tekst
        
        Args:
            termin_data (dict): {ime, usluga, datum_rezervacije, vreme_rezervacije, potvrdio}
            firma_ime (str): Naziv firme (iz preduzeca tabele)
            
        Returns:
            str: Formatiran tekst (kompaktan)
        """
        usluga_text = termin_data.get('usluga', 'N/A')
        if isinstance(usluga_text, str):
            try:
                usluga_dict = json.loads(usluga_text)
                usluga_text = usluga_dict.get('naziv', 'N/A')
            except:
                pass
        
        status = "Potvrđen" if termin_data.get('potvrdio') else "Čeka potvrdu"
        klijent = termin_data.get('ime', 'N/A')
        datum = termin_data.get('datum_rezervacije', 'N/A')
        vreme = termin_data.get('vreme_rezervacije', 'N/A')
        
        # Kompaktan format - usluga, firma, datum, vrijeme, klijent
        tekst = f"Termin: {usluga_text} | Firma: {firma_ime or 'N/A'} | {datum} {vreme} | Klijent: {klijent} | Status: {status}"
        return tekst.strip()
    
    def format_termin_tip3_for_embedding(self, termin_data, firma_ime=None):
        """
        Formatiraj podatke TERMINA za embedding - KLIJENT
        CHUNK OPTIMIZATION: Kompaktan, fokusiran tekst
        Koristi se za TIP 3 (Red x-y) - samo USLUGA, DATUM, VREME, IME_FIRME
        
        Args:
            termin_data (dict): {usluga, datum_rezervacije, vreme_rezervacije}
            firma_ime (str): Naziv firme (iz preduzeca tabele)
            
        Returns:
            str: Formatiran tekst (kompaktan)
        """
        usluga_text = termin_data.get('usluga', 'N/A')
        if isinstance(usluga_text, str):
            try:
                usluga_dict = json.loads(usluga_text)
                usluga_text = usluga_dict.get('naziv', 'N/A')
            except:
                pass
        
        datum = termin_data.get('datum_rezervacije', 'N/A')
        vreme = termin_data.get('vreme_rezervacije', 'N/A')
        
        # Kompaktan format
        tekst = f"Termin: {usluga_text} - Firma: {firma_ime or 'N/A'} | {datum} {vreme}"
        return tekst.strip()
    
    # ============================================================
    # TIP 2 - ZAPOSLEN (tip_id=2)
    # ============================================================
    
    def format_zaposlen_tip2_for_embedding(self, user_data, firma_ime=None):
        """
        Formatiraj podatke ZAPOSLENIKA za embedding (TIP 2 - Red 1)
        CHUNK OPTIMIZATION: Kompaktan, fokusiran tekst
        
        Args:
            user_data (dict): {username, email, brTel}
            firma_ime (str): Naziv firme gdje radi
            
        Returns:
            str: Formatiran tekst (kompaktan)
        """
        username = user_data.get('username', 'N/A')
        email = user_data.get('email', 'N/A')
        firma = firma_ime or 'N/A'
        
        # Kompaktan format
        tekst = f"Zaposlenik: {username} | Firma: {firma} | Email: {email}"
        return tekst.strip()
    
    # ============================================================
    # TIP 3 - KLIJENT (tip_id=3)
    # ============================================================
    
    def format_vlasnik_info_tip3_for_embedding(self, user_data):
        """
        Formatiraj datos VLASNIKA za embedding - KLIJENT (TIP 3 - Red 1)
        CHUNK OPTIMIZATION: Kompaktan, fokusiran tekst
        Samo: ime_preduzeca, opis
        
        Args:
            user_data (dict): {ime_preduzeca, opis}
            
        Returns:
            str: Formatiran tekst (kompaktan)
        """
        ime = user_data.get('ime_preduzeca', 'N/A')
        opis = user_data.get('opis', 'N/A')
        # Kompaktan format
        tekst = f"Preduzeće: {ime} | {opis}"
        return tekst.strip()

