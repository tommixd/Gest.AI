import os
import sys
import threading
import re
import docx
import json
import shutil
import mysql.connector
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, g, request, send_file, jsonify
from werkzeug.utils import secure_filename
from db_config import DB_CONFIG

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
# Usamos DB_CONFIG partilhado em db_config.py
PASTA_UPLOADS = 'PastaUploadsSiteTest'

# --- CONFIGURAÇÃO DA IA EM BACKGROUND ---
global_retriever = None
global_llm = None
ia_pronta = False

def migrar_contratos_existentes_para_bd():
    """Varre Modelos Gerados e registra contratos antigos que não estão na BD."""
    ROOT_DIR = os.path.dirname(BASE_DIR)
    pasta_modelos = os.path.join(ROOT_DIR, 'Modelos Contratuais', 'Modelos Gerados')
    
    if not os.path.exists(pasta_modelos):
        print("[!] Pasta Modelos Gerados não encontrada.")
        return
    
    print("[*] A varrer contratos existentes no disco...")
    ficheiros_registados = 0
    
    try:
        ligacao = mysql.connector.connect(**DB_CONFIG)
        cursor = ligacao.cursor(dictionary=True)
        
        # Obter lista de documentos já registados
        cursor.execute("SELECT caminho FROM documentos WHERE categoria='gerado'")
        caminhos_existentes = {row["caminho"] for row in cursor.fetchall()}
        
        # Varrer estrutura: Contrato_Name/2025-2026/ficheiro.docx
        for nome_contrato in os.listdir(pasta_modelos):
            pasta_contrato = os.path.join(pasta_modelos, nome_contrato)
            if not os.path.isdir(pasta_contrato):
                continue
            
            for periodo in os.listdir(pasta_contrato):
                pasta_periodo = os.path.join(pasta_contrato, periodo)
                if not os.path.isdir(pasta_periodo):
                    continue
                
                for ficheiro in os.listdir(pasta_periodo):
                    if not ficheiro.lower().endswith(('.docx', '.pdf')):
                        continue
                    
                    # Caminho relativo para a BD
                    caminho_relativo = os.path.join('Modelos Contratuais', 'Modelos Gerados', 
                                                    nome_contrato, periodo, ficheiro).replace('\\', '/')
                    
                    if caminho_relativo in caminhos_existentes:
                        continue
                    
                    try:
                        data_upload = datetime.now().strftime('%Y-%m-%d')
                        cursor.execute(
                            """
                            INSERT INTO documentos (nome, caminho, categoria, data_upload, versao_contrato)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (ficheiro, caminho_relativo, 'gerado', data_upload, 1)
                        )
                        ficheiros_registados += 1
                        print(f"[+] Registado: {caminho_relativo}")
                    except Exception as e:
                        print(f"[!] Erro ao registar {ficheiro}: {e}")
        
        ligacao.commit()
        cursor.close()
        ligacao.close()
        print(f"[OK] Migração concluída: {ficheiros_registados} documentos registados.")
    except Exception as e:
        print(f"[!] Erro na migração: {e}")

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

# Executar migração de contratos antigos antes de iniciar a IA
print("\n[Verificando contratos existentes...]")
migrar_contratos_existentes_para_bd()

# Depois iniciar a IA
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

def obter_ano_letivo_destino(dados_formulario):
    """Extrai o ano letivo do formulário ou gera baseado na data atual."""
    ano_letivo = dados_formulario.get("ano_letivo", "").strip()
    if ano_letivo:
        return ano_letivo
    # Se não estiver no formulário, gera baseado na data (ex: 2025-2026)
    ano_atual = datetime.now().year
    if datetime.now().month >= 9:
        return f"{ano_atual}-{ano_atual + 1}"
    else:
        return f"{ano_atual - 1}-{ano_atual}"


def registar_documentos_gerados_na_bd(nome_subpasta_docente, ano_letivo, ficheiros_gerados, tipo_contratacao):
    """Registra os documentos gerados na tabela documentos da BD."""
    ROOT_DIR = os.path.dirname(BASE_DIR)
    categoria = CATEGORIA_POR_TIPO.get(tipo_contratacao, "gerado")
    versao = 1 if ano_letivo.startswith(str(datetime.now().year)) else 2
    
    try:
        ligacao = mysql.connector.connect(**DB_CONFIG)
        cursor = ligacao.cursor()
        data_upload = datetime.now().strftime('%Y-%m-%d')
        
        for nome_ficheiro in ficheiros_gerados:
            # Caminho relativo para a BD
            caminho_relativo = os.path.join('Modelos Contratuais', 'Modelos Gerados', nome_subpasta_docente, ano_letivo, nome_ficheiro)
            caminho_relativo = caminho_relativo.replace('\\', '/')
            
            try:
                cursor.execute(
                    """
                    INSERT INTO documentos (nome, caminho, categoria, data_upload, versao_contrato)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (nome_ficheiro, caminho_relativo, categoria, data_upload, versao)
                )
                print(f"[OK] Registado na BD: {nome_ficheiro}")
            except Exception as e:
                print(f"[!] Erro ao registar {nome_ficheiro} na BD: {e}")
        
        ligacao.commit()
        cursor.close()
        ligacao.close()
        print(f"[*] Documentos registados com sucesso na BD.")
    except Exception as e:
        print(f"[!] Erro ao conectar à BD para registo de documentos: {e}")


