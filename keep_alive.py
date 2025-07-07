# keep_alive.py
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is alive"

def start_server():
    thread = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8090})
    thread.daemon = True
    thread.start()
