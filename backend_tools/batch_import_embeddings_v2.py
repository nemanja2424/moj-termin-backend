"""
Batch Import Embeddings V2 - NOVA LOGIKA
Učitava podatke u embeddings tabelu sa novom tipologijom:
- Tip 1: VLASNIK (sve njihove podatke)
- Tip 2: ZAPOSLEN (samo svoju firmu i termine)  
- Tip 3: KLIJENT (samo firme i terme - bez detalja)

Pokretanje:
  Windows: python backend_tools/batch_import_embeddings_v2.py
  VPS: python3 backend_tools/batch_import_embeddings_v2.py
"""

import sys
import os
import json
from datetime import datetime

# Dodaj parent direktorijum u path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from ai.rag_manager import RAGManager, EmbeddingTypes
from sqlalchemy import text

from threading import Semaphore
MAX_EMBEDDINGS = 10
embedding_limit = Semaphore(MAX_EMBEDDINGS)


def log_progress(message, level="INFO"):
    """Logaj napredak"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")


def get_rag_manager():
    """Get RAG manager instance"""
    return RAGManager(db)


def batch_import_vlasnici_tip1(limit=None):
    """
    ========== TIP 1 - VLASNIK ==========
    Red 1: User info vlasnika
    Red 2-N: Firma info za svaku firmu vlasnika  
    Red N+1-M: Termin info za sve termine u svim firmama vlasnika
    
    Args:
        limit (int): Limitiraj broj vlasnika (za test)
    """
    log_progress("🔄 Počinjem import TIP 1 - VLASNIK", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        # Pronađi sve vlasniče (users sa zaposlen_u = 0)
        query = text("""
            SELECT id, username, email, brTel, paket, istek_pretplate, 
                   ime_preduzeca, opis, paket_limits
            FROM users
            WHERE zaposlen_u = 0
            ORDER BY id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        vlasnici = db.session.execute(query).fetchall()
        log_progress(f"📊 Pronađeno {len(vlasnici)} vlasnika za TIP 1 import")
        
        # ===== RED 1: User info vlasnika =====
        for vlasnik_row in vlasnici:
            vlasnik_id, username, email, brTel, paket, istek_pretplate, ime_preduzeca, opis, paket_limits = vlasnik_row
            
            user_data = {
                'username': username,
                'email': email,
                'brTel': brTel,
                'paket': paket,
                'istek_pretplate': istek_pretplate,
                'ime_preduzeca': ime_preduzeca,
                'opis': opis,
                'paket_limits': paket_limits
            }
            
            tekst = rag.format_vlasnik_tip1_for_embedding(user_data)
            
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, termin_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :termin_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': vlasnik_id,
                'firma_id': None,
                'termin_id': None,
                'tip_id': EmbeddingTypes.VLASNIK,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            
            # ===== RED 2-N: Firma info za sve firme vlasnika =====
            firme_query = text("""
                SELECT id, ime, adresa, radno_vreme, cenovnik, overlapLimit
                FROM preduzeca
                WHERE vlasnik = :vlasnik_id
            """)
            firme = db.session.execute(firme_query, {'vlasnik_id': vlasnik_id}).fetchall()
            
            for firma_row in firme:
                firma_id, ime, adresa, radno_vreme, cenovnik, overlapLimit = firma_row
                
                firma_data = {
                    'ime': ime,
                    'adresa': adresa,
                    'radno_vreme': radno_vreme,
                    'cenovnik': cenovnik,
                    'overlapLimit': overlapLimit
                }
                
                tekst = rag.format_firma_for_embedding(firma_data)
                
                with embedding_limit:
                    embedding = rag.generate_embedding(tekst)
                
                db.session.execute(insert_query, {
                    'user_id': vlasnik_id,
                    'firma_id': firma_id,
                    'termin_id': None,
                    'tip_id': EmbeddingTypes.VLASNIK,
                    'tekst': tekst,
                    'embedding': str(embedding)
                })
                
                count += 1
                
                # ===== RED N+1-M: Termin info za sve termine u ovoj firmi =====
                termini_query = text("""
                    SELECT z.id, z.created_at, z.ime, z.email, z.telefon,
                           z.usluga, z.opis, z.datum_rezervacije, z.vreme_rezervacije,
                           z.potvrdio, z.otkazano, z.token, p.ime as firma_ime
                    FROM zakazivanja z
                    JOIN preduzeca p ON z.ime_firme = p.id
                    WHERE z.ime_firme = :firma_id
                    ORDER BY z.id
                """)
                termini = db.session.execute(termini_query, {'firma_id': firma_id}).fetchall()
                
                for termin_row in termini:
                    (termin_id, created_at, ime, email, telefon,
                     usluga, opis, datum, vreme, potvrdio, otkazano, token, firma_ime) = termin_row
                    
                    termin_data = {
                        'created_at': str(created_at),
                        'ime': ime,
                        'email': email,
                        'telefon': telefon,
                        'usluga': usluga,
                        'opis': opis,
                        'datum_rezervacije': str(datum),
                        'vreme_rezervacije': vreme,
                        'potvrdio': potvrdio,
                        'otkazano': otkazano,
                        'token': token
                    }
                    
                    # Ako je potvrdio, pronađi ime usera koji je potvrdio
                    if potvrdio:
                        potvrdio_user = db.session.execute(
                            text("SELECT username FROM users WHERE id = :id"),
                            {'id': potvrdio}
                        ).fetchone()
                        termin_data['potvrdio_ime'] = potvrdio_user[0] if potvrdio_user else 'N/A'
                    
                    tekst = rag.format_termin_tip1_for_embedding(termin_data, firma_ime)
                    
                    with embedding_limit:
                        embedding = rag.generate_embedding(tekst)
                    
                    db.session.execute(insert_query, {
                        'user_id': vlasnik_id,
                        'firma_id': firma_id,
                        'termin_id': termin_id,
                        'tip_id': EmbeddingTypes.VLASNIK,
                        'tekst': tekst,
                        'embedding': str(embedding)
                    })
                    
                    count += 1
                
                if count % 100 == 0:
                    log_progress(f"✅ TIP 1 - Importovano {count} zapisa do sada")
        
        db.session.commit()
        log_progress(f"✅ TIP 1 - VLASNIK import završen! Ukupno: {count} zapisa", "SUMMARY")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri TIP 1 import-u: {str(e)}", "ERROR")
        return 0


