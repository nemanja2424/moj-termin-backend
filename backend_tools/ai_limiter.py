import json
import os
from datetime import datetime
import requests


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


def get_ai_info(user_id, auth_token):
    """
    Dohvata kompletan ai_info objekat iz Xano-a.
    
    Xano vraća:
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
    
    Returns: kompletna struktura sa "id" i "ai_info"
    """
    try:
        url = f'https://x8ki-letl-twmt.n7.xano.io/api:YgSxZfYk/ai/info/{user_id}'
        response = requests.get(
            url,
            headers={
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            # Vraća kompletan objekat sa "id" i "ai_info"
            return data
        else:
            print(f"❌ Greška pri dohvatanju ai/info: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Greška pri dohvatanju ai_info: {str(e)}")
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
    
    file_path = f'backend_tools/ai_usage/{owner_id}/{date}.json'
    
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
    
    dir_path = f'backend_tools/ai_usage/{owner_id}'
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


def check_and_increment_ai_usage(user_id, auth_token):
    """
    Glavna funkcija koja:
    1. Dohvata ai_info sa Xano-a (sadrži "id" vlasnika i "ai_info" strukturu)
    2. Određuje tip korisnika (owner ili employee)
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
    
    # Dohvati ai_info iz Xano-a (sadrži "id" i "ai_info")
    ai_info_data = get_ai_info(user_id, auth_token)
    if not ai_info_data:
        return {
            "allowed": False,
            "model": None,
            "error": "Nije moguće dohvatiti AI informacije"
        }
    
    # Ekstraktuj owner_id (ID vlasnika) i ai_info strukturu
    owner_id = get_owner_id_from_user(user_id, ai_info_data)
    ai_info = ai_info_data.get('ai_info', {})
    
    # Određuj tip korisnika
    user_type = get_user_type(user_id, owner_id)
    
    # Ekstraktuj limite i llm-switch
    limits = ai_info.get('limits', {})
    llm_switch = ai_info.get('llm-switch', 'default')
    
    # Dohvati dnevnu upotrebu vlasnika
    daily_usage = get_daily_usage(owner_id)
    
    # DEBUG ispis
    print(f"\n📋 DEBUG - AI LIMITER INFO:")
    print(f"  user_id: {user_id}, owner_id: {owner_id}")
    print(f"  user_type: {user_type}")
    print(f"  llm_switch: {llm_switch}")
    user_limits = limits.get(user_type, {})
    user_usage = daily_usage.get(user_type, {})
    print(f"  limits[{user_type}]: {user_limits}")
    print(f"  usage[{user_type}]: {user_usage}")
    print()
    
    # Proveri i odaberi model
    result = check_and_select_model(user_type, limits, daily_usage, llm_switch)
    
    if result["allowed"]:
        # Inkrementira brojač za odgovajući tip korisnika
        model = result["model"]
        daily_usage[user_type][model] += 1
        
        # Čuva u JSON vlasniku (owner_id)
        save_daily_usage(owner_id, daily_usage)
        
        user_type_label = "Vlasnik" if user_type == "owner" else "Zaposlenik"
        print(f"✅ AI usage inkrementiran: {user_type_label}/{model} (owner_id: {owner_id}, user_id: {user_id})")
    
    return result
