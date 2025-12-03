import threading
import time

class Miner:
    def __init__(self, blockchain, broadcast_fn=None):
        self.blockchain = blockchain
        self._running = False
        self.thread = None
        self.broadcast_fn = broadcast_fn

    def start_mining_once(self, miner_address, reward=1):
        # run mining in background thread to avoid blocking request
        if self.thread and self.thread.is_alive():
            return False  # already mining
        self.thread = threading.Thread(target=self._mine, args=(miner_address, reward), daemon=True)
        self.thread.start()
        return True

    def _mine(self, miner_address, reward):
        self._running = True
        try:
            block = self.blockchain.mine_block(miner_address, reward)
            if self.broadcast_fn:
                self.broadcast_fn(block)
        finally:
            self._running = False
