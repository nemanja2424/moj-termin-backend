"""
RAG Manager - Retrieval Augmented Generation sistem za Moj Termin
Pronalazi relevantne dokumente iz baze i prosleđuje LLM-u kao kontekst
"""

import json
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmbeddingTypes:
    """Enum za tipove embedding-a"""
    USER = 1       # User info (username, email, itd)
    FIRMA = 2      # Firma - kombinovano (ime, adresa, radno_vreme, cenovnik)
    TERMIN = 3     # Zakazani termini
    VLASNIK = 4    # Vlasnik info (limits, paket, itd)


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
        # Model za generisanje embeddings-a
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        logger.info("✅ RAG Manager inicijalizovan")
    
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
    
    def retrieve_documents(self, user_id, pitanje, tip_korisnika='vlasnik', k=3):
        """
        Pronađi relevantne dokumente iz embeddings tabele
        
        Args:
            user_id (int): ID korisnika koji pita
            pitanje (str): Pitanje korisnika
            tip_korisnika (str): 'vlasnik' ili 'zakazivac'
            k (int): Broj rezultata (default 3)
            
        Returns:
            list: Lista relevantnih dokumenata (samo tekst)
        """
        try:
            # 1. Generiši embedding za pitanje
            logger.info(f"🔍 Generisem embedding za pitanje: '{pitanje[:50]}...'")
            query_embedding = self.generate_embedding(pitanje)
            
            # 2. Odredì koje tipove may vidjeti korisnik
            if tip_korisnika == 'vlasnik':
                # Vlasnik vidi SVE tipove
                allowed_types = [
                    EmbeddingTypes.USER,
                    EmbeddingTypes.FIRMA,
                    EmbeddingTypes.TERMIN,
                    EmbeddingTypes.VLASNIK
                ]
            else:  # zakazivac
                # Zakazivač vidi samo termin i firma info
                allowed_types = [
                    EmbeddingTypes.FIRMA,
                    EmbeddingTypes.TERMIN
                ]
            
            # 3. SQL pretraga sa embeddings vektorom
            query = text("""
                SELECT id, tekst, tip_id, embedding <-> :embedding as distance
                FROM embeddings
                WHERE user_id = :user_id
                  AND tip_id = ANY(:types)
                ORDER BY embedding <-> :embedding
                LIMIT :k
            """)
            
            results = self.db.session.execute(query, {
                'user_id': user_id,
                'embedding': str(query_embedding),
                'types': allowed_types,
                'k': k
            }).fetchall()
            
            logger.info(f"✅ Pronađeno {len(results)} relevantnih dokumenata")
            
            # 4. Ekstraktuj samo tekstove (bez embeddings vektora)
            documents = []
            for row in results:
                doc_id, tekst, tip_id, distance = row
                documents.append({
                    'id': doc_id,
                    'tekst': tekst,
                    'tip_id': tip_id,
                    'distance': float(distance)
                })
                logger.info(f"   📄 Doc {doc_id} (tip {tip_id}): relevance={distance:.3f}")
            
            return documents
            
        except Exception as e:
            logger.error(f"❌ Greška pri retrieval-u: {str(e)}")
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
        
        # Mapiranje tipova na imena
        type_names = {
            EmbeddingTypes.USER: "👤 KORISNIK",
            EmbeddingTypes.FIRMA: "🏢 FIRMA",
            EmbeddingTypes.TERMIN: "📅 TERMIN",
            EmbeddingTypes.VLASNIK: "👑 VLASNIK"
        }
        
        kontekst = "=== RELEVANTNI PODACI ===\n\n"
        
        for i, doc in enumerate(documents, 1):
            tip_name = type_names.get(doc['tip_id'], "OSTALO")
            kontekst += f"{i}. {tip_name}\n"
            kontekst += f"{doc['tekst']}\n"
            kontekst += f"(Relevantnost: {doc['distance']:.2f})\n\n"
        
        kontekst += "=== KRAJ RELEVANTNIH PODATAKA ===\n"
        
        logger.info(f"📝 Kontekst formatiran: {len(kontekst)} karaktera")
        return kontekst
    
    def format_user_data_for_embedding(self, user_data):
        """
        Formatiraj korisničke podatke u tekst za embedding (tip: USER)
        
        Args:
            user_data (dict): Podaci korisnika iz DB
            
        Returns:
            str: Formatiran tekst
        """
        tekst = f"""
Korisnik: {user_data.get('username', 'N/A')}
Email: {user_data.get('email', 'N/A')}
Telefon: {user_data.get('brTel', 'N/A')}
Zaposlenik u: {user_data.get('zaposlen_u', 'N/A')}
"""
        return tekst.strip()
    
    def format_firma_data_for_embedding(self, firma_data):
        """
        Formatiraj firmu + vreme + cenovnik u tekst za embedding (tip: FIRMA)
        
        Args:
            firma_data (dict): Podaci firme iz DB
            
        Returns:
            str: Formatiran tekst
        """
        radno_vreme = firma_data.get('radno_vreme', {})
        if isinstance(radno_vreme, str):
            radno_vreme = json.loads(radno_vreme)
        
        cenovnik = firma_data.get('cenovnik', {})
        if isinstance(cenovnik, str):
            cenovnik = json.loads(cenovnik)
        
        # Format radno vreme
        vreme_str = ""
        if radno_vreme:
            vreme_str = "\nRadno vreme:\n"
            for dan, vreme in radno_vreme.items():
                vreme_str += f"  {dan}: {vreme}\n"
        
        # Format cenovnik
        cenovnik_str = ""
        if cenovnik:
            cenovnik_str = "\nCenovnik:\n"
            for usluga, cena in cenovnik.items():
                cenovnik_str += f"  {usluga}: {cena} din\n"
        
        tekst = f"""
Firma: {firma_data.get('ime', 'N/A')}
Adresa: {firma_data.get('adresa', 'N/A')}
Kapacitet (overlap limit): {firma_data.get('overlapLimit', 'N/A')}{vreme_str}{cenovnik_str}
"""
        return tekst.strip()
    
    def format_termin_data_for_embedding(self, termin_data):
        """
        Formatiraj zakazivanje u tekst za embedding (tip: TERMIN)
        
        Args:
            termin_data (dict): Podaci termina iz DB
            
        Returns:
            str: Formatiran tekst
        """
        status = "Potvrđen" if termin_data.get('potvrdio') else "Čeka potvrdu"
        otkazano = "DA - OTKAZANO" if termin_data.get('otkazano') else "NE"
        
        usluga = termin_data.get('usluga', {})
        if isinstance(usluga, str):
            usluga = json.loads(usluga)
        
        tekst = f"""
Zakazivanje:
Datum: {termin_data.get('datum_rezervacije', 'N/A')}
Vreme: {termin_data.get('vreme_rezervacije', 'N/A')}
Klijent: {termin_data.get('ime', 'N/A')}
Email: {termin_data.get('email', 'N/A')}
Telefon: {termin_data.get('telefon', 'N/A')}
Usluga: {json.dumps(usluga, ensure_ascii=False)}
Opis: {termin_data.get('opis', 'N/A')}
Status: {status}
Otkazano: {otkazano}
"""
        return tekst.strip()
    
    def format_vlasnik_data_for_embedding(self, vlasnik_data):
        """
        Formatiraj vlasnika u tekst za embedding (tip: VLASNIK)
        
        Args:
            vlasnik_data (dict): Podaci vlasnika iz DB
            
        Returns:
            str: Formatiran tekst
        """
        paket_limits = vlasnik_data.get('paket_limits', {})
        if isinstance(paket_limits, str):
            paket_limits = json.loads(paket_limits)
        
        limits_str = ""
        if paket_limits:
            limits_str = "\nLimitacije paketa:\n"
            for key, value in paket_limits.items():
                limits_str += f"  {key}: {value}\n"
        
        tekst = f"""
Vlasnik: {vlasnik_data.get('username', 'N/A')}
Paket: {vlasnik_data.get('paket', 'N/A')}
Istek pretplate: {vlasnik_data.get('istek_pretplate', 'N/A')}
Firme: {vlasnik_data.get('ime_preduzeca', 'N/A')}
Opis: {vlasnik_data.get('opis', 'N/A')}{limits_str}
"""
        return tekst.strip()
