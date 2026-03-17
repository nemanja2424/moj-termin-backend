import json
from pathlib import Path
from collections import defaultdict

# Putanja do fajla
file_path = Path(__file__).parent / "../ai/ai_usage/sumUsage.json"

# Učitaj postojeći JSON
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

history = data.get("history", [])

# --- Kreiranje novih sum i models ---
sum_data = {
    "total_token_usage": 0,
    "entry_token_usage": 0,
    "generated_token_usage": 0,
    "total_req": 0
}

models_data = defaultdict(lambda: {
    "total_tokens": 0,
    "entry_tokens": 0,
    "generated_tokens": 0,
    "requests": 0
})

# Prođi kroz history i saberi po modelima i ukupno
for entry in history:
    model = entry["model"]
    entry_tokens = entry.get("entry_token_usage", 0)
    gen_tokens = entry.get("generated_token_usage", 0)
    
    # Sum
    sum_data["entry_token_usage"] += entry_tokens
    sum_data["generated_token_usage"] += gen_tokens
    sum_data["total_token_usage"] += entry_tokens + gen_tokens
    sum_data["total_req"] += 1
    
    # Models
    models_data[model]["entry_tokens"] += entry_tokens
    models_data[model]["generated_tokens"] += gen_tokens
    models_data[model]["total_tokens"] += entry_tokens + gen_tokens
    models_data[model]["requests"] += 1

# Ažuriraj data dict
data["sum"] = sum_data
data["models"] = dict(models_data)  # defaultdict → dict

# Sačuvaj nazad
with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)

print("JSON uspešno ažuriran!")