def processar_templates(dados_formulario, tipo_contratacao):
    categoria_bd = CATEGORIA_POR_TIPO.get(tipo_contratacao)
    if not categoria_bd:
        print(f"[!] Erro: Tipo de contratação '{tipo_contratacao}' não mapeado.")
        return None, f"Tipo de contratação '{tipo_contratacao}' não reconhecido."

    nome_docente = dados_formulario.get("nome_docente", "Docente_Desconhecido")
    nome_subpasta_docente = criar_nome_pasta_limpo(nome_docente)
    ano_letivo = obter_ano_letivo_destino(dados_formulario)
    
    ROOT_DIR = os.path.dirname(BASE_DIR)
    # Estrutura: Contrato_Nome/2025-2026/
    caminho_final = os.path.join(ROOT_DIR, 'Modelos Contratuais', 'Modelos Gerados', nome_subpasta_docente, ano_letivo)
    
    print(f"[*] A iniciar processo para: {nome_docente}")
    print(f"[*] Ano letivo: {ano_letivo}")
    print(f"[*] Categoria alvo na BD: {categoria_bd}")
    print(f"[*] Pasta de destino: {caminho_final}")

    if not os.path.exists(caminho_final):
        os.makedirs(caminho_final)
        print(f"[*] Criada pasta de processo: {nome_subpasta_docente}/{ano_letivo}")

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

    # Registar os documentos gerados na BD
    registar_documentos_gerados_na_bd(nome_subpasta_docente, ano_letivo, ficheiros_gerados, tipo_contratacao)

    # Retorna o caminho completo incluindo o período
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
            # Para documentos com estrutura: Modelos Contratuais/Modelos Gerados/Contrato_Name/[AnoLetivo/][AnoLetivo/]ficheiro
            if len(partes) >= 4 and len(partes) > 2 and 'Modelos Gerados' in doc['caminho']:
                # Nome do contrato está sempre em partes[2] (após Modelos Contratuais/Modelos Gerados)
                nome_contrato = partes[2].replace('_', ' ')
                
                # Para o "ano_pasta", usamos tudo entre o contrato e o ficheiro
                if len(partes) == 4:
                    # Estrutura simples: Modelos Contratuais/Modelos Gerados/Contrato/ficheiro
                    ano_pasta = "Ficheiros"
                elif len(partes) == 5:
                    # Estrutura: Modelos Contratuais/Modelos Gerados/Contrato/Ano/ficheiro
                    ano_pasta = partes[-2]
                else:
                    # Estrutura complexa: Modelos Contratuais/Modelos Gerados/Contrato/Ano1/Ano2/ficheiro
                    # Combinamos os níveis entre contrato e ficheiro
                    subpastas = '/'.join(partes[3:-1])
                    ano_pasta = subpastas
                
                # Inicializa o dicionário do contrato se não existir
                if nome_contrato not in documentos_agrupados[cat]:
                    documentos_agrupados[cat][nome_contrato] = {}
                
                # Inicializa a lista de documentos para este ano/período se não existir
                if ano_pasta not in documentos_agrupados[cat][nome_contrato]:
                    documentos_agrupados[cat][nome_contrato][ano_pasta] = []
                
                documentos_agrupados[cat][nome_contrato][ano_pasta].append(doc)
        else:
            if 'Geral' not in documentos_agrupados[cat]: documentos_agrupados[cat]['Geral'] = {}
            if 'Ficheiros' not in documentos_agrupados[cat]['Geral']:
                documentos_agrupados[cat]['Geral']['Ficheiros'] = []
            documentos_agrupados[cat]['Geral']['Ficheiros'].append(doc)
    
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
            cursor.execute("SELECT nome FROM docentes ORDER BY nome")
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

        lista_cargas = []
        try:
            cursor.execute(
                "SELECT id_carga, tempo_contratual, tempo_aulas, tempo_apoio, tempo_preparacao, percentagem FROM carga_horaria ORDER BY id_carga"
            )
            lista_cargas = cursor.fetchall()
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
                           cursos=lista_cursos,
                           cargas=lista_cargas)


