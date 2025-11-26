from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from blockchain import Blockchain, Transaction
from miner import Miner
import json
import time
import queue

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # app-level blockchain state (keeps memory)
    app.blockchain_state = {
        "blockchain": Blockchain(difficulty=3),
        "miner": None,
        "clients": [],  # list of queues for SSE
    }

    # miner with broadcast function
    def broadcast_block(block):
        # notify all SSE clients with new chain JSON
        payload = json.dumps({"type": "new_block", "chain": app.blockchain_state["blockchain"].to_dict()})
        for q in list(app.blockchain_state["clients"]):
            try:
                q.put(payload, block=False)
            except Exception:
                # remove failing queue
                try:
                    app.blockchain_state["clients"].remove(q)
                except ValueError:
                    pass

    app.blockchain_state["miner"] = Miner(app.blockchain_state["blockchain"], broadcast_fn=broadcast_block)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/generate_key", methods=["POST"])
    def generate_key():
        # create ECDSA keypair and return them hex-encoded
        from ecdsa import SigningKey, NIST256p
        sk = SigningKey.generate(curve=NIST256p)
        vk = sk.get_verifying_key()
        sk_hex = sk.to_string().hex()
        vk_hex = vk.to_string().hex()
        return jsonify({"private_key": sk_hex, "public_key": vk_hex})

    @app.route("/local_sign", methods=["POST"])
    def local_sign():
        # デモ用: クライアントから private key (hex) を受け取り、ECDSA で署名を返す
        data = request.get_json()
        priv_hex = data.get("private_key")
        sender_pub = data.get("sender_pub")
        recipient = data.get("recipient")
        amount = data.get("amount")
        if not all([priv_hex, sender_pub, recipient, amount is not None]):
            return jsonify({"error": "missing"}), 400
        from ecdsa import SigningKey, NIST256p
        try:
            sk = SigningKey.from_string(bytes.fromhex(priv_hex), curve=NIST256p)
            msg = f"{sender_pub}:{recipient}:{amount}"
            sig = sk.sign(msg.encode())
            return jsonify({"signature": sig.hex()})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/submit_tx", methods=["POST"])
    def submit_tx():
        data = request.get_json()
        sender = data.get("sender")
        recipient = data.get("recipient")
        amount = data.get("amount")
        signature = data.get("signature")
        if not all([sender, recipient, amount, signature]):
            return jsonify({"error": "missing field"}), 400
        tx = Transaction(sender_pubkey=sender, recipient_pubkey=recipient, amount=amount, signature=signature)
        # append pending
        app.blockchain_state["blockchain"].add_transaction(tx)
        # broadcast pending change to SSE clients
        payload = json.dumps({"type": "pending_tx", "pending": app.blockchain_state["blockchain"].pending_transactions})
        for q in list(app.blockchain_state["clients"]):
            try:
                q.put(payload, block=False)
            except Exception:
                try:
                    app.blockchain_state["clients"].remove(q)
                except ValueError:
                    pass
        return jsonify({"status": "ok"})

    @app.route("/get_chain", methods=["GET"])
    def get_chain():
        return jsonify({"chain": app.blockchain_state["blockchain"].to_dict(),
                        "pending": app.blockchain_state["blockchain"].pending_transactions})

    @app.route("/get_balance", methods=["GET"])
    def get_balance():
        pubkey = request.args.get("pubkey")
        if not pubkey:
            return jsonify({"error": "missing pubkey"}), 400
        bal = app.blockchain_state["blockchain"].get_balance(pubkey)
        return jsonify({"balance": bal})

    @app.route("/mine", methods=["POST"])
    def mine():
        data = request.get_json()
        miner_address = data.get("miner_address")
        if not miner_address:
            return jsonify({"error": "no miner_address"}), 400
        started = app.blockchain_state["miner"].start_mining_once(miner_address, reward=1)
        if not started:
            return jsonify({"status": "already_mining"}), 409
        return jsonify({"status": "mining_started"})

    @app.route("/sse")
    def sse_stream():
        def gen(client_q):
            try:
                # send initial payload
                init = json.dumps({"type": "init", "chain": app.blockchain_state["blockchain"].to_dict(), "pending": app.blockchain_state["blockchain"].pending_transactions})
                yield f"data: {init}\n\n"
                while True:
                    try:
                        data = client_q.get(timeout=30)  # keep-alive
                        yield f"data: {data}\n\n"
                    except queue.Empty:
                        # send a comment as keepalive
                        yield ": keep-alive\n\n"
            finally:
                # cleanup
                try:
                    app.blockchain_state["clients"].remove(client_q)
                except Exception:
                    pass

        q = queue.Queue()
        app.blockchain_state["clients"].append(q)
        return Response(stream_with_context(gen(q)), mimetype="text/event-stream")

    return app

# For local debug
if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=True)
