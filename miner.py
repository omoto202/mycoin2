import threading
import time

class Miner:
    def __init__(self, blockchain, broadcast_fn=None, broadcast_done_fn=None):
        self.blockchain = blockchain
        self._running = False
        self.thread = None
        self.broadcast_fn = broadcast_fn            # 新ブロック通知
        self.broadcast_done_fn = broadcast_done_fn  # マイニング完了通知（オプション）

    def is_mining(self):
        """現在採掘中かどうか UI 判定用"""
        return self._running

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
            # new block broadcast
            if self.broadcast_fn:
                self.broadcast_fn(block)
        finally:
            self._running = False
            # mining done broadcast
            if self.broadcast_done_fn:
                self.broadcast_done_fn()
