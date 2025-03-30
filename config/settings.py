import os

# Configurações do banco de dados
DB_CONFIG_POSTGRES = {
    'dbname': 'medical',
    'user': 'medic',
    'password': 'postgres',
    'host': 'localhost',
    'port': '5432',
    'schema': 'etl'
}

DB_CONFIG_SQLITE = {
    'database': 'medicaldatabase.db',  # Arquivo do SQLite
    'schema': 'elt'           # Schema padrão do SQLite
}

DB_CONFIG_POSTGRES_DOCKER = {
    'dbname': os.getenv('POSTGRES_DB', 'medical'),
    'user': os.getenv('POSTGRES_USER', 'medic'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
    'host': os.getenv('POSTGRES_HOST', 'localhost'),  # Usar nome do serviço
    'port': os.getenv('POSTGRES_PORT', '5432'),      # Porta padrão do PostgreSQL
    'schema': os.getenv('POSTGRES_SCHEMA', 'etl')
}

DB_CONFIG_SQLITE_DOCKER = {
    'database': os.path.join(os.getenv('DATA_DIR', 'data'), 'medicaldatabase.db'),
    'schema': os.getenv('SQLITE_SCHEMA', 'etl')
}
