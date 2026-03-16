from flask import Blueprint, jsonify, request
from sqlalchemy import text
import json
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


podesavnja_bp = Blueprint("podesavanja", __name__)


@podesavnja_bp.route('/dodaj-lokaciju/<int:vlasnik_id>', methods=['POST'])
@jwt_required()
def dodaj_lokaciju(vlasnik_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Verifikovanje da li korisnik pokušava da doda lokaciju za sebe
        if current_user_id != vlasnik_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da dodate lokaciju za drugog korisnika"
            }), 403
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data.get('imeLokacije') or not data.get('adresa'):
            return jsonify({
                "success": False,
                "error": "Ime lokacije i adresa su obavezni"
            }), 400
        
        with app.app_context():
            # SQL INSERT query
            insert_query = text("""
                INSERT INTO preduzeca (
                    vlasnik, ime, adresa, radno_vreme, cenovnik, created_at
                ) VALUES (
                    :vlasnik, :ime, :adresa, :radno_vreme, :cenovnik, :created_at
                )
                RETURNING id, vlasnik, ime, adresa, radno_vreme, cenovnik, created_at
            """)
            
            params = {
                'vlasnik': vlasnik_id,
                'ime': data.get('imeLokacije', '').strip(),
                'adresa': data.get('adresa', '').strip(),
                'radno_vreme': json.dumps(data.get('radno_vreme', {})),
                'cenovnik': json.dumps(data.get('cenovnik', [])),
                'created_at': datetime.utcnow()
            }
            
            # Izvršavanje insertovanja
            result = db.session.execute(insert_query, params).fetchone()
            db.session.commit()
        
        return jsonify({
            "success": True,
            "preduzeca": {
                "id": result[0],
                "vlasnik": result[1],
                "ime": result[2],
                "adresa": result[3],
                "radno_vreme": result[4] if result[4] else {},
                "cenovnik": result[5] if result[5] else [],
                "created_at": str(result[6])
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@podesavnja_bp.route('/cenovnik', methods=['PATCH'])
@jwt_required()
def update_cenovnik():
    try:
        from app import db, app

        currentUserId = int(get_jwt_identity())

        data = request.json

        if not data.get('tip') or not data.get('cenovnik'):
            return jsonify({
                "message": "Tip i cenovnik su obavezni."
            })
        
        userId = data.get('userId')

        if currentUserId != int(userId):
            return jsonify({"message": "Nemate dozvolu da menjate tuđe cenovnike."})
        
        tip = data.get('tip')
        cenovnik = data.get('cenovnik')
        cenovnikJSON = json.dumps(cenovnik)

        with app.app_context():
            if tip == "default":
                query = text("""
                    UPDATE users SET cenovnik = :cenovnik
                    WHERE id = :userId
                """)

                params = {
                    'cenovnik': cenovnikJSON,
                    'userId': userId
                }

            else:
                # Ažuriranje cenovnika za konkretnu lokaciju (preduzece)
                try:
                    lokacija_id = int(tip)
                except (ValueError, TypeError):
                    return jsonify({
                        "success": False,
                        "message": "Tip mora biti validan broj lokacije"
                    }), 400
                
                query = text("""
                    UPDATE preduzeca SET cenovnik = :cenovnik
                    WHERE id = :lokacija_id
                """)

                params = {
                    'cenovnik': cenovnikJSON,
                    'lokacija_id': lokacija_id
                }

            patchResult = db.session.execute(query, params)
            db.session.commit()

            

            return jsonify({"message": "Success"})


    except ValueError as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": "Nevalidna vrednost za ID"
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@podesavnja_bp.route('/izmeni-lokaciju/<int:idLokacije>', methods=['PATCH'])
@jwt_required()
def izmeni_lokaciju(idLokacije):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data.get('ime') or not data.get('adresa'):
            return jsonify({
                "success": False,
                "error": "Ime i adresa su obavezni"
            }), 400
        
        with app.app_context():
            # Proveravanje da li lokacija postoji i da je vlasnik current user
            check_query = text("SELECT id, vlasnik FROM preduzeca WHERE id = :id")
            lokacija = db.session.execute(check_query, {'id': idLokacije}).fetchone()
            
            if not lokacija:
                return jsonify({
                    "success": False,
                    "error": "Lokacija nije pronađena"
                }), 404
            
            if lokacija[1] != current_user_id:
                return jsonify({
                    "success": False,
                    "error": "Nemate dozvolu da menjate ovu lokaciju"
                }), 403
            
            # SQL UPDATE query
            update_query = text("""
                UPDATE preduzeca 
                SET ime = :ime, adresa = :adresa, overlapLimit = :overlapLimit
                WHERE id = :id
                RETURNING id, vlasnik, ime, adresa, radno_vreme, cenovnik, overlapLimit
            """)
            
            params = {
                'id': idLokacije,
                'ime': data.get('ime', '').strip(),
                'adresa': data.get('adresa', '').strip(),
                'overlapLimit': data.get('overlapLimit', 1)
            }
            
            result = db.session.execute(update_query, params).fetchone()
            db.session.commit()
        
        return jsonify({
            "success": True,
            "lokacija": {
                "id": result[0],
                "vlasnik": result[1],
                "ime": result[2],
                "adresa": result[3],
                "radno_vreme": result[4] if result[4] else {},
                "cenovnik": result[5] if result[5] else [],
                "overlapLimit": result[6]
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@podesavnja_bp.route('/nova-lozinka/<int:user_id>', methods=['PATCH'])
@jwt_required()
def nova_lozinka(user_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Provera da li korisnik pokušava da promeni lozinku drugome
        if current_user_id != user_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da promenite lozinku drugom korisniku"
            }), 403
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Validacija obaveznih polja
        if not data.get('currentPass') or not data.get('newPass'):
            return jsonify({
                "success": False,
                "error": "Trenutna i nova lozinka su obavezne"
            }), 400
        
        # Validacija dužine nove lozinke
        if len(data.get('newPass', '')) < 6:
            return jsonify({
                "success": False,
                "error": "Nova lozinka mora imati najmanje 6 karaktera"
            }), 400
        
        with app.app_context():
            # Dohvatanje korisnika
            user_query = text("SELECT id, password FROM users WHERE id = :id")
            user = db.session.execute(user_query, {'id': user_id}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Provera trenutne lozinke
            if not check_password_hash(user[1], data.get('currentPass')):
                return jsonify({
                    "success": False,
                    "error": "Netačna trenutna lozinka"
                }), 401
            
            # Hešovanje nove lozinke
            hashed_new_password = generate_password_hash(data.get('newPass'))
            
            # Ažuriranje lozinke
            update_query = text("""
                UPDATE users SET password = :password
                WHERE id = :id
            """)
            
            db.session.execute(update_query, {
                'password': hashed_new_password,
                'id': user_id
            })
            db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Lozinka je uspešno promenjena"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@podesavnja_bp.route('/user/<int:user_id>', methods=['PATCH'])
@jwt_required()
def update_user(user_id):
    try:
        from app import db, app
        
        # Dohvatanje ID-a iz JWT tokena
        current_user_id = int(get_jwt_identity())
        
        # Provera da li korisnik pokušava da izmeni podatke drugome
        if current_user_id != user_id:
            return jsonify({
                "success": False,
                "error": "Nemate dozvolu da menjate podatke drugom korisniku"
            }), 403
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        with app.app_context():
            # Dohvatanje korisnika
            user_query = text("SELECT id FROM users WHERE id = :id")
            user = db.session.execute(user_query, {'id': user_id}).fetchone()
            
            if not user:
                return jsonify({
                    "success": False,
                    "error": "Korisnik nije pronađen"
                }), 404
            
            # Ažuriranje korisničkih podataka
            update_query = text("""
                UPDATE users 
                SET username = :username, email = :email, brTel = :brTel, 
                    ime_preduzeca = :ime_preduzeca, opis = :opis
                WHERE id = :id
                RETURNING id, username, email, brTel, ime_preduzeca, opis
            """)
            
            params = {
                'id': user_id,
                'username': (data.get('username') or '').strip(),
                'email': (data.get('email') or '').strip(),
                'brTel': (data.get('brTel') or '').strip(),
                'ime_preduzeca': (data.get('ime_preduzeca') or '').strip(),
                'opis': (data.get('opis') or '').strip()
            }
            
            result = db.session.execute(update_query, params).fetchone()
            db.session.commit()
        
        return jsonify({
            "success": True,
            "korisnik": {
                "id": result[0],
                "username": result[1],
                "email": result[2],
                "brTel": result[3],
                "ime_preduzeca": result[4],
                "opis": result[5]
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@podesavnja_bp.route('/radno-vreme', methods=['PATCH'])
@jwt_required()
def update_radno_vreme():
    try:
        from app import db, app

        currentUserId = int(get_jwt_identity())

        data = request.json

        if not data.get('tip') or not data.get('vremena'):
            return jsonify({
                "message": "Tip i vremena su obavezni."
            })
        
        userId = data.get('userId')

        if currentUserId != int(userId):
            return jsonify({"message": "Nemate dozvolu da menjate tuđe radno vreme."})
        
        tip = data.get('tip')
        vremena = data.get('vremena')
        vremeJSON = json.dumps(vremena)

        with app.app_context():
            if tip == "default":
                query = text("""
                    UPDATE users SET radnoVreme = :radnoVreme
                    WHERE id = :userId
                """)

                params = {
                    'radnoVreme': vremeJSON,
                    'userId': userId
                }

            else:
                # Ažuriranje radnog vremena za konkretnu lokaciju (preduzece)
                try:
                    lokacija_id = int(tip)
                except (ValueError, TypeError):
                    return jsonify({
                        "success": False,
                        "message": "Tip mora biti validan broj lokacije"
                    }), 400
                
                query = text("""
                    UPDATE preduzeca SET radno_vreme = :radno_vreme
                    WHERE id = :lokacija_id
                """)

                params = {
                    'radno_vreme': vremeJSON,
                    'lokacija_id': lokacija_id
                }

            db.session.execute(query, params)
            db.session.commit()

            return jsonify({"message": "Success"})


    except ValueError as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": "Nevalidna vrednost za ID"
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
