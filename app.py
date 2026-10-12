"""WSGI entrypoint. Run locally with `python server.py` or deploy via `gunicorn app:app`."""
from server import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
