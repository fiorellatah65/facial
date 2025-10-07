from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import cv2
import os
from mtcnn.mtcnn import MTCNN
import numpy as np
import base64
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Crear carpetas necesarias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('datos_usuarios', exist_ok=True)

# ------------------------ Función auxiliar: Listar usuarios ------------------------
def obtener_lista_usuarios():
    """Retorna lista de todos los usuarios registrados"""
    usuarios = []
    if os.path.exists('datos_usuarios'):
        for archivo in os.listdir('datos_usuarios'):
            if archivo.endswith('.txt'):
                usuarios.append(archivo.replace('.txt', ''))
    return usuarios

# ------------------------ Función auxiliar: Verificar si usuario existe ------------------------
def usuario_existe(usuario):
    """Verifica si un usuario ya está registrado"""
    ruta_usuario = os.path.join('datos_usuarios', f"{usuario}.txt")
    return os.path.exists(ruta_usuario)

# ------------------------ Página Principal ------------------------
@app.route('/')
def index():
    # Obtener estadísticas
    usuarios_registrados = len(obtener_lista_usuarios())
    return render_template('index.html', total_usuarios=usuarios_registrados)

# ------------------------ Registro (Usuario + Contraseña) ------------------------
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contra = request.form.get('contra', '')
        
        # Validaciones
        if not usuario or not contra:
            flash('Por favor completa todos los campos', 'error')
            return render_template('registro.html')
        
        if len(usuario) < 3:
            flash('El usuario debe tener al menos 3 caracteres', 'error')
            return render_template('registro.html')
        
        if len(contra) < 4:
            flash('La contraseña debe tener al menos 4 caracteres', 'error')
            return render_template('registro.html')
        
        # Verificar si el usuario ya existe
        if usuario_existe(usuario):
            flash(f'El usuario "{usuario}" ya existe. Por favor elige otro nombre.', 'error')
            return render_template('registro.html')
        
        # Guardar usuario y contraseña hasheada
        contra_hash = generate_password_hash(contra)
        ruta_usuario = os.path.join('datos_usuarios', f"{usuario}.txt")
        with open(ruta_usuario, "w") as f:
            f.write(f"{usuario}\n{contra_hash}")
        
        # Guardar en sesión para el registro facial
        session['usuario_temporal'] = usuario
        flash(f'✅ Usuario "{usuario}" creado. Ahora captura tu rostro (opcional).', 'success')
        return render_template('registro.html', mostrar_facial=True, usuario=usuario)
    
    return render_template('registro.html')

