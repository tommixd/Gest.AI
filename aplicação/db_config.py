import os
from dotenv import load_dotenv

load_dotenv()  # Carrega as variáveis de ambiente do ficheiro .env

# Configuração partilhada para o acesso MySQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'BaseDadosGestAI')
}
