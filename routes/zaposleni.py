from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash


zaposleni_bp = Blueprint("zaposleni", __name__)


@zaposleni_bp.route('/<int:vlasnik_id>', methods=['GET'])
@jwt_required()
def get_zaposleni(vlasnik_id):
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvatanje vlasnika
            vlasnik_query = text("""
                SELECT id, username, email, brTel, rola, paket, paket_limits 
                FROM users WHERE id = :id
            """)
            vlasnik_result = db.session.execute(vlasnik_query, {'id': vlasnik_id}).fetchone()
            
            if not vlasnik_result:
                return jsonify({
                    "success": False,
                    "error": "Vlasnik nije pronađen"
                }), 404
            
            # Dohvatanje svih preduzeca gde je ovaj vlasnik
            preduzeca_query = text("""
                SELECT id, ime, adresa 
                FROM preduzeca WHERE vlasnik = :vlasnik_id
                ORDER BY id
            """)
            preduzeca_results = db.session.execute(preduzeca_query, {'vlasnik_id': vlasnik_id}).fetchall()
            
            preduzeca_list = []
            korisnici_list = []
            
            # Za svako preduzeće, dohvati zaposlene
            for preduzece in preduzeca_results:
                preduzece_id = preduzece[0]
                
                preduzeca_list.append({
                    "id": preduzece_id,
                    "ime": preduzece[1],
                    "adresa": preduzece[2]
                })
                
                # Dohvatanje svih zaposlenih za ovo preduzeće (rola = 2)
                zaposleni_query = text("""
                    SELECT id, username, email, brTel, zaposlen_u 
                    FROM users 
                    WHERE zaposlen_u = :preduzece_id AND rola = 2
                    ORDER BY id
                """)
                zaposleni_results = db.session.execute(zaposleni_query, {'preduzece_id': preduzece_id}).fetchall()
                
                zaposleni_za_preduzeće = []
                for zaposleni in zaposleni_results:
                    zaposleni_za_preduzeće.append({
                        "id": zaposleni[0],
                        "username": zaposleni[1],
                        "email": zaposleni[2],
                        "brTel": zaposleni[3],
                        "zaposlen_u": zaposleni[4],
                        "preduzece": {
                            "ime": preduzece[1],
                            "adresa": preduzece[2]
                        }
                    })
                
                # Dodaj grupu zaposlenih za ovo preduzeće
                korisnici_list.append(zaposleni_za_preduzeće)
            
            # Prosledi paket_limits kao dict
            paket_limits = vlasnik_result[6]
            if isinstance(paket_limits, str):
                paket_limits = json.loads(paket_limits) if paket_limits else {}
            elif not isinstance(paket_limits, dict):
                paket_limits = {}
            
            vlasnik_info = {
                "id": vlasnik_result[0],
                "username": vlasnik_result[1],
                "email": vlasnik_result[2],
                "brTel": vlasnik_result[3],
                "rola": vlasnik_result[4],
                "paket": vlasnik_result[5],
                "paket_limits": paket_limits
            }
        
        return jsonify({
            "success": True,
            "korisnici": korisnici_list,
            "preduzeca": preduzeca_list,
            "vlasnik": vlasnik_info
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@zaposleni_bp.route('/novi/<int:vlasnik_id>', methods=['POST'])
@jwt_required()
def dodaj_zaposlenog(vlasnik_id):
    try:
        from app import db, app
        from datetime import datetime
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Verifikovanje da li korisnik pokušava da doda zaposlenog za sebe
        if current_user_id != vlasnik_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da dodate zaposlenog drugom korisniku"
            }), 403
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data.get('ime') or not data.get('regEmail') or not data.get('regPass'):
            return jsonify({
                "success": False,
                "error": "Ime, email i šifra su obavezni"
            }), 400
        
        with app.app_context():
            # Proveravanje da li email već postoji
            check_query = text("SELECT id FROM users WHERE email = :email")
            existing_user = db.session.execute(check_query, {'email': data.get('regEmail')}).fetchone()
            
            if existing_user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik sa ovim emailom već postoji"
                }), 400
            
            # Hešovanje šifre
            hashed_password = generate_password_hash(data.get('regPass'))
            
            # SQL INSERT query za novog zaposlenog
            insert_query = text("""
                INSERT INTO users (
                    username, email, brTel, password, rola, paket, 
                    zaposlen_u, istek_pretplate, ime_preduzeca, putanja_za_logo,
                    radnoVreme, cenovnik, forma, ai_info, opis, paket_limits,
                    created_at
                ) VALUES (
                    :username, :email, :brTel, :password, :rola, :paket,
                    :zaposlen_u, :istek_pretplate, :ime_preduzeca, :putanja_za_logo,
                    :radnoVreme, :cenovnik, :forma, :ai_info, :opis, :paket_limits,
                    :created_at
                )
                RETURNING id, username, email, brTel, rola, paket, zaposlen_u
            """)
            
            # Parametri
            params = {
                'username': data.get('ime'),
                'email': data.get('regEmail'),
                'brTel': data.get('brTel', ''),
                'password': hashed_password,
                'rola': 2,  # Zaposleni
                'paket': 'Personalni',
                'zaposlen_u': data.get('zaposlenU'),
                'istek_pretplate': None,
                'ime_preduzeca': None,
                'putanja_za_logo': '/Images/logo.webp',
                'radnoVreme': json.dumps({}),
                'cenovnik': json.dumps({}),
                'forma': json.dumps({}),
                'ai_info': json.dumps({}),
                'opis': '',
                'paket_limits': json.dumps({}),
                'created_at': datetime.utcnow()
            }
            
            # Izvršavanje insertovanja
            result = db.session.execute(insert_query, params).fetchone()
            db.session.commit()
            
            # Dohvatanje vlasnika sa svim podacima
            vlasnik_query = text("""
                SELECT id, username, email, brTel, rola, paket, zaposlen_u, 
                       ime_preduzeca, putanja_za_logo, opis, paket_limits, cenovnik, radnoVreme, forma, ai_info
                FROM users WHERE id = :id
            """)
            vlasnik_info = db.session.execute(vlasnik_query, {'id': vlasnik_id}).fetchone()
            
            if not vlasnik_info:
                return jsonify({
                    "success": False,
                    "error": "Vlasnik nije pronađen"
                }), 404
            
            # Parsing JSONB polja
            paket_limits = vlasnik_info[10]
            if isinstance(paket_limits, str):
                paket_limits = json.loads(paket_limits) if paket_limits else {}
            
            cenovnik = vlasnik_info[11]
            if not isinstance(cenovnik, list):
                cenovnik = []
            
            radnoVreme = vlasnik_info[12]
            if isinstance(radnoVreme, str):
                radnoVreme = json.loads(radnoVreme) if radnoVreme else {}
            
            forma = vlasnik_info[13]
            if isinstance(forma, str):
                forma = json.loads(forma) if forma else {}
            
            ai_info = vlasnik_info[14]
            if isinstance(ai_info, str):
                ai_info = json.loads(ai_info) if ai_info else {}
            
            return jsonify({
                "success": True,
                "message": "Zaposlenik uspešno dodan",
                "zaposlenik": {
                    "id": result[0],
                    "username": result[1],
                    "email": result[2],
                    "brTel": result[3],
                    "rola": result[4]
                },
                "vlasnik": {
                    "id": vlasnik_info[0],
                    "username": vlasnik_info[1],
                    "email": vlasnik_info[2],
                    "brTel": vlasnik_info[3],
                    "rola": vlasnik_info[4],
                    "paket": vlasnik_info[5],
                    "zaposlen_u": vlasnik_info[6],
                    "ime_preduzeca": vlasnik_info[7],
                    "putanja_za_logo": vlasnik_info[8],
                    "opis": vlasnik_info[9],
                    "paket_limits": paket_limits,
                    "cenovnik": cenovnik,
                    "radnoVreme": radnoVreme,
                    "forma": forma,
                    "ai_info": ai_info
                }
            }), 201
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    



