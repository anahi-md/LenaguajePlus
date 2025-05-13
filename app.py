from flask import Flask, request, jsonify, send_file, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import speech_recognition as sr
from gtts import gTTS
from deep_translator import GoogleTranslator
import os
from pydub import AudioSegment
import re
import sqlite3
from datetime import datetime
import tempfile
from shutil import which

# Configuración inicial
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Clave secreta segura
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB límite
DATABASE = 'database.db'

#Pydub con FFmpeg
AudioSegment.converter = which("ffmpeg") or which("ffmpeg")
AudioSegment.ffprobe = which("ffprobe") or which("ffprobe")

#Base de datos
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT DEFAULT 'user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS recordings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        translation TEXT NOT NULL,
                        audio_path TEXT NOT NULL,
                        source_lang TEXT NOT NULL,
                        target_lang TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )''')
        conn.commit()


def validate_password(password):
    conditions = [
        (len(password) >= 8, "La contraseña debe tener al menos 8 caracteres"),
        (re.search(r'[A-Z]', password), "La contraseña debe contener al menos una mayúscula"),
        (re.search(r'[a-z]', password), "La contraseña debe contener al menos una minúscula"),
        (re.search(r'\d', password), "La contraseña debe contener al menos un número"),
        (re.search(r'[!@#$%^&*(),.?":{}|<>]', password), "La contraseña debe contener al menos un carácter especial")
    ]
    
    for condition, message in conditions:
        if not condition:
            return False, message
    return True, ""
#Rutas de vistas
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        with sqlite3.connect(DATABASE) as conn:
            user = conn.execute(
                'SELECT id, username, password, role FROM users WHERE username = ?',
                (username,)
            ).fetchone()
            
            if user and check_password_hash(user[2], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[3]
                return redirect(url_for('index'))
            
        flash('Usuario o contraseña incorrectos', 'error')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        # Validaciones
        if not username or not email or not password:
            flash('Todos los campos son requeridos', 'error')
            return redirect(url_for('register'))
        
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            flash('Correo electrónico inválido', 'error')
            return redirect(url_for('register'))
        
        is_valid, msg = validate_password(password)
        if not is_valid:
            flash(msg, 'error')
            return redirect(url_for('register'))
        
        try:
            with sqlite3.connect(DATABASE) as conn:
                conn.execute(
                    'INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
                    (username, email, generate_password_hash(password), 'user')
                )
                conn.commit()
            flash('Registro exitoso. Por favor inicia sesión.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('El nombre de usuario o correo ya está registrado', 'error')
    
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

#Procesamiento de aduio
def guardar_archivo_temporal(audio_file, timestamp):
    if not audio_file.filename.endswith('.webm'):
        raise ValueError("El archivo debe ser de tipo .webm")
    
    original_path = os.path.join(app.config['UPLOAD_FOLDER'], f'original_{timestamp}.webm')
    audio_file.save(original_path)
    return original_path

def convertir_a_wav(original_path, timestamp):
    try:
        wav_path = os.path.join(app.config['UPLOAD_FOLDER'], f'converted_{timestamp}.wav')
        sound = AudioSegment.from_file(original_path)
        sound.export(wav_path, format='wav')
        return wav_path
    except Exception as e:
        raise ValueError(f"Error al convertir el archivo a wav: {e}")

def reconocer_texto(wav_path, source_lang):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        texto = recognizer.recognize_google(audio, language=source_lang)
        print(f"Texto reconocido: {texto}")
        return texto
    except sr.UnknownValueError:
        raise ValueError("No se pudo entender el audio")
    except sr.RequestError as e:
        raise ValueError(f"Error en el servicio de reconocimiento: {e}")


def traducir_texto(texto, source_lang, target_lang):
    try:
        traduccion = GoogleTranslator(source=source_lang, target=target_lang).translate(texto)
        print(f"Texto traducido: {traduccion}")
        return traduccion
    except Exception as e:
        raise ValueError(f"Error en la traducción: {e}")


def generar_audio_traducido(traduccion, target_lang, timestamp):
    supported_languages = ['en', 'es', 'fr', 'de', 'it', 'pt']
    if target_lang not in supported_languages:
        raise ValueError(f"Idioma no soportado para gTTS: {target_lang}")
    
    translated_path = os.path.join(app.config['UPLOAD_FOLDER'], f'translated_{timestamp}.mp3')
    tts = gTTS(traduccion, lang=target_lang)
    tts.save(translated_path)
    print(f"Archivo MP3 traducido guardado en: {translated_path}")
    return translated_path


def guardar_en_base_datos(user_id, texto, traduccion, translated_path, source_lang, target_lang):
    with sqlite3.connect(DATABASE) as conn:
        conn.execute(
            '''INSERT INTO recordings 
               (user_id, text, translation, audio_path, source_lang, target_lang)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, texto, traduccion, translated_path, source_lang, target_lang)
        )
        conn.commit()

