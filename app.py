import os
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
from routes.auth import auth_bp
from datetime import timedelta, datetime
import requests
from sqlalchemy import text
import json
import secrets
from mailManager import send_confirmation_email, send_email_to_workers, html_head
from ai.askAI import askAI
from ai.chat_manager import (
    create_new_chat, save_chat_message, load_chat, 
    get_user_chats, delete_chat, rename_chat
)
from ai.ai_limiter import check_and_increment_ai_usage
from routes.aiInfo import get_ai_data_for_user

# Učitavanje .env fajla
load_dotenv()

def env_verify():
    required_vars = ['SMTP_SERVER', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'DATABASE', 'PORT', 'SQL_USER', 'SQL_PWD', 'VPS_IP']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"⚠️  UPOZORENJE: Nedostaju sledeće varijable u .env: {', '.join(missing_vars)}")
        print("   Molimo kreirajte .env fajl na osnovu .env.example")
        return False
    
    print("✅ .env je uspesno ucitan")
    return True

# Kreiranje Flask aplikacije
app = Flask(__name__)
CORS(app)
env_verify()

# JWT Konfiguracija
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET', 'default-secret-key-promenite-u-env')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)
jwt = JWTManager(app)

# Konfiguracija baze za SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.getenv('SQL_USER')}:{os.getenv('SQL_PWD')}"
    f"@{os.getenv('VPS_IP')}:{os.getenv('PORT')}/{os.getenv('DATABASE')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)




# Registracija blueprint-a za autentifikaciju
from routes.auth import auth_bp
app.register_blueprint(auth_bp, url_prefix="/api/auth")

from routes.zakazi import zakazi_bp
app.register_blueprint(zakazi_bp, url_prefix="/api/zakazi")

from routes.podesavanja import podesavnja_bp
app.register_blueprint(podesavnja_bp, url_prefix="/api/podesavanja")

from routes.zaposleni import zaposleni_bp
app.register_blueprint(zaposleni_bp, url_prefix="/api/zaposleni")

from routes.brend import brend_bp
app.register_blueprint(brend_bp, url_prefix="/api/brend")

from routes.aiInfo import aiInfo_bp
app.register_blueprint(aiInfo_bp, url_prefix="/api/ai/info")

from routes.zakazivanja import zakazivanja_bp
app.register_blueprint(zakazivanja_bp, url_prefix="/api/zakazivanja")



from routes.tests import tests_bp
app.register_blueprint(tests_bp, url_prefix='/api/tests')







@app.route('/api/hello', methods=['GET'])
def hello():
    return jsonify({"message": "Zdravo iz Flask API-ja!"})

