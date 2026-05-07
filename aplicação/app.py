import os
import sys
import threading
import re
import docx
import json
import mysql.connector # <-- SUBSTITUI O SQLITE3
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, g, request, send_file, jsonify
from werkzeug.utils import secure_filename

# --- GARANTIR IMPORTAÇÃO CORRETA DO RAG_LLM ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    import RAG_LLM
    import importlib
    importlib.reload(RAG_LLM)
    from RAG_LLM import responder_pergunta, inicializar_rag
    print("[OK] Funções do RAG_LLM carregadas com sucesso.")
except Exception as e:
    print(f"[!] Erro crítico ao carregar RAG_LLM: {e}")
    def responder_pergunta(*args): return "IA em manutenção.", ""
    def inicializar_rag(): return None, None

try:
    from templates import processar_renovacao
    print("[OK] Motor de templates importado com sucesso.")
except ImportError:
    print("[!] Aviso: Não foi possível importar templates.py. A usar lógica interna.")
    def processar_renovacao(dados): return None

# Inicializa a aplicação
app = Flask(__name__)
app.config["SITE_NAME"] = "Gest.AI"  

# --- CONFIGURAÇÃO DA BASE DE DADOS MYSQL ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',            
    'password': '04072002Tomas!', 
    'database': 'BaseDadosGestAI' 
}

PASTA_UPLOADS = 'PastaUploadsSiteTest'

# --- CONFIGURAÇÃO DA IA EM BACKGROUND ---
global_retriever = None
global_llm = None
ia_pronta = False

def iniciar_ia_background():
    global global_retriever, global_llm, ia_pronta
    try:
        print("\n[A inicializar o cérebro Gest.AI em 2º plano...]")
        global_retriever, global_llm = inicializar_rag()
        if global_retriever and global_llm:
            ia_pronta = True
            print("\n[=========================================]")
            print("[ IA PRONTA! O Chatbox já pode responder. ]")
            print("[=========================================]\n")
    except Exception as e:
        print(f"\n[!] Erro crítico ao carregar a IA: {e}")

thread_ia = threading.Thread(target=iniciar_ia_background)
thread_ia.daemon = True
thread_ia.start()

# --- MAPEAMENTO E LÓGICA DE TEMPLATES ---
CATEGORIA_POR_TIPO = {
    "renovacao-integral": "tempo integral anual",
    "renovacao-parcial": "tempo parcial semestral",
    "primeira-vez": "tempo parcial edital"
}

def criar_nome_pasta_limpo(nome_completo):
    nome = nome_completo.replace("Professor ", "").replace("Professora ", "")
    nome = nome.replace("Prof. Dr. ", "").replace("Prof. ", "").replace("Prof. Doutor ", "")
    nome = nome.strip().replace(" ", "_")
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    return f"Contrato_{nome_limpo}"