@app.route('/procesar_audio', methods=['POST'])
def procesar_audio():
    if 'audio' not in request.files:
        return jsonify({'error': 'No se envió archivo de audio'}), 400

    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': 'Nombre de archivo inválido'}), 400

    source_lang = request.form.get('source_lang', 'es')
    target_lang = request.form.get('target_lang', 'en')
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

    try:
        original_path = guardar_archivo_temporal(audio_file, timestamp)
        wav_path = convertir_a_wav(original_path, timestamp)
        texto = reconocer_texto(wav_path, source_lang)
        traduccion = traducir_texto(texto, source_lang, target_lang)
        translated_path = generar_audio_traducido(traduccion, target_lang, timestamp)

        if 'user_id' in session:
            guardar_en_base_datos(session['user_id'], texto, traduccion, translated_path, source_lang, target_lang)

        return jsonify({
            'texto': texto,
            'traduccion': traduccion,
            'audio_url': f'/audio_traducido/{timestamp}'
        })

    except sr.UnknownValueError:
        return jsonify({'error': 'No se pudo entender el audio'}), 400
    except sr.RequestError as e:
        return jsonify({'error': f'Error en el servicio de reconocimiento: {e}'}), 500
    except Exception as e:
        print(f"[ERROR] Fallo en /procesar_audio: {e}")
        return jsonify({'error': f'Error inesperado: {str(e)}'}), 500
    finally:
        for ext in ['original', 'converted']:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f'{ext}_{timestamp}.{"webm" if ext == "original" else "wav"}')
            if os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    print(f"Error al eliminar archivo temporal: {e}")


@app.route('/audio_traducido/<timestamp>')
def audio_traducido(timestamp):
    path = os.path.join(app.config['UPLOAD_FOLDER'], f'translated_{timestamp}.mp3')
    if os.path.exists(path):
        return send_file(path, mimetype='audio/mpeg')
    return 'Archivo no encontrado', 404

#Admin
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    with sqlite3.connect(DATABASE) as conn:
        users = conn.execute(
            'SELECT id, username, email, role FROM users ORDER BY created_at DESC'
        ).fetchall()
    
    return render_template('admin/dashboard.html', users=users)

@app.route('/make_admin/<int:user_id>', methods=['POST'])
def make_admin(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
        conn.commit()

    flash("Usuario promovido a administrador", "success")
    return redirect(url_for('dashboard'))

#Grabaciones
@app.route('/recordings')
def recordings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute(
            '''SELECT id, text, translation, audio_path, created_at 
               FROM recordings 
               WHERE user_id = ? 
               ORDER BY created_at DESC''',
            (session['user_id'],)
        )
        recordings = [
            (r[0], r[1], r[2], r[3], datetime.strptime(r[4], '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y %H:%M'))
            for r in cursor.fetchall()
    ]


    return render_template('recordings.html', recordings=recordings)

@app.route('/play/<int:id>')
def play_recording(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute(
            'SELECT audio_path FROM recordings WHERE id = ? AND user_id = ?',
            (id, session['user_id'])
        )
        result = cursor.fetchone()

    if result:
        audio_path = result[0]
        if os.path.exists(audio_path):
            return send_file(audio_path, mimetype='audio/mpeg')

    return 'Archivo no encontrado', 404

@app.route('/delete/<int:id>', methods=['POST'])
def delete_recording(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        # Verificar si la grabación pertenece al usuario
        cursor = conn.execute(
            'SELECT audio_path FROM recordings WHERE id = ? AND user_id = ?',
            (id, session['user_id'])
        )
        result = cursor.fetchone()

        if result:
            audio_path = result[0]
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as e:
                    print(f"Error al eliminar el archivo: {e}")

            # Eliminar la fila de la base de datos
            conn.execute('DELETE FROM recordings WHERE id = ? AND user_id = ?', (id, session['user_id']))
            conn.commit()

    flash('Grabación eliminada exitosamente.', 'success')
    return redirect(url_for('recordings'))

##Iniciar app
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
    #finally:
        #clean_temp_files()