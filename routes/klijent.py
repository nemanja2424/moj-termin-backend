from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import text
import json
from werkzeug.security import generate_password_hash, check_password_hash

klijent_bp = Blueprint('klijent', __name__)


@klijent_bp.route('/<int:client_id>', methods=['GET'])
@jwt_required
def getKlijentInfo(client_id):
    """
    Vraća informacije o klijentu i sve termine koje je zakazao.
    GET /api/klijent/{id}
    
    Response:
    {
        "status": 200,
        "klijent": {
            "id": int,
            "username": string,
            "email": string,
            "brTel": string,
            "created_at": string (ISO format)
        },
        "termini": [
            {
                "id": int,
                "ime_firme": int,
                "ime": string,
                "email": string,
                "telefon": string,
                "datum_rezervacije": string (YYYY-MM-DD),
                "vreme_rezervacije": string,
                "usluga": object,
                "opis": string,
                "potvrdio": int or null,
                "otkazano": boolean,
                "created_at": string (ISO format),
                "token": string
            }
        ],
        "ukupno_termina": int
    }
    """
    try:
        from app import db, app
        
        with app.app_context():
            # 1. Dohvati podatke o klijentu
            user_query = text("""
                SELECT id, username, email, brTel, created_at
                FROM users
                WHERE id = :id
            """)
            user_result = db.session.execute(user_query, {'id': client_id}).fetchone()
            
            if not user_result:
                return jsonify({
                    'status': 404,
                    'error': 'Klijent nije pronađen'
                }), 404
            
            user_id, username, email, brTel, created_at = user_result
            
            # 2. Dohvati sve termine koje je klijent zakazao (sa informacijama o preduzeću)
            zakazivanja_query = text("""
                SELECT z.id, z.ime_firme, z.ime, z.email, z.telefon, z.datum_rezervacije, 
                       z.vreme_rezervacije, z.usluga, z.opis, z.potvrdio, z.otkazano, z.created_at, z.token,
                       p.ime, p.adresa, p.vlasnik
                FROM zakazivanja z
                JOIN preduzeca p ON z.ime_firme = p.id
                WHERE z.zakazivac_id = :zakazivac_id
                ORDER BY z.created_at DESC
            """)
            zakazivanja_results = db.session.execute(zakazivanja_query, {'zakazivac_id': client_id}).fetchall()
            
            # Konvertuj termine u listu rečnika
            termini = []
            for zakaz in zakazivanja_results:
                # Handluj usluga polje - može biti string ili dict
                usluga = zakaz[7]
                if isinstance(usluga, str):
                    usluga = json.loads(usluga) if usluga else {}
                elif not isinstance(usluga, dict):
                    usluga = {}
                
                termini.append({
                    'id': zakaz[0],
                    'preduzece': {
                        'id': zakaz[1],
                        'ime': zakaz[13],
                        'adresa': zakaz[14],
                        'vlasnik_id': zakaz[15]
                    },
                    'ime': zakaz[2],
                    'email': zakaz[3],
                    'telefon': zakaz[4],
                    'datum_rezervacije': str(zakaz[5]),
                    'vreme_rezervacije': zakaz[6],
                    'usluga': usluga,
                    'opis': zakaz[8],
                    'potvrdio': zakaz[9],
                    'otkazano': zakaz[10],
                    'created_at': str(zakaz[11]),
                    'token': zakaz[12]
                })
            
            # 3. Vrati podatke o klijentu i sve njegove termine
            return jsonify({
                'status': 200,
                'klijent': {
                    'id': user_id,
                    'username': username,
                    'email': email,
                    'brTel': brTel,
                    'created_at': str(created_at)
                },
                'termini': termini,
                'ukupno_termina': len(termini)
            }), 200
    
    except Exception as e:
        print(f"❌ Greška u /api/klijent/{client_id}: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@klijent_bp.route('/<int:client_id>', methods=['PATCH'])
@jwt_required
def updateKlijentInfo(client_id):
    """
    Ažurira informacije o klijentu (username, email, brTel).
    PATCH /api/klijent/{id}
    
    Request body:
    {
        "username": string (optional),
        "email": string (optional),
        "brTel": string (optional)
    }
    """
    try:
        from app import db, app
        
        data = request.get_json() or {}
        
        # Validacija - bar jedno polje mora biti dostavljeno
        if not data or not any(key in data for key in ['username', 'email', 'brTel']):
            return jsonify({
                'status': 400,
                'error': 'Bar jedno polje (username, email ili brTel) je obavezno'
            }), 400
        
        with app.app_context():
            with db.session.begin():
                # 1. Pronađi klijenta
                user_query = text("SELECT id FROM users WHERE id = :id")
                user_result = db.session.execute(user_query, {'id': client_id}).fetchone()
                
                if not user_result:
                    return jsonify({
                        'status': 404,
                        'error': 'Klijent nije pronađen'
                    }), 404
                
                # 2. Pripremi update vrednosti
                update_fields = []
                params = {'id': client_id}
                
                if 'username' in data and data['username']:
                    update_fields.append('username = :username')
                    params['username'] = data['username']
                
                if 'email' in data and data['email']:
                    update_fields.append('email = :email')
                    params['email'] = data['email']
                
                if 'brTel' in data and data['brTel']:
                    update_fields.append('brTel = :brTel')
                    params['brTel'] = data['brTel']
                
                # 3. Izvršavanje update-a
                update_query = text(f"""
                    UPDATE users
                    SET {', '.join(update_fields)}
                    WHERE id = :id
                    RETURNING id, username, email, brTel, created_at
                """)
                
                result = db.session.execute(update_query, params).fetchone()
                
                if not result:
                    return jsonify({
                        'status': 404,
                        'error': 'Greška pri ažuriranju'
                    }), 404
                
                user_id, username, email, brTel, created_at = result
                
                # 4. Vrati update-ovane podatke
                return jsonify({
                    'status': 200,
                    'message': 'Klijent uspešno ažuriran',
                    'klijent': {
                        'id': user_id,
                        'username': username,
                        'email': email,
                        'brTel': brTel,
                        'created_at': str(created_at)
                    }
                }), 200
    
    except Exception as e:
        print(f"❌ Greška u PATCH /api/klijent/{client_id}: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@klijent_bp.route('/<int:client_id>/lozinka', methods=['PATCH'])
@jwt_required
def updateKlijentLozinka(client_id):
    """
    Ažurira lozinku klijenta.
    PATCH /api/klijent/{id}/lozinka
    
    Request body:
    {
        "stara_lozinka": string (required),
        "nova_lozinka": string (required)
    }
    """
    try:
        from app import db, app
        
        data = request.get_json() or {}
        
        # Validacija obaveznih polja
        if not data.get('stara_lozinka'):
            return jsonify({
                'status': 400,
                'error': 'Stara lozinka je obavezna'
            }), 400
        
        if not data.get('nova_lozinka'):
            return jsonify({
                'status': 400,
                'error': 'Nova lozinka je obavezna'
            }), 400
        
        # Validacija dužine nove lozinke
        if len(data.get('nova_lozinka', '')) < 6:
            return jsonify({
                'status': 400,
                'error': 'Nova lozinka mora biti najmanje 6 karaktera'
            }), 400
        
        with app.app_context():
            with db.session.begin():
                # 1. Pronađi klijenta i dohvati trenutnu lozinku
                user_query = text("SELECT id, password FROM users WHERE id = :id")
                user_result = db.session.execute(user_query, {'id': client_id}).fetchone()
                
                if not user_result:
                    return jsonify({
                        'status': 404,
                        'error': 'Klijent nije pronađen'
                    }), 404
                
                user_id, current_password_hash = user_result
                
                # 2. Verifikuj staru lozinku
                if not check_password_hash(current_password_hash, data.get('stara_lozinka')):
                    return jsonify({
                        'status': 401,
                        'error': 'Stara lozinka nije tačna'
                    }), 401
                
                # 3. Hashuraj novu lozinku
                nova_lozinka_hash = generate_password_hash(data.get('nova_lozinka'))
                
                # 4. Updateuj lozinku
                update_query = text("""
                    UPDATE users
                    SET password = :password
                    WHERE id = :id
                    RETURNING id, username, email
                """)
                
                result = db.session.execute(update_query, {
                    'password': nova_lozinka_hash,
                    'id': client_id
                }).fetchone()
                
                if not result:
                    return jsonify({
                        'status': 404,
                        'error': 'Greška pri ažuriranju lozinke'
                    }), 404
                
                user_id, username, email = result
                
                # 5. Vrati potvrdu
                return jsonify({
                    'status': 200,
                    'message': 'Lozinka uspešno ažurirana',
                    'user': {
                        'id': user_id,
                        'username': username,
                        'email': email
                    }
                }), 200
    
    except Exception as e:
        print(f"❌ Greška u PATCH /api/klijent/{client_id}/lozinka: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500
