import os
import sys 
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from flask import Flask, jsonify, render_template, send_file # type: ignore
import psycopg2
import sqlite3
import matplotlib # type: ignore
matplotlib.use('Agg')
import matplotlib.pyplot as plt # type: ignore
import numpy as np
from io import BytesIO
from config.settings import DB_CONFIG_SQLITE

app = Flask(__name__, 
           static_folder=os.path.join(os.path.dirname(__file__), 'static'),
           template_folder=os.path.join(os.path.dirname(__file__), 'templates'))

def get_db_connection():
    conn = sqlite3.connect(DB_CONFIG_SQLITE['database'])
    conn.row_factory = sqlite3.Row
    return conn

def generate_bar_chart(data, title):
    fig = plt.figure(figsize=(10, 7))  # Tamanho reduzido
    ax = fig.add_subplot(111)
    
    # Configurações do gráfico
    y_pos = np.arange(len(data['labels']))
    bars = ax.barh(y_pos, data['counts'], height=0.9, color='#4e79a7')
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(data['labels'], fontsize=15)
    ax.invert_yaxis()
    
    ax.set_xlabel('Número de Casos', fontsize=15)
    ax.xaxis.set_tick_params(labelsize=15)
    
    ax.set_title(title, fontsize=15, pad=20)
    ax.grid(axis='x', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    
    img_buffer = BytesIO()
    fig.savefig(img_buffer, format='png', bbox_inches='tight', dpi=100)
    img_buffer.seek(0)
    plt.close(fig)
    return img_buffer

def generate_pie_chart(condition):
    conn = get_db_connection()
    data = conn.execute('''
        SELECT gender, COUNT(*) as count 
        FROM patients 
        WHERE patient_id IN (
            SELECT patient_id FROM conditions WHERE condition_text = ?
        )
        GROUP BY gender
    ''', (condition,)).fetchall()
    conn.close()
    
    labels = [row['gender'] for row in data]
    sizes = [row['count'] for row in data]

    plt.figure(figsize=(8, 8))  # Aumentar tamanho da figura
    ax = plt.gca()
    
    # Configurações do gráfico
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct='%1.1f%%',
        startangle=140,
        textprops={'fontsize': 14},  # Tamanho da fonte dos labels
        pctdistance=0.85,  # Distância dos percentuais
        labeldistance=1.05  # Distância dos labels
    )
    
    # Aumentar tamanho dos textos
    for text in texts + autotexts:
        text.set_size(20)

    ax.set_title(f'Distribuição por Gênero: {condition[:30]}...', fontsize=20, pad=20)
    ax.axis('equal')
    
    # Ajustar layout para evitar cortes
    plt.tight_layout()
    
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=100)
    img_buffer.seek(0)
    plt.close()
    return img_buffer

@app.route('/')
def dashboard():
    conn = get_db_connection()
    
    # Dados para listas e gráficos de barras
    top_conditions = conn.execute('''
        SELECT condition_text, COUNT(*) as count 
        FROM conditions 
        GROUP BY condition_text 
        ORDER BY count DESC 
        LIMIT 10
    ''').fetchall()

    top_meds = conn.execute('''
        SELECT medication_text, COUNT(*) as count 
        FROM medications 
        GROUP BY medication_text 
        ORDER BY count DESC 
        LIMIT 10
    ''').fetchall()

    # Estatísticas de sexos
    gender_stats = conn.execute('''
        SELECT 
            SUM(CASE WHEN gender = 'male' THEN 1 ELSE 0 END) as male,
            SUM(CASE WHEN gender = 'female' THEN 1 ELSE 0 END) as female,
            SUM(CASE WHEN gender NOT IN ('male', 'female') THEN 1 ELSE 0 END) as other
        FROM patients
    ''').fetchone()

    conn.close()
    
    # Converter os objetos Row em dicionários
    top_conditions = [dict(row) for row in top_conditions]
    top_meds = [dict(row) for row in top_meds]
    gender_stats = dict(gender_stats)
    
    return render_template('dashboard.html', 
                         conditions=top_conditions,
                         medications=top_meds,
                         male_count=gender_stats['male'],
                         female_count=gender_stats['female'])

@app.route('/plot/conditions')
def plot_conditions():
    conn = get_db_connection()
    data = conn.execute('''
        SELECT condition_text, COUNT(*) as count 
        FROM conditions 
        GROUP BY condition_text 
        ORDER BY count DESC 
        LIMIT 10
    ''').fetchall()
    conn.close()
    
    chart_data = {
        'labels': [row['condition_text'] for row in data],
        'counts': [row['count'] for row in data]
    }
    
    img = generate_bar_chart(chart_data, 'Top 10 Condições Médicas')  # 2 argumentos
    return send_file(img, mimetype='image/png')

@app.route('/plot/medications')
def plot_medications():
    conn = get_db_connection()
    data = conn.execute('''
        SELECT medication_text, COUNT(*) as count 
        FROM medications 
        GROUP BY medication_text 
        ORDER BY count DESC 
        LIMIT 10
    ''').fetchall()
    conn.close()
    
    chart_data = {
        'labels': [row['medication_text'] for row in data],
        'counts': [row['count'] for row in data]
    }
    
    img = generate_bar_chart(chart_data, 'Top 10 Medicamentos Prescritos')  # 2 argumentos
    return send_file(img, mimetype='image/png')

@app.route('/data/pie/<type>/<value>')
def data_pie(type, value):
    conn = get_db_connection()
    try:
        if type == 'condition':
            data = conn.execute('''
                SELECT gender, COUNT(*) as count 
                FROM patients 
                WHERE patient_id IN (
                    SELECT patient_id FROM conditions WHERE condition_text = ?
                )
                GROUP BY gender
            ''', (value,)).fetchall()
        elif type == 'medication':
            data = conn.execute('''
                SELECT gender, COUNT(*) as count 
                FROM patients 
                WHERE patient_id IN (
                    SELECT patient_id FROM medications WHERE medication_text = ?
                )
                GROUP BY gender
            ''', (value,)).fetchall()
        else:
            return jsonify({'error': 'Tipo inválido'}), 400
        
        data = [dict(row) for row in data]
        
        return jsonify({
            'labels': [row['gender'] for row in data],
            'counts': [row['count'] for row in data],
            'total': sum(row['count'] for row in data)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
