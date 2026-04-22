import os
import sys
import sqlite3
import threading
import re
import docx
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, g, request, send_file, jsonify

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
    # Importamos a função diretamente do teu ficheiro templates.py
    from templates import processar_renovacao
    print("[OK] Motor de templates importado com sucesso.")
except ImportError:
    print("[!] Aviso: Não foi possível importar templates.py. A usar lógica interna.")
    # Fallback caso o ficheiro não exista
    def processar_renovacao(dados): return None
# Inicializa a aplicação
app = Flask(__name__)
app.config["SITE_NAME"] = "Gest.AI"  

DATABASE = os.path.join(BASE_DIR, 'documentos.db')
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
    "novo-contrato": "tempo parcial edital"  # Corrigido para Edital
}

def criar_nome_pasta_limpo(nome_completo):
    nome = nome_completo.replace("Professor ", "").replace("Professora ", "")
    nome = nome.replace("Prof. Dr. ", "").replace("Prof. ", "").replace("Prof. Doutor ", "")
    nome = nome.strip().replace(" ", "_")
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    return f"Contrato_{nome_limpo}"

def processar_templates(dados_formulario, tipo_contratacao):
    """
    Processa os templates Word conforme o tipo de contratação.
    Inclui logs detalhados para diagnóstico de erros.
    """
    categoria_bd = CATEGORIA_POR_TIPO.get(tipo_contratacao)
    if not categoria_bd:
        print(f"[!] Erro: Tipo de contratação '{tipo_contratacao}' não mapeado.")
        return None, f"Tipo de contratação '{tipo_contratacao}' não reconhecido."

    nome_docente = dados_formulario.get("{{nome_docente}}", "Docente_Desconhecido")
    nome_subpasta = criar_nome_pasta_limpo(nome_docente)
    
    # Resolver caminhos absolutos
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
        # IMPORTANTE: Garantir que usamos o caminho absoluto da BD
        print(f"[*] A ligar à BD em: {os.path.abspath(DATABASE)}")
        ligacao = sqlite3.connect(DATABASE)
        ligacao.row_factory = sqlite3.Row
        cursor = ligacao.cursor()
        
        # Procurar templates da categoria correspondente
        cursor.execute("SELECT nome, caminho FROM documentos WHERE categoria LIKE ?", (f"%{categoria_bd}%",))
        templates_encontrados = cursor.fetchall()
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
        # Resolver o caminho do template a partir da raiz do projeto
        caminho_abs_template = os.path.join(ROOT_DIR, template["caminho"])
        
        if not os.path.exists(caminho_abs_template):
            print(f"[!] Ficheiro não encontrado no disco: {caminho_abs_template}")
            continue

        try:
            print(f"[*] A preencher: {nome_ficheiro}...")
            documento = docx.Document(caminho_abs_template)

            # Substituição robusta (Parágrafos)
            for paragrafo in documento.paragraphs:
                for chave, valor in dados_formulario.items():
                    if chave in paragrafo.text and valor:
                        # Substituímos no texto completo do parágrafo para manter a integridade das tags
                        paragrafo.text = paragrafo.text.replace(chave, str(valor))

            # Substituição robusta (Tabelas)
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

# --- ROTAS FLASK ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row 
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

@app.route('/')  
def index():
    db = get_db()
    cursor = db.execute("SELECT * FROM documentos ORDER BY categoria, nome")
    lista_documentos = cursor.fetchall()
    
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
    # Dicionário para os títulos das páginas
    titulos = {
        'renovacao-integral': 'Renovação de Contrato (Integral)',
        'renovacao-parcial': 'Renovação de Contrato (Parcial)',
        'primeira-vez': 'Primeira Contratação (Edital)'
    }
    
    # Dicionário para o regime (box azul)
    regimes = {
        'renovacao-integral': 'Tempo Integral',
        'renovacao-parcial': 'Tempo Parcial',
        'primeira-vez': 'Tempo Parcial Edital'
    }

    titulo = titulos.get(tipo, 'Novo Processo')
    regime_nome = regimes.get(tipo, 'Padrão')
    
    # Importante: passar o 'tipo' para o formulário saber o que submeter
    return render_template('contratacao.html', 
                           titulo=titulo, 
                           regime_nome=regime_nome, 
                           tipo=tipo)


@app.route('/submeter-contratacao', methods=['POST'])
def submeter_contratacao():
    """
    Processa a submissão do formulário, gera os documentos Word 
    e regista o novo processo na base de dados.
    """
    dados = request.get_json()
    tipo = dados.get('tipo')
    
    # Validação: o nome do docente é obrigatório para criar a pasta e registar na BD
    nome_docente_raw = dados.get('{{nome_docente}}')
    if not nome_docente_raw or not tipo:
        return jsonify({"erro": "Dados incompletos: O nome do docente é obrigatório."}), 400
    
    # 1. Chamar a geração de templates Word
    # Esta função preenche os DOCX e guarda-os na pasta 'Em_Processamento'
    caminho_pasta, resultado = processar_templates(dados, tipo)
    
    if caminho_pasta is None:
        # Se a função retornar None, significa que não encontrou templates ou houve erro
        return jsonify({"erro": resultado}), 400
    
    try:
        # 2. Registar o novo processo na Base de Dados
        db = get_db()
        
        # Limpar o nome para o registo na BD
        nome_docente_limpo = nome_docente_raw.replace(' ', '_').replace('.', '')
        
        # Obter o caminho relativo à raiz do projeto para a BD
        ROOT_DIR = os.path.dirname(BASE_DIR)
        caminho_relativo = os.path.relpath(caminho_pasta, ROOT_DIR).replace('\\', '/')
        
        # Inserir o registo do processo (pasta) na BD
        # Usamos a categoria 'processamento' para que apareça no topo do site
        db.execute(
            "INSERT INTO documentos (nome, caminho, categoria, data_upload) VALUES (?, ?, ?, ?)",
            (f"Processo_{nome_docente_limpo}", caminho_relativo, 'processamento', datetime.now().isoformat())
        )
        db.commit()
        
        print(f"[OK] Processo registado na BD: Processo_{nome_docente_limpo}")
        
        return jsonify({
            "mensagem": "Sucesso: Documentos gerados e processo registado.", 
            "pasta": caminho_pasta,
            "ficheiros": resultado
        }), 200

    except Exception as e:
        print(f"[!] Erro ao registar na BD: {e}")
        return jsonify({"erro": f"Documentos gerados, mas erro ao registar na BD: {e}"}), 500

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
    doc = db.execute("SELECT caminho FROM documentos WHERE id = ?", (doc_id,)).fetchone()
    if doc:
        ROOT_DIR = os.path.dirname(BASE_DIR)
        caminho_abs = os.path.join(ROOT_DIR, doc['caminho'])
        if os.path.exists(caminho_abs): return send_file(caminho_abs)
    return "Não encontrado", 404

if __name__ == '__main__':
    app.run(host="localhost", port=5000, debug=True)