@app.route('/api/docente-detalhes')
def docente_detalhes():
    nome = request.args.get('nome', '').strip()
    if not nome:
        return jsonify({"erro": "nome ausente"}), 400

    detalhes = {
        "nome_docente": nome,
        "tipo_docente": None,
        "departamento": None,
        "total_horas_contacto": None,
        "horario_semanal": None
    }

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # 1. Buscar info base do docente e o Histórico Permanente!
        cursor.execute("SELECT tipo_docente, departamento, id_contrato, dados_historico FROM docentes WHERE nome = %s", (nome,))
        docente = cursor.fetchone()
        
        if docente:
            detalhes["tipo_docente"] = docente["tipo_docente"]
            detalhes["departamento"] = docente["departamento"]
            
            # MAGIA: Se tiver histórico guardado, carrega TUDO (UCs, Juris, Áreas, etc.)
            if docente.get("dados_historico"):
                historico = json.loads(docente["dados_historico"])
                for chave, valor in historico.items():
                    if valor:
                        detalhes[chave] = valor
            
            # Buscar dados da Carga horária
            if docente["id_contrato"]:
                cursor.execute(
                    "SELECT ch.tempo_contratual, ch.tempo_aulas, ch.tempo_apoio, ch.tempo_preparacao, ch.percentagem "
                    "FROM contratos c JOIN carga_horaria ch ON c.carga_horaria_id_carga = ch.id_carga "
                    "WHERE c.id_contrato = %s",
                    (docente["id_contrato"],)
                )
                contrato = cursor.fetchone()
                if contrato:
                    detalhes["total_horas_contacto"] = contrato["tempo_aulas"]
                    detalhes["horario_semanal"] = f"Carga {contrato['percentagem']}%: {contrato['tempo_contratual']}h total / {contrato['tempo_aulas']}h aulas / {contrato['tempo_apoio']}h apoio / {contrato['tempo_preparacao']}h preparação"

        # 2. Buscar Rascunho (Se o utilizador tiver um rascunho a meio, ele ganha prioridade sobre o histórico)
        cursor.execute(
            "SELECT dados_formulario FROM rascunhos WHERE nome_docente = %s ORDER BY id DESC LIMIT 1",
            (nome,)
        )
        rascunho = cursor.fetchone()
        if rascunho and rascunho["dados_formulario"]:
            dados_form = json.loads(rascunho["dados_formulario"])
            for chave, valor in dados_form.items():
                if valor:
                    detalhes[chave] = valor

        cursor.close()
    except Exception as e:
        print(f"[!] Erro ao buscar detalhes do docente: {e}")

    return jsonify(detalhes)


