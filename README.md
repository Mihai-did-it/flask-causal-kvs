Citations: https://www.geeksforgeeks.org/anti-entropy-in-distributed-systems/, https://www.geeksforgeeks.org/causal-consistency-model-in-system-design/, 

Contributions:
Alan - 

Arya - worked on essentially a little bit of everything. Mainly focused on the key-value-store functionality and causal consistency

Mihai - Worked on a bit of everything, focused on broadcast handling, causal consistency, and debugging the metadata synchronization

Mechanism Description - We looked to implement vector clocks to track causal dependencies

















Mihai debugging version:


"from flask import Flask, request, jsonify
import threading
import requests
import time
import os
import sys
from copy import deepcopy

app = Flask(__name__)

# Global variables
view = set()
store = {}  # Key-value store
vector_clock = {}  # Global vector clock for causal consistency
self_address = None

# Locks for thread safety
view_lock = threading.Lock()
store_lock = threading.Lock()
vector_clock_lock = threading.Lock()

# Constants
HEALTH_CHECK_INTERVAL = 1  # seconds
HEALTH_CHECK_TIMEOUT = 1  # seconds
RETRY_INTERVAL = 1  # seconds
MAX_RETRIES = 3  # Maximum number of retries for broadcast
ANTI_ENTROPY_INTERVAL = 1  # seconds

# Initialize self_address and view from environment variables
self_address = os.environ.get('SOCKET_ADDRESS')
view_string = os.environ.get('VIEW')
if not self_address or not view_string:
    print("Environment variables SOCKET_ADDRESS and VIEW must be set")
    sys.exit(1)

self_address = self_address.strip()
view = set(view_string.strip().split(','))
view.add(self_address)  # Ensure self_address is in the view

# Initialize vector clock
def initialize_vector_clock():
    global vector_clock
    with vector_clock_lock:
        for replica in view:
            vector_clock[replica] = 0

initialize_vector_clock()

# Health Check Thread
def health_check():
    while True:
        time.sleep(HEALTH_CHECK_INTERVAL)
        with view_lock:
            replicas = list(view)
        for replica in replicas:
            if replica != self_address:
                threading.Thread(target=health_check_replica, args=(replica,)).start()

def health_check_replica(replica):
    try:
        response = requests.get(f"http://{replica}/health", timeout=HEALTH_CHECK_TIMEOUT)
        if response.status_code != 200:
            raise Exception("Unhealthy response")
    except Exception:
        # Replica is down, but we keep it in the view
        pass

# Key-Value Store Operations
@app.route('/kvs/<key>', methods=['PUT', 'GET', 'DELETE'])
def handle_kvs(key):
    data = request.get_json() if request.data else {}
    incoming_metadata = data.get('causal-metadata')

    # Handle null or 'null' causal-metadata
    if incoming_metadata is None or incoming_metadata == 'null':
        incoming_metadata = {}
    elif not isinstance(incoming_metadata, dict):
        incoming_metadata = {}
    else:
        incoming_metadata = {k: v for k, v in incoming_metadata.items() if k != 'null' and k is not None}

    # Check causal dependencies
    if not causal_metadata_satisfied(incoming_metadata):
        return jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503

    if request.method == 'PUT':
        value = data.get('value')
        if value is None:
            return jsonify({"error": "PUT request does not specify a value"}), 400
        if len(key) > 50:
            return jsonify({"error": "Key is too long"}), 400

        with store_lock:
            existing_value = store.get(key)
            store[key] = value

        increment_clock()

        # Prepare response causal-metadata
        with vector_clock_lock:
            response_metadata = deepcopy(vector_clock)
            response_metadata = {k: v for k, v in response_metadata.items() if v > 0}
            if not response_metadata:
                response_metadata = None

        # Broadcast the update to other replicas
        threading.Thread(target=broadcast_key_update, args=(key, value, vector_clock.copy())).start()

        result = "created" if existing_value is None else "replaced"
        return jsonify({"result": result, "causal-metadata": response_metadata}), 201 if result == "created" else 200

    elif request.method == 'GET':
        with store_lock:
            if key not in store:
                return jsonify({"error": "Key does not exist"}), 404
            value = store[key]

        # Prepare response causal-metadata
        with vector_clock_lock:
            response_metadata = deepcopy(vector_clock)
            response_metadata = {k: v for k, v in response_metadata.items() if v > 0}
            if not response_metadata:
                response_metadata = None

        return jsonify({"result": "found", "value": value, "causal-metadata": response_metadata}), 200

    elif request.method == 'DELETE':
        with store_lock:
            if key not in store:
                return jsonify({"error": "Key does not exist"}), 404
            del store[key]

        increment_clock()

        # Prepare response causal-metadata
        with vector_clock_lock:
            response_metadata = deepcopy(vector_clock)
            response_metadata = {k: v for k, v in response_metadata.items() if v > 0}
            if not response_metadata:
                response_metadata = None

        # Broadcast the deletion to other replicas
        threading.Thread(target=broadcast_key_update, args=(key, None, vector_clock.copy())).start()

        return jsonify({"result": "deleted", "causal-metadata": response_metadata}), 200

def broadcast_key_update(key, value, metadata):
    with view_lock:
        replicas = list(view)
    for replica in replicas:
        if replica != self_address:
            threading.Thread(target=send_update_to_replica, args=(replica, key, value, metadata)).start()

