from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json


preduzeca_bp = Blueprint("preduzeca", __name__)


@preduzeca_bp.route('/get', methods=['GET'])
def get_preduzeca_list():
    try:
        from app import db, app
        
        # Dohvatanje opcionalnog query parametra za filtriranje po gradu
        grad_id = request.args.get('grad_id', type=int)
        
        with app.app_context():
            # Pronalaženje svih korisnika (vlasnika) koji imaju preduzeća
            # Ako je grad_id prosleđen, prikazujem samo one koji imaju preduzeće u tom gradu
            base_query = """
                SELECT DISTINCT
                    u.id, 
                    u.ime_preduzeca, 
                    u.putanja_za_logo, 
                    u.opis, 
                    u.id_kateg, 
                    u.sponzorisano,
                    CASE WHEN u.sponzorisano IS NOT NULL AND u.sponzorisano <> '' THEN 0 ELSE 1 END as sort_priority
                FROM users u
                INNER JOIN preduzeca p ON u.id = p.vlasnik
                WHERE u.rola = 1
                AND u.ime_preduzeca IS NOT NULL
                AND u.ime_preduzeca <> ''
            """
            
            # Dodaj uslov za grad ako je prosleđen
            if grad_id:
                base_query += f" AND p.grad_id = {grad_id}"
            
            base_query += """
                ORDER BY sort_priority, u.id
            """
            
            query = text(base_query)
            results = db.session.execute(query).fetchall()
            
            preduzeca_list = []
            for row in results:
                preduzeca_list.append({
                    "id": row[0],
                    "ime_preduzeca": row[1],
                    "putanja_za_logo": row[2],
                    "opis": row[3],
                    "id_kateg": row[4],
                    "sponzorisano": row[5]
                })
            
            # Dohvatanje svih kategorija
            kategorije_query = text("SELECT id, kategorija FROM kategorije ORDER BY kategorija")
            kategorije_results = db.session.execute(kategorije_query).fetchall()
            
            kategorije_list = []
            for kat in kategorije_results:
                kategorije_list.append({
                    "id": kat[0],
                    "kategorija": kat[1]
                })
            
            return jsonify({
                "success": True,
                "preduzeca": preduzeca_list,
                "kategorije": kategorije_list
            }), 200
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500