import json
import os
import uuid
from datetime import datetime
from pathlib import Path

CHATS_DIR = os.path.join(os.path.dirname(__file__), "chats")

def ensure_user_chat_dir(user_id):
    """Proverava i kreira direktorijum za korisnike chatove ako ne postoji"""
    user_chat_dir = os.path.join(CHATS_DIR, str(user_id))
    os.makedirs(user_chat_dir, exist_ok=True)
    return user_chat_dir

def get_chat_file_path(user_id, chat_id):
    """Vraća putanju do chat fajla"""
    return os.path.join(CHATS_DIR, str(user_id), f"{chat_id}.json")

def create_new_chat(user_id, title="Nova konverzacija"):
    """
    Kreira novi chat za korisnika
    Vraća: dict sa chat ID-om i informacijama
    """
    ensure_user_chat_dir(user_id)
    
    chat_id = str(uuid.uuid4())
    chat_data = {
        "chat_id": chat_id,
        "creator_id": str(user_id),
        "created_at": datetime.now().isoformat(),
        "title": title,
        "messages": [
            {
                "id": 1,
                "text": "Zdravo! 👋 Ja sam tvoj asistent. Kako ti mogu da pomognem?",
                "sender": "bot"
            }
        ]
    }
    
    chat_file = get_chat_file_path(user_id, chat_id)
    
    with open(chat_file, 'w', encoding='utf-8') as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)
    
    return {
        "chat_id": chat_id,
        "title": title,
        "created_at": chat_data["created_at"]
    }

def save_chat_message(user_id, chat_id, message):
    """
    Čuva poruku u chat
    
    message format:
    {
        "text": "poruka",
        "sender": "user" ili "bot"
    }
    """
    chat_file = get_chat_file_path(user_id, chat_id)
    
    # Provera da li chat postoji
    if not os.path.exists(chat_file):
        return {
            "success": False,
            "error": "Chat ne postoji"
        }
    
    # Učitavanje postojećeg chata
    with open(chat_file, 'r', encoding='utf-8') as f:
        chat_data = json.load(f)
    
    # Validacija kreatora
    if str(chat_data["creator_id"]) != str(user_id):
        return {
            "success": False,
            "error": "Nemate dozvolu da pristupite ovom chatu"
        }
    
    # Dodavanje nove poruke
    new_id = max([msg.get("id", 0) for msg in chat_data["messages"]], default=0) + 1
    
    new_message = {
        "id": new_id,
        "text": message["text"],
        "sender": message["sender"]
    }
    
    chat_data["messages"].append(new_message)
    
    # Čuvanje chata
    with open(chat_file, 'w', encoding='utf-8') as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "message": new_message
    }

def load_chat(user_id, chat_id):
    """
    Učitava ceo chat
    Provera pristupa: samo kreator može pristupiti
    """
    chat_file = get_chat_file_path(user_id, chat_id)
    
    if not os.path.exists(chat_file):
        return {
            "success": False,
            "error": "Chat ne postoji"
        }
    
    with open(chat_file, 'r', encoding='utf-8') as f:
        chat_data = json.load(f)
    
    # Provera pristupa - samo kreator može učitati chat
    if str(chat_data["creator_id"]) != str(user_id):
        return {
            "success": False,
            "error": "Nemate dozvolu da pristupite ovom chatu"
        }
    
    return {
        "success": True,
        "chat": chat_data
    }

def get_user_chats(user_id):
    """
    Vraća listu svih chatova za korisnika
    """
    user_chat_dir = os.path.join(CHATS_DIR, str(user_id))
    
    if not os.path.exists(user_chat_dir):
        return []
    
    chats = []
    for filename in os.listdir(user_chat_dir):
        if filename.endswith('.json'):
            chat_file = os.path.join(user_chat_dir, filename)
            try:
                with open(chat_file, 'r', encoding='utf-8') as f:
                    chat_data = json.load(f)
                
                chats.append({
                    "chat_id": chat_data["chat_id"],
                    "title": chat_data["title"],
                    "created_at": chat_data["created_at"],
                    "message_count": len(chat_data["messages"])
                })
            except Exception as e:
                print(f"Greška pri učitavanju chata {filename}: {str(e)}")
    
    # Sortiranje po vremenu kreiranja (najnoviji prvi)
    chats.sort(key=lambda x: x["created_at"], reverse=True)
    
    return chats

def delete_chat(user_id, chat_id):
    """
    Briše chat
    Provera pristupa: samo kreator može obrisati
    """
    chat_file = get_chat_file_path(user_id, chat_id)
    
    if not os.path.exists(chat_file):
        return {
            "success": False,
            "error": "Chat ne postoji"
        }
    
    # Provera pristupa pre brisanja
    with open(chat_file, 'r', encoding='utf-8') as f:
        chat_data = json.load(f)
    
    if str(chat_data["creator_id"]) != str(user_id):
        return {
            "success": False,
            "error": "Nemate dozvolu da obrisite ovaj chat"
        }
    
    os.remove(chat_file)
    
    return {
        "success": True,
        "message": "Chat je uspešno obrisan"
    }

def rename_chat(user_id, chat_id, new_title):
    """
    Preimenovava chat
    """
    chat_file = get_chat_file_path(user_id, chat_id)
    
    if not os.path.exists(chat_file):
        return {
            "success": False,
            "error": "Chat ne postoji"
        }
    
    with open(chat_file, 'r', encoding='utf-8') as f:
        chat_data = json.load(f)
    
    # Provera pristupa
    if str(chat_data["creator_id"]) != str(user_id):
        return {
            "success": False,
            "error": "Nemate dozvolu da izmenite ovaj chat"
        }
    
    chat_data["title"] = new_title
    
    with open(chat_file, 'w', encoding='utf-8') as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "message": "Chat je uspešno preimenovan"
    }