# ------------------------ Registro Facial (Captura desde webcam) ------------------------
@app.route('/capturar_registro', methods=['POST'])
def capturar_registro():
    try:
        data = request.get_json()
        imagen_base64 = data.get('imagen')
        usuario = session.get('usuario_temporal')
        
        if not usuario:
            return jsonify({'error': 'No hay usuario en sesión. Registra primero tu usuario y contraseña.'}), 400
        
        # Decodificar imagen base64
        imagen_data = base64.b64decode(imagen_base64.split(',')[1])
        nparr = np.frombuffer(imagen_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Detectar rostro con MTCNN
        detector = MTCNN()
        caras = detector.detect_faces(img)
        
        if not caras:
            return jsonify({'error': 'No se detectó ningún rostro. Intenta de nuevo.'}), 400
        
        # Extraer y guardar el rostro
        x, y, w, h = caras[0]['box']
        rostro = img[y:y+h, x:x+w]
        rostro_redimensionado = cv2.resize(rostro, (150, 200), interpolation=cv2.INTER_CUBIC)
        
        ruta_imagen = os.path.join(app.config['UPLOAD_FOLDER'], f"{usuario}.jpg")
        cv2.imwrite(ruta_imagen, rostro_redimensionado)
        
        session.pop('usuario_temporal', None)
        return jsonify({'success': True, 'mensaje': 'Registro facial completado exitosamente'})
        
    except Exception as e:
        return jsonify({'error': f'Error al procesar la imagen: {str(e)}'}), 500

# ------------------------ Omitir registro facial ------------------------
@app.route('/omitir_facial', methods=['POST'])
def omitir_facial():
    """Permite omitir el registro facial y continuar solo con usuario/contraseña"""
    session.pop('usuario_temporal', None)
    return jsonify({'success': True, 'mensaje': 'Registro completado sin reconocimiento facial'})

# ------------------------ Login Tradicional ------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contra = request.form.get('contra', '')
        
        if not usuario or not contra:
            flash('Por favor completa todos los campos', 'error')
            return render_template('login.html')
        
        ruta_usuario = os.path.join('datos_usuarios', f"{usuario}.txt")
        
        if not os.path.exists(ruta_usuario):
            flash('Usuario no encontrado', 'error')
            return render_template('login.html')
        
        # Verificar contraseña
        with open(ruta_usuario, "r") as f:
            lineas = f.read().splitlines()
            if len(lineas) >= 2:
                contra_guardada = lineas[1]
                if check_password_hash(contra_guardada, contra):
                    session['usuario'] = usuario
                    flash('Inicio de sesión exitoso', 'success')
                    return redirect(url_for('bienvenida'))
        
        flash('Contraseña incorrecta', 'error')
        return render_template('login.html')
    
    return render_template('login.html')

# ------------------------ Login Facial ------------------------
@app.route('/login_facial', methods=['POST'])
def login_facial():
    try:
        data = request.get_json()
        imagen_base64 = data.get('imagen')
        usuario = data.get('usuario', '').strip()
        
        if not usuario:
            return jsonify({'error': 'Por favor ingresa tu nombre de usuario'}), 400
        
        # Verificar que el usuario existe
        ruta_usuario = os.path.join('datos_usuarios', f"{usuario}.txt")
        if not os.path.exists(ruta_usuario):
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Verificar que tiene registro facial
        ruta_rostro_registrado = os.path.join(app.config['UPLOAD_FOLDER'], f"{usuario}.jpg")
        if not os.path.exists(ruta_rostro_registrado):
            return jsonify({'error': 'Este usuario no tiene registro facial. Usa login con contraseña.'}), 404
        
        # Decodificar imagen capturada
        imagen_data = base64.b64decode(imagen_base64.split(',')[1])
        nparr = np.frombuffer(imagen_data, np.uint8)
        img_login = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Detectar rostro
        detector = MTCNN()
        caras = detector.detect_faces(img_login)
        
        if not caras:
            return jsonify({'error': 'No se detectó ningún rostro en la imagen'}), 400
        
        # Extraer rostro
        x, y, w, h = caras[0]['box']
        rostro_login = img_login[y:y+h, x:x+w]
        rostro_login = cv2.resize(rostro_login, (150, 200), interpolation=cv2.INTER_CUBIC)
        
        # Guardar temporalmente para comparación
        ruta_temp = os.path.join(app.config['UPLOAD_FOLDER'], f"{usuario}_temp.jpg")
        cv2.imwrite(ruta_temp, rostro_login)
        
        # Comparar rostros usando ORB
        rostro_reg = cv2.imread(ruta_rostro_registrado, 0)
        rostro_log = cv2.imread(ruta_temp, 0)
        
        orb = cv2.ORB_create()
        kpa, da = orb.detectAndCompute(rostro_reg, None)
        kpb, db = orb.detectAndCompute(rostro_log, None)
        
        if da is None or db is None:
            os.remove(ruta_temp)
            return jsonify({'error': 'Error al procesar las características faciales'}), 400
        
        comp = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = comp.match(da, db)
        
        if len(matches) == 0:
            os.remove(ruta_temp)
            return jsonify({'error': 'No se encontraron coincidencias faciales'}), 400
        
        regiones_similares = [m for m in matches if m.distance < 70]
        similitud = len(regiones_similares) / len(matches)
        
        # Limpiar archivo temporal
        os.remove(ruta_temp)
        
        # Verificar similitud (umbral: 90%)
        if similitud >= 0.90:
            session['usuario'] = usuario
            return jsonify({
                'success': True, 
                'mensaje': f'Login facial exitoso. Similitud: {similitud:.1%}'
            })
        else:
            return jsonify({
                'error': f'Rostro no coincide. Similitud: {similitud:.1%}. Intenta de nuevo o usa tu contraseña.'
            }), 401
            
    except Exception as e:
        return jsonify({'error': f'Error en el proceso: {str(e)}'}), 500

# ------------------------ Página de Bienvenida ------------------------
@app.route('/bienvenida')
def bienvenida():
    usuario = session.get('usuario')
    if not usuario:
        flash('Debes iniciar sesión primero', 'error')
        return redirect(url_for('login'))
    
    return render_template('bienvenida.html', usuario=usuario)

# ------------------------ Cerrar Sesión ------------------------
@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('Sesión cerrada exitosamente', 'info')
    return redirect(url_for('index'))

# ------------------------ Ver Usuarios Registrados ------------------------
@app.route('/usuarios')
def ver_usuarios():
    """Muestra todos los usuarios registrados en el sistema"""
    usuarios = obtener_lista_usuarios()
    usuarios_info = []
    
    for usuario in usuarios:
        tiene_facial = os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], f"{usuario}.jpg"))
        usuarios_info.append({
            'nombre': usuario,
            'tiene_facial': tiene_facial
        })
    
    return render_template('usuarios.html', usuarios=usuarios_info, total=len(usuarios_info))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)