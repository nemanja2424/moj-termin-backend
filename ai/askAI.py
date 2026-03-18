from dotenv import load_dotenv
from together import Together
from datetime import datetime
import json
import os

load_dotenv()
client = Together()


# Mapping od skraćenih imena na pune model zvanične nazive
MODEL_NAMES = {
    "llama3": "mistralai/Mistral-Small-24B-Instruct-2501",
    #"llama3": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
    "llama4": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
}

USAGE_FILE_PATH = os.path.join(os.path.dirname(__file__), "ai_usage", "sumUsage.json")

def update_token_usage(prompt_tokens, completion_tokens, model="llama4"):
    """Ažurira sumUsage.json sa informacijama o potrošnji tokena"""
    try:
        # Provjeri da li fajl postoji
        if not os.path.exists(USAGE_FILE_PATH):
            print(f"📝 Kreiram novi sumUsage.json...")
            # Kreiraj direktorijum ako ne postoji
            os.makedirs(os.path.dirname(USAGE_FILE_PATH), exist_ok=True)
            # Kreiraj template fajl
            template_data = {
                "sum": {
                    "total_token_usage": 0,
                    "entry_token_usage": 0,
                    "generated_token_usage": 0,
                    "total_req": 0
                },
                "models": {
                    "llama3": {
                        "total_tokens": 0,
                        "entry_tokens": 0,
                        "generated_tokens": 0,
                        "requests": 0
                    },
                    "llama4": {
                        "total_tokens": 0,
                        "entry_tokens": 0,
                        "generated_tokens": 0,
                        "requests": 0
                    }
                },
                "history": []
            }
            with open(USAGE_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=4, ensure_ascii=False)
            data = template_data
        else:
            # Pročitaj postojeću datoteku
            with open(USAGE_FILE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        total_tokens = prompt_tokens + completion_tokens
        
        # Ažuriraj sum
        data["sum"]["total_token_usage"] += total_tokens
        data["sum"]["entry_token_usage"] += prompt_tokens
        data["sum"]["generated_token_usage"] += completion_tokens
        data["sum"]["total_req"] += 1
        
        # Ažuriraj brojeve za specifičan model
        if model not in data["models"]:
            data["models"][model] = {
                "total_tokens": 0,
                "entry_tokens": 0,
                "generated_tokens": 0,
                "requests": 0
            }
        
        data["models"][model]["total_tokens"] += total_tokens
        data["models"][model]["entry_tokens"] += prompt_tokens
        data["models"][model]["generated_tokens"] += completion_tokens
        data["models"][model]["requests"] += 1
        
        # Dodaj novu entry u history
        data["history"].append({
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "entry_token_usage": prompt_tokens,
            "generated_token_usage": completion_tokens
        })
        
        # Sačuvaj ažurirani fajl
        with open(USAGE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        print(f"\n✅ TOKENI LOGOVANI:")
        print(f"   📥 Ulazni tokeni: {prompt_tokens}")
        print(f"   📤 Generisani tokeni: {completion_tokens}")
        print(f"   🤖 Model: {model.upper()}")
        
    except Exception as e:
        print(f"❌ Greška pri loganju tokena: {e}")

def askAI(kontekst, poruke, pitanje, model="llama4"):
    """
    AI asistent sa RAG kontekstom
    
    Args:
        kontekst (str): Relevantni podaci iz RAG sistema (tekst, ne JSON)
        poruke (list): Prethodne poruke u razgovoru
        pitanje (str): Trenutno pitanje korisnika
        model (str): Koji model koristiti ('llama3' ili 'llama4')
    """
    today = datetime.today()
    
    # Kontekst je već tekst od RAG sistema, koristi ga direktno
    formatted_data = kontekst
    
    # SYSTEM PROMPT za llama4 - kompletan sa svih mogućnostima
    system_content = """
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
        - Dobio si sve podatke koji postoje, ništa ne fali

        Korisnicima omogućava da podese firmu, lokacije i radno vreme, dodaju zaposlene i upravljaju terminima iz admin panela.
        Priručnik pokriva:
        Prve korake: osnovna podešavanja firme, lokacija i zaposlenih
        Upravljanje terminima: pregled, potvrda, izmena i otkazivanje termina
        Zakazivanje: kako klijenti zakazuju termine i kako se sprečava preklapanje
        Pretplate: paketi, ograničenja i obnova
        Obaveštenja: automatski emailovi pri zakazivanju i promenama termina
        URL za uputsvo: "https://mojtermin.site/pomoc"

        GRAFICI I VIZUELIZACIJA:
        Kada trebaju da prikazeš analizu sa graficima, koristi sledeći format:

        [CHART]{
          "type": "bar|line|pie",
          "title": "Naslov grafikona",
          "data": [{"key": "value", ...}, ...],
          "xKey": "kolona_za_x_osu",
          "yKey": "kolona_za_y_osu"
        }[/CHART]

        Primer - Broj termina po danu:
        [CHART]{
          "type": "bar",
          "title": "Broj termina po danu",
          "data": [
            {"date": "2026-02-13", "count": 1},
            {"date": "2026-02-18", "count": 8},
            {"date": "2026-02-20", "count": 8}
          ],
          "xKey": "date",
          "yKey": "count"
        }[/CHART]

        Primer - Distribucija zaposlenih (pie chart):
        [CHART]{
          "type": "pie",
          "title": "Distribucija termina po zaposlenom",
          "data": [
            {"name": "Marko", "value": 15},
            {"name": "Ana", "value": 22}
          ],
          "xKey": "name",
          "yKey": "value"
        }[/CHART]

        Koristi grafike kada:
        - Analiziruješ trendove termina po vremenskog perioda
        - Prikazuješ distribuciju (zaposleni, usluge, itd)
        - Poređuješ vrednosti (zarada, termini, itd)
        - Prikazuješ progrese i statistiku

        Uvek dodaj tekstualni opis IZ PODATAKA pre i/ili posle grafikona.

        AGENT PROPOSAL:
        Kada korisnik traži akciju, generiši samo radnju i poruku:

        [agent_proposal]
        {
          "radnja": "kreiranje|izmena|otkazivanje|potvrdjivanje",
          "poruka": "Opis šta radiš",
          "body": {
            "ime": [ime iz podataka], "email": [email iz podataka], "telefon": [telefon iz podataka],
            datum_rezervacije: "2026-02-13", "vreme": "08:00", duzina_termina: [trajanje iz podataka]
            "lokacija": [iskljucivo ID, ne ime. iz podataka], "token": [token iz podataka], "opis": [opis iz podataka]
            "potvrdio": [id korisnika ili null]
          }
        }
        [/agent_proposal]
        Nikada ne prikazujes JSON

        Obavezni podaci:
        - Ime
        - email
        - datum
        - vreme 
        - duzina trajanja
        - Lokacija
        
        AGENT PROPOSAL pises tek kada korisnik unese sve ove podatke.
        Ako ne unese naglasi mu da mora da ih unese.

        Popuni sva polja podacima koji su ti dostavljeni, ne izostavljaj nista, ostala ostavljaju null.
        Nema mogucnosti za bulk radnje.
        Nakon kreiranja termina, token se kreira u backend-u i korisnik ako hoce da menja taj termin mora da napravi novi chat.
    """
    
    # Izgradi messages niz sa sistemskim instrukcijama
    messages = [
        {
            "role": "system",
            "content": system_content
        },
        {
            "role": "system",
            "content": f"PODACI FIRME:\n{formatted_data}\n\nDanasnji datum: {today}"
        }
    ]
    #print(formatted_data)
    # Dodaj prethodne poruke (conversation history)
    messages.extend(poruke)
    
    # Dodaj novo pitanje korisnika
    messages.append({
        "role": "user",
        "content": pitanje
    })
    
    # Dobij puni naziv modela
    full_model_name = MODEL_NAMES.get(model, MODEL_NAMES["llama4"])
    
    print(f"\n🤖 AI ZAHTEV - Model: {model.upper()} ({full_model_name})")
    print(f"💬 Pitanje: {pitanje[:80]}...")
    print(f"📊 Broj prethodnih poruka: {len(poruke)}")
    print()

    # Pozovi LLM - Together API compatibility
    try:
        # Pokušaj sa OpenAI-style API (novija verzija Together)
        response = client.chat.completions.create(
            model=full_model_name,
            messages=messages,
            temperature=0.2,
        )
    except AttributeError:
        # Fallback na direktnu Together API verziju
        response = client.complete(
            model=full_model_name,
            prompt=f"System: {messages[0]['content']}\n\nContext: {messages[1]['content']}\n\nUser: {messages[-1]['content']}",
            max_tokens=1000,
            temperature=0.2,
        )
        # Vrati samo tekst odgovora
        return response[0].get('output', response[0].get('text', ''))
    
    # Izvuci informacije o potrošnji tokena
    if hasattr(response, 'usage') and response.usage:
        try:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            update_token_usage(prompt_tokens, completion_tokens, model)
        except Exception as e:
            print(f"⚠️  Greška pri ekstraktovanju tokena: {e}")
    
    return response.choices[0].message.content
