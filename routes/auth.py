from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity
from datetime import datetime, timedelta
import os
from werkzeug.security import generate_password_hash, check_password_hash


auth_bp = Blueprint("auth", __name__)


@auth_bp.route('/test', methods=['GET'])
def auth_test():
    return jsonify({"message": "auth radi"})


@auth_bp.route('/signup', methods=['POST'])
def signup():
    try:
        from app import db, app
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        print(data.get("ime"))
        
        # Validacija obaveznih polja
        if not data.get('ime') or not data.get('regEmail'):
            return jsonify({
                "success": False,
                "error": "Ime i email su obavezni"
            }), 400
        
        # Validacija šifre
        if not data.get('regPass'):
            return jsonify({
                "success": False,
                "error": "Šifra je obavezna"
            }), 400
        
        if len(data.get('regPass', '')) < 6:
            return jsonify({
                "success": False,
                "error": "Šifra mora imati najmanje 6 karaktera"
            }), 400
        
        # Hešovanje šifre
        hashed_password = generate_password_hash(data.get('regPass'))
        
        with app.app_context():
            # Proveravanje da li email već postoji
            check_query = text("SELECT id FROM users WHERE email = :email")
            existing_user = db.session.execute(check_query, {'email': data.get('regEmail')}).fetchone()
            
            if existing_user:
                return jsonify({
                    "success": False,
                    "title": "dupliran mejl",
                    "message": "Nalog sa ovim emailom već postoji"
                }), 400
            
            # SQL INSERT query sa :named parametrima
            query = text("""
                INSERT INTO users (
                    username, email, brTel, password, rola, paket, 
                    zaposlen_u, istek_pretplate, ime_preduzeca, putanja_za_logo,
                    radnoVreme, cenovnik, forma, ai_info, opis, paket_limits
                ) VALUES (
                    :username, :email, :brTel, :password, :rola, :paket,
                    :zaposlen_u, :istek_pretplate, :ime_preduzeca, :putanja_za_logo,
                    :radnoVreme, :cenovnik, :forma, :ai_info, :opis, :paket_limits
                )
                RETURNING id, username, email, created_at
            """)
            
            # Parametri kao dictionary
            params = {
                'username': data.get('ime'),
                'email': data.get('regEmail'),
                'brTel': data.get('brTel'),
                'password': hashed_password,
                'rola': data.get('rola', 1),
                'paket': data.get('paket', 'Personalni'),
                'zaposlen_u': data.get('zaposlen_u', 0),
                'istek_pretplate': data.get('istek_pretplate'),
                'ime_preduzeca': data.get('ime_preduzeca'),
                'putanja_za_logo': data.get('putanja_za_logo', '/Images/logo.webp'),
                'radnoVreme': json.dumps(data.get('radnoVreme', {})),
                'cenovnik': json.dumps(data.get('cenovnik', [])),
                'forma': json.dumps(data.get('forma', {})),
                'ai_info': json.dumps(data.get('ai_info', {})),
                'opis': data.get('opis', ''),
                'paket_limits': json.dumps(data.get('paket_limits', {}))
            }
            
            # Izvršavanje queryja
            result = db.session.execute(query, params).fetchone()
            db.session.commit()
            
            # Generisanje JWT tokena
            user_id = result[0]
            user_ime = result[1]
            user_rola = params['rola']
            
            # Koristi create_access_token iz flask-jwt-extended
            access_token = create_access_token(
                identity=str(user_id),
                additional_claims={
                    'ime': user_ime,
                    'email': params['email'],
                    'rola': user_rola
                }
            )
        
        return jsonify({
            "success": True,
            "authToken": access_token,
            "id": user_id,
            "ime": user_ime,
            "rola": user_rola,
            "nov": True
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        from app import db, app
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data.get('email') or not data.get('password'):
            return jsonify({
                "success": False,
                "error": "Email i šifra su obavezni"
            }), 400
        
        with app.app_context():
            # Pronalaženje korisnika po emailu
            query = text("SELECT id, username, password, rola FROM users WHERE email = :email")
            user = db.session.execute(query, {'email': data.get('email')}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "message": "Invalid Email."
                }), 401
            
            # Verifikovanje šifre
            if not check_password_hash(user[2], data.get('password')):
                return jsonify({
                    "success": False,
                    "message": "Invalid Password."
                }), 401
            
            # Generisanje JWT tokena
            user_id = user[0]
            user_ime = user[1]
            user_rola = user[3]
            
            access_token = create_access_token(
                identity=str(user_id),
                additional_claims={
                    'ime': user_ime,
                    'email': data.get('email'),
                    'rola': user_rola
                }
            )
        
        return jsonify({
            "success": True,
            "authToken": access_token,
            "id": user_id,
            "rola": user_rola
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@auth_bp.route('/me/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_profile(user_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        with app.app_context():
            # Dohvatanje korisnika
            user_query = text("SELECT id, username, email, brTel, rola, paket, zaposlen_u, ime_preduzeca, putanja_za_logo, opis FROM users WHERE id = :id")
            user = db.session.execute(user_query, {'id': user_id}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            user_rola = user[4]  # rola
            zaposlen_u = user[6]  # zaposlen_u
            
            # Lista za preduzeca i zakazivanja
            preduzeca = []
            zakazano = []
            vlasnik_info = None
            
            # LOGIKA NA OSNOVU ROLE
            if user_rola == 1:  # Vlasnik
                # Pronalaženje svih preduzeca gde je korisnik vlasnik
                preduzeca_query = text("""
                    SELECT id, ime, adresa, radno_vreme, cenovnik FROM preduzeca 
                    WHERE vlasnik = :vlasnik_id
                """)
                preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik_id': user_id}).fetchall()
                
                for preduzece in preduzeca_results:
                    preduzece_id = preduzece[0]
                    preduzeca.append({
                        "id": preduzece_id,
                        "ime": preduzece[1],
                        "adresa": preduzece[2],
                        "radno_vreme": preduzece[3] if isinstance(preduzece[3], dict) else (json.loads(preduzece[3]) if isinstance(preduzece[3], str) else {}),
                        "cenovnik": preduzece[4] if isinstance(preduzece[4], (dict, list)) else (json.loads(preduzece[4]) if isinstance(preduzece[4], str) else [])
                    })
                    
                    # Dohvatanje zakazivanja za ovo preduzeće
                    zakazivanja_query = text("""
                        SELECT z.id, z.created_at, p.ime, z.datum_rezervacije, z.vreme_rezervacije,
                            z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano
                        FROM zakazivanja z
                        JOIN preduzeca p ON z.ime_firme = p.id
                        WHERE z.ime_firme = :ime_firme
                        ORDER BY z.created_at DESC
                        LIMIT 20
                    """)
                    zakazivanja = db.session.execute(zakazivanja_query, {'ime_firme': preduzece_id}).fetchall()
                    
                    for zakaz in zakazivanja:
                        # Dohvatanje podataka o zaposlenom koji je potvrdio termin (ako postoji)
                        potrdio_user_info = None
                        if zakaz[10]:  # z.potvrdio je na poziciji 10
                            korisnik_query = text("SELECT username FROM users WHERE id = :id")
                            potrdio_info_res = db.session.execute(korisnik_query, {'id': zakaz[10]}).fetchone()
                            if potrdio_info_res:
                                potrdio_user_info = {
                                    "id": zakaz[10],
                                    "username": potrdio_info_res[0]
                                }
                        
                        zakazano.append({
                            "id": zakaz[0],
                            "created_at": str(zakaz[1]),
                            "ime_firme": zakaz[2],
                            "datum_rezervacije": str(zakaz[3]),
                            "vreme_rezervacije": zakaz[4],
                            "ime": zakaz[5],
                            "email": zakaz[6],
                            "telefon": zakaz[7],
                            "usluga": zakaz[8],
                            "opis": zakaz[9],
                            "potvrdio": zakaz[10],
                            "token": zakaz[11],
                            "otkazano": zakaz[12],
                            "potvrdio_user": potrdio_user_info
                        })
                
                vlasnik_info = {
                    "id": user[0],
                    "ime": user[1],
                    "email": user[2]
                }
            
            else:  # Zaposleni ili redovni korisnik
                # Pronalaženje preduzeca gde je korisnik zaposlen
                preduzeca_query = text("""
                    SELECT DISTINCT p.id, p.ime, p.adresa, p.radno_vreme, p.cenovnik FROM preduzeca p
                    WHERE p.id = (SELECT zaposlen_u FROM users WHERE id = :user_id)
                """)
                preduzeca_results = db.session.execute(preduzeca_query, {'user_id': user_id}).fetchall()
                
                for preduzece in preduzeca_results:
                    preduzece_id = preduzece[0]
                    preduzeca.append({
                        "id": preduzece_id,
                        "ime": preduzece[1],
                        "adresa": preduzece[2],
                        "radno_vreme": preduzece[3] if isinstance(preduzece[3], dict) else (json.loads(preduzece[3]) if isinstance(preduzece[3], str) else {}),
                        "cenovnik": preduzece[4] if isinstance(preduzece[4], (dict, list)) else (json.loads(preduzece[4]) if isinstance(preduzece[4], str) else [])
                    })
                    
                    # Dohvatanje zakazivanja za ovo preduzeće
                    zakazivanja_query = text("""
                        SELECT z.id, z.created_at, p.ime, z.datum_rezervacije, z.vreme_rezervacije,
                            z.ime, z.email, z.telefon, z.usluga, z.opis, z.potvrdio, z.token, z.otkazano
                        FROM zakazivanja z
                        JOIN preduzeca p ON z.ime_firme = p.id
                        WHERE z.ime_firme = :preduzece_id
                        ORDER BY z.created_at DESC
                    """)
                    zakazivanja = db.session.execute(zakazivanja_query, {'preduzece_id': preduzece_id}).fetchall()
                    
                    for zakaz in zakazivanja:
                        # Dohvatanje podataka o zaposlenom koji je potvrdio termin (ako postoji)
                        potrdio_user_info = None
                        if zakaz[10]:  # z.potvrdio je na poziciji 10
                            korisnik_query = text("SELECT username FROM users WHERE id = :id")
                            potrdio_info_res = db.session.execute(korisnik_query, {'id': zakaz[10]}).fetchone()
                            if potrdio_info_res:
                                potrdio_user_info = {
                                    "id": zakaz[10],
                                    "username": potrdio_info_res[0]
                                }
                        
                        zakazano.append({
                            "id": zakaz[0],
                            "created_at": str(zakaz[1]),
                            "ime_firme": zakaz[2],
                            "datum_rezervacije": str(zakaz[3]),
                            "vreme_rezervacije": zakaz[4],
                            "ime": zakaz[5],
                            "email": zakaz[6],
                            "telefon": zakaz[7],
                            "usluga": zakaz[8],
                            "opis": zakaz[9],
                            "potvrdio": zakaz[10],
                            "token": zakaz[11],
                            "otkazano": zakaz[12],
                            "potvrdio_user": potrdio_user_info
                        })
                
                # Dohvatanje podataka o vlasniku preduzeca (iz prvog preduzeca)
                if preduzeca:
                    vlasnik_query = text("""
                        SELECT p.vlasnik FROM preduzeca p WHERE p.id = :preduzece_id
                    """)
                    vlasnik_res = db.session.execute(vlasnik_query, {'preduzece_id': preduzeca[0]['id']}).fetchone()
                    
                    if vlasnik_res:
                        vlasnik_info_query = text("SELECT username, email FROM users WHERE id = :id")
                        vlasnik_info_res = db.session.execute(vlasnik_info_query, {'id': vlasnik_res[0]}).fetchone()
                        if vlasnik_info_res:
                            vlasnik_info = {
                                "id": vlasnik_res[0],
                                "ime": vlasnik_info_res[0],
                                "email": vlasnik_info_res[1]
                            }
        
        return jsonify({
            "vlasnik": {
                "id": user[0],
                "ime_preduzeca": user[7],
                "putanja_za_logo": user[8]
            },
            "korisnik": {
                "username": user[1]
            },
            "zakazano": [zakazano]
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_podesanja_data():
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        with app.app_context():
            # Dohvatanje korisnika
            user_query = text("SELECT id, username, email, brTel, rola, paket, zaposlen_u, ime_preduzeca, putanja_za_logo, opis, paket_limits, cenovnik, radnoVreme, id_kateg FROM users WHERE id = :id")
            user = db.session.execute(user_query, {'id': current_user_id}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            user_rola = user[4]  # rola
            
            # Dohvatanje svih kategorija
            kategorije_query = text("SELECT id, kategorija FROM kategorije ORDER BY kategorija")
            kategorije_results = db.session.execute(kategorije_query).fetchall()
            
            kategorije_list = []
            for kat in kategorije_results:
                kategorije_list.append({
                    "id": kat[0],
                    "kategorija": kat[1]
                })
            
            # Lista za preduzeca
            preduzeca = []
            
            # LOGIKA - Samo vlasnici imaju preduzeca
            if user_rola == 1:  # Vlasnik
                # Pronalaženje svih preduzeca gde je korisnik vlasnik
                preduzeca_query = text("""
                    SELECT id, ime, adresa, radno_vreme, cenovnik, overlapLimit FROM preduzeca 
                    WHERE vlasnik = :vlasnik_id
                    ORDER BY id
                """)
                preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik_id': current_user_id}).fetchall()
                
                for preduzece in preduzeca_results:
                    preduzece_id = preduzece[0]
                    
                    # Dohvatanje zaposlenih za ovo preduzeće
                    zaposleni_query = text("""
                        SELECT id, username, email, brTel, rola FROM users 
                        WHERE zaposlen_u = :preduzece_id
                    """)
                    zaposleni_results = db.session.execute(zaposleni_query, {'preduzece_id': preduzece_id}).fetchall()
                    
                    zaposleni_list = []
                    for zaposleni in zaposleni_results:
                        zaposleni_list.append({
                            "id": zaposleni[0],
                            "ime": zaposleni[1],
                            "email": zaposleni[2],
                            "telefon": zaposleni[3],
                            "rola": zaposleni[4]
                        })
                    
                    preduzeca.append({
                        "id": preduzece_id,
                        "ime": preduzece[1],
                        "adresa": preduzece[2],
                        "radno_vreme": preduzece[3] if isinstance(preduzece[3], dict) else (json.loads(preduzece[3]) if isinstance(preduzece[3], str) else {}),
                        "cenovnik": preduzece[4] if preduzece[4] else [],
                        "overlapLimit": preduzece[5],
                        "zaposleni": zaposleni_list
                    })
        
        return jsonify({
            "success": True,
            "korisnik": {
                "id": user[0],
                "username": user[1],
                "email": user[2],
                "brTel": user[3],
                "rola": user[4],
                "paket": user[5],
                "zaposlen_u": user[6],
                "ime_preduzeca": user[7],
                "putanja_za_logo": user[8],
                "opis": user[9],
                "paket_limits": user[10],
                "cenovnik": user[11],
                "radnoVreme": user[12],
                "id_kateg": user[13]
            },
            "kategorije": kategorije_list,
            "preduzeca": preduzeca
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    


