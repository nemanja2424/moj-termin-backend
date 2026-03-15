import csv
import psycopg2
import json
from datetime import datetime

# --- Podesi konekciju ---
conn = psycopg2.connect(
    dbname="Test",           # ime tvoje baze
    user="postgres",         # tvoj korisnički nalog
    password="nemanja123",   # lozinka za PostgreSQL
    host="localhost",        # lokalni server
    port="5432"
)
cur = conn.cursor()

# --- Unos putanje do CSV fajla od korisnika ---
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

def parse_bool(row, field):
    """Parsira boolean polja"""
    val = row[field].strip().lower() if row[field] else "false"
    return True if val == "true" else False

def parse_timestamp(val, default=None):
    """Pretvara UNIX timestamp u milisekundama u datetime za PostgreSQL"""
    if not val:
        return default
    try:
        ts = int(val)
        if ts > 10**10:  # ako je u milisekundama
            ts = ts / 1000
        return datetime.fromtimestamp(ts)
    except:
        return default

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

# --- Učitavanje CSV-a i ubacivanje u tabelu ---
with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for i, row in enumerate(reader, 1):
        try:
            radnoVreme = parse_json_field(row, 'radnoVreme')
            trajanje = parse_json_field(row, 'trajanje')
            forma = parse_json_field(row, 'forma')
            obavestenja = parse_json_field(row, 'obavestenja')
            ai_info = parse_json_field(row, 'ai_info')
            paket_limits = parse_json_field(row, 'paket_limits')

            gratis = parse_bool(row, 'gratis')
            odobren = parse_bool(row, 'odobren')

            istek_pretplate = parse_date_str(row['istek_pretplate'], default=None)
            created_at = parse_timestamp(row['created_at'], default=datetime.now())

            cur.execute("""
                INSERT INTO users (
                    username, email, brTel, password, rola, paket, gratis, zaposlen_u, 
                    istek_pretplate, odobren, ime_preduzeca, putanja_za_logo, 
                    radnoVreme, trajanje, forma, obavestenja, ai_info, opis, paket_limits, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                row['username'],
                row['email'],
                row['brTel'],
                row['password'],
                int(row['rola']) if row['rola'] else 0,
                row['paket'] if row['paket'] else 'Personalni',
                gratis,
                int(row['zaposlen_u']) if row['zaposlen_u'] else 0,
                istek_pretplate,
                odobren,
                row['ime_preduzeca'],
                row['putanja_za_logo'] if row['putanja_za_logo'] else '/Images/logo.webp',
                radnoVreme,
                trajanje,
                forma,
                obavestenja,
                ai_info,
                row['opis'] if row['opis'] else '',
                paket_limits,
                created_at
            ))
        except Exception as e:
            print(f"Red {i} nije ubačen. Greška: {e}")
            conn.rollback()
        else:
            conn.commit()

cur.close()
conn.close()

print("Migracija završena ✅")