# Medical Dashboard - FHIR Data Analysis
Solução para processamento e visualização de dados médicos no padrão FHIR

## 📋 Funcionalidades
- Download automático de dados do GitHub
- ETL otimizado com SQLite
 - Processa 1.180 arquivos FHIR
 - Cria estrutura relacional otimizada para consultas

- Dashboard interativo com:
  - Top 10 condições médicas
  - Top 10 medicamentos prescritos
  - Estatísticas demográficas

## 🚀 Execução
```bash
# Clonar repositório, o projeto med-eng.
git clone https://github.com/wesdataharmony/med-eng.git

# Ir para a pasta "med-eng" raiz do projeto EXE:

  cd C:\Users\Desktop\med-eng
Exe: C:\Users\Desktop\med-eng> 

# Criar ambiente Virtual

python -m venv venv
.\venv\Scripts\Activate
Exe:(venv) PS C:\Users\Desktop\med-eng>

# Instalar dependências
pip install -r requirements.txt

# CASO NECESSITE excutar: pip freeze > requirements.txt para criar todos as dependencias do projeto.

# Executar pipeline de dados
python -m etl.loader

# Iniciar aplicação web
python -m app.routes

# Limpe o ambiente
## Get-ChildItem -Path .\data\ -File: Lista todos os arquivos dentro da pasta data (mas não remove subpastas).
## | Remove-Item -Force: Remove os arquivos listados dentro da pasta "data".

### Remove os arquivos
Get-ChildItem -Path .\data\ -File | Remove-Item -Force

#Esse comando apaga o arquivo medicaldatabase.db do seu projeto, sem remover nenhuma pasta.
rm -Force .\medicaldatabase.db