@app.route('/api/cargas-horias')
def cargas_horias():
    """Retorna a lista de cargas horárias disponíveis da base de dados."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_carga, tempo_contratual, tempo_aulas, tempo_apoio, tempo_preparacao, percentagem FROM carga_horaria ORDER BY tempo_contratual ASC"
        )
        cargas = cursor.fetchall()
        cursor.close()
        
        # Formatar os dados para exibição
        cargas_formatadas = []
        for carga in cargas:
            # Converter Decimal para float explicitamente
            tempo_contratual = float(carga["tempo_contratual"])
            tempo_aulas = float(carga["tempo_aulas"])
            tempo_apoio = float(carga["tempo_apoio"])
            tempo_preparacao = float(carga["tempo_preparacao"])
            percentagem = float(carga["percentagem"])
            
            item = {
                "id": int(carga["id_carga"]),
                "tempo_contratual": tempo_contratual,
                "tempo_aulas": tempo_aulas,
                "tempo_apoio": tempo_apoio,
                "tempo_preparacao": tempo_preparacao,
                "percentagem": percentagem,
                "display": f"Carga {carga['id_carga']}: {tempo_contratual}h total / {tempo_aulas}h aulas / {tempo_apoio}h apoio / {tempo_preparacao}h preparação ({percentagem}%)"
            }
            cargas_formatadas.append(item)
        
        return jsonify({"cargas": cargas_formatadas})
    except Exception as e:
        print(f"[!] Erro ao buscar cargas horárias: {e}")
        return jsonify({"erro": "Erro ao buscar cargas horárias"}), 500


@app.route('/submeter-contratacao', methods=['POST'])
def submeter_contratacao():
    dados = request.get_json()
    tipo = dados.get('tipo')
    
    nome_docente_raw = dados.get('nome_docente')
    if not nome_docente_raw or not tipo:
        return jsonify({"erro": "Dados incompletos: O nome do docente é obrigatório."}), 400
    
    rascunho_id = dados.get('rascunho_id') or request.args.get('rascunho_id')
    caminho_pasta, resultado = processar_templates(dados, tipo)
    
    if caminho_pasta is None:
        return jsonify({"erro": resultado}), 400
    
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True) # <-- IMPORTANTE: tem de ser dictionary=True
        ROOT_DIR = os.path.dirname(BASE_DIR)
        
        ficheiros_gerados = os.listdir(caminho_pasta)
        documentos_inseridos = 0
        
        for ficheiro in ficheiros_gerados:
            caminho_ficheiro_absoluto = os.path.join(caminho_pasta, ficheiro)
            if os.path.isfile(caminho_ficheiro_absoluto):
                caminho_relativo_ficheiro = os.path.relpath(caminho_ficheiro_absoluto, ROOT_DIR).replace('\\', '/')
                cursor.execute(
                    "INSERT INTO documentos (nome, caminho, categoria, data_upload) VALUES (%s, %s, %s, %s)",
                    (ficheiro, caminho_relativo_ficheiro, 'gerado', datetime.now().isoformat())
                )
                documentos_inseridos += 1
        
        # --- GUARDAR HISTÓRICO NA TABELA DOCENTES ---
        try:
            dados_json = json.dumps(dados) # Transforma o form todo em texto
            cursor.execute("SELECT id_docente FROM docentes WHERE nome = %s", (nome_docente_raw,))
            docente_existente = cursor.fetchone()
            
            departamento = dados.get('departamento', dados.get('area_contratacao', 'matemática'))
            dept_mapping = {
                'matemática': 'matemática', 'matematica': 'matemática',
                'física': 'física', 'fisica': 'física',
                'gestão': 'gestão', 'gestao': 'gestão',
                'informática': 'matemática', 'informatica': 'matemática',
                'design': 'gestão'
            }
            departamento_valido = dept_mapping.get(departamento.strip().lower(), 'matemática')
            tipo_docente_bd = 'carreira' if tipo in ['renovacao-integral', 'renovacao-parcial'] else 'contratado'

            if not docente_existente:
                cursor.execute(
                    "INSERT INTO docentes (nome, tipo_docente, departamento, dados_historico) VALUES (%s, %s, %s, %s)",
                    (nome_docente_raw, tipo_docente_bd, departamento_valido, dados_json)
                )
            else:
                cursor.execute(
                    "UPDATE docentes SET dados_historico = %s WHERE id_docente = %s",
                    (dados_json, docente_existente['id_docente'])
                )
        except Exception as err:
            print(f"[!] Erro ao registar docente/historico na BD: {err}")
        
        if rascunho_id:
            cursor.execute("DELETE FROM rascunhos WHERE id = %s", (rascunho_id,))
        
        db.commit()
        cursor.close()
        
        return jsonify({
            "mensagem": f"Sucesso: {documentos_inseridos} documentos gerados.", 
            "pasta": caminho_pasta,
            "ficheiros": ficheiros_gerados
        }), 200

    except Exception as e:
        print(f"[!] Erro ao registar na BD: {e}")
        return jsonify({"erro": f"Erro BD: {e}"}), 500

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

# --- ROTAS DE ELIMINAÇÃO ---
@app.route('/api/apagar-todos-rascunhos', methods=['DELETE'])
def apagar_todos_rascunhos():
    """Apaga todos os rascunhos da base de dados."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM rascunhos")
        db.commit()
        cursor.close()
        
        print("[OK] Todos os rascunhos foram apagados.")
        return jsonify({"sucesso": True, "mensagem": "Todos os rascunhos foram apagados com sucesso."}), 200
    except Exception as e:
        print(f"[!] Erro ao apagar rascunhos: {e}")
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/apagar-rascunho/<int:rascunho_id>', methods=['DELETE'])
def apagar_rascunho(rascunho_id):
    """Apaga um rascunho específico da base de dados."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM rascunhos WHERE id = %s", (rascunho_id,))
        db.commit()
        cursor.close()
        
        print(f"[OK] Rascunho {rascunho_id} foi apagado.")
        return jsonify({"sucesso": True, "mensagem": "Rascunho apagado com sucesso."}), 200
    except Exception as e:
        print(f"[!] Erro ao apagar rascunho: {e}")
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/apagar-documento/<int:doc_id>', methods=['DELETE'])
def apagar_documento(doc_id):
    """Apaga um documento específico - INCLUINDO toda a pasta do contrato na BD e no disco."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Buscar o documento
        cursor.execute("SELECT caminho FROM documentos WHERE id = %s", (doc_id,))
        doc = cursor.fetchone()
        
        if not doc:
            cursor.close()
            print(f"[!] Documento {doc_id} não encontrado na BD")
            return jsonify({"sucesso": False, "erro": "Documento não encontrado."}), 404
        
        print(f"[DEBUG] Documento encontrado: {doc['caminho']}")
        
        # Extrair o diretório do contrato (pasta pai)
        # Exemplo: "Modelos Contratuais/Modelos Gerados/Contrato_Maria_Antonia/ficheiro.docx"
        caminho_partes = doc['caminho'].replace('\\', '/').split('/')
        print(f"[DEBUG] Partes do caminho: {caminho_partes}")
        
        # Procurar a pasta do contrato (começa com "Contrato_")
        pasta_contrato = None
        indice_contrato = -1
        
        for i, parte in enumerate(caminho_partes):
            if parte.startswith('Contrato_'):
                pasta_contrato = parte
                indice_contrato = i
                print(f"[DEBUG] Pasta do contrato encontrada: {pasta_contrato} no índice {i}")
                break
        
        if pasta_contrato:
            print(f"[DEBUG] A eliminar pasta do contrato: {pasta_contrato}")
            
            # Buscar TODOS os documentos desta pasta na BD
            cursor.execute(
                "SELECT id, caminho FROM documentos WHERE caminho LIKE %s",
                (f"%{pasta_contrato}%",)
            )
            docs_na_pasta = cursor.fetchall()
            print(f"[DEBUG] Encontrados {len(docs_na_pasta)} documentos na pasta")
            
            ROOT_DIR = os.path.dirname(BASE_DIR)
            caminho_abs_pasta = os.path.join(ROOT_DIR, *caminho_partes[:indice_contrato + 1])
            print(f"[DEBUG] Caminho absoluto da pasta: {caminho_abs_pasta}")
            print(f"[DEBUG] Pasta existe? {os.path.exists(caminho_abs_pasta)}")
            
            ficheiros_eliminados = 0
            
            # Apagar ficheiros fisicamente
            if os.path.exists(caminho_abs_pasta):
                try:
                    print(f"[DEBUG] Tentando eliminar pasta: {caminho_abs_pasta}")
                    shutil.rmtree(caminho_abs_pasta)
                    ficheiros_eliminados = len(docs_na_pasta)
                    print(f"[OK] Pasta do contrato eliminada: {caminho_abs_pasta}")
                except Exception as e:
                    print(f"[!] Erro ao eliminar pasta: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({"sucesso": False, "erro": f"Erro ao eliminar pasta: {e}"}), 500
            else:
                print(f"[!] Pasta não existe: {caminho_abs_pasta}")
            
            # Apagar TODOS os documentos desta pasta na BD
            print(f"[DEBUG] A eliminar registos da BD para: %{pasta_contrato}%")
            cursor.execute(
                "DELETE FROM documentos WHERE caminho LIKE %s",
                (f"%{pasta_contrato}%",)
            )
            print(f"[DEBUG] Registos eliminados: {cursor.rowcount}")
        else:
            print(f"[DEBUG] Pasta Contrato_ não encontrada, eliminando ficheiro individual")
            # Se não encontrar pasta Contrato_, apenas apagar o ficheiro individual
            ROOT_DIR = os.path.dirname(BASE_DIR)
            caminho_abs = os.path.join(ROOT_DIR, doc['caminho'])
            
            if os.path.exists(caminho_abs):
                try:
                    os.remove(caminho_abs)
                    print(f"[OK] Ficheiro eliminado: {caminho_abs}")
                except Exception as e:
                    print(f"[!] Erro ao eliminar ficheiro: {e}")
                    return jsonify({"sucesso": False, "erro": f"Erro ao eliminar ficheiro: {e}"}), 500
            
            # Apagar apenas este registo da BD
            cursor.execute("DELETE FROM documentos WHERE id = %s", (doc_id,))
        
        db.commit()
        cursor.close()
        
        print(f"[OK] Documento {doc_id} e contrato associado foram apagados.")
        return jsonify({"sucesso": True, "mensagem": "Contrato e documentos associados foram apagados com sucesso."}), 200
    except Exception as e:
        print(f"[!] Erro ao apagar documento: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/apagar-pasta/<caso>', methods=['DELETE'])
def apagar_pasta(caso):
    """Apaga todos os documentos de uma pasta/caso específico."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Converter espaços em underscores (como são guardados na BD)
        caso_normalizado = caso.replace(' ', '_')
        print(f"[DEBUG] Apagando pasta: '{caso}' -> '{caso_normalizado}'")
        
        # Buscar todos os documentos associados à pasta
        cursor.execute(
            "SELECT id, caminho FROM documentos WHERE caminho LIKE %s",
            (f"%{caso_normalizado}%",)
        )
        documentos = cursor.fetchall()
        print(f"[DEBUG] Encontrados {len(documentos)} documentos na BD")
        pastas_para_apagar = set()
        
        ROOT_DIR = os.path.dirname(BASE_DIR)
        ficheiros_eliminados = 0
        
        for doc in documentos:
            caminho_abs = os.path.join(ROOT_DIR, doc['caminho'])
            print(f"[DEBUG] Tentando eliminar ficheiro: {caminho_abs}")
            
                        # Guardar a pasta do ficheiro
            pasta_do_ficheiro = os.path.dirname(caminho_abs)
            pastas_para_apagar.add(pasta_do_ficheiro)
            
            if os.path.exists(caminho_abs):
                try:
                    os.remove(caminho_abs)
                    ficheiros_eliminados += 1
                    print(f"[OK] Ficheiro eliminado: {caminho_abs}")
                except Exception as e:
                    print(f"[!] Erro ao eliminar ficheiro {caminho_abs}: {e}")
            else:
                print(f"[!] Ficheiro não existe: {caminho_abs}")
                # Eliminar todas as pastas vazias (a partir das mais profundas)
                for pasta in sorted(pastas_para_apagar, reverse=True):
                    try:
                        if os.path.exists(pasta) and not os.listdir(pasta):  # Pasta existe e está vazia
                            os.rmdir(pasta)
                            print(f"[OK] Pasta vazia eliminada: {pasta}")
                    except Exception as e:
                        print(f"[!] Erro ao eliminar pasta {pasta}: {e}")
        
        
        # Eliminar todos os registo da base de dados
        print(f"[DEBUG] A eliminar da BD com padrão: %{caso_normalizado}%")
        cursor.execute("DELETE FROM documentos WHERE caminho LIKE %s", (f"%{caso_normalizado}%",))
        print(f"[DEBUG] Registos eliminados da BD: {cursor.rowcount}")
        db.commit()
        cursor.close()
        
        print(f"[OK] Pasta '{caso}' e conteúdo eliminados ({ficheiros_eliminados} ficheiros).")
        return jsonify({"sucesso": True, "mensagem": f"Pasta eliminada com sucesso ({ficheiros_eliminados} ficheiros removidos)."}), 200
    except Exception as e:
        print(f"[!] Erro ao apagar pasta: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"sucesso": False, "erro": str(e)}), 500

@app.route('/api/renomear-documento/<int:doc_id>', methods=['POST'])
def renomear_documento(doc_id):
    """Renomeia um documento."""
    try:
        dados = request.get_json()
        novo_nome = dados.get('novo_nome', '').strip()
        
        if not novo_nome:
            return jsonify({"sucesso": False, "erro": "Nome não pode estar vazio."}), 400
        
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        # Buscar o documento atual
        cursor.execute("SELECT id, nome, caminho FROM documentos WHERE id = %s", (doc_id,))
        doc = cursor.fetchone()
        
        if not doc:
            cursor.close()
            return jsonify({"sucesso": False, "erro": "Documento não encontrado."}), 404
        
        nome_antigo = doc['nome']
        
        # Se o nome é igual, não fazer nada
        if nome_antigo == novo_nome:
            cursor.close()
            return jsonify({"sucesso": True, "mensagem": "Documento não foi alterado."}), 200
        
        # Atualizar na BD
        cursor.execute(
            "UPDATE documentos SET nome = %s WHERE id = %s",
            (novo_nome, doc_id)
        )
        db.commit()
        cursor.close()
        
        print(f"[OK] Documento renomeado: '{nome_antigo}' -> '{novo_nome}'")
        return jsonify({"sucesso": True, "mensagem": "Documento renomeado com sucesso."}), 200
    except Exception as e:
        print(f"[!] Erro ao renomear documento: {e}")
        return jsonify({"sucesso": False, "erro": str(e)}), 500

if __name__ == '__main__':
    app.run(host="localhost", port=5000, debug=True)