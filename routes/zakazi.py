from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from datetime import datetime
from mailManager import send_confirmation_email, send_email_to_workers, html_head
import time
from functools import wraps


zakazi_bp = Blueprint("zakazi", __name__)


def retry_on_connection_error(max_retries=3, backoff_factor=2):
    """Retry decorator za SQL konekcijske greške"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if 'SSL connection' in str(e) or 'connection' in str(e).lower():
                        last_exception = e
                        wait_time = backoff_factor ** attempt
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                        continue
                    raise
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


@zakazi_bp.route('/<int:vlasnik_id>/forma', methods=['GET'])
@retry_on_connection_error(max_retries=3)
def get_forma(vlasnik_id):
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvatanje podataka o korisniku-vlasnika (preduzeću)
            user_query = text("""
                SELECT id, username, email, paket, istek_pretplate, ime_preduzeca, 
                       putanja_za_logo, forma, opis, radnoVreme, cenovnik
                FROM users WHERE id = :id
            """)
            user_result = db.session.execute(user_query, {'id': vlasnik_id}).fetchone()
            
            if not user_result:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Dohvatanje svih preduzeca sa zakazivanjima u jednoj query (JOIN)
            combined_query = text("""
                SELECT 
                    p.id, p.ime, p.adresa, p.radno_vreme, p.overlapLimit, p.cenovnik,
                    z.id as zak_id, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije
                FROM preduzeca p
                LEFT JOIN zakazivanja z ON p.id = z.ime_firme AND z.otkazano = FALSE
                WHERE p.vlasnik = :vlasnik_id
                ORDER BY p.id, z.datum_rezervacije, z.vreme_rezervacije
            """)
            
            combined_results = db.session.execute(combined_query, {'vlasnik_id': vlasnik_id}).fetchall()
            
            # Grupiraj rezultate na nivou Pythona umjesto N+1 upita
            preduzeca_dict = {}
            for row in combined_results:
                preduzece_id = row[0]
                
                if preduzece_id not in preduzeca_dict:
                    preduzeca_dict[preduzece_id] = {
                        "id": preduzece_id,
                        "ime": row[1],
                        "adresa": row[2],
                        "radno_vreme": row[3] if isinstance(row[3], dict) else (json.loads(row[3]) if isinstance(row[3], str) else {}),
                        "cenovnik": row[5] if isinstance(row[5], list) else [],
                        "overlapLimit": row[4],
                        "zauzeti_termini": []
                    }
                
                # Dodaj zakazivanje ako postoji
                if row[6] is not None:  # zak_id
                    preduzeca_dict[preduzece_id]["zauzeti_termini"].append({
                        "id": row[6],
                        "ime_firme": row[7],
                        "datum_rezervacije": str(row[8]),
                        "vreme_rezervacije": str(row[9])
                    })
            
            preduzeca_list = list(preduzeca_dict.values())
            
            # Parsiranje JSONB polja korisnika
            forma = user_result[7] if isinstance(user_result[7], dict) else (json.loads(user_result[7]) if isinstance(user_result[7], str) else {})
            
        return jsonify({
                "paket": user_result[3],
                "istek_pretplate": str(user_result[4]) if user_result[4] else None,
                "ime_preduzeca": user_result[5],
                "putanja_za_logo": user_result[6],
                "forma": forma,
                "opis": user_result[8],
                "lokacije": preduzeca_list
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    



@zakazi_bp.route('/<int:vlasnik_id>/izmena/<token>', methods=['GET'])
@retry_on_connection_error(max_retries=3)
def get_termin_za_izmenu(vlasnik_id, token):
    """
    Dohvata termin sa datim tokenom i sve podatke o preduzeću/vlasaniku
    Vraća format pogodno za formu za izmenu termina
    """
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvatanje podataka vlasnika i svih termina sa JOIN-om (umjesto N+1 upita)
            user_and_terms_query = text("""
                SELECT 
                    u.id, u.username, u.email, u.paket, u.istek_pretplate, u.ime_preduzeca, 
                    u.putanja_za_logo, u.forma,
                    p.id as pred_id, p.created_at, p.ime as pred_ime, p.vlasnik, p.adresa, p.radno_vreme, 
                    p.cenovnik, p.overlapLimit,
                    z.id as zak_id, z.created_at as zak_created, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije,
                    z.ime, z.email as zak_email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano
                FROM users u
                LEFT JOIN preduzeca p ON u.id = p.vlasnik
                LEFT JOIN zakazivanja z ON p.id = z.ime_firme AND z.token = :token
                WHERE u.id = :vlasnik_id
                ORDER BY p.id, z.created_at
            """)
            
            results = db.session.execute(user_and_terms_query, {'vlasnik_id': vlasnik_id, 'token': token}).fetchall()
            
            if not results:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Grupiraj podatke
            user_result = None
            lokacije_dict = {}
            termin_data = None
            
            for row in results:
                # Provjeri user podatke (isti su za sve redove)
                if user_result is None:
                    user_result = row[:8]  # Prvi 8 kolona su user polja
                
                # Ako nema lokacije, nastavi
                if row[8] is None:  # pred_id
                    continue
                
                pred_id = row[8]
                
                # Dodaj lokaciju ako je nova
                if pred_id not in lokacije_dict:
                    lokacije_dict[pred_id] = {
                        "id": pred_id,
                        "created_at": row[9],
                        "ime": row[10],
                        "vlasnik": row[11],
                        "adresa": row[12],
                        "radno_vreme": row[13] if isinstance(row[13], dict) else (json.loads(row[13]) if isinstance(row[13], str) else {}),
                        "duzina_termina": row[14] if isinstance(row[14], list) else (json.loads(row[14]) if isinstance(row[14], str) else []),
                        "overlapLimit": row[15],
                        "zauzeti_termini": []
                    }
                
                # Ako postoji zakazivanje za ovaj token, skopi ga
                if row[16] is not None:  # zak_id
                    if termin_data is None:  # Prvo zakazivanje sa ovim tokenom
                        usluga = row[24]
                        if isinstance(usluga, str):
                            usluga = json.loads(usluga) if usluga else {}
                        elif not isinstance(usluga, dict):
                            usluga = {}
                        
                        termin_data = {
                            "id": row[16],
                            "created_at": row[17],
                            "ime_firme": row[18],
                            "datum_rezervacije": str(row[19]),
                            "vreme_rezervacije": str(row[20]),
                            "ime": row[21],
                            "email": row[22],
                            "telefon": row[23],
                            "usluga": usluga,
                            "opis": row[25],
                            "potvrdio": row[26],
                            "token": row[27],
                            "otkazano": row[28]
                        }
                    
                    # Dodaj u zauzete termine samo ako je otkazano == FALSE
                    if not row[28]:  # otkazano
                        usluga_zak = row[24]
                        if isinstance(usluga_zak, str):
                            usluga_zak = json.loads(usluga_zak) if usluga_zak else {}
                        elif not isinstance(usluga_zak, dict):
                            usluga_zak = {}
                        
                        lokacije_dict[pred_id]["zauzeti_termini"].append({
                            "id": row[16],
                            "created_at": row[17],
                            "ime_firme": row[18],
                            "datum_rezervacije": str(row[19]),
                            "vreme_rezervacije": str(row[20]),
                            "ime": row[21],
                            "email": row[22],
                            "telefon": row[23],
                            "usluga": usluga_zak,
                            "opis": row[25],
                            "potvrdio": row[26],
                            "token": row[27],
                            "otkazano": row[28]
                        })
            
            if not termin_data:
                return jsonify({
                    "success": False,
                    "error": "Termin nije pronađen"
                }), 404
            
            if user_result is None:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Parsiranje JSONB polja korisnika
            forma = user_result[7]
            if isinstance(forma, str):
                forma = json.loads(forma) if forma else {}
            elif not isinstance(forma, dict):
                forma = {}
            
            lokacije_list = list(lokacije_dict.values())
            
            return jsonify({
                "termin": termin_data,
                "preduzece": {
                    "istek_pretplate": str(user_result[4]) if user_result[4] else None,
                    "ime_preduzeca": user_result[5],
                    "putanja_za_logo": user_result[6],
                    "forma": forma,
                    "lokacije": lokacije_list
                }
            }), 200
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



