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
    



@zakazivanja_bp.route('/<string:token>/xrdcytfuvgbhjnkjhbgvyftucdyrxtsezxrdcytfuvy', methods=['PATCH'])
def potvrdi_termin_by_token(token):
    """
    Potvrđuje termin po tokenu bez autentifikacije.
    Ažurira "potvrdio" polje i šalje mejl o potvrdi.
    
    Request body:
    {
        "potvrdio_id": <ID korisnika koji potvrđuje>
    }
    """
    try:
        from app import db, app
        from mailManager import send_confirmation_email, html_head
        
        data = request.json
        potvrdio_id = data.get('id')
        
        # Validacija
        if not potvrdio_id:
            return jsonify({
                "success": False,
                "error": "Nedostaje potvrdio_id"
            }), 400
        
        with app.app_context():
            # 1. Pronađi zakazivanje po tokenu
            find_query = text("""
                SELECT id, email, ime, datum_rezervacije, vreme_rezervacije, ime_firme
                FROM zakazivanja 
                WHERE token = :token
            """)
            zakazivanje = db.session.execute(find_query, {'token': token}).fetchone()
            
            if not zakazivanje:
                return jsonify({
                    "success": False,
                    "error": "Zakazivanje nije pronađeno"
                }), 404
            
            zakaz_id, email, ime, datum, vreme, ime_firme_id = zakazivanje
            
            # 2. Ažuriraj "potvrdio" polje
            update_query = text("""
                UPDATE zakazivanja 
                SET potvrdio = :potvrdio
                WHERE token = :token
            """)
            db.session.execute(update_query, {'potvrdio': potvrdio_id, 'token': token})
            db.session.commit()
            
            # 3. Dohvati podatke o korisniku koji potvrđuje
            user_query = text("SELECT username FROM users WHERE id = :id")
            user_result = db.session.execute(user_query, {'id': potvrdio_id}).fetchone()
            username = user_result[0] if user_result else 'Zaposlenik'
            
            # 4. Dohvati podatke o firmi
            firma_query = text("SELECT ime FROM preduzeca WHERE id = :id")
            firma_result = db.session.execute(firma_query, {'id': ime_firme_id}).fetchone()
            firma_ime = firma_result[0] if firma_result else 'Firmi'
            
            # 5. Formatiraj datum
            date_parts = str(datum).split('-')
            if len(date_parts) == 3:
                godina, mesec, dan = date_parts[0], date_parts[1], date_parts[2]
                datum_prikaz = f"{dan}.{mesec}.{godina} u {vreme}"
            else:
                datum_prikaz = f"{datum} u {vreme}"
            
            # 6. Pošalji mejl o potvrdi
            poruka = f"""Poštovani,
            \nVaš termin u {firma_ime} je potvrdio {username}.
            \nTermin: {datum_prikaz}
            \n\nHvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis Moj Termin.
            """
            
            html_poruka = f"""
            <html>
                {html_head}
                <body>
                    <div class="content">
                        <h2>Poštovani,</h2>
                        <p>Vaš termin u <b>{firma_ime}</b> je <b>potvrdio {username}</b>.</p>
                        <p><b>Termin:</b> {datum_prikaz}</p>
                        <p style="margin-top: 20px;">Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis <b><a href="https://test.mojtermin.site">Moj Termin</a></b>.</p>
                    </div>
                </body>
            </html>
            """
            
            subject = f"Potvrda termina - {firma_ime}"
            
            try:
                send_confirmation_email(email, poruka, subject, html_poruka)
            except Exception as email_error:
                print(f"❌ Greška pri slanju mejla o potvrdi: {str(email_error)}")
            
            return jsonify({
                "success": True,
                "message": "Termin uspešno potvrđen",
                "zakazi_id": zakaz_id
            }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
