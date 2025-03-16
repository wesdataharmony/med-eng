import os
import json
import sqlite3
import psycopg2
import requests
import hashlib
import time
from urllib.parse import urljoin
import threading
import queue
from datetime import datetime
import subprocess
import webbrowser
from config.settings import DB_CONFIG_SQLITE, DB_CONFIG_POSTGRES

# Configurações de URL e diretórios
DATA_URL = "https://api.github.com/repos/wandersondsm/teste_engenheiro/contents/data?ref=main"
RAW_BASE_URL = "https://raw.githubusercontent.com/wandersondsm/teste_engenheiro/main/data/"
LOCAL_DATA_DIR = None

# Fila para armazenar arquivos baixados
download_queue = queue.Queue()

# Variáveis globais para controle de progresso
downloaded_count = 0
total_to_download = 0
processed_count = 0
errors_count = 0
total_to_process = 0

counter_lock = threading.Lock()

def get_sqlite_connection():
    """Cria uma conexão com o banco de dados SQLite"""
    conn = sqlite3.connect(
        DB_CONFIG_SQLITE['database'],
        check_same_thread=False
    )
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_sqlite_schema(conn):
    """Cria as tabelas no SQLite com verificação de existência"""
    cursor = conn.cursor()
    
    # Tabela patients primeiro (devido às FKs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            gender TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            condition_text TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            medication_text TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_name TEXT PRIMARY KEY,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Criar índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conditions_text ON conditions(condition_text)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medications_text ON medications(medication_text)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_gender ON patients(gender)")
    
    conn.commit()
    cursor.close()

def get_postgres_connection():
    """Cria uma conexão com o banco de dados PostgreSQL"""
    conn = psycopg2.connect(
        dbname=DB_CONFIG_POSTGRES['dbname'],
        user=DB_CONFIG_POSTGRES['user'],
        password=DB_CONFIG_POSTGRES['password'],
        host=DB_CONFIG_POSTGRES['host'],
        port=DB_CONFIG_POSTGRES['port'],
        schema=DB_CONFIG_POSTGRES['schema']
    )
    return conn

