import os
from datetime import datetime
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
from PIL import Image

# --- CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here_change_this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farm_data.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
# Note: Specific video folders are handled in the route to match HTML static paths
app.config['THUMB_FOLDER'] = 'static/thumbnails'
app.config['PROFILE_FOLDER'] = 'static/profiles' 
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  

# API Setup
genai.configure(api_key="AIzaSyDhSagikZ_YKy_TCOELH33rdFpkaAIokMI") 
model = genai.GenerativeModel('gemini-2.0-flash')

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMB_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROFILE_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELS (UPDATED with Helper Properties) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    phone = db.Column(db.String(50)) 
    role = db.Column(db.String(50)) 
    village = db.Column(db.String(100))
    district = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pincode = db.Column(db.String(20))
    profile_image = db.Column(db.String(300))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    image_path = db.Column(db.String(300))
    category = db.Column(db.String(100))
    name = db.Column(db.String(100))
    pick_time = db.Column(db.String(100))
    temperature = db.Column(db.String(50))
    expiry_prediction = db.Column(db.String(100))
    description = db.Column(db.Text)
    tips = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    video_path = db.Column(db.String(300))
    thumbnail_path = db.Column(db.String(300))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    location = db.Column(db.String(100))
    expiry_date = db.Column(db.String(100))
    farmer = db.relationship('User', backref='videos')
    comments = db.relationship('Comment', backref='video')
    likes = db.relationship('Like', backref='video')

    # Properties to allow template compatibility (video.filename vs video.video_path)
    @property
    def filename(self):
        return self.video_path

    @property
    def thumbnail(self):
        return self.thumbnail_path

    @property
    def has_liked(self):
        if not current_user.is_authenticated:
            return False
        return bool(Like.query.filter_by(user_id=current_user.id, video_id=self.id).first())
    
    @property
    def farmer_name(self):
        return self.farmer.name if self.farmer else "Unknown Farmer"

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'))
    text = db.Column(db.String(500))
    user_name = db.Column(db.String(100))

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        role = request.form.get('role')
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match!')
            return redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('signup'))

        profile_img_filename = None
        file = request.files.get('profile_image')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            profile_img_filename = filename
            file.save(os.path.join(app.config['PROFILE_FOLDER'], filename))

        village = request.form.get('village')
        district = request.form.get('district')
        state = request.form.get('state')
        pincode = request.form.get('pincode')

        new_user = User(
            name=name, email=email, role=role, phone=phone,
            password=generate_password_hash(password),
            village=village, district=district, state=state, pincode=pincode,
            profile_image=profile_img_filename
        )
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('farmer_dashboard' if role == 'farmer' else 'user_dashboard'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            if user.role == 'farmer':
                return redirect(url_for('farmer_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- FARMER DASHBOARD ---
@app.route('/farmer/dashboard', methods=['GET', 'POST'])
@login_required
def farmer_dashboard():
    if current_user.role != 'farmer': return redirect(url_for('login'))
    
    analyzed_product = None
    language_map = {
        'en': 'English', 'hi': 'Hindi', 'mr': 'Marathi', 'gu': 'Gujarati', 'bn': 'Bengali',
        'pa': 'Punjabi', 'te': 'Telugu', 'ta': 'Tamil', 'ml': 'Malayalam', 'kn': 'Kannada',
        'ur': 'Urdu', 'or': 'Odia', 'as': 'Assamese', 'mni': 'Manipuri', 'ne': 'Nepali',
        'sa': 'Sanskrit', 'sd': 'Sindhi', 'doi': 'Dogri', 'kok': 'Konkani', 'brx': 'Bodo',
        'mai': 'Maithili', 'sat': 'Santali', 'ks': 'Kashmiri'
    }

    if request.method == 'POST':
        file = request.files['image']
        category = request.form.get('category')
        name = request.form.get('name')
        pick_time = request.form.get('pick_time')
        temp = request.form.get('temp')
        
        lang_code = request.form.get('language', 'en')
        target_language = language_map.get(lang_code, 'English')
        
        if file:
            filename = secure_filename(file.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(path)
            
            prompt = f"""
            You are an expert Agricultural Scientist and Post-Harvest Technologist.
            Analyze the attached image of a harvested crop with high precision.
            
            CROP DETAILS:
            - Name: {name}
            - Category: {category}
            - Harvest Date: {pick_time}
            - Current Temperature: {temp}°C
            - User's Preferred Language: {target_language}

            TASKS:
            1. VISUAL INSPECTION: Analyze the visual condition of the product in the image (color, texture, signs of bruising, wilt, or spoilage).
            2. SHELF-LIFE CALCULATION: Based on the visual inspection, the elapsed time since harvest, and the current storage temperature, scientifically estimate the remaining shelf-life date (Format: YYYY-MM-DD). Be realistic.
            3. QUALITY DESCRIPTION: Write a concise, professional 2-sentence assessment of the crop's current quality based on the visual evidence.
            4. PRESERVATION TIPS: Provide 2 specific, actionable, and scientifically backing storage tips to extend the life of this specific crop under the given temperature.
            
            OUTPUT FORMAT REQUIREMENTS:
            - Provide the content for 'desc' (Description) and 'tips' translated into {target_language}.
            - The JSON keys must remain in English ('expiry', 'desc', 'tips').
            - The 'expiry' date must be strictly in YYYY-MM-DD format.
            
            Return ONLY raw JSON: {{"expiry": "YYYY-MM-DD", "desc": "Translated Description...", "tips": "Translated Tips..."}}
            """
            
            try:
                img = Image.open(path)
                response = model.generate_content([prompt, img])
                text_resp = response.text.replace('```json', '').replace('```', '')
                ai_data = json.loads(text_resp)
                
                new_prod = Product(
                    farmer_id=current_user.id,
                    image_path=filename,
                    category=category,
                    name=name,
                    pick_time=pick_time,
                    temperature=temp,
                    expiry_prediction=ai_data.get('expiry', 'Unknown'),
                    description=ai_data.get('desc', 'No description'),
                    tips=ai_data.get('tips', 'No tips')
                )
                db.session.add(new_prod)
                db.session.commit()
                analyzed_product = new_prod 
                flash("Analyzed Successfully!")
            except Exception as e:
                flash(f"AI Error: {str(e)}")

    return render_template('farmer_dashboard.html', user=current_user, result=analyzed_product)

# --- PRODUCT LIST ---
@app.route('/farmer/list')
@login_required
def product_list():
    if current_user.role != 'farmer': return redirect(url_for('login'))
    search = request.args.get('search')
    query = Product.query.filter_by(farmer_id=current_user.id)
    if search: query = query.filter(Product.name.contains(search))
    products = query.order_by(Product.created_at.desc()).all()
    return render_template('list.html', products=products, user=current_user)

@app.route('/farmer/videos')
@login_required
def farmer_videos():
    if current_user.role != 'farmer': return redirect(url_for('login'))
    # New uploading logic is now in '/farmer/upload_video' (ajax)
    # displaying videos only here
    videos = Video.query.order_by(Video.id.desc()).all()
    return render_template('videos.html', videos=videos, user=current_user)

# --- NEW: DEDICATED AJAX VIDEO UPLOAD ROUTE TO FIX 404 ---
@app.route('/farmer/upload_video', methods=['POST'])
@login_required
def upload_video_ajax():
    if current_user.role != 'farmer':
        return jsonify({'error': 'Unauthorized'}), 403

    # Check for files with the keys used in videos.html form
    if 'video_file' not in request.files or 'thumbnail' not in request.files:
        return jsonify({'error': 'Missing files'}), 400
        
    vid_file = request.files['video_file']
    thumb_file = request.files['thumbnail']
    title = request.form.get('title')
    description = request.form.get('description')
    expiry = request.form.get('expiry_date')
    
    if vid_file.filename == '' or thumb_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    # Setup Specific folders for videos/thumbs if they differ from upload
    video_folder = os.path.join(app.root_path, 'static', 'videos')
    thumb_folder = os.path.join(app.root_path, 'static', 'thumbnails')
    os.makedirs(video_folder, exist_ok=True)
    os.makedirs(thumb_folder, exist_ok=True)
    
    v_name = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{vid_file.filename}")
    t_name = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{thumb_file.filename}")
    
    # Save to the specific folders expected by frontend url_for('static', filename='videos/...')
    vid_file.save(os.path.join(video_folder, v_name))
    thumb_file.save(os.path.join(thumb_folder, t_name))
    
    new_vid = Video(
        farmer_id=current_user.id,
        video_path=v_name, 
        thumbnail_path=t_name,
        title=title,
        description=description,
        location=current_user.village or "Unknown",
        expiry_date=expiry
    )
    db.session.add(new_vid)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Uploaded successfully'}), 200

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    if current_user.role != 'user': return redirect(url_for('login'))
    videos = Video.query.order_by(Video.id.desc()).all()
    return render_template('user_dashboard.html', videos=videos, user=current_user)

@app.route('/video/like/<int:vid_id>', methods=['POST', 'GET'])
@login_required
def like_video(vid_id):
    # Added POST support for JS fetch
    existing = Like.query.filter_by(user_id=current_user.id, video_id=vid_id).first()
    if not existing:
        db.session.add(Like(user_id=current_user.id, video_id=vid_id))
    else:
        db.session.delete(existing) # Toggle functionality for AJAX
        
    db.session.commit()
    
    if request.method == 'POST':
        return jsonify({'status': 'success'})
    return redirect(request.referrer)

@app.route('/video/comment/<int:vid_id>', methods=['POST'])
@login_required
def comment_video(vid_id):
    text = request.form.get('comment')
    if text:
        db.session.add(Comment(user_id=current_user.id, video_id=vid_id, text=text, user_name=current_user.name))
        db.session.commit()
    return redirect(request.referrer)

# --- VIDEO DELETE ROUTE ---
@app.route('/delete_video/<int:vid_id>', methods=['POST'])
@login_required
def delete_video(vid_id):
    video = Video.query.get_or_404(vid_id)
    if video.farmer_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

    try:
        Comment.query.filter_by(video_id=vid_id).delete()
        Like.query.filter_by(video_id=vid_id).delete()
        
        try:
            # Clean up files - Check both config location and static/videos location
            if video.video_path:
                v_path = os.path.join(app.root_path, 'static', 'videos', video.video_path)
                if os.path.exists(v_path): os.remove(v_path)
                
            if video.thumbnail_path:
                t_path = os.path.join(app.root_path, 'static', 'thumbnails', video.thumbnail_path)
                if os.path.exists(t_path): os.remove(t_path)
        except Exception:
            pass 
            
        db.session.delete(video)
        db.session.commit()
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
