"""
Yet to implement:

1. View Operation - replica retrieves all the key-value(Page 3) 
When a new replica is added to the system, it broadcasts a PUT-view request so the existing replicas
add the new replica to their view. Afterwards the new replica retrieves all the key-value pairs from an
existing replica and adds them to its own store.



"""

import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# View operations
view = os.getenv("VIEW", "").split(",")
SOCKET_ADDRESS = os.getenv("SOCKET_ADDRESS", "localhost:8090")  # Current replica address


def broadcast_request(method, endpoint, data):
    """Broadcast a request to all other replicas."""
    failed_replicas = []
    for replica in view:
        if replica != SOCKET_ADDRESS:
            try:
                requests.request(method, f"http://{replica}{endpoint}", json=data, timeout=1)
                #app.logger.info(f"Broadcast {method} to {replica}: {response.status_code}")  # debug
            except requests.exceptions.RequestException:
                #app.logger.error(f"Failed to reach {replica}: {e}")  # debug
                failed_replicas.append(replica)

    # Remove failed replicas and broadcast DELETE requests
    for replica in failed_replicas:
        if replica in view:
            view.remove(replica)
            broadcast_request("DELETE", "/view", {"socket-address": replica})

@app.route('/view', methods=['GET'])
def get_view():
    """Retrieve the current view."""
    return jsonify({"view": view}), 200

@app.route('/view', methods=['PUT'])
def add_view():
    """Add a new replica to the view."""
    data = request.get_json()
    address = data['socket-address']

    if address in view:
        return jsonify({"result": "already present"}), 200
    view.append(address)
    broadcast_request("PUT", "/view", {"socket-address": address})

    """
    if address == SOCKET_ADDRESS:
        for replica in view:
            if replica != SOCKET_ADDRESS:
                try:
                    response = requests.get(f"http://{replica}/kvs")
                    if response.status_code == 200:
                        # Assuming response contains key-value pairs
                        for key, value in response.json().items():
                            store[key] = value
                        break
                except requests.exceptions.RequestException:
                    continue
    """

    return jsonify({"result": "added"}), 201

@app.route('/view', methods=['DELETE'])
def remove_view():
    """Remove an existing replica from the view."""
    data = request.get_json()
    address = data['socket-address']

    if address in view:
        view.remove(address)
        broadcast_request("DELETE", "/view", {"socket-address": address})
        return jsonify({"result": "deleted"}), 200
    return jsonify({"error": "View has no such replica"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8090)