def processar_templates(dados_formulario, tipo_contratacao):
    categoria_bd = CATEGORIA_POR_TIPO.get(tipo_contratacao)
    if not categoria_bd:
        print(f"[!] Erro: Tipo de contratação '{tipo_contratacao}' não mapeado.")
        return None, f"Tipo de contratação '{tipo_contratacao}' não reconhecido."

    nome_docente = dados_formulario.get("nome_docente", "Docente_Desconhecido")
    nome_subpasta = criar_nome_pasta_limpo(nome_docente)
    
    ROOT_DIR = os.path.dirname(BASE_DIR)
    caminho_final = os.path.join(ROOT_DIR, 'Modelos Contratuais', 'Em_Processamento', nome_subpasta)
    
    print(f"[*] A iniciar processo para: {nome_docente}")
    print(f"[*] Categoria alvo na BD: {categoria_bd}")
    print(f"[*] Pasta de destino: {caminho_final}")

    if not os.path.exists(caminho_final):
        os.makedirs(caminho_final)
        print(f"[*] Criada pasta de processo: {nome_subpasta}")

    templates_encontrados = []
    try:
        # Ligar ao MySQL
        ligacao = mysql.connector.connect(**DB_CONFIG)
        cursor = ligacao.cursor(dictionary=True)
        
        cursor.execute("SELECT nome, caminho FROM documentos WHERE categoria LIKE %s", (f"%{categoria_bd}%",))
        templates_encontrados = cursor.fetchall()
        
        cursor.close()
        ligacao.close()
        
        print(f"[*] Templates encontrados na BD: {len(templates_encontrados)}")
    except Exception as e:
        print(f"[!] Erro de SQL: {e}")
        return None, f"Erro ao aceder à base de dados: {e}"

    if not templates_encontrados:
        print(f"[!] Aviso: A categoria '{categoria_bd}' não tem documentos registados.")
        return None, f"Nenhum template encontrado para a categoria '{categoria_bd}'."

    ficheiros_gerados = []
    for template in templates_encontrados:
        nome_ficheiro = template["nome"]
        caminho_abs_template = os.path.join(ROOT_DIR, template["caminho"])
        
        if not os.path.exists(caminho_abs_template):
            print(f"[!] Ficheiro não encontrado no disco: {caminho_abs_template}")
            continue

        try:
            print(f"[*] A preencher: {nome_ficheiro}...")
            documento = docx.Document(caminho_abs_template)

            for paragrafo in documento.paragraphs:
                for chave, valor in dados_formulario.items():
                    if chave in paragrafo.text and valor:
                        paragrafo.text = paragrafo.text.replace(chave, str(valor))

            for tabela in documento.tables:
                for linha in tabela.rows:
                    for celula in linha.cells:
                        for paragrafo in celula.paragraphs:
                            for chave, valor in dados_formulario.items():
                                if chave in paragrafo.text and valor:
                                    paragrafo.text = paragrafo.text.replace(chave, str(valor))

            caminho_output = os.path.join(caminho_final, nome_ficheiro)
            documento.save(caminho_output)
            ficheiros_gerados.append(nome_ficheiro)
            print(f"[OK] Gerado: {nome_ficheiro}")

        except Exception as e:
            print(f"[!] Erro ao processar {nome_ficheiro}: {e}")

    if not ficheiros_gerados:
        return None, "Os templates foram encontrados mas não foi possível gerar nenhum ficheiro."

    return caminho_final, ficheiros_gerados

# --- ROTAS FLASK E BASE DE DADOS ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = mysql.connector.connect(**DB_CONFIG)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')  
def index():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM documentos ORDER BY categoria, nome")
    lista_documentos = cursor.fetchall()
    cursor.close()
    
    documentos_agrupados = {'processamento': {}, 'gerado': {}, 'template': {}, 'pdf_llm': {}}
    ROOT_DIR = os.path.dirname(BASE_DIR)
    
    for doc in lista_documentos:
        caminho_absoluto = os.path.join(ROOT_DIR, doc['caminho'])
        if not os.path.exists(caminho_absoluto): continue 
        cat = doc['categoria']
        if cat not in documentos_agrupados: documentos_agrupados[cat] = {}
        if cat in ['gerado', 'processamento']:
            partes = doc['caminho'].split('/')
            caso = partes[-2].replace('_', ' ') if len(partes) >= 4 else "Documentos Gerais"
            if caso not in documentos_agrupados[cat]: documentos_agrupados[cat][caso] = []
            documentos_agrupados[cat][caso].append(doc)
        else:
            if 'Geral' not in documentos_agrupados[cat]: documentos_agrupados[cat]['Geral'] = []
            documentos_agrupados[cat]['Geral'].append(doc)
    
    documentos_agrupados = {k: v for k, v in documentos_agrupados.items() if v}
    return render_template('index.html', documentos_agrupados=documentos_agrupados)


