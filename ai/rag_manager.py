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
        # Koristi model sa 512 dimenzija za multilingvalne embeddings
        _model = SentenceTransformer('distiluse-base-multilingual-cased-v2')
        logger.info("✅ Multilingual model učitan (512 dimenzije)")
    return _model

def preload_model():
    """Force-loadaj model pri pokretanju app-a"""
    logger.info("🔄 Pre-učitavam embedding model pri pokretanju...")
    get_model()
    logger.info("✅ Model je spreman za upite")


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
    
    def retrieve_documents(self, user_id, pitanje, tip_korisnika='vlasnik', k=6):
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
            
            # 2. Odredì koje tipove može vidjeti korisnik
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
            
            # 3. SQL pretraga sa surowym psycopg2 connection
            # SQLAlchemy text() escapeuje placeholders što se ne slaže sa pgvector operatorima
            embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
            
            # Koristi raw connection sa psycopg2
            conn = self.db.engine.raw_connection()
            try:
                cursor = conn.cursor()
                
                query_sql = """
                    SELECT id, tekst, tip_id, embedding <-> %s::vector as distance
                    FROM embeddings
                    WHERE user_id = %s
                      AND tip_id = ANY(%s)
                    ORDER BY embedding <-> %s::vector
                    LIMIT %s
                """
                
                cursor.execute(query_sql, (
                    embedding_str,
                    int(user_id),
                    allowed_types,
                    embedding_str,
                    int(k)
                ))
                
                results = cursor.fetchall()
                cursor.close()
            finally:
                conn.close()
            
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
            self.db.session.rollback()  # Reset transaction nakon greške
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
            if isinstance(cenovnik, dict):
                for usluga, cena in cenovnik.items():
                    cenovnik_str += f"  {usluga}: {cena} din\n"
            elif isinstance(cenovnik, list):
                for item in cenovnik:
                    if isinstance(item, dict):
                        usluga = item.get('usluga', 'N/A')
                        cena = item.get('cena', 'N/A')
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

    def expand_query(self, pitanje):
        """
        Query Expansion - Generiši sinonimne i povezane varijante pitanja
        Koristi se za bolju pronalaženje semantički sličnih dokumenata
        
        Args:
            pitanje (str): Originalno pitanje korisnika
            
        Returns:
            list: Lista od N varijanti pitanja
        """
        # Sinonimni izrazi u srpskom jeziku
        sinonimi = {
            'koliko': ['broj', 'ukupno', 'suma', 'koliko ima'],
            'termin': ['zakazivanje', 'appointment', 'rezervacija', 'sat'],
            'zaposlenik': ['radnik', 'employee', 'osoblje', 'timski član'],
            'firma': ['preduzeće', 'company', 'organizacija', 'poslodavac'],
            'datum': ['dan', 'vreme', 'vremenski period'],
            'status': ['stanje', 'aktualnost', 'potvrda']
        }
        
        expanded = [pitanje]  # Originaleno prvo
        
        # Generiši nekoliko varijanti kroz zamjenu sinonima
        for key, values in sinonimi.items():
            if key.lower() in pitanje.lower():
                for syn in values[:2]:  # Limit od 2 sinonima po ključi
                    variant = pitanje.lower().replace(key, syn)
                    if variant not in expanded:
                        expanded.append(variant)
        
        logger.info(f"🔄 Query expansion: {len(expanded)} varijanti")
        return expanded[:5]  # Limit od 5 maksimalno

    def rerank_documents(self, documents, pitanje, boost_types=None):
        """
        Reranking - Resortiraj dokumente sa hybrid scoring
        Kombinuje semantic similarity + metadata relevance
        
        Args:
            documents (list): Pronađeni dokumenti
            pitanje (str): Originalno pitanje
            boost_types (list): Tipovi za boost scoring
            
        Returns:
            list: Sortiran lista dokumenata po relevantnosti
        """
        if not documents:
            return documents
        
        # Default boost za TERMIN i VLASNIK (važnijtipo)
        if boost_types is None:
            boost_types = [EmbeddingTypes.TERMIN, EmbeddingTypes.VLASNIK]
        
        # Recalculate scores sa boost
        for doc in documents:
            # Bazični score (inverzna distanca)
            base_score = 1.0 / (1.0 + doc['distance'])
            
            # Boost ako je tip u boost_types
            type_boost = 1.3 if doc.get('tip_id') in boost_types else 1.0
            
            # Final score
            doc['score'] = base_score * type_boost
        
        # Sortiraj po score descending
        documents.sort(key=lambda d: d.get('score', 0), reverse=True)
        
        logger.info(f"📊 Reranking dovršen: top doc score={documents[0].get('score', 0):.3f}")
        return documents

    def aggregate_analytics(self, documents, user_id):
        """
        Analytics Aggregation - Za vlasnika, generiši statistiku iz dokumenata
        
        Args:
            documents (list): Pronađeni dokumenti (TERMIN tipovi)
            user_id (int): User ID vlasnika
            
        Returns:
            dict: Statistika (broj termina, potvrdeni, otkazani, itd)
        """
        termin_docs = [d for d in documents if d.get('tip_id') == EmbeddingTypes.TERMIN]
        
        if not termin_docs:
            return {}
        
        stats = {
            'total_termins': len(termin_docs),
            'confirmed': 0,
            'cancelled': 0,
            'pending': 0,
            'relevance_avg': sum(d.get('score', 0) for d in termin_docs) / len(termin_docs)
        }
        
        logger.info(f"📈 Analitika: {stats['total_termins']} termina, avg relevance={stats['relevance_avg']:.2f}")
        return stats

    def retrieve_documents_advanced(self, user_id, pitanje, role='vlasnik', k=7):
        """
        Advanced Retrieval - Role-based pronalaženje sa query expansion i reranking
        
        Args:
            user_id (int): ID korisnika
            pitanje (str): Pitanje korisnika
            role (str): 'vlasnik', 'zaposlen', 'gost'
            k (int): Broj rezultata
            
        Returns:
            dict: {documents, analytics, expanded_queries, metadata}
        """
        logger.info(f"🚀 Advanced RAG retrieval - Role: {role}, User: {user_id}")
        
        # 1. Query Expansion
        expanded_queries = self.expand_query(pitanje)
        
        # 2. Retrieval sa role-specific persmisijama
        all_documents = []
        
        for query in expanded_queries:
            try:
                # Generiši embedding za expanded query
                query_embedding = self.generate_embedding(query)
                embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
                
                # Odredi dozvoljene tipove po ulozi
                if role == 'vlasnik':
                    allowed_types = [EmbeddingTypes.USER, EmbeddingTypes.FIRMA, 
                                   EmbeddingTypes.TERMIN, EmbeddingTypes.VLASNIK]
                    # Vlasnik vidi sve svoje podatke
                    where_clause = "user_id = %s"
                    
                elif role == 'zaposlen':
                    allowed_types = [EmbeddingTypes.FIRMA, EmbeddingTypes.TERMIN, EmbeddingTypes.USER]
                    # Zaposlenik vidi samo svoje firme termine
                    where_clause = """
                        (user_id = %s OR 
                         (firma_id = (SELECT zaposlen_u FROM users WHERE id = %s) AND tip_id = ANY(%s)))
                    """
                    
                else:  # gost/zakazivac
                    allowed_types = [EmbeddingTypes.FIRMA, EmbeddingTypes.TERMIN]
                    where_clause = "tip_id = ANY(%s)"
                
                # Execute raw SQL sa pgvector
                conn = self.db.engine.raw_connection()
                try:
                    cursor = conn.cursor()
                    
                    query_sql = f"""
                        SELECT id, tekst, tip_id, embedding <-> %s::vector as distance, firma_id
                        FROM embeddings
                        WHERE {where_clause}
                          AND tip_id = ANY(%s)
                        ORDER BY embedding <-> %s::vector
                        LIMIT %s
                    """
                    
                    if role == 'zaposlen':
                        cursor.execute(query_sql, (embedding_str, user_id, user_id, 
                                                 allowed_types, embedding_str, k*2))
                    elif role == 'gost':
                        cursor.execute(query_sql, (embedding_str, allowed_types, 
                                                 embedding_str, k))
                    else:  # vlasnik
                        cursor.execute(query_sql, (embedding_str, user_id, 
                                                 allowed_types, embedding_str, k*2))
                    
                    results = cursor.fetchall()
                    cursor.close()
                    
                    for row in results:
                        doc_id, tekst, tip_id, distance, firma_id = row
                        doc = {
                            'id': doc_id,
                            'tekst': tekst,
                            'tip_id': tip_id,
                            'distance': float(distance),
                            'firma_id': firma_id,
                            'query_source': query  # Track which query pronašao ovaj doc
                        }
                        if doc not in all_documents:  # Izbegni duplikate
                            all_documents.append(doc)
                
                finally:
                    conn.close()
                    
            except Exception as e:
                logger.error(f"❌ Greška pri expanded query retrieval-u: {str(e)}")
        
        # 3. Reranking
        reranked = self.rerank_documents(all_documents, pitanje)
        
        # 4. Výber top K
        final_docs = reranked[:k]
        
        # 5. Analytics (ako je vlasnik)
        analytics = {}
        if role == 'vlasnik':
            analytics = self.aggregate_analytics(final_docs, user_id)
        
        logger.info(f"✅ Advanced retrieval završen: {len(final_docs)} docs, {len(set(q for q in expanded_queries))} queries")
        
        return {
            'documents': final_docs,
            'analytics': analytics,
            'expanded_queries': expanded_queries,
            'metadata': {
                'role': role,
                'total_candidates': len(all_documents),
                'final_count': len(final_docs),
                'k_requested': k
            }
        }
