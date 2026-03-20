from dotenv import load_dotenv
import os
from datetime import datetime
import json

# Together 2.4.0 API
from together import Together

load_dotenv()

# Inicijalizuj Together klijent sa API ključem iz .env
api_key = os.getenv("TOGETHER_API_KEY")
client = Together(api_key=api_key)


# Mapping od skraćenih imena na pune model zvanične nazive
MODEL_NAMES = {
    "llama3": "mistralai/Mistral-Small-24B-Instruct-2501",
    #"llama3": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
    "llama4": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
}

USAGE_FILE_PATH = os.path.join(os.path.dirname(__file__), "ai_usage", "sumUsage.json")

def update_token_usage(prompt_tokens, completion_tokens, model="llama4", user_id=None, owner_id=None):
    """Ažurira sumUsage.json sa informacijama o potrošnji tokena + ID korisnika"""
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
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "entry_token_usage": prompt_tokens,
            "generated_token_usage": completion_tokens
        }
        
        # Dodaj user_id i owner_id ako su dostupni
        if user_id is not None:
            history_entry["user_id"] = user_id
        if owner_id is not None:
            history_entry["owner_id"] = owner_id
        
        data["history"].append(history_entry)
        
        # Sačuvaj ažurirani fajl
        with open(USAGE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        print(f"\n✅ TOKENI LOGOVANI:")
        print(f"   📥 Ulazni tokeni: {prompt_tokens}")
        print(f"   📤 Generisani tokeni: {completion_tokens}")
        print(f"   🤖 Model: {model.upper()}")
        
    except Exception as e:
        print(f"❌ Greška pri loganju tokena: {e}")

def askAI(kontekst, poruke, pitanje, model="llama4", user_id=None, owner_id=None):
    """
    AI asistent sa RAG kontekstom
    
    Args:
        kontekst (str): Relevantni podaci iz RAG sistema (tekst, ne JSON)
        poruke (list): Prethodne poruke u razgovoru
        pitanje (str): Trenutno pitanje korisnika
        model (str): Koji model koristiti ('llama3' ili 'llama4')
        user_id (int): ID korisnika koji postavlja pitanje
        owner_id (int): ID vlasnika (gde se piše usage)
    """
    today = datetime.today()
    
    # Kontekst je već tekst od RAG sistema, koristi ga direktno
    formatted_data = kontekst
    
    # SYSTEM PROMPT za llama4 - kompletan sa svih mogućnostima
    system_content = """
        Ja sam vlasnik, a ti moj asistent na mojtermin.site

        Pravila:
        - Koristi SAMO podatke koji su ti dostupni ispod
        - Ako neka specifična vrednost nedostaje, jasno to reci
        - Ne nagađaj i ne izmišljaj
        - Podatke analiziraj iz tekstualnog formata sa | kao razdelnicima
        - Govori jasno i prijateljski
        - Ne spominji ID-jeve, pipe-razdelnice ili tehnijske detalje
        - Dobio si sve podatke koji postoje, ništa ne fali

        mojtermin.site opis:
        Korisnicima omogućava da podese firmu, lokacije i radno vreme, dodaju zaposlene i upravljaju terminima iz korisničkog panela.
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

        Koristi grafike kada:
        - Analiziruješ trendove termina po vremenskog perioda
        - Prikazuješ distribuciju (zaposleni, usluge, itd)
        - Poređuješ vrednosti (zarada, termini, itd)
        - Prikazuješ progrese i statistiku

        Uvek dodaj tekstualni opis IZ PODATAKA pre i/ili posle grafikona.

        AGENT PROPOSAL:
        Kada korisnik traži akciju, generiši samo radnju i detaljnu poruku sta si uradio:

        [agent_proposal]
        {
          "radnja": "kreiranje|izmena|otkazivanje|potvrdjivanje",
          "poruka": "Opis šta radiš",
          "body": {
            "ime": [ime iz podataka], "email": [email iz podataka], "telefon": [telefon iz podataka],
            datum_rezervacije: "2026-02-13", "vreme": "08:00",
            "usluga": {'cena': [cena odabrane usluga], 'usluga': [usluga koju korisnik bira], 'trajanje': [trajanje odabrane usluge u min, (INT npr. 60)], 'trajanje_prikaz': [trajanje za prikaz odabrane usluge (String)]}
            "lokacija": [iskljucivo ID, ne ime. iz podataka], "token": [token iz podataka], "opis": [opis iz podataka]
            "potvrdio": [id korisnika ili null]
          }
        }
        [/agent_proposal]

        Obavezni podaci:
        - Ime
        - email
        - datum
        - vreme 
        - usluga
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
            "content": f"{system_content} \nPODACI FIRME:\n{formatted_data}\n\nDanasnji datum: {today}"
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
    
    print(f"\n🤖 AI ZAHTEV - Model: {model.upper()}\n")
    #print(json.dumps(messages, indent=2, ensure_ascii=False))
    print(f"\n📤 Slanje zahteva Together AI ({full_model_name})...")
    print()
    
    try:
        response = client.chat.completions.create(
            model=full_model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=1024
        )
        
        # Izvuci odgovor
        answer = response.choices[0].message.content
        
        # Izvuci informacije o potrošnji tokena ako postoje
        if hasattr(response, 'usage') and response.usage:
            try:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                update_token_usage(prompt_tokens, completion_tokens, model, owner_id)
            except Exception as e:
                print(f"⚠️  Greška pri ekstraktovanju tokena: {e}")
        
        return answer
        
    except Exception as e:
        print(f"❌ Together API greška: {str(e)}")
        raise
