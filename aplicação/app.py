import os
import sys
import sqlite3
import threading
import nbformat
from nbconvert import HTMLExporter
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, g, request, send_file, jsonify

# --- GARANTIR IMPORTAÇÃO CORRETA DO RAG_LLM ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Adiciona a pasta atual ao path do Python
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    # Importação explícita do ficheiro na mesma pasta
    import RAG_LLM
    # Recarregar o módulo para garantir que as alterações no ficheiro são lidas
    import importlib
    importlib.reload(RAG_LLM)
    
    from RAG_LLM import responder_pergunta, inicializar_rag
    print("[OK] Funções do RAG_LLM carregadas com sucesso.")
except Exception as e:
    print(f"[!] Erro crítico ao carregar RAG_LLM: {e}")
    def responder_pergunta(*args): return "IA em manutenção.", ""
    def inicializar_rag(): return None, None


# Inicializa a aplicação e define configurações globais
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config["SITE_NAME"] = "Gest.AI"  

# Configurações para a base de dados SQLite
DATABASE = os.path.join(BASE_DIR, 'documentos.db')
PASTA_UPLOADS = 'PastaUploadsSiteTest'

# ==========================================
# --- CONFIGURAÇÃO DA INTELIGÊNCIA ARTIFICIAL ---
# ==========================================
global_retriever = None
global_llm = None
ia_pronta = False

def iniciar_ia_background():
    """Carrega o modelo Qwen e o RAG sem bloquear o arranque do site."""
    global global_retriever, global_llm, ia_pronta
    try:
        print("\n[A inicializar o cérebro Gest.AI em 2º plano...]")
        # Chama a função de inicialização do RAG_LLM.py
        global_retriever, global_llm = inicializar_rag()
        
        if global_retriever and global_llm:
            ia_pronta = True
            print("\n[=========================================]")
            print("[ IA PRONTA! O Chatbox já pode responder. ]")
            print("[=========================================]\n")
        else:
            print("\n[!] A IA não iniciou (poderá não haver documentos na BD ou erro no modelo).")
    except Exception as e:
        print(f"\n[!] Erro crítico ao carregar a IA: {e}")

# Inicia a thread assim que o ficheiro app.py é lido
thread_ia = threading.Thread(target=iniciar_ia_background)
thread_ia.daemon = True
thread_ia.start()
# ==========================================