@zaposleni_bp.route('/<int:zaposleni_id>', methods=['DELETE'])
@jwt_required()
def obrisi_zaposlenog(zaposleni_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        with app.app_context():
            # Dohvatanje zaposlenog
            employee_query = text("SELECT id, zaposlen_u FROM users WHERE id = :id")
            employee = db.session.execute(employee_query, {'id': zaposleni_id}).fetchone()
            
            if not employee:
                return jsonify({
                    "success": False,
                    "error": "Zaposleni nije pronađen"
                }), 404
            
            # Dohvatanje lokacije gde je zaposlen
            lokacija_id = employee[1]
            lokacija_query = text("SELECT id, vlasnik FROM preduzeca WHERE id = :id")
            lokacija = db.session.execute(lokacija_query, {'id': lokacija_id}).fetchone()
            
            if not lokacija:
                return jsonify({
                    "success": False,
                    "error": "Lokacija nije pronađena"
                }), 404
            
            # Provera da li je current_user_id vlasnik te lokacije
            if lokacija[1] != current_user_id:
                return jsonify({
                    "success": False,
                    "error": "Nemate dozvolu da obrišete ovog zaposlenog"
                }), 403
            
            # Brisanje zaposlenog
            delete_query = text("DELETE FROM users WHERE id = :id")
            db.session.execute(delete_query, {'id': zaposleni_id})
            db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Zaposleni je uspešno obrisan"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@zaposleni_bp.route('/izmena/<int:zaposleni_id>', methods=['PATCH'])
@jwt_required()
def izmeni_zaposlenog(zaposleni_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        with app.app_context():
            # Dohvatanje zaposlenog
            employee_query = text("SELECT id, zaposlen_u FROM users WHERE id = :id")
            employee = db.session.execute(employee_query, {'id': zaposleni_id}).fetchone()
            
            if not employee:
                return jsonify({
                    "success": False,
                    "error": "Zaposleni nije pronađen"
                }), 404
            
            # Dohvatanje lokacije gde je zaposlen
            lokacija_id = employee[1]
            lokacija_query = text("SELECT id, vlasnik FROM preduzeca WHERE id = :id")
            lokacija = db.session.execute(lokacija_query, {'id': lokacija_id}).fetchone()
            
            if not lokacija:
                return jsonify({
                    "success": False,
                    "error": "Lokacija nije pronađena"
                }), 404
            
            # Provera da li je current_user_id vlasnik te lokacije
            if lokacija[1] != current_user_id:
                return jsonify({
                    "success": False,
                    "error": "Nemate dozvolu da izmenite ovog zaposlenog"
                }), 403
            
            # Ažuriranje zaposlenog
            update_query = text("""
                UPDATE users 
                SET username = :username, email = :email, brTel = :brTel, zaposlen_u = :zaposlen_u
                WHERE id = :id
                RETURNING id, username, email, brTel, zaposlen_u
            """)
            
            params = {
                'id': zaposleni_id,
                'username': (data.get('username') or '').strip(),
                'email': (data.get('email') or '').strip(),
                'brTel': (data.get('brTel') or '').strip(),
                'zaposlen_u': data.get('zaposlen_u', lokacija_id)
            }
            
            result = db.session.execute(update_query, params).fetchone()
            db.session.commit()
        
        return jsonify({
            "success": True,
            "zaposlenik": {
                "id": result[0],
                "username": result[1],
                "email": result[2],
                "brTel": result[3],
                "zaposlen_u": result[4]
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@zaposleni_bp.route('/nova-lozinka/<int:zaposleni_id>', methods=['PATCH'])
@jwt_required()
def nova_lozinka_zaposlenog(zaposleni_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznog polja
        if not data.get('newPass'):
            return jsonify({
                "success": False,
                "error": "Nova lozinka je obavezna"
            }), 400
        
        # Validacija dužine nove lozinke
        if len(data.get('newPass', '')) < 6:
            return jsonify({
                "success": False,
                "error": "Nova lozinka mora imati najmanje 6 karaktera"
            }), 400
        
        with app.app_context():
            # Dohvatanje zaposlenog
            employee_query = text("SELECT id, zaposlen_u FROM users WHERE id = :id")
            employee = db.session.execute(employee_query, {'id': zaposleni_id}).fetchone()
            
            if not employee:
                return jsonify({
                    "success": False,
                    "error": "Zaposleni nije pronađen"
                }), 404
            
            # Dohvatanje lokacije gde je zaposlen
            lokacija_id = employee[1]
            lokacija_query = text("SELECT id, vlasnik FROM preduzeca WHERE id = :id")
            lokacija = db.session.execute(lokacija_query, {'id': lokacija_id}).fetchone()
            
            if not lokacija:
                return jsonify({
                    "success": False,
                    "error": "Lokacija nije pronađena"
                }), 404
            
            # Provera da li je current_user_id vlasnik te lokacije
            if lokacija[1] != current_user_id:
                return jsonify({
                    "success": False,
                    "error": "Nemate dozvolu da promenite lozinku ovom zaposlenom"
                }), 403
            
            # Hešovanje nove lozinke
            hashed_new_password = generate_password_hash(data.get('newPass'))
            
            # Ažuriranje lozinke
            update_query = text("""
                UPDATE users SET password = :password
                WHERE id = :id
            """)
            
            db.session.execute(update_query, {
                'password': hashed_new_password,
                'id': zaposleni_id
            })
            db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Lozinka zaposlenog je uspešno promenjena"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500