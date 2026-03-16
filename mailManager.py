from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import requests
from sqlalchemy import text

load_dotenv()



html_head = """
<head>
    <!-- Google Fonts: Poppins -->
    <link href="https://fonts.googleapis.com/css2?family=Poppins&display=swap" rel="stylesheet" />

    <style type="text/css">
    body {
        margin: 0;
        padding: 0;
        background-color: #ffffff;
        color: #000000;
        font-family: 'Poppins', sans-serif;
    }

    *{
        color: #000 !important;
    }

    .content {
        padding: 20px;
    }

    a {
        text-decoration: none;
        color: inherit;
    }

    .btn {
        display: inline-block;
        padding: 12px 24px;
        background-color: #3b82f6;
        color: #ffffff;
        font-weight: 600;
        text-transform: uppercase;
        border-radius: 5px;
        margin-top: 15px;
        text-align: center;
    }

    .btn:hover {
        background-color: #000000;
        color: #3b82f6 !important;
    }

    @media (prefers-color-scheme: dark) {
        body {
            background-color: #000000 !important;
            color: #ffffff !important;
        }

        *{
            color: #fff !important;
        }

        .btn {
            background-color: #3b82f6;
            color: #000000;
        }

        .btn:hover {
            background-color: #ffffff;
            color: #3b82f6;
        }
    }
    </style>
</head>"""



def send_confirmation_email(to_email, poruka, subject, html_poruka=None ):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = os.getenv('SMTP_USER')
        msg["To"] = to_email

        # Dodaj tekstualni deo (plain text)
        part1 = MIMEText(poruka, "plain")
        msg.attach(part1)

        # Dodaj HTML deo ako postoji
        if html_poruka:
            part2 = MIMEText(html_poruka, "html")
            msg.attach(part2)

        # Učitaj SMTP kredencijale
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')

        # Validacija kredencijala
        if not all([smtp_server, smtp_port, smtp_user, smtp_password]):
            print("❌ GREŠKA: Nedostaju SMTP kredencijali u .env fajlu!")
            print(f"   SMTP_SERVER: {bool(smtp_server)}")
            print(f"   SMTP_PORT: {bool(smtp_port)}")
            print(f"   SMTP_USER: {bool(smtp_user)}")
            print(f"   SMTP_PASSWORD: {bool(smtp_password)}")
            return False

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        print(f"✅ Email poslat na: {to_email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP autentifikacijska greška: {str(e)}")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP greška: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Neočekivana greška pri slanju emaila: {str(e)}")
        return False



