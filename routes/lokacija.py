from flask import Blueprint, jsonify, request
from sqlalchemy import text
import re
import unicodedata
import requests


lokacija_bp = Blueprint("lokacija", __name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_TIMEOUT = 6
LOCATION_CACHE = {}

CYRILLIC_TO_LATIN = str.maketrans({
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v",
    "Г": "G", "г": "g", "Д": "D", "д": "d", "Ђ": "Dj", "ђ": "dj",
    "Е": "E", "е": "e", "Ж": "Z", "ж": "z", "З": "Z", "з": "z",
    "И": "I", "и": "i", "Ј": "J", "ј": "j", "К": "K", "к": "k",
    "Л": "L", "л": "l", "Љ": "Lj", "љ": "lj", "М": "M", "м": "m",
    "Н": "N", "н": "n", "Њ": "Nj", "њ": "nj", "О": "O", "о": "o",
    "П": "P", "п": "p", "Р": "R", "р": "r", "С": "S", "с": "s",
    "Т": "T", "т": "t", "Ћ": "C", "ћ": "c", "У": "U", "у": "u",
    "Ф": "F", "ф": "f", "Х": "H", "х": "h", "Ц": "C", "ц": "c",
    "Ч": "C", "ч": "c", "Џ": "Dz", "џ": "dz", "Ш": "S", "ш": "s",
})

CITY_ALIASES = {
    "belgrade": "beograd",
    "city of belgrade": "beograd",
    "grad beograd": "beograd",
    "nis": "nis",
    "niš": "nis",
}


def normalize_city(value):
    if not value:
        return ""

    value = str(value).translate(CYRILLIC_TO_LATIN).strip().lower()
    value = CITY_ALIASES.get(value, value)
    value = value.replace("đ", "dj").replace("Đ", "dj")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"\b(grad|gradska|opstina|opstina grada|city|municipality|administrative district)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_city(address):
    municipality = address.get("municipality")
    city = address.get("city")

    if municipality:
        return municipality

    if city and "opstina" not in normalize_city(city):
        return city

    suburb = address.get("suburb")
    if suburb:
        return suburb.split("(")[0].strip()

    for key in ("town", "village", "county", "state", "region"):
        if address.get(key):
            return address[key]
    return None


def find_matching_grad(gradovi, detected_city):
    normalized_detected = normalize_city(detected_city)
    if not normalized_detected:
        return None

    normalized_gradovi = [
        {
            "id": row[0],
            "grad": row[1],
            "normalized": normalize_city(row[1]),
        }
        for row in gradovi
    ]

    for grad in normalized_gradovi:
        if grad["normalized"] == normalized_detected:
            return {"id": grad["id"], "grad": grad["grad"], "match_type": "exact"}

    for grad in normalized_gradovi:
        if grad["normalized"] and (
            grad["normalized"] in normalized_detected or normalized_detected in grad["normalized"]
        ):
            return {"id": grad["id"], "grad": grad["grad"], "match_type": "contains"}

    return None


@lokacija_bp.route("/grad", methods=["POST"])
def resolve_grad_from_location():
    try:
        data = request.get_json(silent=True) or {}
        latitude = data.get("latitude")
        longitude = data.get("longitude")

        if latitude is None or longitude is None:
            return jsonify({
                "success": False,
                "error": "latitude i longitude su obavezni"
            }), 400

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "error": "latitude i longitude moraju biti brojevi"
            }), 400

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return jsonify({
                "success": False,
                "error": "Koordinate nisu validne"
            }), 400

        cache_key = (round(latitude, 4), round(longitude, 4))
        if cache_key in LOCATION_CACHE:
            return jsonify(LOCATION_CACHE[cache_key]), 200

        response = requests.get(
            NOMINATIM_URL,
            params={
                "format": "jsonv2",
                "lat": latitude,
                "lon": longitude,
                "addressdetails": 1,
                "accept-language": "sr-Latn,sr,en",
            },
            headers={
                "User-Agent": "MojTermin/1.0 (https://mojtermin.site)",
            },
            timeout=NOMINATIM_TIMEOUT,
        )
        response.raise_for_status()
        nominatim_data = response.json()
        address = nominatim_data.get("address") or {}
        detected_city = extract_city(address)

        if not detected_city:
            return jsonify({
                "success": False,
                "error": "Nije pronadjen grad za date koordinate",
                "address": address,
            }), 200

        from app import db, app

        with app.app_context():
            gradovi = db.session.execute(text("""
                SELECT id, grad
                FROM gradovi
                ORDER BY grad
            """)).fetchall()

        matched_grad = find_matching_grad(gradovi, detected_city)

        if not matched_grad:
            return jsonify({
                "success": False,
                "error": "Pronadjeni grad ne postoji u bazi",
                "detected_city": detected_city,
                "normalized_city": normalize_city(detected_city),
                "address": address,
            }), 200

        payload = {
            "success": True,
            "grad": {
                "id": matched_grad["id"],
                "grad": matched_grad["grad"],
            },
            "detected_city": detected_city,
            "match_type": matched_grad["match_type"],
            "source": "openstreetmap_nominatim",
        }
        LOCATION_CACHE[cache_key] = payload

        return jsonify(payload), 200

    except requests.Timeout:
        return jsonify({
            "success": False,
            "error": "Servis za lokaciju nije odgovorio na vreme"
        }), 504
    except requests.RequestException as e:
        return jsonify({
            "success": False,
            "error": f"Servis za lokaciju trenutno nije dostupan: {str(e)}"
        }), 502
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
