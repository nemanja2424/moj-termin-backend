import json
import os
from datetime import datetime
import requests
from sqlalchemy import text


def get_owner_id_from_user(user_id, ai_info_data):
    """
    Određuje ID vlasnika na osnovu user_id i ai_info podataka.
    
    Xano endpoint /ai/info/{user_id} vraća:
    {
        "id": owner_id,
        "ai_info": {...}
    }
    
    Returns: owner_id (ID vlasnika/poslodavca)
    """
    return ai_info_data.get('id', user_id)


def get_user_type(user_id, owner_id):
    """
    Određuje tip korisnika na osnovu upoređivanja user_id sa owner_id.
    
    - Ako je user_id == owner_id, korisnik je vlasnik
    - U suprotnom, korisnik je zaposlenik
    
    Returns: "owner" | "employees"
    """
    if user_id == owner_id:
        return "owner"
    else:
        return "employees"


def get_ai_info(user_id, db):
    """
    Dohvata kompletan ai_info objekat iz baze podataka.
    
    Vraća:
    {
        "id": owner_id,
        "ai_info": {
            "limits": {
                "owner": {"llama3": int, "llama4": int},
                "employees": {"llama3": int, "llama4": int},
                "bookings": {"llama3": int, "llama4": int}
            },
            "llm-switch": "default" | "jeftin"
        }
    }
    """
    try:
        from sqlalchemy import text
        
        # Konvertuj user_id u integer ako je string
        user_id = int(user_id)
        
        # Dohvati korisnika iz baze
        user_query = text("""
            SELECT id, ai_info FROM users WHERE id = :id
        """)
        user_result = db.session.execute(user_query, {'id': user_id}).fetchone()
        
        if not user_result:
            print(f"❌ Korisnik {user_id} nije pronađen")
            return None
        
        # Parseri ai_info
        ai_info = user_result[1]
        if isinstance(ai_info, str):
            ai_info = json.loads(ai_info) if ai_info else {}
        elif not isinstance(ai_info, dict):
            ai_info = {}
        
        # Vrati u istoj strukturi kao Xano
        return {
            "id": user_result[0],
            "ai_info": ai_info
        }
    except Exception as e:
        print(f"❌ Greška pri dohvatanju ai_info iz baze: {str(e)}")
        return None


def get_daily_usage(owner_id, date=None):
    """
    Dohvata dnevnu upotrebu AI-ja iz JSON fajla.
    
    Returns:
    {
        "owner": {"llama3": int, "llama4": int},
        "employees": {"llama3": int, "llama4": int},
        "bookings": {"llama3": int, "llama4": int}
    }
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    file_path = f'ai/ai_usage/{owner_id}/{date}.json'
    
    # Default struktura
    default_usage = {
        "owner": {"llama3": 0, "llama4": 0},
        "employees": {"llama3": 0, "llama4": 0},
        "bookings": {"llama3": 0, "llama4": 0}
    }
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Greška pri čitanju ai_usage: {str(e)}")
            return default_usage
    
    return default_usage


def save_daily_usage(owner_id, usage_data, date=None):
    """
    Čuva dnevnu upotrebu AI-ja u JSON fajl.
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    dir_path = f'ai/ai_usage/{owner_id}'
    file_path = f'{dir_path}/{date}.json'
    
    # Kreiraj direktorijum ako ne postoji
    os.makedirs(dir_path, exist_ok=True)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(usage_data, f, indent=2, ensure_ascii=False)
        print(f"✅ AI usage sačuvan: {file_path}")
        return True
    except Exception as e:
        print(f"❌ Greška pri čuvanju ai_usage: {str(e)}")
        return False


def check_and_select_model(user_type, limits, usage, llm_switch):
    """
    Proverava limite i određuje koji model treba da se koristi.
    
    Args:
    - user_type: "owner" | "employees" | "bookings"
    - limits: struktura limitacija za taj tip korisnika
    - usage: struktura trenutne upotrebe
    - llm_switch: "default" | "skup" | "jeftin"
    
    Returns:
    {
        "allowed": True/False,
        "model": "llama3" | "llama4" | None,
        "error": "poruka greške" | None
    }
    """
    user_limits = limits.get(user_type, {})
    user_usage = usage.get(user_type, {"llama3": 0, "llama4": 0})
    
    llama3_limit = user_limits.get('llama3', 0)
    llama4_limit = user_limits.get('llama4', 0)
    
    llama3_used = user_usage.get('llama3', 0)
    llama4_used = user_usage.get('llama4', 0)
    
    # Provera dostupnosti
    llama3_available = llama3_used < llama3_limit
    llama4_available = llama4_used < llama4_limit
    
    if llm_switch == "default":
        # Prvo pokušaj llama4, ako nije dostupan, koristi llama3
        if llama4_available:
            return {
                "allowed": True,
                "model": "llama4",
                "error": None
            }
        elif llama3_available:
            return {
                "allowed": True,
                "model": "llama3",
                "error": None
            }
        else:
            return {
                "allowed": False,
                "model": None,
                "error": "Svi dostupni modeli su iskorišćeni za danas"
            }
    
    elif llm_switch == "skup":
        # Koristi samo llama4
        if llama4_available:
            return {
                "allowed": True,
                "model": "llama4",
                "error": None
            }
        else:
            return {
                "allowed": False,
                "model": None,
                "error": "Plaćeni model je iskorišćen za danas"
            }
    
    elif llm_switch == "jeftin":
        # Koristi samo llama3
        if llama3_available:
            return {
                "allowed": True,
                "model": "llama3",
                "error": None
            }
        else:
            return {
                "allowed": False,
                "model": None,
                "error": "Besplatan model je iskorišćen za danas"
            }
    
    return {
        "allowed": False,
        "model": None,
        "error": "Nepoznat llm_switch"
    }


