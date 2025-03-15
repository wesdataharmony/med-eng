# Medical Dashboard - FHIR Data Analysis
Solução para processamento e visualização de dados médicos no padrão FHIR

## 📋 Funcionalidades
- Download automático de dados do GitHub
- ETL otimizado com SQLite
- Dashboard interativo com:
  - Top 10 condições médicas
  - Top 10 medicamentos prescritos
  - Estatísticas demográficas

## 🚀 Execução
```bash
# Clonar repositório crie uma pasta com o nome "med-dashoard" e dentro da mesma CLONE o projeto.
git clone https://github.com/wesdataharmony/med-dashboard.git

# Ir para na pasta "med-dashoard" raiz do projeto EXE:
cd C:\Users\Desktop\med-dashoard

# Criar ambiente Virtual
python -m venv venv
.\venv\Scripts\Activate

# pip freeze > requirements.txt para criar todos as dependencias do projeto

# Instalar dependências
pip install -r requirements.txt

# Executar pipeline de dados
python -m etl.loader

# Iniciar aplicação web
python -m app.routes

# Limpe o ambiente
rm -Force -Recurse .\data\
rm -Force .\medicaldatabase.db
