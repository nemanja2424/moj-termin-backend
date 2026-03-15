from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json


tests_bp = Blueprint("tests", __name__)


@tests_bp.route('/test', methods=['GET'])
def auth_test():
    try:
        from app import db, app
        
        with app.app_context():
            result = db.session.execute(text("SELECT * FROM users;")).fetchone()

        return jsonify({
            "success": True,
            "data": result[0] if result else None
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@tests_bp.route('/dodaj_korisnika', methods=['POST'])
def dodajKorisnika():
    try:
        from app import db
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data.get('username') or not data.get('email'):
            return jsonify({
                "success": False,
                "error": "Username i email su obavezni"
            }), 400
        
        # SQL INSERT query sa %s
        query = text("""
            INSERT INTO users (
                username, email, brTel, password, rola, paket, 
                zaposlen_u, istek_pretplate, ime_preduzeca, putanja_za_logo,
                radnoVreme, cenovnik, forma, ai_info, opis, paket_limits
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, username, email, created_at
        """)
        
        # Vrednosti u istom redosledu kao u query-ju
        values = [
            data.get('username'),
            data.get('email'),
            data.get('brTel'),
            data.get('password'),
            data.get('rola', 0),
            data.get('paket', 'Personalni'),
            data.get('zaposlen_u', 0),
            data.get('istek_pretplate'),
            data.get('ime_preduzeca'),
            data.get('putanja_za_logo', '/Images/logo.webp'),
            json.dumps(data.get('radnoVreme', {})),
            json.dumps(data.get('cenovnik', {})),
            json.dumps(data.get('forma', {})),
            json.dumps(data.get('ai_info', {})),
            data.get('opis', ''),
            json.dumps(data.get('paket_limits', {}))
        ]
        
        # Izvršavanje queryja
        result = db.session.execute(query, values).fetchone()
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Korisnik je uspešno dodat",
            "data": {
                "id": result[0],
                "username": result[1],
                "email": result[2],
                "created_at": str(result[3])
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    