def check_and_increment_ai_usage(user_id, rola, db):
    """
    Glavna funkcija koja:
    1. Odredi owner_id na osnovu role:
       - rola=1 (VLASNIK): owner_id = user_id
       - rola=2 (ZAPOSLENIK): owner_id = vlasnik od firme gde radi (iz zaposlen_u)
       - rola=3 (ZAKAZIVAC): owner_id treba iz payload-a, ovde pretpostavljamo da je prosleđen
    2. Dohvata ai_info iz baze
    3. Dohvata dnevnu upotrebu vlasnika
    4. Proverava limite
    5. Određuje model
    6. Inkrementira odgovarajući brojač
    7. Čuva dnevnu upotrebu u JSON
    
    Returns:
    {
        "allowed": True/False,
        "model": "llama3" | "llama4" | None,
        "error": "poruka greške" | None
    }
    """
    
    # KORAK 1: Odredi owner_id na osnovu role
    owner_id = user_id  # Default
    user_type = "owner"  # Default
    
    if rola == 1:
        # VLASNIK - owner_id je sam user_id
        owner_id = user_id
        user_type = "owner"
        print(f"👑 VLASNIK (rola={rola}): owner_id={owner_id}")
    
    elif rola == 2:
        # ZAPOSLENIK - pronađi vlasnika firme gde radi
        try:
            zaposlenik_query = text("SELECT zaposlen_u FROM users WHERE id = :id")
            zaposlenik_result = db.session.execute(zaposlenik_query, {'id': int(user_id)}).fetchone()
            
            if zaposlenik_result and zaposlenik_result[0] > 0:
                firma_id = zaposlenik_result[0]
                
                # Pronađi vlasnika te firme
                firma_query = text("SELECT vlasnik FROM preduzeca WHERE id = :id")
                firma_result = db.session.execute(firma_query, {'id': int(firma_id)}).fetchone()
                
                if firma_result:
                    owner_id = firma_result[0]
                    user_type = "employees"
                    print(f"👤 ZAPOSLENIK (rola={rola}): firma_id={firma_id}, owner_id={owner_id}")
        except Exception as e:
            print(f"❌ Greška pri pronalaženju vlasnika: {str(e)}")
            owner_id = user_id
    
    elif rola == 3:
        # ZAKAZIVAC - usage ide vlasniku firme u kojoj se zakazuje
        # owner_id bi trebalo biti u payload-u kao vlasnik_id
        # Za sada, koristi user_id
        owner_id = user_id
        user_type = "bookings"
        print(f"📅 ZAKAZIVAC (rola={rola}): owner_id={owner_id}")
    
    # KORAK 2: Dohvati ai_info iz baze za vlasnika
    ai_info_data = get_ai_info(owner_id, db)
    if not ai_info_data:
        return {
            "allowed": False,
            "model": None,
            "error": "Nije moguće dohvatiti AI informacije"
        }
    
    ai_info = ai_info_data.get('ai_info', {})
    
    # Ekstraktuj limite i llm-switch
    limits = ai_info.get('limits', {})
    llm_switch = ai_info.get('llm-switch', 'default')
    
    # KORAK 3: Dohvati dnevnu upotrebu vlasnika
    daily_usage = get_daily_usage(owner_id)
    
    # DEBUG ispis
    print(f"\n📋 DEBUG - AI LIMITER INFO:")
    print(f"  original_user_id: {user_id}, rola: {rola}")
    print(f"  owner_id (gde se piše usage): {owner_id}")
    print(f"  user_type (tip limitacije): {user_type}")
    print(f"  llm_switch: {llm_switch}")
    user_limits = limits.get(user_type, {})
    user_usage = daily_usage.get(user_type, {})
    print(f"  limits[{user_type}]: {user_limits}")
    print(f"  usage[{user_type}]: {user_usage}")
    print()
    
    # KORAK 4: Proveri i odaberi model
    result = check_and_select_model(user_type, limits, daily_usage, llm_switch)
    
    if result["allowed"]:
        # Inkrementira brojač za odgovajući tip korisnika
        model = result["model"]
        daily_usage[user_type][model] += 1
        
        # Čuva u JSON vlasniku (owner_id)
        save_daily_usage(owner_id, daily_usage)
        
        user_type_label = {"owner": "Vlasnik", "employees": "Zaposlenik", "bookings": "Zakazivač"}.get(user_type, "Korisnik")
        print(f"✅ AI usage inkrementiran: {user_type_label}/{model} (owner_id: {owner_id}, original_user_id: {user_id})")
    
    # Dodaj owner_id u rezultat
    result["owner_id"] = owner_id
    
    return result