def send_email_to_workers(vlasnikId, naslov, token, lokacija, preduzece, datum_i_vreme, zakazivac, stariPodaci=None):
    print(f"\n=== SLANJE MEJLOVA ZAPOSLENIMA ===")
    print(f"vlasnikId: {vlasnikId}, naslov: {naslov}, lokacija: {lokacija}")
    zaposleni = []
    
    try:
        from app import db, app
        
        with app.app_context():
            # Dohvatanje vlasnika
            vlasnik_query = text("SELECT id, email FROM users WHERE id = :vlasnik_id")
            vlasnik = db.session.execute(vlasnik_query, {'vlasnik_id': vlasnikId}).fetchone()
            
            if vlasnik and vlasnik[1]:
                zaposleni.append({'email': vlasnik[1], 'id': vlasnik[0]})
                print(f"Dodat vlasnik: {vlasnik[1]}")
            
            # Dohvatanje svih zaposlenih koji su dodeljeni ovoj lokaciji
            zaposleni_query = text("""
                SELECT id, email FROM users 
                WHERE zaposlen_u = :lokacija AND email IS NOT NULL AND email != ''
            """)
            zaposleni_results = db.session.execute(zaposleni_query, {'lokacija': lokacija}).fetchall()
            
            print(f"Broj zaposlenih za lokaciju {lokacija}: {len(zaposleni_results)}")
            
            for zaposleni_osoba in zaposleni_results:
                zaposleni.append({'email': zaposleni_osoba[1], 'id': zaposleni_osoba[0]})
                print(f"Dodan zaposlenik: {zaposleni_osoba[1]}")

        print(f"Ukupno zaposlenih za obaveštavanja: {len(zaposleni)}")
        
        # Slanje mejlova svakom od njih
        for z in zaposleni:
            email = z['email']
            korisnik_id = z['id']
            if naslov == 'Novo zakazivanje':
                send_confirmation_email(
                    to_email=email,
                    poruka=f"""
                        Novi termin zakazan u {preduzece} za {datum_i_vreme}. Klijent: {zakazivac}.
                        \nNa linku ispod možete izmeniti vreme i datum termina, potvrditi ga ili otkazati.
                        \nhttps://mojtermin.site/zakazi/{vlasnikId}/izmena/{token}
                    """,
                    subject=f"{naslov} - {preduzece}",
                    html_poruka=f"""
                        <html>
                            {html_head}
                            <body>
                                <div class="content">
                                    <p>Novi termin zakazan u {preduzece} za {datum_i_vreme}. Klijent: {zakazivac}</p>
                                    <a href="https://mojtermin.site/zakazi/{vlasnikId}/izmeni/{token}/potvrda/{korisnik_id}" class="btn">Potvrdi termin</a>
                                    <a href="https://mojtermin.site/zakazi/{vlasnikId}/izmeni/{token}" class="btn">Izmenite termin</a>
                                </div>
                            </body>
                        </html>
                    """
                )

            elif naslov == 'Izmena termina':
                send_confirmation_email(
                    to_email=email,
                    poruka=f"""
                        Izmenjen termin zakazan u {preduzece} za {datum_i_vreme}. Izmenio ga je {zakazivac}.
                        \nNa linku ispod možete izmeniti vreme i datum termina, potvrditi ga ili otkazati.
                        \nhttps://mojtermin.site/zakazi/{vlasnikId}/izmena/{token}
                        \nStari podaci: 
                        \nIme: {stariPodaci.get("ime", "N/A")},
                        \nLokacija: {stariPodaci.get("lokacija", "N/A")},
                        \nVreme: {stariPodaci.get('dan')}.{stariPodaci.get('mesec')}.{stariPodaci.get('godina')} u {stariPodaci.get('vreme')},
                        \nTrajanje termina: {stariPodaci.get('trajanje', 'N/A')}
                    """,
                    subject=f"{naslov}",
                    html_poruka=f"""
                        <html>
                            {html_head}
                            <body>
                                <div class="content">
                                    <p>Izmenjen termin zakazan u {preduzece} za {datum_i_vreme}. Izmenio ga je {zakazivac}</p>
                                    <a href="https://mojtermin.site/zakazi/{vlasnikId}/izmeni/{token}/potvrda/{korisnik_id}" class="btn">Potvrdi termin</a>
                                    <a href="https://mojtermin.site/zakazi/{vlasnikId}/izmeni/{token}" class="btn">Izmenite termin</a>
                                    <p style="margin-top: 20px;">Stari podaci:</p>
                                    <ul>
                                        <li>Ime: {stariPodaci.get("ime", "N/A")}</li>
                                        <li>Lokacija: {stariPodaci.get("lokacija", "N/A")}</li>
                                        <li>Vreme: {stariPodaci.get('dan')}.{stariPodaci.get('mesec')}.{stariPodaci.get('godina')} u {stariPodaci.get('vreme')}</li>
                                        <li>Trajanje termina: {stariPodaci.get('trajanje', 'N/A')}</li>
                                    </ul>
                                </div>
                            </body>
                        </html>
                    """
                )
            
            elif naslov == 'Izmena termina - nova lokacija':
                send_confirmation_email(
                    to_email=email,
                    poruka=f"""Termin koji je bio zakazan na drugom radnom mestu je izmenjen i odabrano je novo radno mesto - {preduzece} za {datum_i_vreme}. Izmenio ga je {zakazivac}.
                        \nNa linku ispod možete izmeniti vreme i datum termina, potvrditi ga ili otkazati.
                        \nhttps://mojtermin.site/zakazi/{vlasnikId}/izmena/{token}
                        \nStari podaci: 
                        \nIme: {stariPodaci.get("ime", "N/A")},
                        \nLokacija: {stariPodaci.get("lokacija", "N/A")} (id),
                        \nVreme: {stariPodaci.get('dan')}.{stariPodaci.get('mesec')}.{stariPodaci.get('godina')} u {stariPodaci.get('vreme')},
                        \nTrajanje termina: {stariPodaci.get('trajanje', 'N/A')}
                    """,
                    subject=f"{naslov}",
                    html_poruka=f"""
                        <html>
                            {html_head}
                            <body>
                                <div class="content">
                                    <p>Termin koji je bio zakazan na drugom radnom mestu je izmenjen i odabrano je novo radno mesto - {preduzece} za {datum_i_vreme}. Izmenio ga je {zakazivac}.</p>
                                    <a href="https://mojtermin.site/zakazi/{vlasnikId}/izmeni/{token}/potvrda/{korisnik_id}" class="btn">Potvrdi termin</a>
                                    <a href="https://mojtermin.site/zakazi/{vlasnikId}/izmeni/{token}" class="btn">Izmenite termin</a>
                                    <p style="margin-top: 20px;">Stari podaci:</p>
                                    <ul>
                                        <li>Ime: {stariPodaci.get("ime", "N/A")}</li>
                                        <li>Lokacija: {stariPodaci.get("lokacija", "N/A")} (id)</li>
                                        <li>Vreme: {stariPodaci.get('dan')}.{stariPodaci.get('mesec')}.{stariPodaci.get('godina')} u {stariPodaci.get('vreme')}</li>
                                        <li>Trajanje termina: {stariPodaci.get('trajanje', 'N/A')}</li>
                                    </ul>
                                </div>
                            </body>
                        </html>
                    """
                )

            elif naslov == 'Izmena termina na novu lokaciju':
                send_confirmation_email(
                    to_email=email,
                    poruka=f"""Termin koji je bio zakazan na vašem radnom mestu je izmenjen i odabrano je novo radno mesto -  {preduzece}. Izmenio ga je {zakazivac}.
                        \nStari podaci: 
                        \nIme: {stariPodaci.get("ime", "N/A")},
                        \nLokacija: {stariPodaci.get("lokacija", "N/A")} (id),
                        \nVreme: {stariPodaci.get('dan')}.{stariPodaci.get('mesec')}.{stariPodaci.get('godina')} u {stariPodaci.get('vreme')},
                        \nTrajanje termina: {stariPodaci.get('trajanje', 'N/A')}
                    """,
                    subject=f"{naslov}"
                )
            
            elif naslov == 'Otkazivanje termina':
                send_confirmation_email(
                    to_email=email,
                    poruka=f"Termin u {preduzece} za {datum_i_vreme} je otkazan od strane {zakazivac}.",
                    subject=f"{naslov} - {preduzece}"
                )

        return True

    except Exception as e:
        print(f"GREŠKA u send_email_to_workers: {str(e)}")
        return False

