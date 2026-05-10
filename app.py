from flask import Flask, session
from database import init_db
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.profile import profile_bp
from routes.test import test_bp
from routes.notifications import notifications_bp, unread_count

app = Flask('Gemini 2.5 Flash')
app.secret_key = 'AIzaSyDwlW65IwtxBRGUSHywEFMN2FNzF7yZ68Q'

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(profile_bp, url_prefix='/profile')
app.register_blueprint(test_bp, url_prefix='/test')
app.register_blueprint(notifications_bp, url_prefix='/notifications')


@app.context_processor
def inject_notification_count():
    """Make the unread-notification badge available to every template."""
    if 'user_id' in session and not session.get('is_admin'):
        return {'unread_notifications': unread_count(session['user_id'])}
    return {'unread_notifications': 0}


@app.route('/')
def index():
    from flask import render_template, redirect, url_for
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('profile.dashboard'))
    return render_template('index.html')


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
