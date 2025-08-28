from flask import Flask
import os

app = Flask(__name__)

@app.route('/health')
def health():
    return {"status": "ok"}

@app.route('/')
def home():
    return "Flask is working!"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
