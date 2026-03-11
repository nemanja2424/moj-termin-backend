import os
import json
from dotenv import load_dotenv
from together import Together
import requests
from datetime import date

# Load env vars
load_dotenv()

# Together client (uzima TOGETHER_API_KEY automatski)
client = Together()

# Xano
XANO_API = "https://x8ki-letl-twmt.n7.xano.io/api:YgSxZfYk/zakazivanja/1"
XANO_TOKEN = os.getenv("XANO_TOKEN")  # ⬅️ PREPORUKA: stavi u .env

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {XANO_TOKEN}"
}

xano_response = requests.get(XANO_API, headers=headers)

if xano_response.status_code != 200:
    raise Exception(f"Xano error {xano_response.status_code}: {xano_response.text}")

data = xano_response.json()

# Formatiran JSON za LLM
formatted_data = json.dumps(data, indent=2, ensure_ascii=False)
today = date.today()
pitanje = "Zašto mi je sledeća nedelja skoro puna?"

response = client.chat.completions.create(
    model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
    messages=[
        {
            "role": "system",
            "content": """
                Ti si AI asistent za mojtermin.site.

                Tvoj zadatak je da pomažeš vlasnicima firmi u donošenju odluka
                na osnovu TAČNO prosleđenih podataka u JSON formatu.

                Pravila:
                - Koristi isključivo podatke iz JSON-a
                - Ako podatak ne postoji, jasno to reci
                - Ne nagađaj i ne izmišljaj
                - Predlaži optimizacije samo ako postoji osnova u podacima
                - Govori jasno i prijateljski
                - Ne spominji ID-jeve i JSON
                - Dobio si sve podatke koji postoje, nista ne fali
            """
        },
        {
            "role": "system",
            "content": f"PODACI FIRME:\n{formatted_data}\nDanasnji datum: {today}"
        },
        {
            "role": "user",
            "content": pitanje
        }
    ],
    temperature=0.2
)


print(response.choices[0].message.content)
print(response)