# models.py
# Modelo de utilizador (funcionários e admin) para autenticação.

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
bcrypt = Bcrypt()


class Funcionario(UserMixin, db.Model):
    __tablename__ = "funcionarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="funcionario")  # 'admin' ou 'funcionario'
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow)

    # --- Password ---
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    # --- Helpers de permissões ---
    @property
    def is_admin(self):
        return self.role == "admin"

    # Flask-Login usa get_id() -> deve devolver uma string
    def get_id(self):
        return str(self.id)

    # Impede login de contas desativadas (Flask-Login chama is_active)
    @property
    def is_active(self):
        return self.ativo

    def __repr__(self):
        return f"<Funcionario {self.username} ({self.role})>"
