from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from flask_jwt_extended import jwt_required, get_jwt_identity


aiInfo_bp = Blueprint("aiInfo", __name__)


@aiInfo_bp.route('/<int:user_id>', methods=['GET'])
@jwt_required()
def get_ai_info(user_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Provera da li korisnik pokušava da dohvati podatke drugome
        if current_user_id != user_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da vidite AI info drugom korisniku"
            }), 403
        
        with app.app_context():
            # Dohvatanje korisnika
            user_query = text("""
                SELECT rola, paket, zaposlen_u, ai_info 
                FROM users WHERE id = :id
            """)
            user = db.session.execute(user_query, {'id': user_id}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Parsing ai_info polja
            ai_info = user[3]
            if isinstance(ai_info, str):
                ai_info = json.loads(ai_info) if ai_info else {}
            elif not isinstance(ai_info, dict):
                ai_info = {}
        
        return jsonify({
            "success": True,
            "rola": user[0],
            "paket": user[1],
            "zaposlen_u": user[2],
            "ai_info": ai_info
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@aiInfo_bp.route('/<int:user_id>', methods=['PATCH'])
@jwt_required()
def update_ai_info(user_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Provera da li korisnik pokušava da izmeni podatke drugome
        if current_user_id != user_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da menjate AI info drugom korisniku"
            }), 403
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznog polja
        if not data.get('ai_info'):
            return jsonify({
                "success": False,
                "error": "ai_info je obavezno"
            }), 400
        
        with app.app_context():
            # Verifikovanje da korisnik postoji
            user_query = text("SELECT id FROM users WHERE id = :id")
            user = db.session.execute(user_query, {'id': user_id}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Ažuriranje ai_info polja
            ai_info_json = json.dumps(data.get('ai_info'))
            
            update_query = text("""
                UPDATE users SET ai_info = :ai_info
                WHERE id = :id
                RETURNING ai_info
            """)
            
            result = db.session.execute(update_query, {
                'ai_info': ai_info_json,
                'id': user_id
            }).fetchone()
            db.session.commit()
            
            # Parsing ai_info polja
            ai_info = result[0]
            if isinstance(ai_info, str):
                ai_info = json.loads(ai_info) if ai_info else {}
        
        return jsonify({
            "success": True,
            "message": "AI info je uspešno ažurirano",
            "ai_info": ai_info
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def get_ai_data_for_user(user_id, db):
    """
    Dohvata sve potrebne podatke za AI na osnovu korisnika.
    - Ako je vlasnik (rola=1): sve njegove lokacije i sve termine iz tih lokacija
    - Ako je zaposlenik (rola=2): lokacija gde je zaposlen i termini te lokacije
    """
    try:
        
        # Dohvati korisnika
        user_query = text("""
            SELECT id, username, email, rola, zaposlen_u, paket, cenovnik, radnoVreme, forma 
            FROM users WHERE id = :id
        """)
        user = db.session.execute(user_query, {'id': user_id}).fetchone()
        
        if not user:
            return None
        
        user_data = {
            "id": user[0],
            "username": user[1],
            "email": user[2],
            "rola": user[3],
            "zaposlen_u": user[4],
            "paket": user[5],
            "cenovnik": user[6],
            "radnoVreme": user[7],
            "forma": user[8]
        }
        
        preduzeca = []
        termini = []
        
        if user[3] == 1:  # Vlasnik
            # Dohvati sve lokacije vlasnika
            preduzeca_query = text("""
                SELECT id, ime, adresa, radno_vreme, cenovnik, overlapLimit 
                FROM preduzeca WHERE vlasnik = :vlasnik
            """)
            preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik': user_id}).fetchall()
            
            for pred in preduzeca_results:
                preduzeca.append({
                    "id": pred[0],
                    "ime": pred[1],
                    "adresa": pred[2],
                    "radno_vreme": pred[3],
                    "cenovnik": pred[4],
                    "overlapLimit": pred[5]
                })
            
            # Dohvati sve termine iz svih lokacija
            if preduzeca:
                termini_query = text("""
                    SELECT z.id, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije, 
                           z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano,
                           p.ime as ime_firme_tekst
                    FROM zakazivanja z
                    JOIN preduzeca p ON z.ime_firme = p.id
                    WHERE p.vlasnik = :vlasnik
                    ORDER BY z.datum_rezervacije DESC
                """)
                termini_results = db.session.execute(termini_query, {'vlasnik': user_id}).fetchall()
                
                for term in termini_results:
                    usluga = term[7]
                    if isinstance(usluga, str):
                        usluga = json.loads(usluga) if usluga else {}
                    
                    termini.append({
                        "id": term[0],
                        "ime_firme": term[12],
                        "datum_rezervacije": str(term[2]),
                        "vreme_rezervacije": term[3],
                        "ime": term[4],
                        "email": term[5],
                        "telefon": term[6],
                        "usluga": usluga,
                        "opis": term[8],
                        "potvrdio": term[9],
                        "token": term[10],
                        "otkazano": term[11]
                    })
        
        elif user[3] == 2:  # Zaposlenik
            # Dohvati lokaciju gde je zaposlen
            lokacija_id = user[4]  # zaposlen_u
            if lokacija_id:
                preduzeca_query = text("""
                    SELECT id, ime, adresa, radno_vreme, cenovnik, overlapLimit 
                    FROM preduzeca WHERE id = :id
                """)
                preduzeca_result = db.session.execute(preduzeca_query, {'id': lokacija_id}).fetchone()
                
                if preduzeca_result:
                    preduzeca.append({
                        "id": preduzeca_result[0],
                        "ime": preduzeca_result[1],
                        "adresa": preduzeca_result[2],
                        "radno_vreme": preduzeca_result[3],
                        "cenovnik": preduzeca_result[4],
                        "overlapLimit": preduzeca_result[5]
                    })
                
                # Dohvati termine iz te lokacije
                termini_query = text("""
                    SELECT z.id, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije, 
                           z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano,
                           p.ime as ime_firme_tekst
                    FROM zakazivanja z
                    JOIN preduzeca p ON z.ime_firme = p.id
                    WHERE z.ime_firme = :lokacija_id
                    ORDER BY z.datum_rezervacije DESC
                """)
                termini_results = db.session.execute(termini_query, {'lokacija_id': lokacija_id}).fetchall()
                
                for term in termini_results:
                    usluga = term[7]
                    if isinstance(usluga, str):
                        usluga = json.loads(usluga) if usluga else {}
                    
                    termini.append({
                        "id": term[0],
                        "ime_firme": term[12],
                        "datum_rezervacije": str(term[2]),
                        "vreme_rezervacije": term[3],
                        "ime": term[4],
                        "email": term[5],
                        "telefon": term[6],
                        "usluga": usluga,
                        "opis": term[8],
                        "potvrdio": term[9],
                        "token": term[10],
                        "otkazano": term[11]
                    })
        
        return {
            "user": user_data,
            "preduzeca": preduzeca,
            "termini": termini
        }
    
    except Exception as e:
        print(f"❌ Greška pri dohvatanju AI podataka: {str(e)}")
        return None