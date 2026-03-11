import os
import requests

# Putanja do foldera gde su logo fajlovi
LOGOS_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'public', 'logos')

# API endpoint
API_URL = 'https://x8ki-letl-twmt.n7.xano.io/api:YgSxZfYk/alati/obrisi-logotipe'

def get_logo_filenames_from_api():
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()
        # Izdvajamo samo fajl imena iz putanja (npr. 'betting.jpeg' iz '/logos/betting.jpeg')
        filenames = set(
            os.path.basename(entry['putanja_za_logo'])
            for entry in data
            if entry['putanja_za_logo'] and '/logos/' in entry['putanja_za_logo']
        )
        return filenames
    except Exception as e:
        print("Greška prilikom poziva API-ja:", e)
        return set()

def obrisi_nepotrebne_fajlove():
    valid_filenames = get_logo_filenames_from_api()
    print("Fajlovi koji treba da ostanu:", valid_filenames)

    if not os.path.exists(LOGOS_FOLDER):
        print(f"Folder ne postoji: {LOGOS_FOLDER}")
        return

    for filename in os.listdir(LOGOS_FOLDER):
        file_path = os.path.join(LOGOS_FOLDER, filename)
        if os.path.isfile(file_path) and filename not in valid_filenames:
            try:
                os.remove(file_path)
                print(f"Obrisan fajl: {filename}")
            except Exception as e:
                print(f"Greška prilikom brisanja fajla {filename}: {e}")

if __name__ == '__main__':
    obrisi_nepotrebne_fajlove()