def create_postgres_schema(conn):
    """Cria o schema e as tabelas no PostgreSQL com a coluna data_inclusao"""
    cursor = conn.cursor()
    
    # Criar o schema se não existir
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}")
    
    # Definir o search_path para o schema especificado
    cursor.execute(f"SET search_path TO {DB_CONFIG_POSTGRES['schema']}")
    
    # Criar tabela patients
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.patients (
            patient_id TEXT PRIMARY KEY,
            gender TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Criar tabela conditions
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.conditions (
            id SERIAL PRIMARY KEY,
            patient_id TEXT,
            condition_text TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES {DB_CONFIG_POSTGRES['schema']}.patients(patient_id)
        )
    """)
    
    # Criar tabela medications
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.medications (
            id SERIAL PRIMARY KEY,
            patient_id TEXT,
            medication_text TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES {DB_CONFIG_POSTGRES['schema']}.patients(patient_id)
        )
    """)
    
    # Criar tabela processed_files
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.processed_files (
            file_name TEXT PRIMARY KEY,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Criar índices para otimizar consultas
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_conditions_text ON {DB_CONFIG_POSTGRES['schema']}.conditions(condition_text)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_medications_text ON {DB_CONFIG_POSTGRES['schema']}.medications(medication_text)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_patients_gender ON {DB_CONFIG_POSTGRES['schema']}.patients(gender)")
    
    conn.commit()
    cursor.close()

def migrate_to_postgres():
    """Migra os dados do SQLite para o PostgreSQL"""
    sqlite_conn = get_sqlite_connection()  # Função que conecta ao SQLite
    postgres_conn = get_postgres_connection()  # Função que conecta ao PostgreSQL
    create_postgres_schema(postgres_conn)  # Cria o schema e as tabelas
    
    sqlite_cursor = sqlite_conn.cursor()
    postgres_cursor = postgres_conn.cursor()
    
    # Migrar patients
    sqlite_cursor.execute("SELECT patient_id, gender, data_inclusao FROM patients")
    for row in sqlite_cursor.fetchall():
        postgres_cursor.execute(
            f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.patients (patient_id, gender, data_inclusao) VALUES (%s, %s, %s) ON CONFLICT (patient_id) DO NOTHING",
            row
        )
    
    # Migrar conditions
    sqlite_cursor.execute("SELECT patient_id, condition_text, data_inclusao FROM conditions")
    for row in sqlite_cursor.fetchall():
        postgres_cursor.execute(
            f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.conditions (patient_id, condition_text, data_inclusao) VALUES (%s, %s, %s)",
            row
        )
    
    # Migrar medications
    sqlite_cursor.execute("SELECT patient_id, medication_text, data_inclusao FROM medications")
    for row in sqlite_cursor.fetchall():
        postgres_cursor.execute(
            f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.medications (patient_id, medication_text, data_inclusao) VALUES (%s, %s, %s)",
            row
        )
    
    # Migrar processed_files
    sqlite_cursor.execute("SELECT file_name, data_inclusao FROM processed_files")
    for row in sqlite_cursor.fetchall():
        postgres_cursor.execute(
            f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.processed_files (file_name, data_inclusao) VALUES (%s, %s) ON CONFLICT (file_name) DO NOTHING",
            row
        )
    
    postgres_conn.commit()
    sqlite_cursor.close()
    postgres_cursor.close()
    sqlite_conn.close()
    postgres_conn.close()
    print("Migração concluída com sucesso!")


def is_file_processed(conn, file_name):
    """Verifica se o arquivo já foi processado"""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_files WHERE file_name = ?", (file_name,))
    result = cursor.fetchone()
    cursor.close()
    return result is not None

def mark_file_as_processed(conn, file_name):
    """Marca o arquivo como processado"""
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO processed_files (file_name) VALUES (?)", (file_name,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
    finally:
        cursor.close()

def get_remote_files():
    """Obtém arquivos com tratamento de erro melhorado"""
    try:
        page = 1
        all_files = []
        
        while True:
            response = requests.get(
                f"{DATA_URL}&page={page}&per_page=100",
                headers={"Accept": "application/vnd.github+json"},
                timeout=30
            )
            response.raise_for_status()
            
            files = response.json()
            if not files:
                break
                
            all_files.extend([
                f for f in files 
                if isinstance(f, dict) and f.get('type') == 'file' and f.get('name', '').endswith('.json')
            ])
            
            if 'next' not in response.links:
                break
                
            page += 1

        return {f['name']: f for f in all_files if 'name' in f}
        
    except Exception as e:
        print(f"\nERRO: Falha na conexão com o GitHub - {str(e)}")
        return None

def calculate_file_hash(file_path):
    """Calcula hash SHA-256 do arquivo"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(4096):
            sha256.update(chunk)
    return sha256.hexdigest()

def print_progress(current, total, prefix=""):
    """Exibe uma barra de progresso simples no console"""
    bar_length = 40
    fraction = current / total if total else 0
    arrow = int(fraction * bar_length) * "="
    spaces = (bar_length - len(arrow)) * " "
    percent = int(fraction * 100)
    print(f"\r{prefix} [{arrow}{spaces}] {percent}% ({current}/{total})", end="", flush=True)

def download_files():
    """Baixa os arquivos JSON do repositório e os adiciona à fila"""
    global downloaded_count, total_to_download, total_to_process
    start_time = time.time()
    conn = get_sqlite_connection()
    try:
        remote_files = get_remote_files()
        
        if not remote_files:
            print("Nenhum arquivo encontrado no repositório!")
            return

        files_to_download = {}
        for name, meta in remote_files.items():
            if is_file_processed(conn, name):
                print(f"Arquivo {name} já foi processado, pulando...")
                continue
            files_to_download[name] = meta
        
        total_to_download = len(files_to_download)
        total_to_process = total_to_download

        print(f"\nTotal de arquivos a baixar: {total_to_download}")

        for name, meta in files_to_download.items():
            file_url = urljoin(RAW_BASE_URL, name)
            file_path = os.path.join(LOCAL_DATA_DIR, name)
            
            try:
                response = requests.get(file_url)
                response.raise_for_status()
                
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                    
                download_queue.put(file_path)
                with counter_lock:
                    downloaded_count += 1
                    print_progress(downloaded_count, total_to_download, prefix="Download")
            except Exception as e:
                print(f"\nErro ao baixar {name}: {str(e)}")
                if os.path.exists(file_path):
                    os.remove(file_path)
        
        download_queue.put(None)
        elapsed = time.time() - start_time
        print(f"\nDownload concluído: {downloaded_count} novos arquivos")
        print(f"Tempo total: {int(elapsed // 60)}m {int(elapsed % 60)}s")
    finally:
        conn.close()

def clean_text(text):
    """Substitui barras e colchetes nos textos."""
    return text.replace("/", "-").replace("\\", "-").replace("[", "(").replace("]", ")")

def process_files():
    """Processa os arquivos da fila"""
    global processed_count, errors_count
    start_time = time.time()
    conn = get_sqlite_connection()
    try:
        while True:
            file_path = download_queue.get()
            if file_path is None:
                download_queue.put(None)
                break

            file_name = os.path.basename(file_path)
            if is_file_processed(conn, file_name):
                print(f"\nArquivo {file_name} já foi processado, pulando...")
                download_queue.task_done()
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    entries = data.get('entry', [])

                    patient = next(
                        (e['resource'] for e in entries
                         if e.get('resource', {}).get('resourceType') == 'Patient'),
                        None
                    )

                    if not patient:
                        download_queue.task_done()
                        continue

                    patient_id = patient.get('id')
                    gender = patient.get('gender', 'unknown')

                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR IGNORE INTO patients (patient_id, gender) VALUES (?, ?)",
                        (patient_id, gender)
                    )

                    for entry in entries:
                        resource = entry.get('resource', {})
                        resource_type = resource.get('resourceType')

                        if resource_type == 'Condition':
                            condition_text = clean_text(resource.get('code', {}).get('text', ''))
                            if condition_text:
                                cursor.execute(
                                    "INSERT INTO conditions (patient_id, condition_text) VALUES (?, ?)",
                                    (patient_id, condition_text)
                                )

                        elif resource_type == 'MedicationRequest':
                            medication_text = clean_text(resource.get('medicationCodeableConcept', {}).get('text', ''))
                            if medication_text:
                                cursor.execute(
                                    "INSERT INTO medications (patient_id, medication_text) VALUES (?, ?)",
                                    (patient_id, medication_text)
                                )

                    conn.commit()
                    mark_file_as_processed(conn, file_name)
                    with counter_lock:
                        processed_count += 1
                        print_progress(processed_count, total_to_process, prefix="Ingestão")
                    print(f"\nArquivo {file_name} processado com sucesso.")
            except Exception as e:
                with counter_lock:
                    errors_count += 1
                print(f"\nErro no arquivo {file_name}: {str(e)}")
                conn.rollback()
            finally:
                download_queue.task_done()
    finally:
        conn.close()
        elapsed = time.time() - start_time
        print("\nProcessamento concluído:")
        print(f"- Arquivos processados: {processed_count}")
        print(f"- Erros: {errors_count}")
        print(f"- Tempo total: {int(elapsed // 60)}m {int(elapsed % 60)}s")

def handle_dashboard_choice(choice):
    if choice == 'S':
        print("Iniciando dashboard...")
        subprocess.Popen(["python", "-m", "app.routes"])
        webbrowser.open("http://localhost:5000/")
    elif choice == 'N':
        print("Encerrando o programa.")

def validate_environment():
    """Verifica estrutura de diretórios necessária"""
    required_dirs = [
        os.path.join(os.path.dirname(__file__), '..', 'data'),
        os.path.join(os.path.dirname(__file__), '..', 'app', 'static'),
        os.path.join(os.path.dirname(__file__), '..', 'app', 'templates')
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

def check_postgres_tables_exist():
    """Verifica se todas as tabelas necessárias existem no PostgreSQL"""
    required_tables = {'patients', 'conditions', 'medications', 'processed_files'}
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s
        """, (DB_CONFIG_POSTGRES['schema'],))
        existing_tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        return required_tables.issubset(existing_tables)
    except Exception as e:
        print(f"\nERRO: Falha ao verificar tabelas no PostgreSQL - {str(e)}")
        return False

