import os
import json
import sqlite3
import requests
import hashlib
import time
from urllib.parse import urljoin
import threading
import queue
from config.settings import DB_CONFIG_SQLITE

# Configurações de URL e diretórios
DATA_URL = "https://api.github.com/repos/wandersondsm/teste_engenheiro/contents/data?ref=main"
RAW_BASE_URL = "https://raw.githubusercontent.com/wandersondsm/teste_engenheiro/main/data/"
LOCAL_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# Fila para armazenar arquivos baixados
download_queue = queue.Queue()

# Variáveis globais para controle de progresso
downloaded_count = 0
total_to_download = 0
processed_count = 0
errors_count = 0
total_to_process = 0

# Lock para atualização dos contadores
counter_lock = threading.Lock()

def get_db_connection():
    """Cria uma conexão com o banco de dados SQLite"""
    conn = sqlite3.connect(
        DB_CONFIG_SQLITE['database'],
        check_same_thread=False  # Permitir acesso de múltiplas threads
    )
    # Ativar suporte a chaves estrangeiras
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_database_schema(conn):
    """Cria as tabelas com o schema como prefixo"""
    cursor = conn.cursor()
    # Tabela de pacientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            gender TEXT
        )
    """)
    
    # Tabela de condições médicas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            condition_text TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
    """)
    
    # Tabela de medicamentos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            medication_text TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
        )
    """)
    
    # Tabela de controle de arquivos processados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_name TEXT PRIMARY KEY
        )
    """)
    
    # Criar índices para otimizar consultas
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conditions_text ON conditions(condition_text)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medications_text ON medications(medication_text)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_patients_gender ON patients(gender)")
    
    conn.commit()
    cursor.close()

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
    cursor.execute("INSERT INTO processed_files (file_name) VALUES (?)", (file_name,))
    conn.commit()
    cursor.close()

def get_remote_files():
    """Obtém todos os arquivos JSON do repositório com paginação"""
    try:
        page = 1
        all_files = []
        
        while True:
            response = requests.get(
                f"{DATA_URL}&page={page}&per_page=100",
                headers={"Accept": "application/vnd.github+json"}
            )
            response.raise_for_status()
            
            files = response.json()
            if not files:
                break
                
            all_files.extend([
                f for f in files 
                if f['type'] == 'file' and f['name'].endswith('.json')
            ])
            
            if 'next' not in response.links:
                break
                
            page += 1

        return {f['name']: f for f in all_files}
        
    except Exception as e:
        print(f"Falha na conexão com o GitHub: {str(e)}")
        return {}

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
    conn = get_db_connection()
    try:
        remote_files = get_remote_files()
        
        if not remote_files:
            print("Nenhum arquivo encontrado no repositório!")
            return

        # Filtra apenas arquivos que ainda não foram processados
        files_to_download = {}
        for name, meta in remote_files.items():
            if is_file_processed(conn, name):
                print(f"Arquivo {name} já foi processado, pulando...")
                continue
            files_to_download[name] = meta
        
        total_to_download = len(files_to_download)
        total_to_process = total_to_download  # Para o processamento posterior

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
        
        # Indica o fim da fila
        download_queue.put(None)
        elapsed = time.time() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        print(f"\nDownload concluído: {downloaded_count} novos arquivos")
        print(f"Tempo total de download: {minutes} minutos e {seconds} segundos")
    finally:
        conn.close()

def clean_text(text):
    """Substitui barras e colchetes nos textos."""
    return text.replace("/", "-").replace("\\", "-").replace("[", "(").replace("]", ")")

def process_files():
    """Processa os arquivos da fila"""
    global processed_count, errors_count
    start_time = time.time()
    conn = get_db_connection()
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
                            condition_text = resource.get('code', {}).get('text', '')
                            condition_text = clean_text(condition_text)  # Aplicar limpeza
                            if condition_text:
                                cursor.execute(
                                    "INSERT INTO conditions (patient_id, condition_text) VALUES (?, ?)",
                                    (patient_id, condition_text)
                                )

                        elif resource_type == 'MedicationRequest':
                            medication_text = resource.get('medicationCodeableConcept', {}).get('text', '')
                            medication_text = clean_text(medication_text)  # Aplicar limpeza
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
                        if processed_count % 100 == 0:
                            print(f"\nLote {processed_count // 100}: {processed_count} arquivos processados | Erros: {errors_count}")
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
        minutes, seconds = divmod(int(elapsed), 60)
        print("\nProcessamento concluído:")
        print(f"- Arquivos processados: {processed_count}")
        print(f"- Erros: {errors_count}")
        print(f"- Tempo total: {minutes} minutos e {seconds} segundos")

def main():
    """Função principal que coordena o download e processamento"""
    # Garantir que o diretório de dados existe
    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
    
    # Criar schema e tabelas
    conn = get_db_connection()
    create_database_schema(conn)
    conn.close()

    # Inicia as threads
    download_thread = threading.Thread(target=download_files)
    process_thread = threading.Thread(target=process_files)
    
    download_thread.start()
    process_thread.start()
    
    # Aguarda as threads terminarem
    download_thread.join()
    process_thread.join()

    print("Processamento concluído.")

if __name__ == '__main__':
    main()
