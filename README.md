# Medical Dashboard - FHIR Data Analysis
Solução para processamento e visualização de dados médicos no padrão FHIR

## ⚠️ Arquivo "docker-compose.yml" não implementado

## 📋 Funcionalidades
- Download automático de dados do GitHub
- ETL otimizado com SQLite
 - Processa 1.180 arquivos FHIR
 - Cria estrutura relacional otimizada para consultas

- Dashboard interativo com:
  - Top 10 condições médicas
  - Top 10 medicamentos prescritos
  - Gráfico de Barra horizontal Condições Médicas
  - Gráfico de Barra horizontal Medicamentos
  - Gráfico de Pizza
  - Estatísticas demográficas

## 🚀 Execução
```bash
# Clonar repositório, o projeto med-eng.
git clone https://github.com/wesdataharmony/med-eng.git

##Ir para a pasta "med-eng" raiz do projeto EXE:
  cd C:\Users\Desktop\med-eng
Exe: C:\Users\Desktop\med-eng> 

## Criar ambiente Virtual
python -m venv venv
.\venv\Scripts\Activate
Exe:(venv) PS C:\Users\Desktop\med-eng>

## Instalar dependências
pip install -r requirements.txt

# CASO NECESSITE excutar: pip freeze > requirements.txt para criar todos as dependencias do projeto.

## Executar pipeline de dados
python -m etl.loader

## Executar pipeline de dados com a função de migração para o Postgres.
python -m etl.loader_pipeline.py

# Iniciar aplicação web
python -m app.routes

# Limpe o ambiente
### Remove os arquivos - Remove a pasta "data".
Remove-Item -Path .\data\ -Recurse -Force

### Remove o banco "medicaldatabase".
rm -Force .\medicaldatabase.db
