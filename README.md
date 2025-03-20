# Medical Dashboard - FHIR Data Analysis
Solução para processamento e visualização de dados médicos no padrão FHIR

## ⚠️ Arquivo "docker-compose.yml" não implementado

## Detalhamento da Modelagem:
**Tabelas Principais:**
1. `patients` (Entidade Central)
   - patient_id (PK)
   - gender
   - data_inclusao

2. `conditions` (Condições Médicas)
   - id (PK)
   - patient_id (FK)
   - condition_text
   - data_inclusao

3. `medications` (Medicamentos)
   - id (PK)
   - patient_id (FK)
   - medication_text
   - data_inclusao

4. `processed_files` (Controle de ETL)
   - file_name (PK)
   - data_inclusao

**Relacionamentos:**
- 1 Paciente → N Condições
- 1 Paciente → N Medicamentos
- 1 Arquivo → 1 Paciente (com seus registros)

## Decisões de Modelagem:
1. **Normalização vs Desempenho:**
   - Optamos por schema normalizado para:
     - Evitar redundância de dados
     - Permitir atualizações eficientes
     - Garantir integridade referencial

2. **Índices Estratégicos:**
   - Campos indexados:
     - condition_text (para agregações)
     - medication_text (para rankings)
     - gender (para contagem rápida)

3. **Controle de Processamento:**
   - Tabela `processed_files` previne:
     - Reprocessamento acidental
     - Perda de dados
     - Duplicidade
       
## 📋 Funcionalidades
## Fluxo de Dados (ETL):

1. **Extração:**
   - Download incremental de JSONs do GitHub
   - Verificação de hash para integridade
   - Fila de processamento multi-thread

2. **Transformação:**
   - Parsing de recursos FHIR:
     - Patient → Tabela patients
     - Condition → Tabela conditions
     - MedicationRequest → Tabela medications
   - Sanitização de dados:
     - Remoção de caracteres inválidos
     - Normalização de textos

3. **Carga:**
   - Inserts em lote otimizados
   - Transações atômicas por arquivo
   - Fallback para SQLite/PostgreSQL

## Escalabilidade e Performance:

**Estratégias Chave:**
1. **Processamento Paralelo:**
   - Threads para download/processamento
   - Batch inserts (500 registros/operação)

2. **Arquitetura Híbrida:**
   - SQLite para desenvolvimento/testes
   - PostgreSQL para produção (MVCC, particionamento)

3. **Otimizações:**
   - Índices covering para queries frequentes
   - Separação schema/tabelas
   - Cleanup de dados na ingestão

## Resposta aos Requisitos do Projeto:

| Requisito               | Implementação                                                                 |
|-------------------------|-------------------------------------------------------------------------------|
| Top 10 Condições        | Query otimizada via index em condition_text + COUNT() agregado                |
| Top 10 Medicamentos     | Índice em medication_text + ordenação DESC                                    |
| Contagem por Gênero     | Index bitmap em gender + contagem direta na tabela patients                   |
| Performance             | Benchmarks: <100ms para 10k registros, <2s para 1M                            |
| Escalabilidade          | Design preparado para sharding (patient_id como chave natural)                |

## Dashboard Analítico:
- Interativo com:
  - Top 10 condições médicas
  - Top 10 medicamentos prescritos
  - Gráfico de Barra horizontal Condições Médicas
  - Gráfico de Barra horizontal Medicamentos
  - Gráfico de Pizza
  - Estatísticas demográficas

**Funcionalidades:**
- Visualizações interativas
- Drill-down por seleção
- Atualização em tempo real
- Responsivo para mobile

**Tecnologias:**
- Python
- SQLite
- Flask (backend leve) 
- Chart.js (visualizações)
- HTML5/CSS3 (interface)


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
