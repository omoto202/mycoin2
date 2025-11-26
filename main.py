from fastapi import FastAPI, Request
from pydantic import BaseModel
import time, hashlib, json, asyncio
import httpx

app = FastAPI()

# -----------------------------------------------------
#   INITIAL STATE（global変数は使わない）
# -----------------------------------------------------
app.state.blockchain = []
app.state.pending_txs = []
app.state.peers = set()


# -----------------------------------------------------
#   BLOCKCHAIN BASE STRUCTURE
# -----------------------------------------------------
def hash_block(block: dict) -> str:
    block_str = json.dumps(block, sort_keys=True).encode()
    return hashlib.sha256(block_str).hexdigest()


def create_genesis_block():
    return {
        "index": 0,
        "timestamp": time.time(),
        "transactions": [],
        "previous_hash": "0",
        "nonce": 0,
        "hash": ""
    }


# 起動時に genesis をセット
@app.on_event("startup")
async def startup_event():
    genesis = create_genesis_block()
    genesis["hash"] = hash_block(genesis)
    app.state.blockchain = [genesis]
    app.state.pending_txs = []
    app.state.peers = set()


# -----------------------------------------------------
#   CHAIN VALIDATION
# -----------------------------------------------------
def chain_is_valid(chain: list) -> bool:
    for i in range(1, len(chain)):
        prev = chain[i-1]
        curr = chain[i]

        if curr["previous_hash"] != prev["hash"]:
            return False

        if hash_block(curr) != curr["hash"]:
            return False

    return True


# -----------------------------------------------------
#   API MODELS
# -----------------------------------------------------
class Transaction(BaseModel):
    sender: str
    receiver: str
    amount: int
    signature: str | None = None


class NewPeer(BaseModel):
    url: str


# -----------------------------------------------------
#   ADD TRANSACTION
# -----------------------------------------------------
@app.post("/add_tx")
async def add_tx(tx: Transaction, request: Request):
    pending = request.app.state.pending_txs
    pending.append(tx.dict())
    return {"success": True}


# -----------------------------------------------------
#   GET CHAIN
# -----------------------------------------------------
@app.get("/chain")
async def get_chain(request: Request):
    return {
        "chain": request.app.state.blockchain,
        "length": len(request.app.state.blockchain)
    }


# -----------------------------------------------------
#   RECEIVE CHAIN FROM OTHER NODE
# -----------------------------------------------------
@app.post("/receive_chain")
async def receive_chain(data: dict, request: Request):
    new_chain = data.get("chain")
    if not new_chain:
        return {"success": False, "error": "no chain"}

    if chain_is_valid(new_chain) and len(new_chain) > len(request.app.state.blockchain):
        request.app.state.blockchain = new_chain
        return {"success": True, "status": "updated"}
    else:
        return {"success": True, "status": "ignored"}


# -----------------------------------------------------
#   BROADCAST CHAIN TO PEERS
# -----------------------------------------------------
async def broadcast_chain(request: Request):
    peers = request.app.state.peers
    chain = request.app.state.blockchain

    async with httpx.AsyncClient(timeout=5) as client:
        for peer in peers:
            try:
                await client.post(f"{peer}/receive_chain", json={"chain": chain})
            except:
                continue


# -----------------------------------------------------
#   MINING
# -----------------------------------------------------
def proof_of_work(block: dict) -> dict:
    block["nonce"] = 0
    while True:
        h = hash_block(block)
        if h.startswith("0000"):
            block["hash"] = h
            return block
        block["nonce"] += 1


@app.post("/mine")
async def mine(request: Request):
    blockchain = request.app.state.blockchain
    pending = request.app.state.pending_txs

    if not pending:
        return {"success": False, "message": "no pending txs"}

    last = blockchain[-1]
    new_block = {
        "index": last["index"] + 1,
        "timestamp": time.time(),
        "transactions": pending.copy(),
        "previous_hash": last["hash"],
        "nonce": 0,
        "hash": ""
    }

    mined = proof_of_work(new_block)

    # ------------- global 無しで更新する部分 -----------------
    # pending をクリア
    request.app.state.pending_txs = []

    # chain を更新
    request.app.state.blockchain.append(mined)

    # broadcast
    await broadcast_chain(request)

    return {"success": True, "block": mined}


# -----------------------------------------------------
#   ADD PEER
# -----------------------------------------------------
@app.post("/add_peer")
async def add_peer(peer: NewPeer, request: Request):
    request.app.state.peers.add(peer.url)
    return {"success": True}
