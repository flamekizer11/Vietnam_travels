#!/usr/bin/env python3
# viz_server.py
# Flask server for serving visualization assets and sample graph data

from flask import Flask, send_from_directory, jsonify
import os
import json

app = Flask(__name__)

# Serve static files from current directory
@app.route('/')
def index():
    return send_from_directory('.', 'neo4j_viz.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# API endpoint for sample graph data
@app.route('/sample_graph')
def sample_graph():
    try:
        with open('data/sample_graph.json', 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "Sample graph not found"}), 404

@app.route('/status')
def status():
    return jsonify({"status": "running", "message": "Visualization server is active"})

if __name__ == '__main__':
    print("Starting visualization server...")
    print("Open http://localhost:5000/neo4j_viz.html?local=true")
    app.run(debug=True, host='0.0.0.0', port=5000)