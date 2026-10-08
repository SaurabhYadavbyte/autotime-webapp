import os
from flask import jsonify

def add_debug_route(app, db):
    @app.route('/debug_db')
    def debug_db():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'success', 'message': 'Database connection works!'})
        except Exception as e:
            import traceback
            return jsonify({'status': 'error', 'message': str(e), 'traceback': traceback.format_exc()})
