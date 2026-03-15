import csv
import psycopg2
import json
from datetime import datetime

# --- Podesi konekciju ---
conn = psycopg2.connect(
    dbname="Test",           
    user="postgres",         
    password="nemanja123",   
    host="localhost",        
    port="5432"
)
cur = conn.cursor()

# --- Unos putanje do CSV fajla ---
csv_file_path = input("Unesite punu putanju do CSV fajla: ").strip()

# --- Funkcije za parsiranje ---
def parse_json_field(row, field):
    """Parsira JSON polja i vraća kao string"""
    try:
        if row[field]:
            return json.dumps(json.loads(row[field]))
        else:
            return json.dumps({})
    except:
        return json.dumps({})

def parse_date_str(val, default=None):
    """Parsira datum iz stringa CSV-a u datetime"""
    if not val:
        return default
    val = val.strip().replace("\r", "").replace("\n", "")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    print(f"⚠️ Nepoznat format datuma: '{val}'")
    return default

def parse_int(val, default=0):
    """Parsira integer vrednost"""
    try:
        return int(val)
    except:
        return default

def check_user_exists(user_id):
    """Proverava da li postoji korisnik sa datim id-om u tabeli users"""
    cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
    return cur.fetchone() is not None

# --- Učitavanje CSV-a i ubacivanje u tabelu preduzeca ---
with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for i, row in enumerate(reader, 1):
        try:
            ime = row['ime'].strip() if row['ime'] else ''
            adresa = row['adresa'].strip() if row['adresa'] else ''
            vlasnik = parse_int(row['vlasnik'], default=0)
            
            # Provera da li vlasnik postoji u users
            if not check_user_exists(vlasnik):
                print(f"⚠️ Red {i} preskočen jer vlasnik (id={vlasnik}) ne postoji u users.")
                continue

            istek_pretplate = parse_date_str(row.get('istek_pretplate'), default=None)
            radno_vreme = parse_json_field(row, 'radno_vreme')
            duzina_termina = parse_json_field(row, 'duzina_termina')
            overlapLimit = parse_int(row.get('overlapLimit'), default=1)
            
            cur.execute("""
                INSERT INTO preduzeca (
                    created_at, ime, vlasnik, adresa, istek_pretplate,
                    radno_vreme, duzina_termina, overlapLimit
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                ime,
                vlasnik,
                adresa,
                istek_pretplate,
                radno_vreme,
                duzina_termina,
                overlapLimit
            ))
        except Exception as e:
            print(f"Red {i} nije ubačen. Greška: {e}")
            conn.rollback()
        else:
            conn.commit()

cur.close()
conn.close()

print("Migracija završena ✅")