@app.route('/contratacao/<tipo>')
def iniciar_contratacao(tipo):
    titulos = {
        'renovacao-integral': 'Renovação de Contrato (Integral)',
        'renovacao-parcial': 'Renovação de Contrato (Parcial)',
        'primeira-vez': 'Primeira Contratação (Edital)'
    }
    
    regimes = {
        'renovacao-integral': 'Tempo Integral',
        'renovacao-parcial': 'Tempo Parcial',
        'primeira-vez': 'Tempo Parcial Edital'
    }

    titulo = titulos.get(tipo, 'Novo Processo')
    regime_nome = regimes.get(tipo, 'Padrão')
    
    # -----------------------------------------------------------------
    # LÓGICA DO RASCUNHO: Verifica se fomos chamados por um rascunho_id
    # -----------------------------------------------------------------
    rascunho_id = request.args.get('rascunho_id')
    dados_preenchidos = {}

    lista_professores = []
    lista_areas = []
    lista_ucs = []
    lista_cursos = []

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Carregar Rascunho
        if rascunho_id:
            cursor.execute("SELECT dados_formulario FROM rascunhos WHERE id = %s", (rascunho_id,))
            resultado = cursor.fetchone()
            if resultado:
                dados_preenchidos = json.loads(resultado['dados_formulario'])
        
        # --- NOVA PARTE: Buscar dados dinâmicos ao MySQL ---
        # Usamos try/except individuais para não quebrar a página se uma tabela falhar
        try:
            cursor.execute("SELECT nome FROM docentes WHERE tipo_docente = 'carreira' ORDER BY nome")
            lista_professores = [row['nome'] for row in cursor.fetchall()]
        except Exception: pass

        try:
            cursor.execute("SELECT nome FROM areas_estudo ORDER BY nome")
            lista_areas = [row['nome'] for row in cursor.fetchall()]
        except Exception: pass

        try:
            cursor.execute("SELECT nome FROM ucs ORDER BY nome")
            lista_ucs = [row['nome'] for row in cursor.fetchall()]
        except Exception: pass

        try:
            cursor.execute("SELECT nome FROM cursos ORDER BY nome")
            lista_cursos = [row['nome'] for row in cursor.fetchall()]
        except Exception: pass
        
        cursor.close()
    except Exception as e:
        print(f"[!] Erro ao carregar dados para o formulário: {e}")

    # Passamos as listas para o HTML usar!
    return render_template('contratacao.html', 
                           titulo=titulo, 
                           regime_nome=regime_nome, 
                           tipo=tipo,
                           tipo_contrato=tipo,
                           form_data=dados_preenchidos,
                           professores=lista_professores,
                           areas=lista_areas,
                           ucs=lista_ucs,
                           cursos=lista_cursos)


@app.route('/submeter-contratacao', methods=['POST'])
def submeter_contratacao():
    dados = request.get_json()
    tipo = dados.get('tipo')
    
    nome_docente_raw = dados.get('nome_docente')
    if not nome_docente_raw or not tipo:
        return jsonify({"erro": "Dados incompletos: O nome do docente é obrigatório."}), 400
    
    caminho_pasta, resultado = processar_templates(dados, tipo)
    
    if caminho_pasta is None:
        return jsonify({"erro": resultado}), 400
    
    try:
        db = get_db()
        cursor = db.cursor() # Usar cursor no MySQL
        ROOT_DIR = os.path.dirname(BASE_DIR)
        
        ficheiros_gerados = os.listdir(caminho_pasta)
        documentos_inseridos = 0
        
        for ficheiro in ficheiros_gerados:
            caminho_ficheiro_absoluto = os.path.join(caminho_pasta, ficheiro)
            
            if os.path.isfile(caminho_ficheiro_absoluto):
                caminho_relativo_ficheiro = os.path.relpath(caminho_ficheiro_absoluto, ROOT_DIR).replace('\\', '/')
                
                cursor.execute(
                    "INSERT INTO documentos (nome, caminho, categoria, data_upload) VALUES (%s, %s, %s, %s)",
                    (ficheiro, caminho_relativo_ficheiro, 'processamento', datetime.now().isoformat())
                )
                documentos_inseridos += 1
                
        db.commit()
        cursor.close()
        
        print(f"[OK] Processo registado: Foram inseridos {documentos_inseridos} documentos na BD para o(a) {nome_docente_raw}")
        
        return jsonify({
            "mensagem": f"Sucesso: {documentos_inseridos} documentos gerados e registados.", 
            "pasta": caminho_pasta,
            "ficheiros": ficheiros_gerados
        }), 200

    except Exception as e:
        print(f"[!] Erro ao registar na BD: {e}")
        return jsonify({"erro": f"Documentos gerados, mas erro ao registar na BD: {e}"}), 500
    

