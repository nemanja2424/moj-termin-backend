from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from datetime import datetime
from mailManager import send_confirmation_email, send_email_to_workers, html_head


zakazi_bp = Blueprint("zakazi", __name__)



@zakazi_bp.route('/<int:vlasnik_id>/forma', methods=['GET'])
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
            
            # Dohvatanje svih preduzeca (lokacija) vlasnika
            preduzeca_query = text("""
                SELECT id, ime, adresa, radno_vreme, overlapLimit, cenovnik
                FROM preduzeca WHERE vlasnik = :vlasnik_id
            """)
            print(vlasnik_id)
            preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik_id': vlasnik_id}).fetchall()
            
            preduzeca_list = []
            
            for preduzece in preduzeca_results:
                preduzece_id = preduzece[0]
                
                # Dohvatanje svih zakazanih termina za ovu lokaciju
                zakazivanja_query = text("""
                    SELECT id, ime_firme, datum_rezervacije, vreme_rezervacije
                    FROM zakazivanja 
                    WHERE ime_firme = :preduzece_id AND otkazano = FALSE
                    ORDER BY datum_rezervacije, vreme_rezervacije
                """)
                zakazivanja_results = db.session.execute(zakazivanja_query, {'preduzece_id': preduzece_id}).fetchall()
                
                zauzeti_termini = []
                for zak in zakazivanja_results:
                    zauzeti_termini.append({
                        "id": zak[0],
                        "ime_firme": zak[1],
                        "datum_rezervacije": str(zak[2]),
                        "vreme_rezervacije": str(zak[3])
                    })
                
                # Parsiranje cenovnika - niz sa uslugama
                cenovnik_val = preduzece[5] if isinstance(preduzece[5], list) else []
                
                preduzeca_list.append({
                    "id": preduzece_id,
                    "ime": preduzece[1],
                    "adresa": preduzece[2],
                    "radno_vreme": preduzece[3] if isinstance(preduzece[3], dict) else (json.loads(preduzece[3]) if isinstance(preduzece[3], str) else {}),
                    "cenovnik": cenovnik_val,
                    "overlapLimit": preduzece[4],
                    "zauzeti_termini": zauzeti_termini
                })
            
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
def get_termin_za_izmenu(vlasnik_id, token):
    """
    Dohvata termin sa datim tokenom i sve podatke o preduzeću/vlasaniku
    Vraća format pogodno za formu za izmenu termina
    """
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvatanje podataka vlasnika
            user_query = text("""
                SELECT id, username, email, paket, istek_pretplate, ime_preduzeca, 
                       putanja_za_logo, forma
                FROM users WHERE id = :id
            """)
            user_result = db.session.execute(user_query, {'id': vlasnik_id}).fetchone()
            
            if not user_result:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Dohvatanje svih lokacija vlasnika
            preduzeca_query = text("""
                SELECT id, created_at, ime, vlasnik, adresa, radno_vreme, 
                       cenovnik, overlapLimit
                FROM preduzeca WHERE vlasnik = :vlasnik_id
            """)
            preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik_id': vlasnik_id}).fetchall()
            
            # Pronađi termin sa datim tokenom u bilo kojoj lokaciji vlasnika
            preduzeca_ids = [pred[0] for pred in preduzeca_results]
            
            termin_result = None
            if preduzeca_ids:
                # Kreiraj placeholder za IN klauzulu
                placeholders = ','.join([f':pred_id_{i}' for i in range(len(preduzeca_ids))])
                termin_query = text(f"""
                    SELECT id, created_at, ime_firme, datum_rezervacije, vreme_rezervacije,
                           ime, email, telefon, usluga, opis, potvrdio, token, otkazano
                    FROM zakazivanja WHERE token = :token AND ime_firme IN ({placeholders})
                """)
                params = {'token': token}
                for i, pred_id in enumerate(preduzeca_ids):
                    params[f'pred_id_{i}'] = pred_id
                
                termin_result = db.session.execute(termin_query, params).fetchone()
            
            if not termin_result:
                return jsonify({
                    "success": False,
                    "error": "Termin nije pronađen"
                }), 404
            
            # Parse termin data
            usluga = termin_result[8]
            if isinstance(usluga, str):
                usluga = json.loads(usluga) if usluga else {}
            elif not isinstance(usluga, dict):
                usluga = {}
            
            termin_data = {
                "id": termin_result[0],
                "created_at": termin_result[1],
                "ime_firme": termin_result[2],
                "datum_rezervacije": str(termin_result[3]),
                "vreme_rezervacije": str(termin_result[4]),
                "ime": termin_result[5],
                "email": termin_result[6],
                "telefon": termin_result[7],
                "usluga": usluga,
                "opis": termin_result[9],
                "potvrdio": termin_result[10],
                "token": termin_result[11],
                "otkazano": termin_result[12]
            }
            
            lokacije_list = []
            
            for preduzece in preduzeca_results:
                preduzece_id = preduzece[0]
                
                # Dohvatanje svih zakazanih termina za ovu lokaciju
                zakazivanja_query = text("""
                    SELECT id, created_at, ime_firme, datum_rezervacije, vreme_rezervacije,
                           ime, email, telefon, usluga, opis, potvrdio, token, otkazano
                    FROM zakazivanja 
                    WHERE ime_firme = :preduzece_id AND otkazano = FALSE
                    ORDER BY datum_rezervacije, vreme_rezervacije
                """)
                zakazivanja_results = db.session.execute(zakazivanja_query, {'preduzece_id': preduzece_id}).fetchall()
                
                zauzeti_termini = []
                for zak in zakazivanja_results:
                    usluga_zak = zak[8]
                    if isinstance(usluga_zak, str):
                        usluga_zak = json.loads(usluga_zak) if usluga_zak else {}
                    elif not isinstance(usluga_zak, dict):
                        usluga_zak = {}
                    
                    zauzeti_termini.append({
                        "id": zak[0],
                        "created_at": zak[1],
                        "ime_firme": zak[2],
                        "datum_rezervacije": str(zak[3]),
                        "vreme_rezervacije": str(zak[4]),
                        "ime": zak[5],
                        "email": zak[6],
                        "telefon": zak[7],
                        "usluga": usluga_zak,
                        "opis": zak[9],
                        "potvrdio": zak[10],
                        "token": zak[11],
                        "otkazano": zak[12]
                    })
                
                # Parsiranje cenovnika - niz sa uslugama (duzina_termina)
                cenovnik_val = preduzece[6]
                if isinstance(cenovnik_val, str):
                    cenovnik_val = json.loads(cenovnik_val) if cenovnik_val else []
                elif not isinstance(cenovnik_val, list):
                    cenovnik_val = []
                
                # Parsiranje radnog vremena
                radno_vreme_val = preduzece[5]
                if isinstance(radno_vreme_val, str):
                    radno_vreme_val = json.loads(radno_vreme_val) if radno_vreme_val else {}
                elif not isinstance(radno_vreme_val, dict):
                    radno_vreme_val = {}
                
                lokacije_list.append({
                    "id": preduzece_id,
                    "created_at": preduzece[1],
                    "ime": preduzece[2],
                    "vlasnik": preduzece[3],
                    "adresa": preduzece[4],
                    "radno_vreme": radno_vreme_val,
                    "duzina_termina": cenovnik_val,
                    "overlapLimit": preduzece[7],
                    "zauzeti_termini": zauzeti_termini
                })
            
            # Parsiranje JSONB polja korisnika
            forma = user_result[7]
            if isinstance(forma, str):
                forma = json.loads(forma) if forma else {}
            elif not isinstance(forma, dict):
                forma = {}
            
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



