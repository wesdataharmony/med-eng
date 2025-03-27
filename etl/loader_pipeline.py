import os
import sys 
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
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
from app import routes
import traceback

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
        port=DB_CONFIG_POSTGRES['port']
    )
    return conn

def create_postgres_schema(conn):
    """Cria o schema e as tabelas no PostgreSQL com a coluna data_inclusao"""
    cursor = conn.cursor()

    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}")
    conn.commit()

    cursor.execute(f"SET search_path TO {DB_CONFIG_POSTGRES['schema']}")

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.patients (
            patient_id TEXT PRIMARY KEY,
            gender TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.conditions (
            id SERIAL PRIMARY KEY,
            patient_id TEXT,
            condition_text TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES {DB_CONFIG_POSTGRES['schema']}.patients(patient_id)
        )
    """)
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.medications (
            id SERIAL PRIMARY KEY,
            patient_id TEXT,
            medication_text TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(patient_id) REFERENCES {DB_CONFIG_POSTGRES['schema']}.patients(patient_id)
        )
    """)
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.processed_files (
            file_name TEXT PRIMARY KEY,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.aggregated_conditions (
            condition_text TEXT PRIMARY KEY,
            count INTEGER,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.aggregated_medications (
            medication_text TEXT PRIMARY KEY,
            count INTEGER,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {DB_CONFIG_POSTGRES['schema']}.gender_stats (
            gender TEXT PRIMARY KEY,
            count INTEGER,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_conditions_text ON {DB_CONFIG_POSTGRES['schema']}.conditions(condition_text)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_medications_text ON {DB_CONFIG_POSTGRES['schema']}.medications(medication_text)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_patients_gender ON {DB_CONFIG_POSTGRES['schema']}.patients(gender)")
    
    conn.commit()
    cursor.close()

def check_migration_status():
    """Verifica de forma segura se a migração foi completada"""
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        
        # Verificar existência do schema
        cursor.execute("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = %s)", 
                      (DB_CONFIG_POSTGRES['schema'],))
        if not cursor.fetchone()[0]:
            return False
            
        # Verificar existência das tabelas
        required_tables = {'patients', 'conditions', 'medications', 'processed_files'}
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s
        """, (DB_CONFIG_POSTGRES['schema'],))
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        if not required_tables.issubset(existing_tables):
            return False
            
        # Verificar dados
        for table in required_tables:
            cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {DB_CONFIG_POSTGRES['schema']}.{table} LIMIT 1)")
            if not cursor.fetchone()[0]:
                return False
                
        return True
        
    except psycopg2.Error as e:
        print(f"\nERRO POSTGRESQL: {str(e)}")
        return False
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

def validate_data_for_postgres(conn):
    """Valida os dados do SQLite para migração para o PostgreSQL"""
    print("\nValidando dados para migração...")
    cursor = conn.cursor()
    
    cursor.execute("SELECT patient_id, gender, data_inclusao FROM patients")
    invalid_patients = []
    
    for row in cursor.fetchall():
        patient_id, gender, data_inclusao = row
        if patient_id is None or patient_id == '':
            invalid_patients.append((patient_id, "Patient ID não pode ser nulo ou vazio"))
    
    if invalid_patients:
        print(f"Encontrados {len(invalid_patients)} pacientes com dados inválidos:")
        for patient_id, error in invalid_patients[:5]:
            print(f"  - Patient ID: {patient_id}, Erro: {error}")
        if len(invalid_patients) > 5:
            print(f"  ... e mais {len(invalid_patients) - 5} registros com problemas.")
        return False
    
    cursor.execute("""
        SELECT c.patient_id
        FROM conditions c
        LEFT JOIN patients p ON c.patient_id = p.patient_id
        WHERE p.patient_id IS NULL
        GROUP BY c.patient_id
    """)
    
    orphan_conditions = cursor.fetchall()
    if orphan_conditions:
        print(f"Encontradas {len(orphan_conditions)} condições sem paciente correspondente:")
        for row in orphan_conditions[:5]:
            print(f"  - Patient ID: {row[0]}")
        if len(orphan_conditions) > 5:
            print(f"  ... e mais {len(orphan_conditions) - 5} registros com problemas.")
        return False
    
    cursor.execute("""
        SELECT m.patient_id
        FROM medications m
        LEFT JOIN patients p ON m.patient_id = p.patient_id
        WHERE p.patient_id IS NULL
        GROUP BY m.patient_id
    """)
    
    orphan_medications = cursor.fetchall()
    if orphan_medications:
        print(f"Encontrados {len(orphan_medications)} medicamentos sem paciente correspondente:")
        for row in orphan_medications[:5]:
            print(f"  - Patient ID: {row[0]}")
        if len(orphan_medications) > 5:
            print(f"  ... e mais {len(orphan_medications) - 5} registros com problemas.")
        return False
    
    print("Todos os dados são válidos para migração.")
    return True

def estimate_migration_time(total_records):
    """Estima o tempo de migração com base em uma taxa realista"""
    time_per_record = 0.12  # 0.12 segundos por registro
    return total_records * time_per_record

def format_time(seconds):
    """Formata segundos em horas, minutos e segundos"""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 and hours == 0:
        parts.append(f"{seconds}s")
    return " ".join(parts) or "0s"

def print_progress(current, total, prefix=""):
    """Exibe uma barra de progresso simples no console"""
    bar_length = 40
    fraction = current / total if total else 0
    arrow = int(fraction * bar_length) * "="
    spaces = (bar_length - len(arrow)) * " "
    percent = int(fraction * 100)
    print(f"\r{prefix} [{arrow}{spaces}] {percent}% ({current}/{total})", end="", flush=True)

cancel_flag = False

def cancel_monitor():
    """Monitora entrada do usuário para cancelamento"""
    global cancel_flag
    input()
    cancel_flag = True

def check_cancel():
    """Verifica se houve solicitação de cancelamento"""
    global cancel_flag
    if cancel_flag:
        print("\nOperação cancelada pelo usuário!")
        return True
    return False

def migrate_to_postgres():
    """Migra os dados do SQLite para o PostgreSQL com controle de cancelamento"""
    if check_migration_status():
        print("\nOs dados processados e inseridos já foram migrados.")
        return
    
    global cancel_flag
    cancel_flag = False
    sqlite_conn = None
    postgres_conn = None
    sqlite_cursor = None
    postgres_cursor = None
    
    start_time = time.time()
  
    try:
        sqlite_conn = get_sqlite_connection()

        if not validate_data_for_postgres(sqlite_conn):
            print("\nMigração cancelada devido a problemas nos dados.")
            sqlite_conn.close()
            return
        
        tables = {
            'patients': 0,
            'conditions': 0,
            'medications': 0,
            'processed_files': 0
        }
        
        for table in tables:
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            tables[table] = sqlite_cursor.fetchone()[0]
            sqlite_cursor.close()
        
        total_records = sum(tables.values())
        if total_records == 0:
            print("Não há dados para migrar.")
            sqlite_conn.close()
            return

        # Confirmação do usuário
        print(f"\n⚠️ ATENÇÃO: Esta operação pode levar aproximadamente {format_time(estimate_migration_time(total_records))}")
        print(f"• Total de registros: {total_records:,}")
        print(f"• Pacientes: {tables['patients']:,}")
        print(f"• Condições: {tables['conditions']:,}")
        print(f"• Medicamentos: {tables['medications']:,}")

        confirm = input("\nDeseja prosseguir com a migração? (S/N) ").strip().upper()
        if confirm != 'S':
            print("\nMigração cancelada pelo usuário.")
            return
        
        postgres_conn = get_postgres_connection()
        create_postgres_schema(postgres_conn)
        sqlite_cursor = sqlite_conn.cursor()
        postgres_cursor = postgres_conn.cursor()

        cancel_thread = threading.Thread(target=cancel_monitor)
        cancel_thread.daemon = True
        cancel_thread.start()
        
        current_record = 0
        batch_size = 500

        print("\nMigrando pacientes...")
        sqlite_cursor.execute("SELECT patient_id, gender, data_inclusao FROM patients")
        while True:
            batch = sqlite_cursor.fetchmany(batch_size)
            if not batch or check_cancel():
                break

            for row in batch:
                try:
                    postgres_cursor.execute(
                        f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.patients VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        row
                    )
                    current_record += 1
                except Exception as e:
                    print(f"\nErro no paciente {row[0]}: {str(e)}")
            
            postgres_conn.commit()
            print_progress(current_record, tables['patients'], prefix="Pacientes")

        if check_cancel():
            return

        print("\n\nMigrando condições...")
        sqlite_cursor.execute("SELECT patient_id, condition_text, data_inclusao FROM conditions")
        current_record = 0
        while True:
            batch = sqlite_cursor.fetchmany(batch_size)
            if not batch or check_cancel():
                break

            for row in batch:
                try:
                    postgres_cursor.execute(
                        f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.conditions (patient_id, condition_text, data_inclusao) VALUES (%s, %s, %s)",
                        row
                    )
                    current_record += 1
                except Exception as e:
                    print(f"\nErro na condição do paciente {row[0]}: {str(e)}")
            
            postgres_conn.commit()
            print_progress(current_record, tables['conditions'], prefix="Condições  ")

        if check_cancel():
            return

        print("\n\nMigrando medicamentos...")
        sqlite_cursor.execute("SELECT patient_id, medication_text, data_inclusao FROM medications")
        current_record = 0
        while True:
            batch = sqlite_cursor.fetchmany(batch_size)
            if not batch or check_cancel():
                break

            for row in batch:
                try:
                    postgres_cursor.execute(
                        f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.medications (patient_id, medication_text, data_inclusao) VALUES (%s, %s, %s)",
                        row
                    )
                    current_record += 1
                except Exception as e:
                    print(f"\nErro no medicamento do paciente {row[0]}: {str(e)}")
            
            postgres_conn.commit()
            print_progress(current_record, tables['medications'], prefix="Medicamentos")

        if check_cancel():
            return

        print("\n\nMigrando arquivos processados...")
        sqlite_cursor.execute("SELECT file_name, data_inclusao FROM processed_files")
        current_record = 0
        while True:
            batch = sqlite_cursor.fetchmany(batch_size)
            if not batch or check_cancel():
                break

            for row in batch:
                try:
                    postgres_cursor.execute(
                        f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.processed_files VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        row
                    )
                    current_record += 1
                except Exception as e:
                    print(f"\nErro no arquivo {row[0]}: {str(e)}")
            
            postgres_conn.commit()
            print_progress(current_record, tables['processed_files'], prefix="Arquivos    ")

        elapsed = time.time() - start_time
        print(f"\n\nMigração concluída com sucesso!")
        print(f"Tempo total: {format_time(elapsed)}")
        print(f"Registros migrados: {sum(tables.values())}")

    except Exception as e:
        if 'postgres_conn' in locals():
            postgres_conn.rollback()
        print(f"\n❌ ERRO NA MIGRAÇÃO: {str(e)}")
        traceback.print_exc()
        if postgres_conn:
            postgres_conn.rollback()
    finally:
        # Ordem correta de fechamento
        try:
            if 'postgres_cursor' in locals(): 
                postgres_cursor.close()
        except Exception as e:
            print(f"Erro ao fechar cursor PostgreSQL: {str(e)}")

        try:
            if postgres_conn is not None: 
                postgres_conn.close()
        except Exception as e:
            print(f"Erro ao fechar conexão PostgreSQL: {str(e)}")

        try:
            if 'sqlite_cursor' in locals(): 
                sqlite_cursor.close()
        except Exception as e:
            print(f"Erro ao fechar cursor SQLite: {str(e)}")    

        try:
            if sqlite_conn is not None: 
                sqlite_conn.close()
        except Exception as e:
            print(f"Erro ao fechar conexão SQLite: {str(e)}")    
        cancel_flag = True

def migrate_aggregated_data_to_postgres():
    """Migra os dados agregados do SQLite para o PostgreSQL"""
    print("Iniciando migração de dados agregados para PostgreSQL...")
    try:
        postgres_conn = get_postgres_connection()
        create_postgres_schema(postgres_conn)
    except Exception as e:
        print(f"Erro ao conectar ao PostgreSQL: {str(e)}")
        return
        
    start_time = time.time()
    
    sqlite_conn = get_sqlite_connection()
    sqlite_cursor = sqlite_conn.cursor()
    postgres_cursor = postgres_conn.cursor()
    
    try:
        print("Migrando aggregated_conditions...")
        sqlite_cursor.execute("""
            SELECT condition_text, COUNT(*) as count 
            FROM conditions 
            GROUP BY condition_text 
            ORDER BY count DESC 
            LIMIT 10
        """)
        for row in sqlite_cursor.fetchall():
            postgres_cursor.execute(
                f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.aggregated_conditions VALUES (%s, %s) ON CONFLICT (condition_text) DO UPDATE SET count = EXCLUDED.count",
                row
            )
        
        print("\nMigrando aggregated_medications...")
        sqlite_cursor.execute("""
            SELECT medication_text, COUNT(*) as count 
            FROM medications 
            GROUP BY medication_text 
            ORDER BY count DESC 
            LIMIT 10
        """)
        for row in sqlite_cursor.fetchall():
            postgres_cursor.execute(
                f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.aggregated_medications VALUES (%s, %s) ON CONFLICT (medication_text) DO UPDATE SET count = EXCLUDED.count",
                row
            )
        
        print("\nMigrando gender_stats...")
        sqlite_cursor.execute("""
            SELECT gender, COUNT(*) as count 
            FROM patients 
            GROUP BY gender
        """)
        for row in sqlite_cursor.fetchall():
            postgres_cursor.execute(
                f"INSERT INTO {DB_CONFIG_POSTGRES['schema']}.gender_stats VALUES (%s, %s) ON CONFLICT (gender) DO UPDATE SET count = EXCLUDED.count",
                row
            )
        
        postgres_conn.commit()
        elapsed = time.time() - start_time
        print(f"\nMigração de dados agregados concluída em {format_time(elapsed)}")

    except Exception as e:
        postgres_conn.rollback()
        print(f"\nERRO: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_cursor.close()
        postgres_cursor.close()
        sqlite_conn.close()
        postgres_conn.close()

def check_postgres_connection():
    """Verifica se a conexão com PostgreSQL está ativa"""
    try:
        conn = get_postgres_connection()
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print(f"\nERRO: Não foi possível conectar ao PostgreSQL - {str(e)}")
        return False

def handle_migration_choice(choice):
    """Lida com a escolha de migração de forma segura"""
    try:
        if choice == 'M':
            if check_migration_status():
                print("\n✓ Migração já foi realizada e os dados estão íntegros")
                return
                
            print("\nIniciando migração completa...")
            migrate_to_postgres()
            
        elif choice == 'A':
            #print("\nIniciando migração de dados agregados...")
            migrate_aggregated_data_to_postgres()
            
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: {str(e)}")
        import traceback
        traceback.print_exc()

def handle_visualization_choice(choice):
    """Lida com a escolha de visualização do dashboard"""
    if choice == 'V':
        print("\nIniciando dashboard...")
        try:
            subprocess.Popen([sys.executable, "-m", "app.routes"])
            webbrowser.open("http://localhost:5000/")
        except Exception as e:
            print(f"Erro ao iniciar dashboard: {str(e)}")
    print("\nO dashboard foi aberto em seu navegador. Você pode continuar usando o terminal.")

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

def main():
    global LOCAL_DATA_DIR
    validate_environment()

    while True: 
                # Verificar conexão com PostgreSQL
        if not check_postgres_connection():
            print("Verifique as configurações do PostgreSQL e tente novamente.")
            return
        conn = get_sqlite_connection()
        create_sqlite_schema(conn)
        
        try:
            remote_files = get_remote_files()
        except Exception as e:
            print(f"Erro ao obter arquivos remotos: {str(e)}")
            conn.close()
            continue

        if remote_files is None:
            print("Não foi possível verificar arquivos remotos. Verifique sua conexão.")
            conn.close()
            continue
            
        files_to_process = [name for name in remote_files if not is_file_processed(conn, name)]
        
        if not files_to_process:
            conn.close()
            while True:  # Submenu interativo
                print("\nEscolha uma opção:")
                print("  V - Visualizar dados no dashboard")
                print("  M - Migração normal (todos os registros)")
                print("  A - Migração de dados agregados (resumos)")
                print("  N - Sair do programa")
                choice = input("Digite sua escolha (V/M/A/N): ").strip().upper()

                if choice == 'V':
                    handle_visualization_choice('V')
                elif choice == 'M':
                    handle_migration_choice('M')
                elif choice == 'A':
                    handle_migration_choice('A')
                elif choice == 'N':
                    print("\nEncerrando programa...")
                    return
                else:
                    print("Opção inválida. Tente novamente.")
                
                input("\nPressione Enter para continuar...")
                #os.system('cls' if os.name == 'nt' else 'clear')  # Limpa a tela
                
        else:
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

            while True:
                visualization_choice = input("\nDeseja visualizar os dados agora? (V/N) ").strip().upper()
                if visualization_choice in ('V', 'N'):
                    break
                print("Opção inválida. Digite V para visualizar ou N para sair.")
            
            handle_visualization_choice(visualization_choice)
            input("\nPressione Enter para voltar ao menu principal...")
            os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == '__main__':
    main()
