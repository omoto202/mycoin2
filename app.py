import json
import time
import base64
import hashlib
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Simple blockchain structures ---
class Transaction(BaseModel):
    sender: str  # base64-encoded public key (SPKI DER)
    recipient: str
    amount: float
    signature: str  # base64 signature

class Block(BaseModel):
    index: int
    timestamp: float
    previous_hash: str
    nonce: int
    hash: str
    transactions: List[Dict[str, Any]]

# In-memory server state (note: Render may reset this; clients persist locally)
server_chain: List[Dict[str, Any]] = []
pending_txs: List[Dict[str, Any]] = []
WS_CONNECTIONS: List[WebSocket] = []

DIFFICULTY = 3  # adjust for speed; small for demo

# --- Helper crypto ---
def base64_to_bytes(b64: str) -> bytes:
    return base64.b64decode(b64)

def verify_signature(public_spki_b64: str, signature_b64: str, message_bytes: bytes) -> bool:
    try:
        pub_der = base64_to_bytes(public_spki_b64)
        public_key = serialization.load_der_public_key(pub_der)
        sig = base64_to_bytes(signature_b64)
        # ECDSA signature verification with SHA-256
        public_key.verify(sig, message_bytes, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception as e:
        return False

def hash_block_content(index: int, timestamp: float, previous_hash: str, nonce: int, txs: List[Dict]) -> str:
    content = json.dumps({
        "index": index,
        "timestamp": timestamp,
        "previous_hash": previous_hash,
        "nonce": nonce,
        "transactions": txs
    }, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(content.encode()).hexdigest()

# --- Chain management ---
def create_genesis():
    if server_chain:
        return
    genesis = {
        "index": 0,
        "timestamp": time.time(),
        "previous_hash": "0"*64,
        "nonce": 0,
        "transactions": [],
    }
    genesis["hash"] = hash_block_content(genesis["index"], genesis["timestamp"], genesis["previous_hash"], genesis["nonce"], genesis["transactions"])
    server_chain.append(genesis)

create_genesis()

def chain_is_valid(chain: List[Dict[str,Any]]) -> bool:
    # basic validation: hashes link and proof-of-work check
    for i in range(1, len(chain)):
        prev = chain[i-1]
        block = chain[i]
        if block['previous_hash'] != prev['hash']:
            return False
        recalculated = hash_block_content(block['index'], block['timestamp'], block['previous_hash'], block['nonce'], block['transactions'])
        if recalculated != block['hash']:
            return False
        if not block['hash'].startswith('0'*DIFFICULTY):
            return False
    return True

def replace_chain_if_longer(candidate_chain: List[Dict[str,Any]]) -> bool:
    global server_chain
    if len(candidate_chain) > len(server_chain) and chain_is_valid(candidate_chain):
        server_chain = candidate_chain
        return True
    return False

def compute_balances(chain: List[Dict[str,Any]]) -> Dict[str, float]:
    balances = {}
    for block in chain:
        for tx in block.get("transactions", []):
            sender = tx.get("sender")
            recipient = tx.get("recipient")
            amount = float(tx.get("amount", 0))
            if sender != "SYSTEM":
                balances[sender] = balances.get(sender, 0.0) - amount
            balances[recipient] = balances.get(recipient, 0.0) + amount
    return balances

# --- WebSocket broadcast ---
async def broadcast_chain():
    if not WS_CONNECTIONS:
        return
    data = {"type":"chain_update", "chain": server_chain}
    to_remove=[]
    for ws in WS_CONNECTIONS:
        try:
            await ws.send_text(json.dumps(data))
        except:
            to_remove.append(ws)
    for r in to_remove:
        try:
            WS_CONNECTIONS.remove(r)
        except:
            pass

# --- Endpoints ---
@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/chain")
async def get_chain():
    return {"chain": server_chain}

@app.post("/submit_tx")
async def submit_tx(tx: Transaction):
    # verify signature: message = sender|recipient|amount as bytes (same as client)
    message = f"{tx.sender}|{tx.recipient}|{tx.amount}".encode()
    if not verify_signature(tx.sender, tx.signature, message):
        return {"success": False, "error": "invalid signature"}
    # optional: verify balance against server chain + pending
    balances = compute_balances(server_chain)
    # apply pending txs
    for p in pending_txs:
        balances[p['sender']] = balances.get(p['sender'], 0.0) - float(p['amount'])
        balances[p['recipient']] = balances.get(p['recipient'], 0.0) + float(p['amount'])
    sender_balance = balances.get(tx.sender, 0.0)
    if sender_balance < float(tx.amount):
        return {"success": False, "error": "insufficient funds"}
    pending_txs.append(tx.dict())
    return {"success": True, "pending_count": len(pending_txs)}

@app.post("/submit_chain")
async def submit_chain(req: Request):
    body = await req.json()
    candidate = body.get("chain")
    if not candidate:
        return {"success": False, "error": "no chain"}
    if replace_chain_if_longer(candidate):
        # clear pending txs that are included in chain
        # naive approach: remove pending txs that appear in chain
        txs_in_chain = set()
        for b in server_chain:
            for t in b.get("transactions", []):
                txs_in_chain.add(json.dumps(t, sort_keys=True))
        global pending_txs
        pending_txs = [p for p in pending_txs if json.dumps(p, sort_keys=True) not in txs_in_chain]
        await broadcast_chain()
        return {"success": True, "replaced": True}
    return {"success": False, "replaced": False}

@app.post("/mine")
async def mine(req: Request):
    body = await req.json()
    miner_pub = body.get("miner_pub")  # base64 spki
    if not miner_pub:
        return {"success": False, "error": "no miner pub key"}
    # create reward tx (SYSTEM -> miner)
    reward_tx = {"sender": "SYSTEM", "recipient": miner_pub, "amount": 1.0, "signature": ""}
    # take pending txs snapshot
    txs_to_include = pending_txs.copy()
    txs_to_include.append(reward_tx)
    # build new block
    index = server_chain[-1]['index'] + 1
    previous_hash = server_chain[-1]['hash']
    timestamp = time.time()
    nonce = 0
    found = False
    # simple proof-of-work (blocking) - small DIFFICULTY for demo
    while True:
        h = hash_block_content(index, timestamp, previous_hash, nonce, txs_to_include)
        if h.startswith('0'*DIFFICULTY):
            found = True
            break
        nonce += 1
    new_block = {
        "index": index,
        "timestamp": timestamp,
        "previous_hash": previous_hash,
        "nonce": nonce,
        "transactions": txs_to_include,
        "hash": h
    }
    # validate then append
    if chain_is_valid(server_chain + [new_block]):
        server_chain.append(new_block)
        # clear pending txs (those included)
        global pending_txs
        # remove any pending txs that are in txs_to_include (non-SYSTEM)
        included_serials = set(json.dumps(t, sort_keys=True) for t in txs_to_include if t.get("sender")!="SYSTEM")
        pending_txs = [p for p in pending_txs if json.dumps(p, sort_keys=True) not in included_serials]
        # broadcast new chain
        await broadcast_chain()
        return {"success": True, "block": new_block}
    else:
        return {"success": False, "error": "invalid chain after mining"}

# WebSocket endpoint for realtime updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    WS_CONNECTIONS.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()  # we don't expect messages, but keep alive
            # optional: if client sends 'ping' or requests, could respond
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        try:
            WS_CONNECTIONS.remove(websocket)
        except:
            pass
