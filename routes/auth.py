from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm = request.form['confirm_password']

        error = None
        if not username or not email or not password:
            error = 'All fields are required.'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'

        if error is None:
            db = get_db()
            existing = db.execute(
                'SELECT id FROM users WHERE username = ? OR email = ?',
                (username, email)
            ).fetchone()
            if existing:
                error = 'Username or email already taken.'
            else:
                db.execute(
                    'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                    (username, email, generate_password_hash(password))
                )
                db.commit()
                db.close()
                flash('Registration successful. Please log in.', 'success')
                return redirect(url_for('auth.login'))
            db.close()

        flash(error, 'danger')

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('index'))

    if request.method == 'POST':
        identifier = request.form['identifier'].strip()
        password = request.form['password']

        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ? OR email = ?',
            (identifier, identifier)
        ).fetchone()
        db.close()

        if user is None or not check_password_hash(user['password'], password):
            flash('Invalid username/email or password.', 'danger')
        else:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            flash(f"Welcome back, {user['username']}!", 'success')
            if session['is_admin']:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('profile.dashboard'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
