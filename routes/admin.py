from flask import Blueprint, jsonify


admin_bp = Blueprint("admin", __name__)

# Test ruta
@admin_bp.route('/hello', methods=['GET'])
def hello():
    return jsonify({"message": "Zdravo ADMINE!"})