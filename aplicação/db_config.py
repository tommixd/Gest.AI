import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "gestai"),
    "port": int(os.environ.get("DB_PORT", 3306)),
}

# String de ligação usada pelo SQLAlchemy (Flask-Login / modelo Funcionario).
# Mantém os mesmos dados de DB_CONFIG acima.
SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)
