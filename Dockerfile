FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar todo o projeto
COPY . .

# Variáveis de ambiente
ENV FLASK_APP=app/routes.py
ENV FLASK_ENV=production
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000

# Porta exposta
#EXPOSE 5000

# Comando para executar a aplicação
CMD ["tail", "-f", "/dev/null"]
#CMD ["flask", "run"]
