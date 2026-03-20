#!/usr/bin/env python
"""
Skripte za provere i migracije AI sistema

Funkcionalnosti:
1. Proverava da li `users` tabela ima `ai_info` i `ai_usage` kolone
2. Kreira kolone ako nedostaju
3. Popunjava default vrednosti za postojeće korisnike
"""

import json
import sys
sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))  # Idi do root direktorijuma

from app import app, db
from sqlalchemy import text


def check_and_create_ai_columns():
    """Proverava da li postoje ai_info i ai_usage kolone, kreira ih ako nedostaju"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║      VERIFIKACIJA AI SCHEMA - USERS TABELA              ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    with app.app_context():
        try:
            # Proverite da li kolone postoje
            print("🔍 Proveravanje kolona u users tabeli...")
            
            # Za PostgreSQL - proverite information_schema
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('ai_info', 'ai_usage')
            """)
            
            result = db.session.execute(check_query).fetchall()
            existing_columns = [row[0] for row in result]
            
            print(f"   Pronađene kolone: {existing_columns if existing_columns else 'NEMA'}")
            
            # Kreiraj ai_info ako nedostaje
            if 'ai_info' not in existing_columns:
                print("\n   ❌ NEDOSTAJE kolona: ai_info")
                print("   ⚠️  Kreiram ai_info kolonu...")
                try:
                    create_ai_info = text("""
                        ALTER TABLE users 
                        ADD COLUMN ai_info JSON DEFAULT NULL
                    """)
                    db.session.execute(create_ai_info)
                    db.session.commit()
                    print("   ✅ Kolona ai_info je kreirana")
                except Exception as e:
                    print(f"   ❌ Greška pri kreiranju ai_info: {e}")
                    db.session.rollback()
            else:
                print("   ✅ Kolona ai_info postoji")
            
            # Kreiraj ai_usage ako nedostaje
            if 'ai_usage' not in existing_columns:
                print("\n   ❌ NEDOSTAJE kolona: ai_usage")
                print("   ⚠️  Kreiram ai_usage kolonu (JSONB)...")
                try:
                    # Za PostgreSQL, koristi JSONB
                    create_ai_usage = text("""
                        ALTER TABLE users 
                        ADD COLUMN ai_usage JSONB DEFAULT NULL
                    """)
                    db.session.execute(create_ai_usage)
                    db.session.commit()
                    print("   ✅ Kolona ai_usage je kreirana")
                except Exception as e:
                    print(f"   ❌ Greška pri kreiranju ai_usage: {e}")
                    db.session.rollback()
            else:
                print("   ✅ Kolona ai_usage postoji")
            
            print("\n✅ Schema verifikacija je gotova!")
            
        except Exception as e:
            print(f"\n❌ Kritična greška: {e}")
            return False
    
    return True


