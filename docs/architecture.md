## Arquitetura do Sistema

### Componentes Principais

1. **ETL (Extract, Transform, Load)**
   - Python script para carregar dados JSON para SQLite
   - Processa 1.180 arquivos FHIR
   - Cria estrutura relacional otimizada para consultas

2. **Banco de Dados**
   - SQLite com índices otimizados:
     - Índices nas colunas de texto para agregações rápidas
     - Chaves primárias e estrangeiras para integridade

3. **API Web**
   - Flask para servir requisições HTTP
   - Três endpoints principais:
     - /conditions - Top 10 condições
     - /medications - Top 10 medicamentos
     - /patients/male - Contagem por gênero

4. **Visualização**
   - Templates HTML simples
   - Estilização básica com CSS
   - Compatível com ferramentas BI via SQL

### Diagrama de Fluxo

[GITHUB URL] → [Download JSON Files] → [ETL Script] → [SQLite] ↔ [Flask API] ↔ [Web Browser]

[ Fonte de Dados FHIR (GitHub) ]
Download e ETL: Os dados são baixados e processados pelo loader.py, que os organiza e insere no banco SQLite.
          |
          v
[ Download e ETL - loader.py ]
Armazenamento: O SQLite armazena os dados em tabelas otimizadas.
          |
          v
[ Banco SQLite - meddatabase.db ]
          |
          v
[ Backend Flask - routes.py ]
Backend: O Flask consulta o banco e gera gráficos dinâmicos usando Matplotlib.
          |
          v
[ Dashboard Web - dashboard.html ]
Frontend: O dashboard exibe os resultados em listas e gráficos interativos.

### Escalabilidade
- Processamento distribuído.