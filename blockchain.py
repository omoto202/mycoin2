import time
import json
import hashlib
from ecdsa import VerifyingKey, SigningKey, NIST256p, BadSignatureError

def hash_block(block):
    block_string = json.dumps(block, sort_keys=True).encode()
    return hashlib.sha256(block_string).hexdigest()

class Transaction:
    def __init__(self, sender_pubkey, recipient_pubkey, amount, signature=None):
        self.sender = sender_pubkey
        self.recipient = recipient_pubkey
        self.amount = amount
        self.signature = signature

    def to_dict(self):
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "signature": self.signature,
        }

class Block:
    def __init__(self, index, previous_hash, transactions, timestamp=None, nonce=0):
        self.index = index
        self.timestamp = timestamp or time.time()
        self.transactions = transactions  # list of dict
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = None

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }

class Blockchain:
    def __init__(self, difficulty=3):
        self.chain = []
        self.pending_transactions = []
        self.difficulty = difficulty
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis = Block(index=0, previous_hash="0", transactions=[], timestamp=time.time(), nonce=0)
        genesis.hash = hash_block(genesis.to_dict())
        self.chain.append(genesis)

    def add_transaction(self, tx: Transaction):
        self.pending_transactions.append(tx.to_dict())

    def last_block(self):
        return self.chain[-1]

    def mine_block(self, miner_address, reward=1):
        # reward transaction
        reward_tx = Transaction(sender_pubkey="SYSTEM", recipient_pubkey=miner_address, amount=reward, signature=None)
        txs = self.pending_transactions + [reward_tx.to_dict()]
        index = len(self.chain)
        previous_hash = self.last_block().hash
        block = Block(index=index, previous_hash=previous_hash, transactions=txs, timestamp=time.time(), nonce=0)

        prefix = "0" * self.difficulty
        while True:
            block_dict = block.to_dict()
            block.hash = hash_block({**block_dict, "nonce": block.nonce})
            if block.hash.startswith(prefix):
                break
            block.nonce += 1

        self.chain.append(block)
        self.pending_transactions = []
        return block

    def validate_signature(self, sender_pubkey_hex, signature_hex, message_str):
        if sender_pubkey_hex == "SYSTEM":
            return True
        try:
            vk = VerifyingKey.from_string(bytes.fromhex(sender_pubkey_hex), curve=NIST256p)
            sig = bytes.fromhex(signature_hex)
            vk.verify(sig, message_str.encode())
            return True
        except (BadSignatureError, Exception):
            return False

    def verify_transaction(self, tx_dict):
        # Check signature & balance
        sender = tx_dict["sender"]
        recipient = tx_dict["recipient"]
        amount = tx_dict["amount"]
        signature = tx_dict.get("signature")
        if sender == "SYSTEM":
            return False
        if not signature:
            return False
        msg = f"{sender}:{recipient}:{amount}"
        if not self.validate_signature(sender, signature, msg):
            return False
        # balance check
        bal = self.get_balance(sender)
        return bal >= amount

    def get_balance(self, pubkey_hex):
        balance = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx["recipient"] == pubkey_hex:
                    balance += tx["amount"]
                if tx["sender"] == pubkey_hex:
                    balance -= tx["amount"]
        # pending txs reduce balance for sender
        for tx in self.pending_transactions:
            if tx["sender"] == pubkey_hex:
                balance -= tx["amount"]
        return balance

    def to_dict(self):
        return [b.to_dict() | {"hash": b.hash} for b in self.chain]
