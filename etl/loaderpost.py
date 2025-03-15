import os
import json
import requests
import hashlib
import time
from urllib.parse import urljoin
import psycopg2
import threading
import queue
from config.settings import DB_CONFIG


# Configurações de URL e diretórios
DATA_URL = "https://api.github.com/repos/wandersondsm/teste_engenheiro/contents/data?ref=main"
RAW_BASE_URL = "https://raw.githubusercontent.com/wandersondsm/teste_engenheiro/main/data/"
LOCAL_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# Fila para armazenar arquivos baixados
download_queue = queue.Queue()

def get_db_connection():
    """Cria uma conexão com o banco de dados PostgreSQL"""
    conn = psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )
    return conn

def create_schema(conn):
    """Cria o schema 'etl' se não existir"""
    cursor = conn.cursor()
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {DB_CONFIG['schema']}")
    conn.commit()
    cursor.close()

def create_database_schema(conn):
    """Cria as tabelas no schema 'etl'"""
    cursor = conn.cursor()
    
    # Definir o schema para as operações
    cursor.execute(f"SET search_path TO {DB_CONFIG['schema']}")
    
    # Tabela de pacientes
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG['schema']}.patients (
            patient_id TEXT PRIMARY KEY,
            gender TEXT
        )
    """)
    
    # Tabela de condições médicas
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG['schema']}.conditions (
            id SERIAL PRIMARY KEY,
            patient_id TEXT,
            condition_text TEXT,
            FOREIGN KEY(patient_id) REFERENCES {DB_CONFIG['schema']}.patients(patient_id)
        )
    """)
    
    # Tabela de medicamentos
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG['schema']}.medications (
            id SERIAL PRIMARY KEY,
            patient_id TEXT,
            medication_text TEXT,
            FOREIGN KEY(patient_id) REFERENCES {DB_CONFIG['schema']}.patients(patient_id)
        )
    """)
    
    # Tabela de controle de arquivos processados
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG['schema']}.processed_files (
            file_name TEXT PRIMARY KEY
        )
    """)
    
    # Criar índices para otimizar consultas
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_conditions_text ON {DB_CONFIG['schema']}.conditions(condition_text)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_medications_text ON {DB_CONFIG['schema']}.medications(medication_text)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_patients_gender ON {DB_CONFIG['schema']}.patients(gender)")
    
    conn.commit()
    cursor.close()

def is_file_processed(conn, file_name):
    """Verifica se o arquivo já foi processado"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT 1 FROM {DB_CONFIG['schema']}.processed_files WHERE file_name = %s", (file_name,))
    result = cursor.fetchone()
    cursor.close()
    return result is not None

def mark_file_as_processed(conn, file_name):
    """Marca o arquivo como processado"""
    cursor = conn.cursor()
    cursor.execute(f"INSERT INTO {DB_CONFIG['schema']}.processed_files (file_name) VALUES (%s)", (file_name,))
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

def download_files(conn):
    """Baixa os arquivos JSON do repositório e os adiciona à fila"""
    remote_files = get_remote_files()
    
    if not remote_files:
        print("Nenhum arquivo encontrado no repositório!")
        return

    print(f"\nTotal de arquivos no repositório: {len(remote_files)}")
    
    for name, meta in remote_files.items():
        if is_file_processed(conn, name):
            print(f"Arquivo {name} já foi processado, pulando...")
            continue
        
        file_url = urljoin(RAW_BASE_URL, name)
        file_path = os.path.join(LOCAL_DATA_DIR, name)
        
        try:
            print(f"Baixando: {name}")
            response = requests.get(file_url)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
                
            download_queue.put(file_path)  # Adiciona o arquivo à fila para processamento
        except Exception as e:
            print(f"Erro em {name}: {str(e)}")
            if os.path.exists(file_path):
                os.remove(file_path)
    
    download_queue.put(None)  # Sinaliza o fim do download

def process_files(conn):
    """Processa os arquivos da fila"""
    while True:
        file_path = download_queue.get()  # Pega o próximo arquivo da fila
        if file_path is None:  # Fim do processamento
            break
        
        file_name = os.path.basename(file_path)
        if is_file_processed(conn, file_name):
            print(f"Arquivo {file_name} já foi processado, pulando...")
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
                    continue

                patient_id = patient.get('id')
                gender = patient.get('gender', 'unknown')

                # Inserir paciente
                cursor = conn.cursor()
                cursor.execute(
                    f"INSERT INTO {DB_CONFIG['schema']}.patients (patient_id, gender) VALUES (%s, %s) ON CONFLICT (patient_id) DO NOTHING",
                    (patient_id, gender))
                
                # Processar entradas
                for entry in entries:
                    resource = entry.get('resource', {})
                    resource_type = resource.get('resourceType')

                    if resource_type == 'Condition':
                        condition_text = resource.get('code', {}).get('text', '')
                        if condition_text:
                            cursor.execute(
                                f"INSERT INTO {DB_CONFIG['schema']}.conditions (patient_id, condition_text) VALUES (%s, %s)",
                                (patient_id, condition_text))
                    
                    elif resource_type == 'MedicationRequest':
                        medication_text = resource.get('medicationCodeableConcept', {}).get('text', '')
                        if medication_text:
                            cursor.execute(
                                f"INSERT INTO {DB_CONFIG['schema']}.medications (patient_id, medication_text) VALUES (%s, %s)",
                                (patient_id, medication_text))
                
                conn.commit()
                mark_file_as_processed(conn, file_name)
                print(f"Arquivo {file_name} processado com sucesso.")
        except Exception as e:
            print(f"Erro no arquivo {file_name}: {str(e)}")
        finally:
            download_queue.task_done()

def main():
    """Função principal que coordena o download e processamento"""
    conn = get_db_connection()
    try:
        create_schema(conn)
        create_database_schema(conn)

        # Inicia as threads
        download_thread = threading.Thread(target=download_files, args=(conn,))
        process_thread = threading.Thread(target=process_files, args=(conn,))
        
        download_thread.start()
        process_thread.start()
        
        # Aguarda as threads terminarem
        download_thread.join()
        process_thread.join()
        
        print("Processamento concluído.")
    finally:
        conn.close()

if __name__ == '__main__':
    main()