def handle_migration_choice(choice):
    """Lida com a escolha de migração para o PostgreSQL"""
    if choice == 'S':
        if check_postgres_tables_exist():
            print("\nA migração das tabelas já foi realizada anteriormente.")
        else:
            try:
                print("\nIniciando migração para PostgreSQL...")
                migrate_to_postgres()
                print("Migração concluída com sucesso!")
            except Exception as e:
                print(f"\nERRO NA MIGRAÇÃO: {str(e)}")

def handle_visualization_choice(choice):
    """Lida com a escolha de visualização do dashboard"""
    if choice == 'V':
        print("\nIniciando dashboard...")
        subprocess.Popen(["python", "-m", "app.routes"])
        webbrowser.open("http://localhost:5000/")
    elif choice == 'N':
        print("\nEncerrando o programa.")

def main():
    global LOCAL_DATA_DIR
    validate_environment()

    conn = get_sqlite_connection()
    create_sqlite_schema(conn)
    
    try:
        remote_files = get_remote_files()
    except Exception as e:
        print(f"Erro ao obter arquivos remotos: {str(e)}")
        conn.close()
        return

    if remote_files is None:
        print("Não foi possível verificar arquivos remotos. Verifique sua conexão.")
        conn.close()
        return
        
    files_to_process = [name for name in remote_files if not is_file_processed(conn, name)]
    
    if not files_to_process:
        conn.close()
        choice = input("\nTodos os arquivos já foram processados!\nDeseja visualizar os dados? (S/N) ").strip().upper()
        handle_dashboard_choice(choice)
        return

    current_time = datetime.now().strftime("%Y%m%d_Hs%H-%M")
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    process_dir = os.path.join(base_dir, 'data', f'data_process_{current_time}')
    os.makedirs(process_dir, exist_ok=True)
    LOCAL_DATA_DIR = process_dir
    conn.close()

    download_thread = threading.Thread(target=download_files)
    process_thread = threading.Thread(target=process_files)
    
    download_thread.start()
    process_thread.start()
    
    download_thread.join()
    process_thread.join()

    # Fluxo pós-processamento
    #while True:
     #   migration_choice = input("\nDeseja migrar os dados para o Postgres? (S/N) ").strip().upper()
      #  if migration_choice in ('S', 'N'):
       #     break
        #print("Opção inválida. Digite S ou N.")
    
    #handle_migration_choice(migration_choice)

    while True:
        visualization_choice = input("\nProcessamento concluído! Deseja visualizar os dados? (V/N) ").strip().upper()
        if visualization_choice in ('V', 'N'):
            break
        print("Opção inválida. Digite V para visualizar ou N para sair.")
    
    handle_visualization_choice(visualization_choice)

if __name__ == '__main__':
    main()