def send_update_to_replica(replica, key, value, metadata):
    url = f"http://{replica}/replica/kvs/{key}"
    payload = {"causal-metadata": metadata}
    if value is not None:
        payload["value"] = value
    method = 'PUT' if value is not None else 'DELETE'

    retries = 0
    while retries < MAX_RETRIES:
        try:
            if method == 'PUT':
                response = requests.put(url, json=payload, timeout=HEALTH_CHECK_TIMEOUT)
            else:
                response = requests.delete(url, json=payload, timeout=HEALTH_CHECK_TIMEOUT)
            if response.status_code in [200, 201]:
                break
            else:
                retries += 1
                time.sleep(RETRY_INTERVAL)
        except Exception:
            retries += 1
            time.sleep(RETRY_INTERVAL)

def causal_metadata_satisfied(incoming_metadata):
    with vector_clock_lock:
        for node, count in incoming_metadata.items():
            if node is None or node == 'null':
                continue
            local_count = vector_clock.get(node, 0)
            if local_count < count:
                return False
    return True

def increment_clock():
    with vector_clock_lock:
        vector_clock[self_address] = vector_clock.get(self_address, 0) + 1

# Replica endpoints for receiving updates
@app.route('/replica/kvs/<key>', methods=['PUT', 'DELETE'])
def replica_kvs_operations(key):
    data = request.get_json() if request.data else {}
    incoming_metadata = data.get("causal-metadata", None)

    # Handle null or 'null' causal-metadata
    if incoming_metadata is None or incoming_metadata == 'null':
        incoming_metadata = {}
    elif not isinstance(incoming_metadata, dict):
        incoming_metadata = {}
    else:
        incoming_metadata = {k: v for k, v in incoming_metadata.items() if k != 'null' and k is not None}

    # Check causal dependencies
    if not causal_metadata_satisfied(incoming_metadata):
        # Merge the incoming vector clock
        with vector_clock_lock:
            vector_clock.update(merge_clocks(vector_clock, incoming_metadata))
        return jsonify({"error": "Causal dependencies not satisfied; try again later"}), 503

    if request.method == 'PUT':
        value = data.get("value")
        if value is None:
            return jsonify({"error": "PUT request does not specify a value"}), 400

        with store_lock:
            store[key] = value

        with vector_clock_lock:
            vector_clock.update(merge_clocks(vector_clock, incoming_metadata))

        return jsonify({"result": "updated"}), 200

    elif request.method == 'DELETE':
        with store_lock:
            if key in store:
                del store[key]

        with vector_clock_lock:
            vector_clock.update(merge_clocks(vector_clock, incoming_metadata))

        return jsonify({"result": "deleted"}), 200

def merge_clocks(clock1, clock2):
    merged = clock1.copy()
    for node, timestamp in clock2.items():
        if node is None or node == 'null':
            continue
        merged[node] = max(merged.get(node, 0), timestamp)
    return merged

# Anti-Entropy Thread
def anti_entropy():
    while True:
        time.sleep(ANTI_ENTROPY_INTERVAL)
        with view_lock:
            replicas = list(view)
        for replica in replicas:
            if replica != self_address:
                threading.Thread(target=synchronize_with_replica, args=(replica,)).start()

def synchronize_with_replica(replica):
    try:
        response = requests.get(f"http://{replica}/kvs/sync", timeout=HEALTH_CHECK_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            remote_store = data.get('store', {})
            remote_vector_clock = data.get('vector_clock', {})
            merge_stores(remote_store, remote_vector_clock)
    except Exception:
        pass  # Replica is down or unreachable

def merge_stores(remote_store, remote_vector_clock):
    with store_lock, vector_clock_lock:
        for key, value in remote_store.items():
            if key not in store:
                store[key] = value
            else:
                # Compare vector clocks
                if vector_clock_compare(remote_vector_clock, vector_clock) == 'gt':
                    store[key] = value
        vector_clock.update(merge_clocks(vector_clock, remote_vector_clock))

def vector_clock_compare(vc1, vc2):
    """Compare two vector clocks.

    Returns 'eq' if vc1 == vc2,
            'gt' if vc1 > vc2,
            'lt' if vc1 < vc2,
            'conflict' if vc1 and vc2 are concurrent.
    """
    vc1_bigger = False
    vc2_bigger = False
    keys = set(vc1.keys()).union(vc2.keys())
    for k in keys:
        v1 = vc1.get(k, 0)
        v2 = vc2.get(k, 0)
        if v1 > v2:
            vc1_bigger = True
        elif v2 > v1:
            vc2_bigger = True
    if vc1_bigger and not vc2_bigger:
        return 'gt'
    elif vc2_bigger and not vc1_bigger:
        return 'lt'
    elif not vc1_bigger and not vc2_bigger:
        return 'eq'
    else:
        return 'conflict'

# Health Endpoint
@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

# Synchronization Endpoint
@app.route('/kvs/sync', methods=['GET'])
def sync_store():
    with store_lock, vector_clock_lock:
        data = {"store": deepcopy(store), "vector_clock": deepcopy(vector_clock)}
    return jsonify(data), 200

if __name__ == '__main__':
    threading.Thread(target=health_check, daemon=True).start()
    threading.Thread(target=anti_entropy, daemon=True).start()
    app.run(host='0.0.0.0', port=8090)"