UPLOAD_FOLDER = '/var/www/moj-termin-frontend-test/public/logos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
@app.route('/api/novi_logo', methods=['POST'])
def upload_logo():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    userId = request.form.get('id')
    authToken = request.form.get('authToken')
    logoName = f'{file.filename}'

    if not userId or not authToken:
        return jsonify({'error': 'Nedostaju podaci'}), 400

    try:
        with app.app_context():
            # Ažuriraj putanja_za_logo u users tabeli
            update_query = text("""
                UPDATE users
                SET putanja_za_logo = :logo_name
                WHERE id = :user_id
            """)
            db.session.execute(update_query, {'logo_name': logoName, 'user_id': int(userId)})
            db.session.commit()

        return jsonify({'message': 'Logo uploaded successfully', 'filename': filename}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route("/api/logo/<filename>")
def serve_logo(filename):
    if filename == "/images/logo.webp":
        return send_from_directory("/var/www/moj-termin-frontend-test/public/Images", "logo.webp")
    
    safe_name = secure_filename(filename)
    putanja = f'/var/www/moj-termin-frontend-test/public/logos'
    print(putanja)
    return send_from_directory(putanja, safe_name)



@app.route('/api/zakazi', methods=['POST'])
def zakazi_termin():
    try:
        from app import db, app
        
        # Čitanje JSON podataka iz request-a
        data = request.get_json()
        
        # Ekstraktovanje poddata iz "podaci" objekta
        podaci = data.get('podaci', {})
        user_id = data.get('userId')
        preduzece_id = podaci.get('lokacija')
        
        # Validacija obaveznih polja
        if not podaci.get('email'):
            return jsonify({
                "success": False,
                "error": "Email je obavezan"
            }), 400
        
        # Validacija preduzece_id
        if not preduzece_id:
            return jsonify({
                "success": False,
                "error": "Lokacija (preduzece) je obavezna"
            }), 400
        
        try:
            preduzece_id = int(preduzece_id)
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "error": "Lokacija mora biti validan broj"
            }), 400
        
        # Validacija i kreiranje datuma
        try:
            datum_rezervacije = podaci.get('datum_rezervacije', '').strip()
            
            # Pokušaj da parsam datum iz dela: YYYY-MM-DD
            if datum_rezervacije:
                date_parts = datum_rezervacije.split('-')
                if len(date_parts) == 3:
                    godina, mesec, dan = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
                    
                    if dan < 1 or dan > 31:
                        return jsonify({
                            "success": False,
                            "error": f"Neispravan dan: {dan}. Dan mora biti između 1 i 31"
                        }), 400
                    
                    # Kreiraj validan datum
                    datum_rezervacije = f"{godina:04d}-{mesec:02d}-{dan:02d}"
                    datetime.strptime(datum_rezervacije, '%Y-%m-%d')
                else:
                    return jsonify({
                        "success": False,
                        "error": "Neispravan format datuma. Očekujem YYYY-MM-DD"
                    }), 400
            else:
                # Ako nema datum_rezervacije, koristi dan, mesec, godina
                dan = podaci.get('dan', '')
                mesec = podaci.get('mesec', '')
                godina = podaci.get('godina', '')
                
                if not dan or not mesec or not godina:
                    return jsonify({
                        "success": False,
                        "error": "Dan, mesec i godina su obavezni"
                    }), 400
                
                dan = int(dan)
                mesec = int(mesec) + 1  # mesec je 0-11 pa se dodaje 1
                godina = int(godina)
                
                if dan < 1 or dan > 31 or mesec < 1 or mesec > 12 or godina < 2000:
                    return jsonify({
                        "success": False,
                        "error": "Neispravan datum - dan (1-31), mesec (1-12) ili godina (≥2000)"
                    }), 400
                
                datum_rezervacije = f"{godina:04d}-{mesec:02d}-{dan:02d}"
                datetime.strptime(datum_rezervacije, '%Y-%m-%d')
            
        except ValueError as e:
            return jsonify({
                "success": False,
                "error": f"Neispravan datum: {str(e)}"
            }), 400
        
        # Generisanje tokena
        token = secrets.token_urlsafe(10)
        
        with app.app_context():
            # Proveravanje da li preduzeće postoji
            preduzeca_check = text("SELECT vlasnik, ime FROM preduzeca WHERE id = :id")
            preduzeca_result = db.session.execute(preduzeca_check, {'id': int(preduzece_id)}).fetchone()
            
            if not preduzeca_result:
                return jsonify({
                    "success": False,
                    "error": "Preduzeće nije pronađeno"
                }), 404
            
            vlasnik_id = preduzeca_result[0]
            preduzece_ime = preduzeca_result[1]
            
            # Kreiranje novog zakazivanja
            insert_query = text("""
                INSERT INTO zakazivanja (
                    ime_firme, ime, email, telefon, datum_rezervacije, vreme_rezervacije,
                    usluga, opis, potvrdio, token, otkazano, created_at
                ) VALUES (
                    :ime_firme, :ime, :email, :telefon, :datum_rezervacije, :vreme_rezervacije,
                    :usluga, :opis, :potvrdio, :token, :otkazano, :created_at
                )
                RETURNING id, ime_firme, ime, email, telefon, datum_rezervacije, 
                          vreme_rezervacije, usluga, opis, potvrdio, created_at
            """)
            
            params = {
                'ime_firme': int(preduzece_id),
                'ime': podaci.get('ime') or podaci.get('email'),
                'email': podaci.get('email'),
                'telefon': podaci.get('telefon'),
                'datum_rezervacije': datum_rezervacije,
                'vreme_rezervacije': podaci.get('vreme'),
                'usluga': json.dumps(podaci.get('usluga', {})),
                'opis': podaci.get('opis', ''),
                'potvrdio': int(user_id) if user_id else None,
                'token': token,
                'otkazano': False,
                'created_at': datetime.utcnow()
            }
            
            # Izvršavanje insertovanja
            result = db.session.execute(insert_query, params).fetchone()
            db.session.commit()
            
            # Dohvatanje vlasnika preduzeca
            vlasnik_query = text("""
                SELECT id, username, email, brTel, paket FROM users WHERE id = :id
            """)
            vlasnik_info = db.session.execute(vlasnik_query, {'id': vlasnik_id}).fetchone()
            
            # Dohvatanje lokacije sa adresom
            lokacija_query = text("""
                SELECT adresa FROM preduzeca WHERE id = :id
            """)
            lokacija_info = db.session.execute(lokacija_query, {'id': int(preduzece_id)}).fetchone()
            adresa = lokacija_info[0] if lokacija_info else ''
            
            # Formatiranje datuma i vremena
            date_parts = datum_rezervacije.split('-')
            godina, mesec, dan = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
            datum_i_vreme = f"{dan}.{mesec}.{godina} u {podaci.get('vreme')}"
            
            # Slanje potvrde emaila zakazivačу
            subject = f"Zakazivanje termina - {preduzece_ime}"
            poruka = f"""Poštovani,
            Vaš termin u {preduzece_ime} je uspešno zakazan za {datum_i_vreme}, na adresi {adresa}. Dobićete obaveštenje kada neko potvrdi vaš termin.
            Takođe možete izmeniti vreme i datum Vašeg termina na linku ispod. Nakon izmene očekujte ponovnu potvrdu.
            https://test.mojtermin.site/zakazi/{vlasnik_id}/izmeni/{token}
            
            Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis Moj Termin."""

            html_poruka = f"""
            <html>
                {html_head}
                <body>
                    <div class="content">
                    <h2>Poštovani,</h2>
                    <p>Vaš termin u {preduzece_ime} je <b>uspešno zakazan</b> za <b>{datum_i_vreme}</b> na adresi <b>{adresa}</b>. Dobićete obaveštenje kada neko potvrdi vaš termin.</p>
                    <p>Takođe možete izmeniti vreme i datum Vašeg termina. Nakon izmene očekujte ponovnu potvrdu.</p>
                    <a href="https://test.mojtermin.site/zakazi/{vlasnik_id}/izmeni/{token}" class="btn">Izmenite termin</a>
                    <p style="margin-top: 20px;">Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis <b><a href="https://test.mojtermin.site">Moj Termin</a></b>.</p>
                    </div>
                </body>
            </html>
            """

            # Slanje emaila sa error handling-om
            try:
                send_confirmation_email(
                    podaci.get('email'),
                    poruka,
                    subject,
                    html_poruka
                )
            except Exception as email_error:
                print(f"❌ Greška pri slanju potvrde emaila: {str(email_error)}")
            
            # Slanje mejla zaposlenima ako je userId postavljen (nije null)
            if user_id is None:
                print(f"Slanje mejla zaposlenima...")
                try:
                    send_email_to_workers(
                        vlasnik_id,
                        'Novo zakazivanje',
                        token,
                        int(preduzece_id),
                        preduzece_ime,
                        datum_i_vreme,
                        podaci.get('ime') or podaci.get('email')
                    )
                except Exception as worker_email_error:
                    print(f"❌ Greška pri slanju emaila zaposlenima: {str(worker_email_error)}")
            else:
                print(f"UserId je {user_id}, mejl zaposlenima se ne šalje")
        
        return jsonify({
            "success": True,
            "message": "Zakazivanje uspešno",
            "zakazivanje_id": result[0],
            "token": token
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/zakazi/izmena', methods=['POST'])
def izmeniTermin():
    """
    Izmena zakazivanja u bazi podataka na osnovu tokena.
    Ažurira podatke zakazivanja i šalje odgovarajuće mejlove.
    """
    try:
        data = request.json
        podaci = data.get('podaci', {})
        token = data.get('token')
        tip_ulaska = data.get('tipUlaska')
        user_id = data.get('userId')
        stari_podaci = data.get('stariPodaci', {})
        
        # Validacija obaveznih polja
        if not podaci:
            return jsonify({'error': 'Nedostaju podaci'}), 400
        if not token:
            return jsonify({'error': 'Nema tokena'}), 400
        
        with app.app_context():
            # 1. Pronađi zakazivanje po tokenu
            find_query = text("SELECT id, ime_firme FROM zakazivanja WHERE token = :token")
            result = db.session.execute(find_query, {'token': token}).fetchone()
            
            if not result:
                return jsonify({'error': 'Zakazivanje nije pronađeno'}), 404
            
            zakaz_id, ime_firme_id = result[0], result[1]
            
            # 2. Pripremi datum za ažuriranje
            datum_rezervacije = None
            if podaci.get('datum_rezervacije'):
                datum_rezervacije = podaci.get('datum_rezervacije')
            else:
                dan = podaci.get('dan', '')
                mesec = podaci.get('mesec', '')
                godina = podaci.get('godina', '')
                
                if dan and mesec and godina:
                    dan = int(dan)
                    mesec = int(mesec) + 1  # mesec je 0-11
                    godina = int(godina)
                    datum_rezervacije = f"{godina:04d}-{mesec:02d}-{dan:02d}"
            
            # 3. Ažuriraj zakazivanje u bazi
            update_query = text("""
                UPDATE zakazivanja 
                SET 
                    ime = :ime,
                    email = :email,
                    telefon = :telefon,
                    datum_rezervacije = :datum_rezervacije,
                    vreme_rezervacije = :vreme_rezervacije,
                    usluga = :usluga,
                    opis = :opis,
                    ime_firme = :ime_firme,
                    potvrdio = NULL
                WHERE token = :token
                RETURNING id, ime_firme, ime, email, telefon, datum_rezervacije, 
                          vreme_rezervacije, usluga, opis
            """)
            
            update_result = db.session.execute(update_query, {
                'ime': podaci.get('ime') or podaci.get('email'),
                'email': podaci.get('email'),
                'telefon': podaci.get('telefon'),
                'datum_rezervacije': datum_rezervacije,
                'vreme_rezervacije': podaci.get('vreme') or podaci.get('vreme_rezervacije'),
                'usluga': json.dumps(podaci.get('usluga', {})),
                'opis': podaci.get('opis', ''),
                'ime_firme': podaci.get('ime_firme') or ime_firme_id,
                'token': token
            }).fetchone()
            
            db.session.commit()
            
            # 4. Dohvati podatke o preduzeću
            preduzece_query = text("SELECT ime FROM preduzeca WHERE id = :id")
            preduzece_result = db.session.execute(preduzece_query, {'id': ime_firme_id}).fetchone()
            preduzece_ime = preduzece_result[0] if preduzece_result else 'Preduzeće'
            
            # 5. Formatiraj datum i vreme za mejl
            datum_i_vreme = f"{podaci.get('dan', stari_podaci.get('dan'))}.{int(podaci.get('mesec', stari_podaci.get('mesec'))) + 1}.{podaci.get('godina', stari_podaci.get('godina'))} u {podaci.get('vreme') or podaci.get('vreme_rezervacije')}"
            
            # 6. Utvrledi da li se lokacija promenila
            nova_lokacija = podaci.get('lokacija') or podaci.get('ime_firme')
            stara_lokacija = stari_podaci.get('lokacija') or stari_podaci.get('ime_firme')
            lokacija_promenjena = nova_lokacija != stara_lokacija
            
            # 7. Slaj mejlove na osnovu tipa ulaska i što se promenilo
            subject = f"Izmena termina - {preduzece_ime}"
            
            if not lokacija_promenjena:
                # Ista lokacija
                if tip_ulaska == 2:  # Korisnik menja
                    poruka = f"""Poštovani,
                    \nVaš termin je uspešno izmenjen za {datum_i_vreme}. Dobićete obaveštenje kada neko potvrdi vaš termin.
                    \n Takođe možete izmeniti vreme i datum Vašeg termina na linku ispod. Nakon izmene očekujte ponovnu potvrdu.
                    \n https://test.mojtermin.site/zakazi/{data.get('id')}/izmeni/{token}
                    \n\nHvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis Moj Termin.
                    """

                    html_poruka = f"""
                    <html>
                        {html_head}
                        <body>
                            <div class="content">
                            <h2>Poštovani,</h2>
                            <p>Vaš termin je <b>uspešno izmenjen</b> za <b>{datum_i_vreme}</b>. Dobićete obaveštenje kada neko potvrdi vaš termin.</p>
                            <p>Takođe možete izmeniti vreme i datum Vašeg termina. Nakon izmene očekujte ponovnu potvrdu.</p>
                            <a href="https://test.mojtermin.site/zakazi/{data.get('id')}/izmeni/{token}" class="btn">Izmenite termin</a>
                            <p style="margin-top: 20px;">Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis <b><a href="https://test.mojtermin.site">Moj Termin</a></b>.</p>
                            </div>
                        </body>
                    </html>
                    """
                    
                    try:
                        send_confirmation_email(
                            podaci.get('email'),
                            poruka,
                            subject,
                            html_poruka
                        )
                    except Exception as email_error:
                        print(f"❌ Greška pri slanju mejla korisniku: {str(email_error)}")
                    
                    if user_id is not None:
                        try:
                            send_email_to_workers(
                                data.get('id'),
                                nova_lokacija,
                                'Izmena termina',
                                token,
                                nova_lokacija,
                                preduzece_ime,
                                datum_i_vreme,
                                podaci.get('ime') or podaci.get('email'),
                                stari_podaci
                            )
                        except Exception as worker_error:
                            print(f"❌ Greška pri slanju mejla zaposlenima: {str(worker_error)}")
                
                else:  # Zaposleni menja (tip_ulaska != 2)
                    poruka = f"""Poštovani,
                    \nVaš termin u {preduzece_ime} je izmenio zaposlenik za {datum_i_vreme}.
                    \nUkoliko Vam novo vreme termina ne odgovara, možete da izmeniti ili otkazati na linku ispod.
                    \nhttps://test.mojtermin.site/zakazi/{data.get('id')}/izmeni/{token}
                    \n Ukoliko menjate termin vreme termina, molimo Vas da ne zakazujete termin u vreme koje ste prvobitno odabrali.
                    \n\nHvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis Moj Termin.
                    """
                    
                    html_poruka = f"""
                    <html>
                        {html_head}
                        <body>
                            <div class="content">
                                <h2>Poštovani,</h2>
                                <p>Vaš termin u {preduzece_ime} je izmenio zaposlenik za <b>{datum_i_vreme}</b>.</p>
                                <p>Ukoliko Vam novo vreme termina ne odgovara, možete da izmenite ili otkazati na linku ispod.</p>
                                <a href="https://test.mojtermin.site/zakazi/{data.get('id')}/izmeni/{token}" class="btn">Izmenite termin</a>
                                <p style="margin-top: 20px;">Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis <b><a href="https://test.mojtermin.site">Moj Termin</a></b>.</p>
                            </div>
                        </body>
                    </html>
                    """

                    try:
                        send_confirmation_email(
                            podaci.get('email'),
                            poruka,
                            subject,
                            html_poruka
                        )
                    except Exception as email_error:
                        print(f"❌ Greška pri slanju mejla: {str(email_error)}")
            
            else:
                # Promena lokacije
                if tip_ulaska == 2:  # Korisnik menja
                    poruka = f"""Poštovani,
                    \nVaš termin je uspešno izmenjen za {datum_i_vreme}. Dobićete obaveštenje kada neko potvrdi vaš termin.
                    \n Takođe možete izmeniti vreme i datum Vašeg termina na linku ispod. Nakon izmene očekujte ponovnu potvrdu.
                    \n https://test.mojtermin.site/zakazi/{data.get('id')}/izmeni/{token}
                    \n\nHvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis Moj Termin.
                    """

                    html_poruka = f"""
                    <html>
                        {html_head}
                        <body>
                            <div class="content">
                            <h2>Poštovani,</h2>
                            <p>Vaš termin je <b>uspešno izmenjen</b> za <b>{datum_i_vreme}</b>. Dobićete obaveštenje kada neko potvrdi vaš termin.</p>
                            <p>Takođe možete izmeniti vreme i datum Vašeg termina. Nakon izmene očekujte ponovnu potvrdu.</p>
                            <a href="https://test.mojtermin.site/zakazi/{data.get('id')}/izmeni/{token}" class="btn">Izmenite termin</a>
                            <p style="margin-top: 20px;">Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis <b><a href="https://test.mojtermin.site">Moj Termin</a></b>.</p>
                            </div>
                        </body>
                    </html>
                    """
                    
                    try:
                        send_confirmation_email(
                            podaci.get('email'),
                            poruka,
                            subject,
                            html_poruka
                        )
                    except Exception as email_error:
                        print(f"❌ Greška pri slanju mejla: {str(email_error)}")

                    if user_id is not None:
                        try:
                            send_email_to_workers(  # Novoj lokaciji
                                data.get('id'),
                                nova_lokacija,
                                'Izmena termina - nova lokacija',
                                token,
                                nova_lokacija,
                                preduzece_ime,
                                datum_i_vreme,
                                podaci.get('ime') or podaci.get('email'),
                                stari_podaci
                            )
                        except Exception as worker_error:
                            print(f"❌ Greška pri slanju mejla zaposlenima (nova): {str(worker_error)}")
                        
                        try:
                            send_email_to_workers(  # Staroj lokaciji
                                data.get('id'),
                                stara_lokacija,
                                'Izmena termina na novu lokaciju',
                                token,
                                stara_lokacija,
                                preduzece_ime,
                                datum_i_vreme,
                                podaci.get('ime') or podaci.get('email'),
                                stari_podaci
                            )
                        except Exception as worker_error:
                            print(f"❌ Greška pri slanju mejla zaposlenima (stara): {str(worker_error)}")
                
                else:  # Zaposleni menja
                    if user_id is not None:
                        try:
                            send_email_to_workers(
                                data.get('id'),
                                nova_lokacija,
                                'Izmena termina - nova lokacija',
                                token,
                                nova_lokacija,
                                preduzece_ime,
                                datum_i_vreme,
                                podaci.get('ime') or podaci.get('email'),
                                stari_podaci
                            )
                        except Exception as worker_error:
                            print(f"❌ Greška pri slanju mejla zaposlenima (nova): {str(worker_error)}")
                        
                        try:
                            send_email_to_workers(
                                data.get('id'),
                                stara_lokacija,
                                'Izmena termina na novu lokaciju',
                                token,
                                stara_lokacija,
                                preduzece_ime,
                                datum_i_vreme,
                                podaci.get('ime') or podaci.get('email'),
                                stari_podaci
                            )
                        except Exception as worker_error:
                            print(f"❌ Greška pri slanju mejla zaposlenima (stara): {str(worker_error)}")
        
        return jsonify({
            'status': 200,
            'app_response': 'Zakazivanje uspešno izmenjeno',
            'zakazi_id': zakaz_id
        }), 200

    except Exception as e:
        print(f"❌ Greška u /api/zakazi/izmena: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@app.route('/api/potvrdi_termin', methods=['POST'])
def potvrdiTermin():
    """
    Potvrđuje zakazivanje i menja "potvrdio" polje sa ID-om korisnika koji potvrđuje.
    Šalje mejl korisniku o potvrdi.
    """
    try:
        data = request.json
        termin = data.get('termin', {})
        auth_token = data.get('authToken')
        
        termin_token = termin.get('token')
        potvrdio_id = termin.get('potvrdio')
        
        # Validacija
        if not termin_token:
            return jsonify({'error': 'Nedostaje token termina'}), 400
        if not potvrdio_id:
            return jsonify({'error': 'Nedostaje ID korisnika koji potvrđuje'}), 400
        if not auth_token:
            return jsonify({'error': 'Nedostaje authToken'}), 400
        
        with app.app_context():
            # 1. Pronađi zakazivanje po tokenu i preuzmi podatke
            find_query = text("""
                SELECT id, email, ime, datum_rezervacije, vreme_rezervacije, ime_firme
                FROM zakazivanja 
                WHERE token = :token
            """)
            zakazivanje = db.session.execute(find_query, {'token': termin_token}).fetchone()
            
            if not zakazivanje:
                return jsonify({'error': 'Zakazivanje nije pronađeno'}), 404
            
            zakaz_id, email, ime, datum, vreme, ime_firme_id = zakazivanje
            
            # 2. Ažuriraj "potvrdio" polje
            update_query = text("""
                UPDATE zakazivanja 
                SET potvrdio = :potvrdio
                WHERE token = :token
            """)
            db.session.execute(update_query, {'potvrdio': potvrdio_id, 'token': termin_token})
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
            'status': 200,
            'message': 'Termin uspešno potvrđen',
            'zakazi_id': zakaz_id
        }), 200

    except Exception as e:
        print(f"❌ Greška u /api/potvrdi_termin: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


@app.route('/api/otkazi', methods=['PATCH'])
def otkaziTermin():
    """
    Otkazuje zakazivanje i menja "otkazano" polje na true.
    Šalje mejl korisniku o otkazivanju.
    """
    try:
        data = request.json
        token = data.get('token')
        
        # Validacija
        if not token:
            return jsonify({'error': 'Nedostaje token termina'}), 400
        
        with app.app_context():
            # 1. Pronađi zakazivanje po tokenu i preuzmi podatke
            find_query = text("""
                SELECT id, email, ime, datum_rezervacije, vreme_rezervacije, ime_firme
                FROM zakazivanja 
                WHERE token = :token
            """)
            zakazivanje = db.session.execute(find_query, {'token': token}).fetchone()
            
            if not zakazivanje:
                return jsonify({'error': 'Zakazivanje nije pronađeno'}), 404
            
            zakaz_id, email, ime, datum, vreme, ime_firme_id = zakazivanje
            
            # 2. Ažuriraj "otkazano" polje na true
            update_query = text("""
                UPDATE zakazivanja 
                SET otkazano = true
                WHERE token = :token
            """)
            db.session.execute(update_query, {'token': token})
            db.session.commit()
            
            # 3. Dohvati podatke o firmi
            firma_query = text("SELECT ime FROM preduzeca WHERE id = :id")
            firma_result = db.session.execute(firma_query, {'id': ime_firme_id}).fetchone()
            firma_ime = firma_result[0] if firma_result else 'Firmi'
            
            # 4. Formatiraj datum
            date_parts = str(datum).split('-')
            if len(date_parts) == 3:
                godina, mesec, dan = date_parts[0], date_parts[1], date_parts[2]
                datum_prikaz = f"{dan}.{mesec}.{godina} u {vreme}"
            else:
                datum_prikaz = f"{datum} u {vreme}"
            
            # 5. Pošalji mejl o otkazivanju
            poruka = f"""Poštovani,
            \nVaš termin u {firma_ime} za {datum_prikaz} je otkazan.
            \nNaravno možete ponovo zakazati termin.
            \n\nHvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis Moj Termin.
            """
            
            html_poruka = f"""
            <html>
                {html_head}
                <body>
                    <div class="content">
                        <h2>Poštovani,</h2>
                        <p>Vaš termin u <b>{firma_ime}</b> za <b>{datum_prikaz}</b> je <b>otkazan</b>.</p>
                        <p>Naravno možete ponovo zakazati termin.</p>
                        <p style="margin-top: 20px;">Hvala što ste izabrali našu uslugu! Ovu uslugu je omogućio servis <b><a href="https://test.mojtermin.site">Moj Termin</a></b>.</p>
                    </div>
                </body>
            </html>
            """
            
            subject = f"Otkazivanje termina - {firma_ime}"
            
            try:
                send_confirmation_email(email, poruka, subject, html_poruka)
            except Exception as email_error:
                print(f"❌ Greška pri slanju mejla o otkazivanju: {str(email_error)}")
        
        return jsonify({
            'status': 200,
            'message': 'Termin uspešno otkazan',
            'zakazi_id': zakaz_id
        }), 200

    except Exception as e:
        print(f"❌ Greška u /api/otkazi: {str(e)}")
        db.session.rollback()
        return jsonify({
            'status': 500,
            'error': str(e)
        }), 500


# AI RUTE >>>>>>>>>>>>>
@app.route('/api/askAI', methods=['POST'])
def askAI_route():
    """
    Ruta koja poziva askAI funkciju nakon provere validnosti tokena i limitacija.
    """
    data = request.json

    # Validacija ulaznih podataka
    auth_token = data.get('authToken')
    poruke = data.get('poruke', [])
    pitanje = data.get('pitanje')
    user_id = data.get('userId')

    if not auth_token:
        return jsonify({'error': 'Nedostaje authToken'}), 400
    if not pitanje:
        return jsonify({'error': 'Nedostaje pitanje'}), 400
    if not user_id:
        return jsonify({'error': 'Nedostaje userId'}), 400

    # ===== PROVERA AI LIMITACIJA =====
    limit_result = check_and_increment_ai_usage(user_id, auth_token, db)
    
    if not limit_result['allowed']:
        return jsonify({
            'error': limit_result['error'],
            'status': 'limit_exceeded'
        }), 429  # Too Many Requests
    
    selected_model = limit_result['model']
    print(f"✅ Odabrani model: {selected_model}")
    # ===== KRAJ PROVERE LIMITACIJA =====

    # Dohvatanje podataka firme iz baze
    try:
        data_firme = get_ai_data_for_user(user_id, db)
        
        if not data_firme:
            return jsonify({'error': 'Korisnik nije pronađen'}), 404

    except Exception as e:
        return jsonify({'error': f'Greška pri dohvatanju podataka: {str(e)}'}), 500

    # Pozivanje askAI funkcije
    try:
        odgovor = askAI(data_firme, poruke, pitanje, selected_model)
        
        return jsonify({
            'status': 'success',
            'odgovor': odgovor,
            'model': selected_model,
            'poruka': 'Odgovor uspešno generisan'
        }), 200

    except Exception as e:
        return jsonify({
            'error': 'Greška pri generisanju odgovora',
            'details': str(e)
        }), 500


@app.route('/api/aiUsage', methods=['GET'])
def get_ai_usage():
    """
    Vraća podatke o korišćenju AI za određeni dan.
    Čita .json fajl iz backend_tools/ai_usage/[owner_id]/[datum].json
    
    Query parametri:
    - owner_id (obavezno): ID vlasnika
    - date (opciono): Datum u formatu YYYY-MM-DD, ako nije prosleđen koristi se danasnnji datum
    
    Vraća:
    - JSON sa strukturom:
      {
        "owner": {"llama3": 0, "llama4": 0},
        "employees": {"llama3": 0, "llama4": 0},
        "bookings": {"llama3": 0, "llama4": 0}
      }
    
    Ako fajl ne postoji, vraća default values sa svim 0.
    """
    try:
        owner_id = request.args.get('owner_id')
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not owner_id:
            return jsonify({'error': 'Nedostaje owner_id parametar'}), 400
        
        # Konstruiši putanju do fajla
        file_path = f'backend_tools/ai_usage/{owner_id}/{date}.json'
        
        # Provera da li fajl postoji
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return jsonify(data), 200
            except json.JSONDecodeError as e:
                print(f"❌ Greška pri parsiranju JSON fajla {file_path}: {str(e)}")
                return jsonify({'error': 'Invalid JSON file'}), 500
            except Exception as e:
                print(f"❌ Greška pri čitanju fajla {file_path}: {str(e)}")
                return jsonify({'error': f'Greška pri čitanju fajla: {str(e)}'}), 500
        else:
            # Ako fajl ne postoji, vrati default vrednosti
            default_data = {
                "owner": {"llama3": 0, "llama4": 0},
                "employees": {"llama3": 0, "llama4": 0},
                "bookings": {"llama3": 0, "llama4": 0}
            }
            return jsonify(default_data), 200
    
    except Exception as e:
        print(f"❌ Greška u /api/aiUsage: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500





# ========== CHAT RUTE ==========

@app.route('/api/chat/create', methods=['POST'])
def create_chat():
    """
    Kreira novi chat za korisnika
    """
    try:
        data = request.json
        user_id = data.get('userId')
        auth_token = data.get('authToken')
        title = data.get('title', 'Nova konverzacija')

        if not user_id or not auth_token:
            return jsonify({'error': 'Nedostaju userId i authToken'}), 400

        result = create_new_chat(user_id, title)
        return jsonify(result), 201

    except Exception as e:
        print(f"[ERROR] Greška pri kreiranju chata: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500


@app.route('/api/chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    """
    Učitava specifičan chat
    Samo kreator može pristupiti
    """
    try:
        user_id = request.args.get('userId')
        auth_token = request.args.get('authToken')

        if not user_id or not auth_token:
            return jsonify({'error': 'Nedostaju userId i authToken'}), 400

        result = load_chat(user_id, chat_id)
        
        if not result.get('success'):
            return jsonify(result), 403

        return jsonify(result), 200

    except Exception as e:
        print(f"[ERROR] Greška pri učitavanju chata: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500


@app.route('/api/chats', methods=['GET'])
def list_chats():
    """
    Vraća sve chatove za trenutnog korisnika
    """
    try:
        user_id = request.args.get('userId')
        auth_token = request.args.get('authToken')

        if not user_id or not auth_token:
            return jsonify({'error': 'Nedostaju userId i authToken'}), 400

        chats = get_user_chats(user_id)
        return jsonify({'chats': chats}), 200

    except Exception as e:
        print(f"[ERROR] Greška pri učitavanju liste chatova: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500


@app.route('/api/chat/<chat_id>/message', methods=['POST'])
def add_message_to_chat(chat_id):
    """
    Dodaje poruku u chat i čuva je
    """
    try:
        data = request.json
        user_id = data.get('userId')
        auth_token = data.get('authToken')
        message_text = data.get('message')
        sender = data.get('sender', 'user')

        if not user_id or not auth_token or not message_text:
            return jsonify({'error': 'Nedostaju obavezni podaci'}), 400

        result = save_chat_message(user_id, chat_id, {
            'text': message_text,
            'sender': sender
        })

        if not result.get('success'):
            return jsonify(result), 403

        return jsonify(result), 200

    except Exception as e:
        print(f"[ERROR] Greška pri čuvanju poruke: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500


@app.route('/api/chat/<chat_id>', methods=['DELETE'])
def delete_chat_route(chat_id):
    """
    Briše chat (samo kreator može)
    """
    try:
        data = request.json
        user_id = data.get('userId')
        auth_token = data.get('authToken')

        if not user_id or not auth_token:
            return jsonify({'error': 'Nedostaju userId i authToken'}), 400

        result = delete_chat(user_id, chat_id)

        if not result.get('success'):
            return jsonify(result), 403

        return jsonify(result), 200

    except Exception as e:
        print(f"[ERROR] Greška pri brisanju chata: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500


@app.route('/api/chat/<chat_id>/rename', methods=['PATCH'])
def rename_chat_route(chat_id):
    """
    Preimenovava chat (samo kreator može)
    """
    try:
        data = request.json
        user_id = data.get('userId')
        auth_token = data.get('authToken')
        new_title = data.get('title')

        if not user_id or not auth_token or not new_title:
            return jsonify({'error': 'Nedostaju obavezni podaci'}), 400

        result = rename_chat(user_id, chat_id, new_title)

        if not result.get('success'):
            return jsonify(result), 403

        return jsonify(result), 200

    except Exception as e:
        print(f"[ERROR] Greška pri preimenovanju chata: {str(e)}")
        return jsonify({'error': f'Server greška: {str(e)}'}), 500







# Pokretanje aplikacije
if __name__ == '__main__':
    app.run(debug=True)