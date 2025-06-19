import sys
from pathlib import Path
from app import create_app, socketio

sys.path.append(str(Path(__file__).parent))

app = create_app()

if __name__ == "__main__":
    socketio.run(app, debug=True, host="127.0.0.1", port=5000)