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


def get_ai_usage_from_db(owner_id, db):
    """
    Dohvata AI usage iz baze - users.ai_usage kolona (JSONB)
    
    Returns:
    {
        "owner": {"llama4": 0, "Mistral-24b": 0, "GPT-OSS20B": 0},
        "employees": {...},
        "bookings": {...}
    }
    """
    try:
        user_query = text("SELECT ai_usage FROM users WHERE id = :id")
        user_result = db.session.execute(user_query, {'id': int(owner_id)}).fetchone()
        
        if not user_result:
            print(f"❌ Korisnik {owner_id} nije pronađen")
            return get_default_usage()
        
        ai_usage = user_result[0]
        
        # Ako je NULL ili prazan, vrati default
        if not ai_usage:
            return get_default_usage()
        
        # Ako je već dict (iz JSONB), vrati ga
        if isinstance(ai_usage, dict):
            return ai_usage
        
        # Ako je string, parsuj
        if isinstance(ai_usage, str):
            return json.loads(ai_usage)
        
        return get_default_usage()
        
    except Exception as e:
        print(f"❌ Greška pri čitanju ai_usage iz baze: {str(e)}")
        return get_default_usage()


def get_default_usage():
    """Default struktura za AI usage"""
    return {
        "owner": {"llama4": 0, "Mistral-24b": 0, "Qwen-3.5": 0, "GPT-OSS20B": 0},
        "employees": {"llama4": 0, "Mistral-24b": 0, "Qwen-3.5": 0, "GPT-OSS20B": 0},
        "bookings": {"llama4": 0, "Mistral-24b": 0, "Qwen-3.5": 0, "GPT-OSS20B": 0}
    }


def update_ai_usage_in_db(owner_id, usage_data, db):
    """
    Ažurira AI usage u bazi - users.ai_usage kolona (JSONB)
    """
    try:
        update_query = text("UPDATE users SET ai_usage = :usage WHERE id = :id")
        db.session.execute(update_query, {
            'id': int(owner_id),
            'usage': json.dumps(usage_data)
        })
        db.session.commit()
        print(f"✅ AI usage ažuriran u bazi za owner_id={owner_id}")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"❌ Greška pri ažuriranju ai_usage u bazi: {str(e)}")
        return False


def check_and_select_model(user_type, limits, usage, llm_switch):
    """
    Proverava limite i određuje koji model treba da se koristi.
    
    "default": birira se od gore na dole (best-first) - llama4 → Mistral-24b → GPT-OSS20B
    "jeftin": bira se od dole na gore (cheap-first) - GPT-OSS20B → Mistral-24b → llama4
    
    Args:
    - user_type: "owner" | "employees" | "bookings"
    - limits: struktura limitacija za taj tip korisnika
    - usage: struktura trenutne upotrebe
    - llm_switch: "default" | "jeftin"
    
    Returns:
    {
        "allowed": True/False,
        "model": "llama4" | "Mistral-24b" | "GPT-OSS20B" | None,
        "error": "poruka greške" | None
    }
    """
    user_limits = limits.get(user_type, {})
    user_usage = usage.get(user_type, {})
    
    # Định redosled modela
    if llm_switch == "jeftin":
        # Jeftin mode: od jeftinog ka skupom
        model_order = ["GPT-OSS20B", "Qwen-3.5", "Mistral-24b", "llama4"]
    else:  # default
        # Default mode: od skupog ka jeftinom
        model_order = ["llama4", "Mistral-24b", "Qwen-3.5", "GPT-OSS20B"]
    
    # Proveri svaki model u redosledu
    for model in model_order:
        model_limit = user_limits.get(model, 0)
        model_used = user_usage.get(model, 0)
        
        if model_used < model_limit:
            print(f"✅ Model dostupan: {model} (korišćeno: {model_used}/{model_limit})")
            return {
                "allowed": True,
                "model": model,
                "error": None
            }
        else:
            print(f"⚠️  Model iskorišćen: {model} (limit: {model_limit})")
    
    # Nijedan model nije dostupan
    return {
        "allowed": False,
        "model": None,
        "error": "Svi dostupni modeli su iskorišćeni. Pokušajte kasnije."
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
    
    # KORAK 3: Dohvati AI upotrebu vlasnika iz baze (JSONB)
    ai_usage = get_ai_usage_from_db(owner_id, db)
    
    # DEBUG ispis
    print(f"\n📋 DEBUG - AI LIMITER INFO:")
    print(f"  original_user_id: {user_id}, rola: {rola}")
    print(f"  owner_id (gde se piše usage): {owner_id}")
    print(f"  user_type (tip limitacije): {user_type}")
    print(f"  llm_switch: {llm_switch}")
    user_limits = limits.get(user_type, {})
    user_usage = ai_usage.get(user_type, {})
    print(f"  limits[{user_type}]: {user_limits}")
    print(f"  usage[{user_type}]: {user_usage}")
    print()
    
    # KORAK 4: Proveri i odaberi model
    result = check_and_select_model(user_type, limits, ai_usage, llm_switch)
    
    if result["allowed"]:
        # Inkrementira brojač za odgovajući tip korisnika
        model = result["model"]
        ai_usage[user_type][model] += 1
        
        # Čuva u bazi (JSONB kolona) vlasniku (owner_id)
        update_ai_usage_in_db(owner_id, ai_usage, db)
        
        user_type_label = {"owner": "Vlasnik", "employees": "Zaposlenik", "bookings": "Zakazivač"}.get(user_type, "Korisnik")
        print(f"✅ AI usage inkrementiran: {user_type_label}/{model} (owner_id: {owner_id}, original_user_id: {user_id})")
    
    # Dodaj owner_id u rezultat
    result["owner_id"] = owner_id
    
    return result
