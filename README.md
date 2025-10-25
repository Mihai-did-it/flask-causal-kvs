# Flask Causal Key-Value Store

A distributed key–value store built with Flask that maintains **causal consistency** across replicas using **vector clocks** and periodic **anti-entropy synchronization**.

## Overview
Each replica stores keys locally and exchanges metadata with other replicas to maintain a consistent causal order.  
Updates are tracked via vector clocks, and background threads handle synchronization and health checks to keep replicas up to date.

The system supports `PUT`, `GET`, and `DELETE` operations on `/kvs/<key>` with causal metadata attached to each request and response.

## Features
- **Causal Consistency:** Ensures operations respect causal dependencies across replicas.
- **Vector Clocks:** Used to track and compare version histories.
- **Anti-Entropy Sync:** Background threads reconcile state between replicas periodically.
- **Automatic Health Checks:** Each replica continuously verifies connectivity with others.
- **Request Forwarding:** Replicas can forward requests to a designated main node if needed.
- **Graceful Error Handling:** Returns descriptive JSON messages for all failure conditions.

## Endpoints

### `PUT /kvs/<key>`
- **Body:** `{ "value": <string>, "causal-metadata": <object|null> }`
- **Creates** new key: returns `201 {"result": "created"}`
- **Replaces** existing key: returns `200 {"result": "replaced"}`
- Errors:
  - Missing value → `400`
  - Key too long → `400`
  - Dependencies not satisfied → `503`

### `GET /kvs/<key>`
- **Returns:** `200 {"result": "found", "value": <string>, "causal-metadata": <object|null>}`
- Missing key → `404 {"error": "Key does not exist"}`

### `DELETE /kvs/<key>`
- Deletes the key if it exists, returns `200 {"result": "deleted"}`
- Missing key → `404 {"error": "Key does not exist"}`

### `GET /kvs/sync`
- Used internally by replicas to exchange store contents and vector clocks.

### `GET /health`
- Returns `"OK"` if the replica is alive.

---

## How It Works
Each replica maintains:
- A local **key-value store**
- A **vector clock** for causal metadata
- A **view** (list of known replicas)

Background threads:
- Perform **health checks** to detect failed nodes.
- Run **anti-entropy** to synchronize state across all reachable replicas.

If a request arrives before its causal dependencies are satisfied, the server responds with a `503` so the client can retry later.

---

## Run Locally
### Requirements
Install dependencies:
```bash
pip install -r requirements.txt