def get_db():
    """Abre a ligação à BD (se ainda não estiver aberta)."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row 
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Fecha a ligação à BD no final de cada pedido."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

NOTEBOOK_PATH = Path(__file__).parent.parent / 'Notebook'

@app.route('/notebooks/<notebook_name>')
def view_notebook(notebook_name):
    notebook_file = NOTEBOOK_PATH / f'{notebook_name}.ipynb'
    if not notebook_file.exists():
        return 'Notebook not found', 404
    
    with open(notebook_file, 'r', encoding='utf-8') as f:
        notebook = nbformat.read(f, as_version=4)
    
    exporter = HTMLExporter()
    exporter.template_name = 'basic'    
    html_body, _ = exporter.from_notebook_node(notebook)
    return html_body

@app.route('/')  
def index():
    db = get_db()
    cursor = db.execute("SELECT * FROM documentos ORDER BY categoria, nome")
    lista_documentos = cursor.fetchall()
    
    # Definimos a ordem e inicializamos as categorias
    documentos_agrupados = {
        'processamento': {}, # Fica no topo
        'gerado': {},
        'template': {},
        'pdf_llm': {}
    }
    
    ROOT_DIR = os.path.dirname(BASE_DIR)
    
    for doc in lista_documentos:
        caminho_absoluto = os.path.join(ROOT_DIR, doc['caminho'])
        if not os.path.exists(caminho_absoluto): continue 

        cat = doc['categoria']
        if cat not in documentos_agrupados: documentos_agrupados[cat] = {}

        # Agrupamento por CASO para 'gerado' e 'processamento'
        if cat in ['gerado', 'processamento']:
            partes = doc['caminho'].split('/')
            caso = partes[-2].replace('_', ' ') if len(partes) >= 4 else "Documentos Gerais"
                
            if caso not in documentos_agrupados[cat]:
                documentos_agrupados[cat][caso] = []
            documentos_agrupados[cat][caso].append(doc)
        else:
            # Agrupamento simples para o resto
            if 'Geral' not in documentos_agrupados[cat]:
                documentos_agrupados[cat]['Geral'] = []
            documentos_agrupados[cat]['Geral'].append(doc)
    
    # Remove categorias que não têm ficheiros para não aparecerem vazias
    documentos_agrupados = {k: v for k, v in documentos_agrupados.items() if v}
    
    return render_template('index.html', documentos_agrupados=documentos_agrupados)

@app.route('/contratacao/<tipo>')
def iniciar_contratacao(tipo):
    # Lógica para lidar com a rota de contratação
    titulos = {
        'renovacaoIntegral' : 'Renovação de contrato (Tempo Integral)',
        'renovacaoParcial' : 'Renovação de contrato (Tempo Parcial)',
        'novoContrato' : 'Novo contrato (Tempo Parcial)',
    }

    titulo = titulos.get(tipo, 'Contratação')
    return render_template('contratacao.html', titulo=titulo, tipo=tipo)

@app.route('/processar_documentos', methods=['POST'])
def processar_documentos():
    if 'files' not in request.files:
        return {"erro": "Nenhum ficheiro enviado"}, 400

    ficheiros = request.files.getlist('files')
    db = get_db()

    ROOT_DIR = os.path.dirname(BASE_DIR)
    PASTA_UPLOADS_ABS = os.path.join(ROOT_DIR, PASTA_UPLOADS)
    os.makedirs(PASTA_UPLOADS_ABS, exist_ok=True)

    for ficheiro in ficheiros:
        if ficheiro.filename == '':
            continue 

        caminho_seguro = os.path.join(PASTA_UPLOADS_ABS, ficheiro.filename).replace('\\', '/')
        ficheiro.save(caminho_seguro)

        # Caminho relativo para guardar na BD
        caminho_db = os.path.relpath(caminho_seguro, ROOT_DIR).replace('\\', '/') 
        query = '''INSERT INTO documentos (nome, caminho, categoria, data_upload) VALUES (?, ?, ?, ?)'''
        db.execute(query, (ficheiro.filename, caminho_db, 'pdf_llm', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    db.commit()
    return {"mensagem": "Ficheiros processados com sucesso"}, 200

@app.route('/ver_documento/<int:doc_id>')
def ver_documento(doc_id):
    db = get_db()
    doc = db.execute("SELECT caminho FROM documentos WHERE id = ?", (doc_id,)).fetchone()

    if doc:
        ROOT_DIR = os.path.dirname(BASE_DIR)
        caminho_absoluto = os.path.join(ROOT_DIR, doc['caminho'])
        
        if os.path.exists(caminho_absoluto):
            return send_file(caminho_absoluto)
    return "Ficheiro não encontrado", 404

# ==========================================
# --- ROTA PARA O CHATBOX ---
# ==========================================
@app.route('/chat', methods=['POST'])
def chat():
    dados = request.json
    mensagem_utilizador = dados.get('message', '')

    if not mensagem_utilizador:
        return jsonify({"reply": "Por favor, escreve uma mensagem."}), 400

    # Verifica se a IA já terminou de carregar
    if not ia_pronta or global_retriever is None or global_llm is None:
        return jsonify({"reply": "Ainda estou a preparar os documentos... Tenta de novo em alguns segundos!"}), 200

    try:
        # Chama a função de resposta do RAG_LLM.py
        resposta, contexto = responder_pergunta(mensagem_utilizador, global_retriever, global_llm)
        return jsonify({"reply": resposta}), 200

    except Exception as e:
        print(f"[!] Erro no processamento do Chat: {e}")
        return jsonify({"reply": "Ocorreu um erro ao processar a tua pergunta."}), 500

if __name__ == '__main__':
    # Executa o servidor em localhost na porta 5000
    app.run(host="localhost", port=5000, debug=True)