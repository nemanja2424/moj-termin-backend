from flask import Blueprint, jsonify


template_bp = Blueprint("template", __name__)


@template_bp.route('/test', methods=['GET'])
def auth_test():
    return jsonify({"message": "template radi"})


