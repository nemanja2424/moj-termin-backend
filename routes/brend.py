from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from flask_jwt_extended import jwt_required, get_jwt_identity


brend_bp = Blueprint("brend", __name__)


@brend_bp.route('/<int:user_id>', methods=['PATCH'])
@jwt_required()
def update_brend(user_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Provera da li korisnik pokušava da izmeni podatke drugome
        if current_user_id != user_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da menjate brend drugom korisniku"
            }), 403
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznog polja
        if not data.get('forma'):
            return jsonify({
                "success": False,
                "error": "Forma je obavezna"
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
            
            # Ažuriranje forma polja
            forma_json = json.dumps(data.get('forma'))
            
            update_query = text("""
                UPDATE users SET forma = :forma
                WHERE id = :id
                RETURNING id, forma
            """)
            
            result = db.session.execute(update_query, {
                'forma': forma_json,
                'id': user_id
            }).fetchone()
            db.session.commit()
            
            # Parsing forma polja
            forma = result[1]
            if isinstance(forma, str):
                forma = json.loads(forma) if forma else {}
        
        return jsonify({
            "success": True,
            "message": "Brend je uspešno ažuriran",
            "forma": forma
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500