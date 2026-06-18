# admin.py
# Blueprint de gestão de funcionários (apenas acessível ao admin).

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user

from auth import admin_required
from models import db, Funcionario

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/funcionarios")
@admin_required
def pagina_funcionarios():
    funcionarios = Funcionario.query.order_by(Funcionario.nome).all()
    return render_template("gestao_funcionarios.html", funcionarios=funcionarios)


@admin_bp.route("/api/funcionarios", methods=["POST"])
@admin_required
def criar_funcionario():
    dados = request.get_json() or {}
    nome = dados.get("nome", "").strip()
    username = dados.get("username", "").strip().lower()
    password = dados.get("password", "")
    role = dados.get("role", "funcionario")

    if not nome or not username or not password:
        return jsonify({"sucesso": False, "erro": "Preenche todos os campos."}), 400

    if role not in ("admin", "funcionario"):
        return jsonify({"sucesso": False, "erro": "Perfil inválido."}), 400

    if len(password) < 6:
        return jsonify({"sucesso": False, "erro": "A password deve ter pelo menos 6 caracteres."}), 400

    if Funcionario.query.filter_by(username=username).first():
        return jsonify({"sucesso": False, "erro": "Já existe um funcionário com este username."}), 400

    novo = Funcionario(nome=nome, username=username, role=role, ativo=True)
    novo.set_password(password)

    db.session.add(novo)
    db.session.commit()

    return jsonify({"sucesso": True, "id": novo.id}), 201


@admin_bp.route("/api/funcionarios/<int:func_id>/password", methods=["POST"])
@admin_required
def alterar_password(func_id):
    dados = request.get_json() or {}
    password = dados.get("password", "")

    if len(password) < 6:
        return jsonify({"sucesso": False, "erro": "A password deve ter pelo menos 6 caracteres."}), 400

    funcionario = Funcionario.query.get(func_id)
    if not funcionario:
        return jsonify({"sucesso": False, "erro": "Funcionário não encontrado."}), 404

    funcionario.set_password(password)
    db.session.commit()

    return jsonify({"sucesso": True})


@admin_bp.route("/api/funcionarios/<int:func_id>/estado", methods=["POST"])
@admin_required
def alternar_estado(func_id):
    dados = request.get_json() or {}
    novo_estado = dados.get("ativo")

    funcionario = Funcionario.query.get(func_id)
    if not funcionario:
        return jsonify({"sucesso": False, "erro": "Funcionário não encontrado."}), 404

    if funcionario.id == current_user.id:
        return jsonify({"sucesso": False, "erro": "Não podes desativar a tua própria conta."}), 400

    funcionario.ativo = bool(novo_estado)
    db.session.commit()

    return jsonify({"sucesso": True})


@admin_bp.route("/api/funcionarios/<int:func_id>", methods=["DELETE"])
@admin_required
def apagar_funcionario(func_id):
    funcionario = Funcionario.query.get(func_id)
    if not funcionario:
        return jsonify({"sucesso": False, "erro": "Funcionário não encontrado."}), 404

    if funcionario.id == current_user.id:
        return jsonify({"sucesso": False, "erro": "Não podes apagar a tua própria conta."}), 400

    db.session.delete(funcionario)
    db.session.commit()

    return jsonify({"sucesso": True})
