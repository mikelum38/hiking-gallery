from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
from werkzeug.utils import secure_filename
import sqlite3
from datetime import datetime
import locale

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
app.config['DEV_MODE'] = os.environ.get('FLASK_ENV') == 'development'
app.secret_key = 'votre_clé_secrète_ici'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def init_db():
    # Vérifie si la base de données existe déjà
    if not os.path.exists('galleries.db'):
        conn = sqlite3.connect('galleries.db')
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS galleries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                cover_image TEXT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                photo_date TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gallery_id INTEGER,
                filename TEXT NOT NULL,
                FOREIGN KEY (gallery_id) REFERENCES galleries (id)
            )
        ''')
        conn.commit()
        conn.close()
        print("Base de données initialisée avec succès!")

# Initialise la base de données au démarrage
init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_galleries_by_month():
    print("Fetching galleries by month")  # Debug log
    conn = sqlite3.connect('galleries.db')
    c = conn.cursor()
    
    # Récupérer toutes les galeries triées par année et mois
    c.execute('''
        SELECT id, name, description, cover_image, year, month, created_at, photo_date
        FROM galleries
        ORDER BY year DESC, month DESC, photo_date DESC
    ''')
    galleries = c.fetchall()
    print(f"Found {len(galleries)} total galleries")  # Debug log
    conn.close()

    galleries_by_month = {}
    
    for gallery in galleries:
        month_key = f"{MOIS_FR[gallery[5]]} {gallery[4]}"  # Mois Année
        print(f"Processing gallery for {month_key}")  # Debug log
        
        if month_key not in galleries_by_month:
            galleries_by_month[month_key] = {
                'galleries': [],
                'cover': None,
                'year': gallery[4],
                'month': gallery[5]
            }
        
        galleries_by_month[month_key]['galleries'].append(gallery)
        if galleries_by_month[month_key]['cover'] is None and gallery[3]:
            galleries_by_month[month_key]['cover'] = gallery[3]

    print(f"Organized into {len(galleries_by_month)} months")  # Debug log
    return galleries_by_month

@app.route('/')
def index():
    galleries_by_month = get_galleries_by_month()
    return render_template('index.html', galleries_by_month=galleries_by_month)

@app.route('/month/<int:year>/<int:month>')
def month_galleries(year, month):
    try:
        print(f"Accessing month page for {year}/{month}")  # Debug log
        
        if month < 1 or month > 12:
            print(f"Invalid month number: {month}")
            flash('Mois invalide')
            return redirect(url_for('index'))
            
        month_key = f"{MOIS_FR[month]} {year}"
        print(f"Month key: {month_key}")  # Debug log
        
        galleries_by_month = get_galleries_by_month()
        print(f"Available months: {list(galleries_by_month.keys())}")  # Debug log
        
        if month_key in galleries_by_month:
            galleries = galleries_by_month[month_key]['galleries']
            print(f"Found {len(galleries)} galleries for {month_key}")  # Debug log
            return render_template('month.html', 
                                 month=month_key, 
                                 galleries=galleries,
                                 year=year,
                                 month_num=month)
        
        print(f"Month {month_key} not found in available months")  # Debug log
        flash('Aucune galerie trouvée pour ce mois')
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"Error in month_galleries: {str(e)}")  # Debug log
        flash('Une erreur est survenue')
        return redirect(url_for('index'))

@app.route('/create_gallery', methods=['POST'])
def create_gallery():
    name = request.form.get('name')
    description = request.form.get('description')
    cover_image = request.files.get('cover_image')
    photo_date = request.form.get('photo_date')
    
    if not name:
        flash('Le nom de la galerie est requis')
        return redirect(url_for('index'))
    
    # Si aucune date n'est fournie, utiliser la date actuelle
    try:
        if photo_date:
            photo_datetime = datetime.strptime(photo_date, '%Y-%m-%d')
        else:
            photo_datetime = datetime.now()
    except ValueError:
        flash('Format de date invalide. Utilisez YYYY-MM-DD')
        return redirect(url_for('index'))
    
    if cover_image and allowed_file(cover_image.filename):
        filename = secure_filename(cover_image.filename)
        cover_image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    else:
        filename = None
    
    # Obtenir la date actuelle pour created_at
    now = datetime.now()
    current_time = now.strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('galleries.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO galleries 
        (name, description, cover_image, year, month, created_at, photo_date) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, description, filename, photo_datetime.year, photo_datetime.month, current_time, photo_date))
    gallery_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return redirect(url_for('view_gallery', gallery_id=gallery_id))

@app.route('/gallery/<int:gallery_id>')
def view_gallery(gallery_id):
    conn = sqlite3.connect('galleries.db')
    c = conn.cursor()
    c.execute('SELECT * FROM galleries WHERE id = ?', (gallery_id,))
    gallery = c.fetchone()
    
    if gallery is None:
        flash('Galerie non trouvée')
        return redirect(url_for('index'))
        
    c.execute('SELECT filename FROM photos WHERE gallery_id = ?', (gallery_id,))
    photos = c.fetchall()
    conn.close()
    
    return render_template('gallery.html', gallery=gallery, photos=photos, MOIS_FR=MOIS_FR)

@app.route('/upload/<int:gallery_id>', methods=['POST'])
def upload_files(gallery_id):
    if 'files[]' not in request.files:
        flash('Aucun fichier sélectionné')
        return redirect(url_for('view_gallery', gallery_id=gallery_id))
    
    files = request.files.getlist('files[]')
    conn = sqlite3.connect('galleries.db')
    c = conn.cursor()
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            c.execute('INSERT INTO photos (gallery_id, filename) VALUES (?, ?)',
                     (gallery_id, filename))
    
    conn.commit()
    conn.close()
    return redirect(url_for('view_gallery', gallery_id=gallery_id))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/edit_gallery_date/<int:gallery_id>', methods=['GET', 'POST'])
def edit_gallery_date(gallery_id):
    conn = sqlite3.connect('galleries.db')
    c = conn.cursor()
    
    if request.method == 'POST':
        photo_date = request.form.get('photo_date')
        
        try:
            photo_datetime = datetime.strptime(photo_date, '%Y-%m-%d')
            c.execute('''
                UPDATE galleries 
                SET year = ?, month = ?, photo_date = ?
                WHERE id = ?
            ''', (photo_datetime.year, photo_datetime.month, photo_date, gallery_id))
            conn.commit()
            flash('Date de la galerie mise à jour avec succès')
        except ValueError:
            flash('Format de date invalide. Utilisez YYYY-MM-DD')
        except Exception as e:
            flash(f'Erreur lors de la mise à jour: {str(e)}')
        
        conn.close()
        return redirect(url_for('view_gallery', gallery_id=gallery_id))
    
    # GET request - afficher le formulaire
    c.execute('SELECT name, year, month, photo_date FROM galleries WHERE id = ?', (gallery_id,))
    gallery = c.fetchone()
    conn.close()
    
    if gallery is None:
        flash('Galerie non trouvée')
        return redirect(url_for('index'))
    
    current_date = gallery[3] if gallery[3] else f"{gallery[1]:04d}-{gallery[2]:02d}-01"  # Format YYYY-MM-DD
    return render_template('edit_gallery_date.html', gallery=gallery, current_date=current_date, gallery_id=gallery_id)

if __name__ == '__main__':
    app.run(debug=True)