def populate_default_ai_info():
    """Popunjava default ai_info za sve korisnike koji nemaju postavljen"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║      POPULACIJA DEFAULT AI_INFO VREDNOSTI                ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    default_ai_info = {
        "limits": {
            "owner": {"llama4": 50, "Mistral-24b": 100, "GPT-OSS20B": 50},
            "employees": {"llama4": 2, "Mistral-24b": 500, "GPT-OSS20B": 50},
            "bookings": {"llama4": 0, "Mistral-24b": 5000, "GPT-OSS20B": 50}
        },
        "llm-switch": "default"
    }
    
    with app.app_context():
        try:
            # Pronađi sve korisnike bez ai_info
            find_empty = text("SELECT id FROM users WHERE ai_info IS NULL OR ai_info = ''")
            result = db.session.execute(find_empty).fetchall()
            user_ids = [row[0] for row in result]
            
            if not user_ids:
                print("✅ Svi korisnici već imaju ai_info postavljen!")
                return True
            
            print(f"🔧 Pronađeno {len(user_ids)} korisnika bez ai_info")
            print(f"   Postavljam default vrednosti...")
            
            # Update sve korisnike
            update_query = text("""
                UPDATE users 
                SET ai_info = :ai_info 
                WHERE ai_info IS NULL OR ai_info = ''
            """)
            
            db.session.execute(update_query, {
                'ai_info': json.dumps(default_ai_info)
            })
            db.session.commit()
            
            print(f"✅ Ažurirano {len(user_ids)} korisnika sa default ai_info")
            
        except Exception as e:
            print(f"❌ Greška pri populaciji ai_info: {e}")
            db.session.rollback()
            return False
    
    return True


def populate_default_ai_usage():
    """Popunjava default ai_usage za sve korisnike koji nemaju postavljen"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║      POPULACIJA DEFAULT AI_USAGE VREDNOSTI               ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    default_ai_usage = {
        "owner": {"llama4": 0, "Mistral-24b": 0, "GPT-OSS20B": 0},
        "employees": {"llama4": 0, "Mistral-24b": 0, "GPT-OSS20B": 0},
        "bookings": {"llama4": 0, "Mistral-24b": 0, "GPT-OSS20B": 0}
    }
    
    with app.app_context():
        try:
            # Pronađi sve korisnike bez ai_usage
            find_empty = text("SELECT id FROM users WHERE ai_usage IS NULL OR ai_usage = ''")
            result = db.session.execute(find_empty).fetchall()
            user_ids = [row[0] for row in result]
            
            if not user_ids:
                print("✅ Svi korisnici već imaju ai_usage postavljen!")
                return True
            
            print(f"🔧 Pronađeno {len(user_ids)} korisnika bez ai_usage")
            print(f"   Postavljam default vrednosti...")
            
            # Update sve korisnike
            update_query = text("""
                UPDATE users 
                SET ai_usage = :ai_usage 
                WHERE ai_usage IS NULL OR ai_usage = ''
            """)
            
            db.session.execute(update_query, {
                'ai_usage': json.dumps(default_ai_usage)
            })
            db.session.commit()
            
            print(f"✅ Ažurirano {len(user_ids)} korisnika sa default ai_usage")
            
        except Exception as e:
            print(f"❌ Greška pri populaciji ai_usage: {e}")
            db.session.rollback()
            return False
    
    return True


def display_sample_users():
    """Prikaži uzorak korisnika sa njihovim ai_info i ai_usage"""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║      PRIKAZ UZORKA KORISNIKA                             ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    with app.app_context():
        try:
            # Prikaži 5 korisnika sa ai_info
            sample_query = text("SELECT id, ai_info, ai_usage FROM users LIMIT 5")
            result = db.session.execute(sample_query).fetchall()
            
            if not result:
                print("❌ Nema korisnika u bazi!")
                return
            
            for idx, (user_id, ai_info, ai_usage) in enumerate(result, 1):
                print(f"\n📌 Korisnik #{user_id}:")
                
                # Prikaži ai_info
                if ai_info:
                    if isinstance(ai_info, str):
                        ai_info_dict = json.loads(ai_info)
                    else:
                        ai_info_dict = ai_info
                    print(f"   ai_info: {json.dumps(ai_info_dict, indent=2, ensure_ascii=False)}")
                else:
                    print(f"   ai_info: NULL")
                
                # Prikaži ai_usage
                if ai_usage:
                    if isinstance(ai_usage, str):
                        ai_usage_dict = json.loads(ai_usage)
                    else:
                        ai_usage_dict = ai_usage
                    print(f"   ai_usage: {json.dumps(ai_usage_dict, indent=2, ensure_ascii=False)}")
                else:
                    print(f"   ai_usage: NULL")
            
            print("\n✅ Prikaz uzorka je gotov!")
            
        except Exception as e:
            print(f"❌ Greška pri prikazu uzorka: {e}")


def main():
    """Glavna funkcija"""
    print("\n🚀 POKREĆE SE VERIFIKACIJA I MIGRACIJA AI SCHEMA\n")
    
    # 1. Proverite i kreirajte kolone
    if not check_and_create_ai_columns():
        print("❌ Neuspešna verifikacija schema!")
        return False
    
    # 2. Popunjajte default ai_info
    if not populate_default_ai_info():
        print("⚠️  Upozorenje: ai_info populacija nije uspela (možda nisu potrebne)")
    
    # 3. Popunjajte default ai_usage
    if not populate_default_ai_usage():
        print("⚠️  Upozorenje: ai_usage populacija nije uspela (možda nisu potrebne)")
    
    # 4. Prikažite uzorak
    display_sample_users()
    
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║     ✅ VERIFIKACIJA I MIGRACIJA JE GOTOVA!               ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
