# auth.py
# Blueprint de autenticação: login, logout e decoradores de permissão.

from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user

from models import Funcionario

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Se já está autenticado, não tem razão para ver o login outra vez
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        utilizador = Funcionario.query.filter_by(username=username).first()

        if utilizador and utilizador.ativo and utilizador.check_password(password):
            login_user(utilizador)
            destino = request.args.get("next") or url_for("index")
            return redirect(destino)

        flash("Utilizador ou password incorretos.", "erro")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# --- Decoradores de permissão ---

def admin_required(f):
    """Permite o acesso apenas a utilizadores com role='admin'."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated
