import os

# Configurações do banco de dados
DB_CONFIG_POSTGRES = {
    'dbname': 'data',
    'user': 'postgres',
    'password': '00@000',
    'host': '00.000.00.00',
    'port': '6431',
    'schema': 'test_medical'
}

DB_CONFIG_SQLITE = {
    'database': 'medicaldatabase.db',  # Arquivo do SQLite
    'schema': 'test_medical'           # Schema padrão do SQLite
}

DB_CONFIG_POSTGRES_DOCKER = {
    'dbname': os.getenv('POSTGRES_DB', 'data'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '00@000'),
    'host': os.getenv('POSTGRES_HOST', 'postgres'),  # Usar nome do serviço
    'port': os.getenv('POSTGRES_PORT', '5432'),      # Porta padrão do PostgreSQL
    'schema': os.getenv('POSTGRES_SCHEMA', 'test_medical')
}

DB_CONFIG_SQLITE_DOCKER = {
    'database': os.path.join(os.getenv('DATA_DIR', 'data'), 'medicaldatabase.db'),
    'schema': os.getenv('SQLITE_SCHEMA', 'test_medical')
}
