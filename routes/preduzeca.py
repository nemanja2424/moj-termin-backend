from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json


preduzeca_bp = Blueprint("preduzeca", __name__)


@preduzeca_bp.route('/get', methods=['GET'])
def get_preduzeca_list():
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvatanje vlasnika sa njihovim podacima
            # Sortiranje: prvo sponzorisani (koji imaju tekst), zatim ostali
            query = text("""
                SELECT id, ime_preduzeca, putanja_za_logo, opis, id_kateg, sponzorisano
                FROM users
                WHERE rola = 1
                AND ime_preduzeca IS NOT NULL
                AND ime_preduzeca <> ''
                ORDER BY 
                    CASE WHEN sponzorisano IS NOT NULL AND sponzorisano <> '' THEN 0 ELSE 1 END,
                    id;
            """)
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