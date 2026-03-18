"""
Batch Import Embeddings - Učitava postojeće podatke u embeddings tabelu
Koristi se za prvo učitavanje i test

Pokretanje:
  Windows: python backend_tools/batch_import_embeddings.py
  VPS: python3 backend_tools/batch_import_embeddings.py
"""

import sys
import os
import json
from datetime import datetime

# Dodaj parent direktorijum u path da bi mogao da importa iz app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from ai.rag_manager import RAGManager, EmbeddingTypes
from sqlalchemy import text

# Semaphore za limitaciju simultanih embedding operacija
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


def batch_import_users(limit=None):
    """
    Importuj USER tipove embeddings-a (za vlasniče)
    
    Args:
        limit (int): Limitiraj broj zapisa (za test)
    """
    log_progress("🔄 Počinjem import USER tipova...", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        # Pronađi sve vlasniče (users sa zaposlen_u = 0)
        query = text("""
            SELECT id, username, email, brTel, zaposlen_u
            FROM users
            WHERE zaposlen_u = 0
            ORDER BY id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        users = db.session.execute(query).fetchall()
        
        log_progress(f"📊 Pronađeno {len(users)} vlasnika za import")
        
        for user_row in users:
            user_id, username, email, brTel, zaposlen_u = user_row
            
            # Formatiraj user podatke
            user_data = {
                'id': user_id,
                'username': username,
                'email': email,
                'brTel': brTel,
                'zaposlen_u': zaposlen_u
            }
            
            tekst = rag.format_user_data_for_embedding(user_data)
            
            # Generiši embedding
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            # Unesi u embeddings tabelu
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': user_id,
                'firma_id': None,  # NULL - nema firme za user tip
                'tip_id': EmbeddingTypes.USER,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            if count % 10 == 0:
                log_progress(f"✅ Importovano {count} USER zapisa")
        
        db.session.commit()
        log_progress(f"✅ USER import završen! Ukupno: {count} zapisa")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri USER import-u: {str(e)}", "ERROR")
        return 0


def batch_import_zaposleni(limit=None):
    """
    Importuj ZAPOSLENI tipove embeddings-a (zaposleni u firmama)
    
    Args:
        limit (int): Limitiraj broj zapisa (za test)
    """
    log_progress("🔄 Počinjem import ZAPOSLENI tipova...", "START")
    
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
        
        log_progress(f"📊 Pronađeno {len(zaposleni)} zaposlenih za import")
        
        for zaposlenik_row in zaposleni:
            zaposlenik_id, username, email, brTel, firma_id = zaposlenik_row
            
            # Formatiraj zaposlenik podatke
            zaposlenik_data = {
                'id': zaposlenik_id,
                'username': username,
                'email': email,
                'brTel': brTel,
                'zaposlen_u': firma_id
            }
            
            tekst = rag.format_user_data_for_embedding(zaposlenik_data)
            
            # Generiši embedding
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            # Unesi u embeddings tabelu
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': zaposlenik_id,
                'firma_id': firma_id,  # firma_id = ID firme u kojoj je zaposlen
                'tip_id': EmbeddingTypes.USER,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            if count % 10 == 0:
                log_progress(f"✅ Importovano {count} ZAPOSLENI zapisa")
        
        db.session.commit()
        log_progress(f"✅ ZAPOSLENI import završen! Ukupno: {count} zapisa")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri ZAPOSLENI import-u: {str(e)}", "ERROR")
        return 0


def batch_import_firme(limit=None):
    """
    Importuj FIRMA tipove embeddings-a
    Kombinovano: ime, adresa, radno_vreme, cenovnik
    
    Args:
        limit (int): Limitiraj broj zapisa (za test)
    """
    log_progress("🔄 Počinjem import FIRMA tipova...", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        query = text("""
            SELECT id, vlasnik, ime, adresa, radno_vreme, cenovnik, overlapLimit
            FROM preduzeca
            ORDER BY id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        firme = db.session.execute(query).fetchall()
        
        log_progress(f"📊 Pronađeno {len(firme)} firmi za import")
        
        for firma_row in firme:
            firma_id, vlasnik, ime, adresa, radno_vreme, cenovnik, overlapLimit = firma_row
            
            # Formatiraj firma podatke
            firma_data = {
                'id': firma_id,
                'vlasnik': vlasnik,
                'ime': ime,
                'adresa': adresa,
                'radno_vreme': radno_vreme,
                'cenovnik': cenovnik,
                'overlapLimit': overlapLimit
            }
            
            tekst = rag.format_firma_data_for_embedding(firma_data)
            
            # Generiši embedding
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            # Unesi u embeddings tabelu
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': vlasnik,
                'firma_id': firma_id,
                'tip_id': EmbeddingTypes.FIRMA,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            if count % 10 == 0:
                log_progress(f"✅ Importovano {count} FIRMA zapisa")
        
        db.session.commit()
        log_progress(f"✅ FIRMA import završen! Ukupno: {count} zapisa")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri FIRMA import-u: {str(e)}", "ERROR")
        return 0


def batch_import_termini(limit=None):
    """
    Importuj TERMIN tipove embeddings-a
    
    Args:
        limit (int): Limitiraj broj zapisa (za test)
    """
    log_progress("🔄 Počinjem import TERMIN tipova...", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        query = text("""
            SELECT z.id, p.vlasnik, z.ime_firme, z.token, z.created_at, z.ime_firme, 
                   z.datum_rezervacije, z.vreme_rezervacije, z.ime, z.email, z.telefon, 
                   z.usluga, z.opis, z.potvrdio, z.otkazano
            FROM zakazivanja z
            JOIN preduzeca p ON z.ime_firme = p.id
            ORDER BY z.id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        termini = db.session.execute(query).fetchall()
        
        log_progress(f"📊 Pronađeno {len(termini)} termina za import")
        
        for termin_row in termini:
            termin_id, vlasnik, ime_firme, token, created_at, ime_firme_id, datum, vreme, ime, email, telefon, usluga, opis, potvrdio, otkazano = termin_row
            
            # Formatiraj termin podatke
            termin_data = {
                'id': termin_id,
                'token': token,
                'created_at': str(created_at),
                'ime_firme': ime_firme_id,
                'datum_rezervacije': str(datum),
                'vreme_rezervacije': vreme,
                'ime': ime,
                'email': email,
                'telefon': telefon,
                'usluga': usluga,
                'opis': opis,
                'potvrdio': potvrdio,
                'otkazano': otkazano
            }
            
            tekst = rag.format_termin_data_for_embedding(termin_data)
            
            # Generiši embedding
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            # Unesi u embeddings tabelu
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, termin_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :termin_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': vlasnik,
                'firma_id': ime_firme_id,
                'termin_id': termin_id,
                'tip_id': EmbeddingTypes.TERMIN,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            if count % 50 == 0:
                log_progress(f"✅ Importovano {count} TERMIN zapisa")
        
        db.session.commit()
        log_progress(f"✅ TERMIN import završen! Ukupno: {count} zapisa")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri TERMIN import-u: {str(e)}", "ERROR")
        return 0


def batch_import_vlasnici(limit=None):
    """
    Importuj VLASNIK tipove embeddings-a
    
    Args:
        limit (int): Limitiraj broj zapisa (za test)
    """
    log_progress("🔄 Počinjem import VLASNIK tipova...", "START")
    
    rag = get_rag_manager()
    count = 0
    
    try:
        query = text("""
            SELECT id, username, paket, istek_pretplate, ime_preduzeca, opis, paket_limits
            FROM users
            WHERE zaposlen_u = 0
            ORDER BY id
        """)
        if limit:
            query = text(query.text + f" LIMIT {limit}")
        
        vlasnici = db.session.execute(query).fetchall()
        
        log_progress(f"📊 Pronađeno {len(vlasnici)} vlasnika za import")
        
        for vlasnik_row in vlasnici:
            vlasnik_id, username, paket, istek_pretplate, ime_preduzeca, opis, paket_limits = vlasnik_row
            
            # Formatiraj vlasnik podatke
            vlasnik_data = {
                'id': vlasnik_id,
                'username': username,
                'paket': paket,
                'istek_pretplate': str(istek_pretplate) if istek_pretplate else 'N/A',
                'ime_preduzeca': ime_preduzeca,
                'opis': opis,
                'paket_limits': paket_limits
            }
            
            tekst = rag.format_vlasnik_data_for_embedding(vlasnik_data)
            
            # Generiši embedding
            with embedding_limit:
                embedding = rag.generate_embedding(tekst)
            
            # Unesi u embeddings tabelu
            insert_query = text("""
                INSERT INTO embeddings (user_id, firma_id, tip_id, tekst, embedding)
                VALUES (:user_id, :firma_id, :tip_id, :tekst, :embedding)
                ON CONFLICT DO NOTHING
            """)
            
            db.session.execute(insert_query, {
                'user_id': vlasnik_id,
                'firma_id': None,  # NULL - nema firme za vlasnik tip
                'tip_id': EmbeddingTypes.VLASNIK,
                'tekst': tekst,
                'embedding': str(embedding)
            })
            
            count += 1
            if count % 10 == 0:
                log_progress(f"✅ Importovano {count} VLASNIK zapisa")
        
        db.session.commit()
        log_progress(f"✅ VLASNIK import završen! Ukupno: {count} zapisa")
        return count
        
    except Exception as e:
        db.session.rollback()
        log_progress(f"❌ Greška pri VLASNIK import-u: {str(e)}", "ERROR")
        return 0


def main():
    """Glavna funkcija - pokreni sve import tipove"""
    
    with app.app_context():
        log_progress("=" * 60, "START")
        log_progress("🚀 BATCH IMPORT EMBEDDINGS - POČINJEM", "START")
        log_progress("=" * 60, "START")
        
        # Provera da postoji tabela embeddings
        try:
            db.session.execute(text("SELECT 1 FROM embeddings LIMIT 1"))
        except:
            log_progress("❌ Tabela embeddings ne postoji! Kreiraj je prvo sa SQL skriptom.", "ERROR")
            return
        
        start_time = datetime.now()
        
        # Importuj sve tipove
        users_count = batch_import_users()  # Vlasnici
        zaposleni_count = batch_import_zaposleni()  # Zaposleni
        firme_count = batch_import_firme()  # Za sve firme
        termini_count = batch_import_termini()  # Za sve termine
        vlasnici_count = batch_import_vlasnici()  # Za sve vlasniče
        
        total_count = users_count + zaposleni_count + firme_count + termini_count + vlasnici_count
        elapsed = datetime.now() - start_time
        
        log_progress("=" * 60, "SUMMARY")
        log_progress(f"✅ IMPORT ZAVRŠEN!", "SUMMARY")
        log_progress(f"   • VLASNICI: {users_count} zapisa", "SUMMARY")
        log_progress(f"   • ZAPOSLENI: {zaposleni_count} zapisa", "SUMMARY")
        log_progress(f"   • FIRMA: {firme_count} zapisa", "SUMMARY")
        log_progress(f"   • TERMIN: {termini_count} zapisa", "SUMMARY")
        log_progress(f"   • VLASNIK: {vlasnici_count} zapisa", "SUMMARY")
        log_progress(f"   • UKUPNO: {total_count} embeddings-a", "SUMMARY")
        log_progress(f"   • Vreme: {elapsed.total_seconds():.1f} sekundi", "SUMMARY")
        log_progress("=" * 60, "SUMMARY")


if __name__ == "__main__":
    main()
