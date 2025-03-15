from flask import Flask, render_template, send_file  # type: ignore
import psycopg2
import psycopg2.extras
import matplotlib  # type: ignore
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # type: ignore
import numpy as np
from io import BytesIO
from config.settings import DB_CONFIG

app = Flask(__name__)

# Função de conexão ajustada para PostgreSQL
def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_CONFIG['dbname'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port']
    )
    conn.cursor_factory = psycopg2.extras.DictCursor  # Para resultados como dicionários
    return conn

# Função de gráfico de barras (sem alterações)
def generate_bar_chart(data, title):
    fig = plt.figure(figsize=(15, 8))  # Tamanho reduzido
    ax = fig.add_subplot(111)
    
    y_pos = np.arange(len(data['labels']))
    bars = ax.barh(y_pos, data['counts'], height=0.9, color='#4e79a7')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(data['labels'], fontsize=20)
    ax.invert_yaxis()
    
    ax.set_xlabel('Número de Casos', fontsize=20)
    ax.xaxis.set_tick_params(labelsize=15)
    
    ax.set_title(title, fontsize=20, pad=23)
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    
    img_buffer = BytesIO()
    fig.savefig(img_buffer, format='png', bbox_inches='tight', dpi=120)
    img_buffer.seek(0)
    plt.close(fig)
    return img_buffer

# Função de gráfico de pizza ajustada
def generate_pie_chart(condition):
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute('''
            SELECT gender, COUNT(*) as count 
            FROM etl.patients 
            WHERE patient_id IN (
                SELECT patient_id FROM etl.conditions WHERE condition_text = %s
            )
            GROUP BY gender
        ''', (condition,))
        data = cursor.fetchall()
    conn.close()

    labels = [row['gender'] for row in data]
    sizes = [row['count'] for row in data]

    plt.figure(figsize=(10, 10))
    ax = plt.gca()
    
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct='%1.1f%%',
        startangle=140,
        textprops={'fontsize': 14},
        pctdistance=0.85,
        labeldistance=1.05
    )
    
    for text in texts + autotexts:
        text.set_size(20)

    ax.set_title(f'Distribuição por Gênero: {condition[:30]}...', fontsize=20, pad=20)
    ax.axis('equal')
    
    plt.tight_layout()
    
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=100)
    img_buffer.seek(0)
    plt.close()
    return img_buffer

@app.route('/')
def dashboard():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        # Top condições
        cursor.execute('''
            SELECT condition_text, COUNT(*) as count 
            FROM etl.conditions 
            GROUP BY condition_text 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_conditions = cursor.fetchall()

        # Top medicamentos
        cursor.execute('''
            SELECT medication_text, COUNT(*) as count 
            FROM etl.medications 
            GROUP BY medication_text 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        top_meds = cursor.fetchall()

        # Estatísticas de gênero
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN gender = 'male' THEN 1 ELSE 0 END) as male,
                SUM(CASE WHEN gender = 'female' THEN 1 ELSE 0 END) as female,
                SUM(CASE WHEN gender NOT IN ('male', 'female') THEN 1 ELSE 0 END) as other
            FROM etl.patients
        ''')
        gender_stats = cursor.fetchone()

    conn.close()
    
    return render_template('dashboard.html', 
                         conditions=top_conditions,
                         medications=top_meds,
                         male_count=gender_stats['male'],
                         female_count=gender_stats['female'],
                         other_gender_count=gender_stats['other'])

@app.route('/plot/conditions')
def plot_conditions():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute('''
            SELECT condition_text, COUNT(*) as count 
            FROM etl.conditions 
            GROUP BY condition_text 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        data = cursor.fetchall()
    conn.close()
    
    chart_data = {
        'labels': [row['condition_text'] for row in data],
        'counts': [row['count'] for row in data]
    }
    
    img = generate_bar_chart(chart_data, 'Top 10 Condições Médicas')
    return send_file(img, mimetype='image/png')

@app.route('/plot/medications')
def plot_medications():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute('''
            SELECT medication_text, COUNT(*) as count 
            FROM etl.medications 
            GROUP BY medication_text 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        data = cursor.fetchall()
    conn.close()
    
    chart_data = {
        'labels': [row['medication_text'] for row in data],
        'counts': [row['count'] for row in data]
    }
    
    img = generate_bar_chart(chart_data, 'Top 10 Medicamentos Prescritos')
    return send_file(img, mimetype='image/png')

@app.route('/plot/pie/<condition>')
def plot_pie(condition):
    img = generate_pie_chart(condition)
    return send_file(img, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True)