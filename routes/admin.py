from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity
from datetime import timedelta
from sqlalchemy import text
import os
import json
from dotenv import load_dotenv

load_dotenv()



admin_bp = Blueprint("admin", __name__)


def verify_admin_credentials(request_data):
    """
    Proverava admin kredencijale iz zahteva.
    Vraća True ako su kredencijali ispravni, False inače.
    """
    if not request_data:
        return False
    
    username = request_data.get('username')
    password = request_data.get('password')
    env_username = os.getenv('ADMIN_USERNAME')
    env_password = os.getenv('ADMIN_PWD')
    
    return username == env_username and password == env_password


# Test ruta
@admin_bp.route('/hello', methods=['GET'])
def hello():
    return jsonify({"message": "Zdravo ADMINE!"})


@admin_bp.route('/info/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_info(user_id):
    """
    Dohvata informacije o korisniku sa specificiranim ID-om.
    
    Vraća:
    - 200: Korisnikovi podaci (id, email, paket, ai_info, paket_limits)
    - 404: Korisnik nije pronađen
    - 500: Serverska greška
    """
    try:
        from app import db
        
        query = text("""
            SELECT id, email, paket, ai_info, paket_limits
            FROM users
            WHERE id = :user_id
        """)
        
        result = db.session.execute(query, {'user_id': user_id}).fetchone()
        
        if not result:
            return jsonify({'error': 'Korisnik nije pronađen'}), 404
        
        return jsonify({
            'status': 200,
            'user': {
                'id': result[0],
                'email': result[1],
                'paket': result[2],
                'ai_info': result[3] if result[3] else {},
                'paket_limits': result[4] if result[4] else {}
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Greška u /api/admin/info/{user_id}: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@admin_bp.route('/paket_limits', methods=['PATCH'])
def update_paket_limits():
    """
    Ažurira paket_limits polje za korisnika.
    
    Očekuje:
    - username: string (admin kredencijali)
    - password: string (admin kredencijali)
    - id: int (obavezno ako se ne prosleđuje email)
    - email: string (obavezno ako se ne prosleđuje id)
    - paket_limits: dict/object (JSONB)
    
    Vraća:
    - 200: Uspešna ažuriranja
    - 400: Validacijska greška ili neispravni kredencijali
    - 404: Korisnik nije pronađen
    """
    try:
        from app import db
        
        data = request.json
        
        if not data:
            return jsonify({'error': 'Nedostaje JSON u zahtevу'}), 400
        
        # Provera admin kredencijala
        if not verify_admin_credentials(data):
            return jsonify({'error': 'Neispravni admin kredencijali'}), 401
        
        user_id = data.get('id')
        email = data.get('email')
        paket_limits = data.get('paket_limits')
        
        # Validacija paket_limits-a
        if paket_limits is None:
            return jsonify({'error': 'paket_limits je obavezan'}), 400
        
        if not isinstance(paket_limits, dict):
            return jsonify({'error': 'paket_limits mora biti JSON objekat'}), 400
        
        # Određivanje po čemu ćemo pretraživati
        if user_id and user_id != 0:
            # Koristi ID
            query = text("""
                UPDATE users
                SET paket_limits = :paket_limits
                WHERE id = :user_id
                RETURNING id, email, paket_limits
            """)
            params = {
                'paket_limits': json.dumps(paket_limits),
                'user_id': user_id
            }
            result = db.session.execute(query, params).fetchone()
            
        elif email:
            # Koristi email
            query = text("""
                UPDATE users
                SET paket_limits = :paket_limits
                WHERE email = :email
                RETURNING id, email, paket_limits
            """)
            params = {
                'paket_limits': json.dumps(paket_limits),
                'email': email
            }
            result = db.session.execute(query, params).fetchone()
        else:
            return jsonify({'error': 'Nedostaje id ili email'}), 400
        
        # Proveravamo da li je korisnik pronađen
        if not result:
            return jsonify({'error': 'Korisnik nije pronađen'}), 404
        
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'message': 'paket_limits uspešno ažuriran',
            'user_id': result[0],
            'email': result[1],
            'paket_limits': result[2] if result[2] else {}
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Greška u /api/admin/paket_limits: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@admin_bp.route('/ai_info', methods=['PATCH'])
def update_ai_info():
    """
    Ažurira ai_info polje za korisnika.
    
    Očekuje:
    - username: string (admin kredencijali)
    - password: string (admin kredencijali)
    - id: int (obavezno ako se ne prosleđuje email)
    - email: string (obavezno ako se ne prosleđuje id)
    - ai_info: dict/object (JSONB)
    
    Vraća:
    - 200: Uspešna ažuriranja
    - 400: Validacijska greška ili neispravni kredencijali
    - 404: Korisnik nije pronađen
    """
    try:
        from app import db
        
        data = request.json
        
        if not data:
            return jsonify({'error': 'Nedostaje JSON u zahtevу'}), 400
        
        # Provera admin kredencijala
        if not verify_admin_credentials(data):
            return jsonify({'error': 'Neispravni admin kredencijali'}), 401
        
        user_id = data.get('id')
        email = data.get('email')
        ai_info = data.get('ai_info')
        
        # Validacija ai_info-a
        if ai_info is None:
            return jsonify({'error': 'ai_info je obavezan'}), 400
        
        if not isinstance(ai_info, dict):
            return jsonify({'error': 'ai_info mora biti JSON objekat'}), 400
        
        # Određivanje po čemu ćemo pretraživati
        if user_id and user_id != 0:
            # Koristi ID
            query = text("""
                UPDATE users
                SET ai_info = :ai_info
                WHERE id = :user_id
                RETURNING id, email, ai_info
            """)
            params = {
                'ai_info': json.dumps(ai_info),
                'user_id': user_id
            }
            result = db.session.execute(query, params).fetchone()
            
        elif email:
            # Koristi email
            query = text("""
                UPDATE users
                SET ai_info = :ai_info
                WHERE email = :email
                RETURNING id, email, ai_info
            """)
            params = {
                'ai_info': json.dumps(ai_info),
                'email': email
            }
            result = db.session.execute(query, params).fetchone()
        else:
            return jsonify({'error': 'Nedostaje id ili email'}), 400
        
        # Proveravamo da li je korisnik pronađen
        if not result:
            return jsonify({'error': 'Korisnik nije pronađen'}), 404
        
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'message': 'ai_info uspešno ažuriran',
            'user_id': result[0],
            'email': result[1],
            'ai_info': result[2] if result[2] else {}
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Greška u /api/admin/ai_info: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@admin_bp.route('/paket', methods=['PATCH'])
def update_paket():
    """
    Ažurira paket polje za korisnika.
    
    Očekuje:
    - username: string (admin kredencijali)
    - password: string (admin kredencijali)
    - id: int (obavezno ako se ne prosleđuje email)
    - email: string (obavezno ako se ne prosleđuje id)
    - paket: string (obavezno)
    
    Vraća:
    - 200: Uspešna ažuriranja
    - 400: Validacijska greška ili neispravni kredencijali
    - 404: Korisnik nije pronađen
    """
    try:
        from app import db
        
        data = request.json
        
        if not data:
            return jsonify({'error': 'Nedostaje JSON u zahtevу'}), 400
        
        # Provera admin kredencijala
        if not verify_admin_credentials(data):
            return jsonify({'error': 'Neispravni admin kredencijali'}), 401
        
        user_id = data.get('id')
        email = data.get('email')
        paket = data.get('paket')
        
        # Validacija paket-a
        if paket is None or paket == '':
            return jsonify({'error': 'paket je obavezan'}), 400
        
        if not isinstance(paket, str):
            return jsonify({'error': 'paket mora biti string'}), 400
        
        # Određivanje po čemu ćemo pretraživati
        if user_id and user_id != 0:
            # Koristi ID
            query = text("""
                UPDATE users
                SET paket = :paket
                WHERE id = :user_id
                RETURNING id, email, paket
            """)
            params = {
                'paket': paket,
                'user_id': user_id
            }
            result = db.session.execute(query, params).fetchone()
            
        elif email:
            # Koristi email
            query = text("""
                UPDATE users
                SET paket = :paket
                WHERE email = :email
                RETURNING id, email, paket
            """)
            params = {
                'paket': paket,
                'email': email
            }
            result = db.session.execute(query, params).fetchone()
        else:
            return jsonify({'error': 'Nedostaje id ili email'}), 400
        
        # Proveravamo da li je korisnik pronađen
        if not result:
            return jsonify({'error': 'Korisnik nije pronađen'}), 404
        
        db.session.commit()
        
        return jsonify({
            'status': 200,
            'message': 'paket uspešno ažuriran',
            'user_id': result[0],
            'email': result[1],
            'paket': result[2]
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Greška u /api/admin/paket: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@admin_bp.route('/ai_usage', methods=['GET'])
def get_ai_usage():
    """
    Dohvata AI usage statistiku iz ai/ai_usage/sumUsage.json fajla.
    
    Vraća:
    - 200: sum objekat sa total_token_usage, entry_token_usage, generated_token_usage, total_req
    - 404: Fajl nije pronađen
    - 500: Serverska greška
    """
    try:
        # Učitaj sumUsage.json fajl
        usage_file_path = os.path.join(
            os.path.dirname(__file__), 
            '..', 'ai', 'ai_usage', 'sumUsage.json'
        )
        
        if not os.path.exists(usage_file_path):
            return jsonify({'error': 'Fajl sa AI usage statistikom nije pronađen'}), 404
        
        with open(usage_file_path, 'r', encoding='utf-8') as f:
            usage_data = json.load(f)
        
        # Vrati samo sum objekat
        return jsonify({
            'sum': usage_data.get('sum', {})
        }), 200
        
    except json.JSONDecodeError as e:
        print(f"❌ Greška pri parsiranju JSON fajla: {str(e)}")
        return jsonify({
            'status': 500,
            'error': 'Greška pri čitanju AI usage podataka'
        }), 500
    except Exception as e:
        print(f"❌ Greška u /api/admin/ai_usage: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@admin_bp.route('/ai_usage/history', methods=['GET'])
def get_ai_usage_history():
    """
    Dohvata AI usage istoriju iz ai/ai_usage/sumUsage.json fajla.
    
    Vraća:
    - 200: history niz sa svim zahtjevima
    - 404: Fajl nije pronađen
    - 500: Serverska greška
    """
    try:
        # Učitaj sumUsage.json fajl
        usage_file_path = os.path.join(
            os.path.dirname(__file__), 
            '..', 'ai', 'ai_usage', 'sumUsage.json'
        )
        
        if not os.path.exists(usage_file_path):
            return jsonify({'error': 'Fajl sa AI usage statistikom nije pronađen'}), 404
        
        with open(usage_file_path, 'r', encoding='utf-8') as f:
            usage_data = json.load(f)
        
        # Vrati samo history niz
        return jsonify({
            'history': usage_data.get('history', [])
        }), 200
        
    except json.JSONDecodeError as e:
        print(f"❌ Greška pri parsiranju JSON fajla: {str(e)}")
        return jsonify({
            'status': 500,
            'error': 'Greška pri čitanju AI usage podataka'
        }), 500
    except Exception as e:
        print(f"❌ Greška u /api/admin/ai_usage/history: {str(e)}")
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