def batch_import_zaposleni_tip2(limit=None):
    """
    ========== TIP 2 - ZAPOSLEN ==========
    Red 1: User info zaposlenika
    Red 2: Firma info (samo firma gdje radi)
    Red 3-N: Termin info (samo termini u toj firmi)
    
    Args:
        limit (int): Limitiraj broj zaposlenih (za test)
    """
    log_progress("🔄 Počinjem import TIP 2 - ZAPOSLEN", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        # Pronađi sve zaposlene (users gdje zaposlen_u > 0)
        query = text("""
            SELECT id, username, email, brTel, zaposlen_u
            FROM users
            WHERE zaposlen_u > 0
            ORDER BY id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        zaposleni = db.session.execute(query).fetchall()
        log_progress(f"📊 Pronađeno {len(zaposleni)} zaposlenih za TIP 2 import")
        
        for zaposlenik_row in zaposleni:
            zaposlenik_id, username, email, brTel, firma_id = zaposlenik_row
            
            # ===== RED 1: User info zaposlenika =====
            # Pronađi naziv firme
            firma_info = db.session.execute(
                text("SELECT ime FROM preduzeca WHERE id = :id"),
                {'id': firma_id}
            ).fetchone()
            firma_ime = firma_info[0] if firma_info else 'N/A'
            
            user_data = {
                'username': username,
                'email': email,
                'brTel': brTel
            }
            
            tekst = rag.format_zaposlen_tip2_for_embedding(user_data, firma_ime)
            
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, termin_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :termin_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': zaposlenik_id,
                'firma_id': firma_id,
                'termin_id': None,
                'tip_id': EmbeddingTypes.ZAPOSLEN,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            
            # ===== RED 2: Firma info (samo firma gdje radi) =====
            firma_full = db.session.execute(
                text("SELECT ime, adresa, radno_vreme, cenovnik, overlapLimit FROM preduzeca WHERE id = :id"),
                {'id': firma_id}
            ).fetchone()
            
            if firma_full:
                ime, adresa, radno_vreme, cenovnik, overlapLimit = firma_full
                
                firma_data = {
                    'ime': ime,
                    'adresa': adresa,
                    'radno_vreme': radno_vreme,
                    'cenovnik': cenovnik,
                    'overlapLimit': overlapLimit
                }
                
                tekst = rag.format_firma_for_embedding(firma_data)
                
                with embedding_limit:
                    embedding = rag.generate_embedding(tekst)
                
                db.session.execute(insert_query, {
                    'user_id': zaposlenik_id,
                    'firma_id': firma_id,
                    'termin_id': None,
                    'tip_id': EmbeddingTypes.ZAPOSLEN,
                    'tekst': tekst,
                    'embedding': str(embedding)
                })
                
                count += 1
                
                # ===== RED 3-N: Termini samo te firme - ALI user_id je VLASNIK! =====
                vlasnik_id = db.session.execute(
                    text("SELECT vlasnik FROM preduzeca WHERE id = :id"),
                    {'id': firma_id}
                ).fetchone()[0]
                
                termini_query = text("""
                    SELECT z.id, z.created_at, z.ime, z.email, z.telefon,
                           z.usluga, z.opis, z.datum_rezervacije, z.vreme_rezervacije,
                           z.potvrdio, z.otkazano, z.token, p.ime as firma_ime
                    FROM zakazivanja z
                    JOIN preduzeca p ON z.ime_firme = p.id
                    WHERE z.ime_firme = :firma_id
                    ORDER BY z.id
                """)
                termini = db.session.execute(termini_query, {'firma_id': firma_id}).fetchall()
                
                for termin_row in termini:
                    (termin_id, created_at, ime, email, telefon,
                     usluga, opis, datum, vreme, potvrdio, otkazano, token, firma_ime_termin) = termin_row
                    
                    termin_data = {
                        'created_at': str(created_at),
                        'ime': ime,
                        'email': email,
                        'telefon': telefon,
                        'usluga': usluga,
                        'opis': opis,
                        'datum_rezervacije': str(datum),
                        'vreme_rezervacije': vreme,
                        'potvrdio': potvrdio,
                        'otkazano': otkazano,
                        'token': token
                    }
                    
                    # Ako je potvrdio, pronađi ime usera
                    if potvrdio:
                        potvrdio_user = db.session.execute(
                            text("SELECT username FROM users WHERE id = :id"),
                            {'id': potvrdio}
                        ).fetchone()
                        termin_data['potvrdio_ime'] = potvrdio_user[0] if potvrdio_user else 'N/A'
                    
                    tekst = rag.format_termin_tip1_for_embedding(termin_data, firma_ime_termin)
                    
                    with embedding_limit:
                        embedding = rag.generate_embedding(tekst)
                    
                    # VAŽNO: user_id je VLASNIK, ne zaposlenik!
                    db.session.execute(insert_query, {
                        'user_id': vlasnik_id,
                        'firma_id': firma_id,
                        'termin_id': termin_id,
                        'tip_id': EmbeddingTypes.ZAPOSLEN,
                        'tekst': tekst,
                        'embedding': str(embedding)
                    })
                    
                    count += 1
            
            if count % 100 == 0:
                log_progress(f"✅ TIP 2 - Importovano {count} zapisa do sada")
        
        db.session.commit()
        log_progress(f"✅ TIP 2 - ZAPOSLEN import završen! Ukupno: {count} zapisa", "SUMMARY")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri TIP 2 import-u: {str(e)}", "ERROR")
        return 0


def batch_import_klijenti_tip3(limit=None):
    """
    ========== TIP 3 - KLIJENT ==========
    Red 1: Minimalne info vlasnika (ime_preduzeca, opis)
    Red 2-N: Firma info (sve firme vlasnika)
    Red N+1-M: Termin info SAMO sa (usluga, datum, vreme, ime_firme)
    
    Args:
        limit (int): Limitiraj broj vlasnika (za test)
    """
    log_progress("🔄 Počinjem import TIP 3 - KLIJENT", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        # Pronađi sve vlasniče
        query = text("""
            SELECT id, ime_preduzeca, opis
            FROM users
            WHERE zaposlen_u = 0
            ORDER BY id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        vlasnici = db.session.execute(query).fetchall()
        log_progress(f"📊 Pronađeno {len(vlasnici)} vlasnika za TIP 3 import")
        
        for vlasnik_row in vlasnici:
            vlasnik_id, ime_preduzeca, opis = vlasnik_row
            
            # ===== RED 1: Minimalne info vlasnika =====
            user_data = {
                'ime_preduzeca': ime_preduzeca,
                'opis': opis
            }
            
            tekst = rag.format_vlasnik_info_tip3_for_embedding(user_data)
            
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, termin_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :termin_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': vlasnik_id,
                'firma_id': None,
                'termin_id': None,
                'tip_id': EmbeddingTypes.KLIJENT,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            
            # ===== RED 2-N: Firma info (sve firme vlasnika) =====
            firme_query = text("""
                SELECT id, ime, adresa, radno_vreme, cenovnik, overlapLimit
                FROM preduzeca
                WHERE vlasnik = :vlasnik_id
            """)
            firme = db.session.execute(firme_query, {'vlasnik_id': vlasnik_id}).fetchall()
            
            for firma_row in firme:
                firma_id, ime, adresa, radno_vreme, cenovnik, overlapLimit = firma_row
                
                firma_data = {
                    'ime': ime,
                    'adresa': adresa,
                    'radno_vreme': radno_vreme,
                    'cenovnik': cenovnik,
                    'overlapLimit': overlapLimit
                }
                
                tekst = rag.format_firma_for_embedding(firma_data)
                
                with embedding_limit:
                    embedding = rag.generate_embedding(tekst)
                
                db.session.execute(insert_query, {
                    'user_id': vlasnik_id,
                    'firma_id': firma_id,
                    'termin_id': None,
                    'tip_id': EmbeddingTypes.KLIJENT,
                    'tekst': tekst,
                    'embedding': str(embedding)
                })
                
                count += 1
                
                # ===== RED N+1-M: Termini - SAMO usluga, datum, vreme, ime_firme =====
                termini_query = text("""
                    SELECT z.id, z.usluga, z.datum_rezervacije, z.vreme_rezervacije, p.ime as firma_ime
                    FROM zakazivanja z
                    JOIN preduzeca p ON z.ime_firme = p.id
                    WHERE z.ime_firme = :firma_id
                    ORDER BY z.id
                """)
                termini = db.session.execute(termini_query, {'firma_id': firma_id}).fetchall()
                
                for termin_row in termini:
                    termin_id, usluga, datum, vreme, firma_ime_termin = termin_row
                    
                    termin_data = {
                        'usluga': usluga,
                        'datum_rezervacije': str(datum),
                        'vreme_rezervacije': vreme
                    }
                    
                    tekst = rag.format_termin_tip3_for_embedding(termin_data, firma_ime_termin)
                    
                    with embedding_limit:
                        embedding = rag.generate_embedding(tekst)
                    
                    db.session.execute(insert_query, {
                        'user_id': vlasnik_id,
                        'firma_id': firma_id,
                        'termin_id': termin_id,
                        'tip_id': EmbeddingTypes.KLIJENT,
                        'tekst': tekst,
                        'embedding': str(embedding)
                    })
                    
                    count += 1
                
                if count % 100 == 0:
                    log_progress(f"✅ TIP 3 - Importovano {count} zapisa do sada")
        
        db.session.commit()
        log_progress(f"✅ TIP 3 - KLIJENT import završen! Ukupno: {count} zapisa", "SUMMARY")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri TIP 3 import-u: {str(e)}", "ERROR")
        return 0


def main():
    """Glavna funkcija - pokreni sve import tipove"""
    
    with app.app_context():
        log_progress("=" * 60, "START")
        log_progress("🚀 BATCH IMPORT EMBEDDINGS V2 - NOVA TIPOLOGIJA - POČINJEM", "START")
        log_progress("=" * 60, "START")
        
        # Provera da postoji tabela embeddings
        try:
            db.session.execute(text("SELECT 1 FROM embeddings LIMIT 1"))
        except:
            log_progress("❌ Tabela embeddings ne postoji! Kreiraj je prvo sa SQL skriptom.", "ERROR")
            return
        
        start_time = datetime.now()
        
        # Prvo OBRIŠI sve stare embeddings
        log_progress("🔄 Brišem stare embeddings...", "INFO")
        db.session.execute(text("DELETE FROM embeddings"))
        db.session.commit()
        log_progress("✅ Stari embeddings obrisani", "INFO")
        
        # Importuj sve tri tipologije
        tip1_count = batch_import_vlasnici_tip1()
        tip2_count = batch_import_zaposleni_tip2()
        tip3_count = batch_import_klijenti_tip3()
        
        total_count = tip1_count + tip2_count + tip3_count
        elapsed = datetime.now() - start_time
        
        log_progress("=" * 60, "SUMMARY")
        log_progress(f"✅ IMPORT ZAVRŠEN!", "SUMMARY")
        log_progress(f"   • TIP 1 (VLASNIK): {tip1_count} zapisa", "SUMMARY")
        log_progress(f"   • TIP 2 (ZAPOSLEN): {tip2_count} zapisa", "SUMMARY")
        log_progress(f"   • TIP 3 (KLIJENT): {tip3_count} zapisa", "SUMMARY")
        log_progress(f"   • UKUPNO: {total_count} embeddings-a", "SUMMARY")
        log_progress(f"   • Vreme: {elapsed.total_seconds():.1f} sekundi", "SUMMARY")
        log_progress("=" * 60, "SUMMARY")


if __name__ == "__main__":
    main()