@app.route('/guardar-rascunho', methods=['POST'])
def rota_guardar_rascunho():
    dados = request.get_json()
    
    nome = dados.get('nome_docente', 'Sem Nome')
    tipo = dados.get('tipo', 'indefinido')
    
    dados_texto = json.dumps(dados)
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        db = get_db()
        cursor = db.cursor()
        
        query = """
            INSERT INTO rascunhos (nome_docente, tipo_contrato, dados_formulario, data_guardado) 
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (nome, tipo, dados_texto, data_atual))
        db.commit()
        
        return jsonify({"sucesso": True})
        
    except Exception as e:
        print(f"[!] Erro ao guardar rascunho: {e}")
        return jsonify({"sucesso": False, "erro": str(e)})
    finally:
        if 'cursor' in locals():
            cursor.close()
        # Removi o db.close() daqui para não fechar a ligação prematuramente. O @app.teardown_appcontext trata disso.

@app.route('/meus-rascunhos')
def ver_rascunhos():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM rascunhos ORDER BY id DESC")
    lista_rascunhos = cursor.fetchall()
    cursor.close()
    
    return render_template('pasta_rascunhos.html', rascunhos=lista_rascunhos)

@app.route('/upload-documento', methods=['POST'])
def upload_documento():
    # Verifica se a requisição contém ficheiros
    if 'file' not in request.files:
        return jsonify({"erro": "Nenhum ficheiro foi enviado."}), 400

    ficheiros = request.files.getlist('file')
    if not ficheiros or ficheiros[0].filename == '':
        return jsonify({"erro": "Nenhum ficheiro selecionado."}), 400

    try:
        db = get_db()
        cursor = db.cursor()
        
        ROOT_DIR = os.path.dirname(BASE_DIR)
        caminho_uploads = os.path.join(ROOT_DIR, PASTA_UPLOADS)
        
        # Garantir que a pasta existe
        if not os.path.exists(caminho_uploads):
            os.makedirs(caminho_uploads)

        documentos_inseridos = 0
        
        for ficheiro in ficheiros:
            if ficheiro.filename:
                # Limpar o nome do ficheiro para evitar problemas no sistema operativo
                nome_seguro = secure_filename(ficheiro.filename)
                caminho_absoluto = os.path.join(caminho_uploads, nome_seguro)
                
                # Guardar fisicamente no disco
                ficheiro.save(caminho_absoluto)
                
                # Caminho relativo para gravar na BD
                caminho_relativo = os.path.join(PASTA_UPLOADS, nome_seguro).replace('\\', '/')
                
                # Inserir na base de dados (categoria pdf_llm conforme os teus dados)
                cursor.execute(
                    "INSERT INTO documentos (nome, caminho, categoria, data_upload) VALUES (%s, %s, %s, %s)",
                    (nome_seguro, caminho_relativo, 'pdf_llm', datetime.now().isoformat())
                )
                documentos_inseridos += 1
                
        db.commit()
        cursor.close()
        
        print(f"[OK] Upload concluído: {documentos_inseridos} ficheiros recebidos.")
        return jsonify({"mensagem": f"{documentos_inseridos} ficheiros guardados com sucesso!"}), 200

    except Exception as e:
        print(f"[!] Erro no upload: {e}")
        return jsonify({"erro": f"Erro interno ao processar o upload: {e}"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    dados = request.json
    msg = dados.get('message', '')
    if not msg: return jsonify({"reply": "Escreve uma mensagem."}), 400
    if not ia_pronta: return jsonify({"reply": "IA a carregar..."}), 200
    try:
        res, _ = responder_pergunta(msg, global_retriever, global_llm)
        return jsonify({"reply": res}), 200
    except Exception as e:
        return jsonify({"reply": f"Erro: {e}"}), 500

@app.route('/ver_documento/<int:doc_id>')
def ver_documento(doc_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT caminho FROM documentos WHERE id = %s", (doc_id,))
    doc = cursor.fetchone()
    cursor.close()
    
    if doc:
        ROOT_DIR = os.path.dirname(BASE_DIR)
        caminho_abs = os.path.join(ROOT_DIR, doc['caminho'])
        if os.path.exists(caminho_abs): 
            return send_file(caminho_abs)
    return "Não encontrado", 404

if __name__ == '__main__':
    app.run(host="localhost", port=5000, debug=True)