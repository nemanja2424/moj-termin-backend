from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import text
import json


zakazivanja_bp = Blueprint("zakazivanja", __name__)


@zakazivanja_bp.route('/<int:id>', methods=['GET'])
@jwt_required()
def get_zakazivanja(id):
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvati korisnika
            user_query = text("""
                SELECT id, rola, zaposlen_u FROM users WHERE id = :id
            """)
            user_result = db.session.execute(user_query, {'id': id}).fetchone()
            
            if not user_result:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            user_id, rola, zaposlen_u = user_result[0], user_result[1], user_result[2]
            
            preduzeca_list = []
            zakazano_list = []
            
            if rola == 1:  # Vlasnik
                # Dohvati sve lokacije vlasnika
                preduzeca_query = text("""
                    SELECT id, ime, adresa FROM preduzeca WHERE vlasnik = :vlasnik_id
                    ORDER BY id
                """)
                preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik_id': user_id}).fetchall()
                
                for pred in preduzeca_results:
                    preduzeca_list.append({
                        "id": pred[0],
                        "ime": pred[1],
                        "adresa": pred[2]
                    })
                
                # Dohvati sve termine iz svih lokacija vlasnika
                for preduzece in preduzeca_results:
                    preduzece_id = preduzece[0]
                    
                    termini_query = text("""
                        SELECT z.id, z.created_at, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije,
                               z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano,
                               p.id, p.ime, p.adresa
                        FROM zakazivanja z
                        JOIN preduzeca p ON z.ime_firme = p.id
                        WHERE z.ime_firme = :preduzece_id
                        ORDER BY z.datum_rezervacije DESC, z.vreme_rezervacije DESC
                    """)
                    termini_results = db.session.execute(termini_query, {'preduzece_id': preduzece_id}).fetchall()
                    
                    lokacija_termini = []
                    for term in termini_results:
                        # Parse usluga field
                        usluga = term[8]
                        if isinstance(usluga, str):
                            usluga = json.loads(usluga) if usluga else {}
                        elif not isinstance(usluga, dict):
                            usluga = {}
                        
                        termin_data = {
                            "id": term[0],
                            "created_at": term[1],
                            "ime_firme": term[14],
                            "datum_rezervacije": str(term[3]),
                            "vreme_rezervacije": str(term[4]),
                            "ime": term[5],
                            "email": term[6],
                            "telefon": term[7],
                            "usluga": usluga,
                            "opis": term[9],
                            "potvrdio": term[10],
                            "token": term[11],
                            "otkazano": term[12],
                            "lokacija": {
                                "id": term[13],
                                "ime": term[14],
                                "adresa": term[15]
                            }
                        }
                        
                        # Ako je termin potvrđen, dodaj potvrdio_user
                        if term[10] != 0:
                            potvrdio_user_query = text("""
                                SELECT id, created_at, username, email, brTel, rola, paket, 
                                       zaposlen_u, istek_pretplate, ime_preduzeca, putanja_za_logo,
                                       radnoVreme, cenovnik, forma, ai_info, opis, paket_limits
                                FROM users WHERE id = :potvrdio_id
                            """)
                            potvrdio_result = db.session.execute(potvrdio_user_query, {'potvrdio_id': term[10]}).fetchone()
                            
                            if potvrdio_result:
                                # Parse JSONB fields
                                radnoVreme = potvrdio_result[11]
                                if isinstance(radnoVreme, str):
                                    radnoVreme = json.loads(radnoVreme) if radnoVreme else {}
                                elif not isinstance(radnoVreme, dict):
                                    radnoVreme = {}
                                
                                cenovnik = potvrdio_result[12]
                                if isinstance(cenovnik, str):
                                    cenovnik = json.loads(cenovnik) if cenovnik else []
                                elif not isinstance(cenovnik, list):
                                    cenovnik = []
                                
                                forma = potvrdio_result[13]
                                if isinstance(forma, str):
                                    forma = json.loads(forma) if forma else {}
                                elif not isinstance(forma, dict):
                                    forma = {}
                                
                                ai_info = potvrdio_result[14]
                                if isinstance(ai_info, str):
                                    ai_info = json.loads(ai_info) if ai_info else {}
                                elif not isinstance(ai_info, dict):
                                    ai_info = {}
                                
                                paket_limits = potvrdio_result[16]
                                if isinstance(paket_limits, str):
                                    paket_limits = json.loads(paket_limits) if paket_limits else {}
                                elif not isinstance(paket_limits, dict):
                                    paket_limits = {}
                                
                                termin_data["potvrdio_user"] = {
                                    "id": potvrdio_result[0],
                                    "created_at": potvrdio_result[1],
                                    "username": potvrdio_result[2],
                                    "email": potvrdio_result[3],
                                    "brTel": potvrdio_result[4],
                                    "rola": potvrdio_result[5],
                                    "paket": potvrdio_result[6],
                                    "zaposlen_u": potvrdio_result[7],
                                    "istek_pretplate": str(potvrdio_result[8]) if potvrdio_result[8] else None,
                                    "ime_preduzeca": potvrdio_result[9],
                                    "putanja_za_logo": potvrdio_result[10],
                                    "radnoVreme": radnoVreme,
                                    "cenovnik": cenovnik,
                                    "forma": forma,
                                    "ai_info": ai_info,
                                    "opis": potvrdio_result[15],
                                    "paket_limits": paket_limits
                                }
                        
                        lokacija_termini.append(termin_data)
                    
                    zakazano_list.append(lokacija_termini)
            
            elif rola == 2:  # Zaposlenik
                # Dohvati lokaciju gde je zaposlen
                if zaposlen_u:
                    preduzeca_query = text("""
                        SELECT id, ime, adresa FROM preduzeca WHERE id = :preduzece_id
                    """)
                    preduzeca_result = db.session.execute(preduzeca_query, {'preduzece_id': zaposlen_u}).fetchone()
                    
                    if preduzeca_result:
                        preduzeca_list.append({
                            "id": preduzeca_result[0],
                            "ime": preduzeca_result[1],
                            "adresa": preduzeca_result[2]
                        })
                        
                        # Dohvati sve termine za tu lokaciju
                        termini_query = text("""
                            SELECT z.id, z.created_at, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije,
                                   z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano,
                                   p.id, p.ime, p.adresa
                            FROM zakazivanja z
                            JOIN preduzeca p ON z.ime_firme = p.id
                            WHERE z.ime_firme = :preduzece_id
                            ORDER BY z.datum_rezervacije DESC, z.vreme_rezervacije DESC
                        """)
                        termini_results = db.session.execute(termini_query, {'preduzece_id': zaposlen_u}).fetchall()
                        
                        lokacija_termini = []
                        for term in termini_results:
                            # Parse usluga field
                            usluga = term[8]
                            if isinstance(usluga, str):
                                usluga = json.loads(usluga) if usluga else {}
                            elif not isinstance(usluga, dict):
                                usluga = {}
                            
                            termin_data = {
                                "id": term[0],
                                "created_at": term[1],
                                "ime_lokacije": term[14],
                                "datum_rezervacije": str(term[3]),
                                "vreme_rezervacije": str(term[4]),
                                "ime": term[5],
                                "email": term[6],
                                "telefon": term[7],
                                "usluga": usluga,
                                "opis": term[9],
                                "potvrdio": term[10],
                                "token": term[11],
                                "otkazano": term[12],
                                "lokacija": {
                                    "id": term[13],
                                    "ime": term[14],
                                    "adresa": term[15]
                                }
                            }
                            
                            # Ako je termin potvrđen, dodaj potvrdio_user
                            if term[10] != 0:
                                potvrdio_user_query = text("""
                                    SELECT id, created_at, username, email, brTel, rola, paket, 
                                           zaposlen_u, istek_pretplate, ime_preduzeca, putanja_za_logo,
                                           radnoVreme, cenovnik, forma, ai_info, opis, paket_limits
                                    FROM users WHERE id = :potvrdio_id
                                """)
                                potvrdio_result = db.session.execute(potvrdio_user_query, {'potvrdio_id': term[10]}).fetchone()
                                
                                if potvrdio_result:
                                    # Parse JSONB fields
                                    radnoVreme = potvrdio_result[11]
                                    if isinstance(radnoVreme, str):
                                        radnoVreme = json.loads(radnoVreme) if radnoVreme else {}
                                    elif not isinstance(radnoVreme, dict):
                                        radnoVreme = {}
                                    
                                    cenovnik = potvrdio_result[12]
                                    if isinstance(cenovnik, str):
                                        cenovnik = json.loads(cenovnik) if cenovnik else []
                                    elif not isinstance(cenovnik, list):
                                        cenovnik = []
                                    
                                    forma = potvrdio_result[13]
                                    if isinstance(forma, str):
                                        forma = json.loads(forma) if forma else {}
                                    elif not isinstance(forma, dict):
                                        forma = {}
                                    
                                    ai_info = potvrdio_result[14]
                                    if isinstance(ai_info, str):
                                        ai_info = json.loads(ai_info) if ai_info else {}
                                    elif not isinstance(ai_info, dict):
                                        ai_info = {}
                                    
                                    paket_limits = potvrdio_result[16]
                                    if isinstance(paket_limits, str):
                                        paket_limits = json.loads(paket_limits) if paket_limits else {}
                                    elif not isinstance(paket_limits, dict):
                                        paket_limits = {}
                                    
                                    termin_data["potvrdio_user"] = {
                                        "id": potvrdio_result[0],
                                        "created_at": potvrdio_result[1],
                                        "username": potvrdio_result[2],
                                        "email": potvrdio_result[3],
                                        "brTel": potvrdio_result[4],
                                        "rola": potvrdio_result[5],
                                        "paket": potvrdio_result[6],
                                        "zaposlen_u": potvrdio_result[7],
                                        "istek_pretplate": str(potvrdio_result[8]) if potvrdio_result[8] else None,
                                        "ime_preduzeca": potvrdio_result[9],
                                        "putanja_za_logo": potvrdio_result[10],
                                        "radnoVreme": radnoVreme,
                                        "cenovnik": cenovnik,
                                        "forma": forma,
                                        "ai_info": ai_info,
                                        "opis": potvrdio_result[15],
                                        "paket_limits": paket_limits
                                    }
                            
                            lokacija_termini.append(termin_data)
                        
                        zakazano_list.append(lokacija_termini)
            
            return jsonify({
                "success": True,
                "preduzeca": preduzeca_list,
                "zakazano": zakazano_list
            }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    



@zakazivanja_bp.route('/<string:token>/xrdcytfuvgbhjnkjhbgvyftucdyrxtsezxrdcytfuvy', methods=['GET'])
def get_termin_by_token(token):
    """
    Dohvata termin po tokenu bez autentifikacije.
    Koristi se na frontendu za izmenu termina bez logovanja.
    """
    try:
        from app import db, app
        
        with app.app_context():
            # Pronađi zakazivanje po tokenu
            termin_query = text("""
                SELECT z.id, z.created_at, z.ime_firme, z.datum_rezervacije, z.vreme_rezervacije,
                       z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano,
                       p.id, p.ime, p.adresa
                FROM zakazivanja z
                JOIN preduzeca p ON z.ime_firme = p.id
                WHERE z.token = :token
            """)
            term = db.session.execute(termin_query, {'token': token}).fetchone()
            
            if not term:
                return jsonify({
                    "success": False,
                    "error": "Termin nije pronađen"
                }), 404
            
            # Parse usluga field
            usluga = term[8]
            if isinstance(usluga, str):
                usluga = json.loads(usluga) if usluga else {}
            elif not isinstance(usluga, dict):
                usluga = {}
            
            termin_data = {
                "id": term[0],
                "created_at": term[1],
                "ime_firme": term[14],
                "datum_rezervacije": str(term[3]),
                "vreme_rezervacije": str(term[4]),
                "ime": term[5],
                "email": term[6],
                "telefon": term[7],
                "usluga": usluga,
                "opis": term[9],
                "potvrdio": term[10],
                "token": term[11],
                "otkazano": term[12],
                "lokacija": {
                    "id": term[13],
                    "ime": term[14],
                    "adresa": term[15]
                }
            }
            
            # Ako je termin potvrđen, dodaj potvrdio_user
            if term[10] != 0:
                potvrdio_user_query = text("""
                    SELECT id, created_at, username, email, brTel, rola, paket, 
                           zaposlen_u, istek_pretplate, ime_preduzeca, putanja_za_logo,
                           radnoVreme, cenovnik, forma, ai_info, opis, paket_limits
                    FROM users WHERE id = :potvrdio_id
                """)
                potvrdio_result = db.session.execute(potvrdio_user_query, {'potvrdio_id': term[10]}).fetchone()
                
                if potvrdio_result:
                    # Parse JSONB fields
                    radnoVreme = potvrdio_result[11]
                    if isinstance(radnoVreme, str):
                        radnoVreme = json.loads(radnoVreme) if radnoVreme else {}
                    elif not isinstance(radnoVreme, dict):
                        radnoVreme = {}
                    
                    cenovnik = potvrdio_result[12]
                    if isinstance(cenovnik, str):
                        cenovnik = json.loads(cenovnik) if cenovnik else []
                    elif not isinstance(cenovnik, list):
                        cenovnik = []
                    
                    forma = potvrdio_result[13]
                    if isinstance(forma, str):
                        forma = json.loads(forma) if forma else {}
                    elif not isinstance(forma, dict):
                        forma = {}
                    
                    ai_info = potvrdio_result[14]
                    if isinstance(ai_info, str):
                        ai_info = json.loads(ai_info) if ai_info else {}
                    elif not isinstance(ai_info, dict):
                        ai_info = {}
                    
                    paket_limits = potvrdio_result[16]
                    if isinstance(paket_limits, str):
                        paket_limits = json.loads(paket_limits) if paket_limits else {}
                    elif not isinstance(paket_limits, dict):
                        paket_limits = {}
                    
                    termin_data["potvrdio_user"] = {
                        "id": potvrdio_result[0],
                        "created_at": potvrdio_result[1],
                        "username": potvrdio_result[2],
                        "email": potvrdio_result[3],
                        "brTel": potvrdio_result[4],
                        "rola": potvrdio_result[5],
                        "paket": potvrdio_result[6],
                        "zaposlen_u": potvrdio_result[7],
                        "istek_pretplate": str(potvrdio_result[8]) if potvrdio_result[8] else None,
                        "ime_preduzeca": potvrdio_result[9],
                        "putanja_za_logo": potvrdio_result[10],
                        "radnoVreme": radnoVreme,
                        "cenovnik": cenovnik,
                        "forma": forma,
                        "ai_info": ai_info,
                        "opis": potvrdio_result[15],
                        "paket_limits": paket_limits
                    }
            
            return jsonify({
                "success": True,
                "termin": termin_data
            }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500