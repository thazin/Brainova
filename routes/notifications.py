"""Notification helpers and user-facing routes.

Notifications are fanned out at write-time: when an admin publishes a test we
insert one row per non-admin user. This trades a little extra storage for a
trivial per-user read query, which keeps the user dashboard fast as the user
base grows.
"""
from flask import Blueprint, render_template, redirect, url_for, session, flash, abort
from functools import wraps

from database import get_db


notifications_bp = Blueprint('notifications', __name__)


# ---------------------------------------------------------------------------
# Helpers (importable from other blueprints)
# ---------------------------------------------------------------------------

def fanout_notification(db, title, message, test_id=None):
    """Insert one notification row per non-admin user.

    Caller is responsible for committing the transaction. Returns the number of
    recipients so the caller can surface it in a flash message.
    """
    user_ids = [r['id'] for r in db.execute(
        'SELECT id FROM users WHERE is_admin = 0'
    ).fetchall()]

    db.executemany(
        '''INSERT INTO notifications (user_id, test_id, title, message)
           VALUES (?, ?, ?, ?)''',
        [(uid, test_id, title, message) for uid in user_ids]
    )
    return len(user_ids)


def unread_count(user_id):
    """Lightweight count used by the navbar badge on every page."""
    db = get_db()
    n = db.execute(
        'SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0',
        (user_id,)
    ).fetchone()[0]
    db.close()
    return n


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to view notifications.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@notifications_bp.route('/')
@_login_required
def inbox():
    db = get_db()
    rows = db.execute(
        '''SELECT n.*, t.title AS test_title, t.status AS test_status
           FROM notifications n
           LEFT JOIN tests t ON n.test_id = t.id
           WHERE n.user_id = ?
           ORDER BY n.created_at DESC''',
        (session['user_id'],)
    ).fetchall()

    # Mark everything read on view — matches the user expectation that opening
    # the inbox clears the badge. We do this *after* fetching so the page can
    # still highlight rows that were unread on this visit.
    db.execute(
        'UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0',
        (session['user_id'],)
    )
    db.commit()
    db.close()
    return render_template('notifications/inbox.html', notifications=rows)


@notifications_bp.route('/<int:note_id>/read', methods=['POST'])
@_login_required
def mark_read(note_id):
    db = get_db()
    note = db.execute(
        'SELECT user_id FROM notifications WHERE id = ?', (note_id,)
    ).fetchone()
    if not note or note['user_id'] != session['user_id']:
        db.close()
        abort(404)
    db.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (note_id,))
    db.commit()
    db.close()
    return redirect(url_for('notifications.inbox'))


@notifications_bp.route('/<int:note_id>/delete', methods=['POST'])
@_login_required
def delete(note_id):
    db = get_db()
    note = db.execute(
        'SELECT user_id FROM notifications WHERE id = ?', (note_id,)
    ).fetchone()
    if not note or note['user_id'] != session['user_id']:
        db.close()
        abort(404)
    db.execute('DELETE FROM notifications WHERE id = ?', (note_id,))
    db.commit()
    db.close()
    flash('Notification deleted.', 'success')
    return redirect(url_for('notifications.inbox'))
