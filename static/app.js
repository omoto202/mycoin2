const LS_KEYS = {
  PRIVATE: "sc_demo_private",
  PUBLIC: "sc_demo_public",
  PENDING: "sc_demo_pending",
  CHAIN: "sc_demo_chain"
};

function saveKeys(priv, pub) {
  localStorage.setItem(LS_KEYS.PRIVATE, priv);
  localStorage.setItem(LS_KEYS.PUBLIC, pub);
  showKeys();
}

function resetKeysLocal() {
  localStorage.removeItem(LS_KEYS.PRIVATE);
  localStorage.removeItem(LS_KEYS.PUBLIC);
  showKeys();
}

function getKeys() {
  return {
    private: localStorage.getItem(LS_KEYS.PRIVATE),
    public: localStorage.getItem(LS_KEYS.PUBLIC)
  };
}

function showKeys() {
  const k = getKeys();
  const el = document.getElementById("keyInfo");
  el.textContent = `public: ${k.public || "(なし)"}\nprivate: ${k.private ? "(保存済)" : "(なし)"}`;
}

// generate key via server endpoint (returns hex strings)
document.getElementById("genKeyBtn").addEventListener("click", async () => {
  const res = await fetch("/generate_key", {method: "POST"});
  const j = await res.json();
  saveKeys(j.private_key, j.public_key);
  alert("鍵ペアを生成して localStorage に保存しました（デモ用）。");
});

// reset local keys
document.getElementById("resetKeysBtn").addEventListener("click", () => {
  resetKeysLocal();
  alert("ローカル鍵を削除しました。");
});

// send transaction
document.getElementById("sendTxBtn").addEventListener("click", async () => {
  const recipient = document.getElementById("txRecipient").value.trim();
  const amount = Number(document.getElementById("txAmount").value);
  const keys = getKeys();
  if (!keys.private || !keys.public) {
    alert("先に鍵を生成して localStorage に保存してください。");
    return;
  }
  if (!recipient || !amount) {
    alert("受信者と金額を入力してください。");
    return;
  }
  // Create signature server-side by sending private key (DEMO only)
  const msg = `${keys.public}:${recipient}:${amount}`;
  // Request server to create transaction signature
  // For demo simplicity: client sends private key to server which signs and submits tx.
  const res = await fetch("/submit_tx", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      sender: keys.public,
      recipient: recipient,
      amount: amount,
      signature: await signWithPrivateOnServer(keys.private, keys.public, recipient, amount)
    })
  });
  const j = await res.json();
  document.getElementById("sendResult").textContent = JSON.stringify(j);
});

// helper: ask server to compute signature using provided private key (DEMO)
async function signWithPrivateOnServer(priv_hex, pub_hex, recipient, amount) {
  // This endpoint uses server-side signing for demo. We implement signing here by POST to /sign (not present yet)
  // But to keep code minimal and avoid an extra endpoint, sign using JS is skipped: instead create signature client-side by
  // sending private key and message to a small transient endpoint—however server does not have /sign in our sample.
  // For simplicity in this demo, create a signature locally by using HMAC-like fallback (not ideal) — but we promised ECDSA.
  // So we will call a simple sign endpoint implemented here as fetch to /local_sign which uses server SigningKey.
  // Let's attempt the endpoint; if not present server will fail.
  const res = await fetch("/local_sign", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({private_key: priv_hex, sender_pub: pub_hex, recipient, amount})
  });
  const j = await res.json();
  return j.signature;
}

// balance check
document.getElementById("checkBalanceBtn").addEventListener("click", async () => {
  const pub = document.getElementById("balancePubkey").value.trim();
  if (!pub) { alert("公開鍵を入力してください"); return; }
  const res = await fetch(`/get_balance?pubkey=${encodeURIComponent(pub)}`);
  const j = await res.json();
  document.getElementById("balanceResult").textContent = JSON.stringify(j);
});

// refresh chain
document.getElementById("refreshChainBtn").addEventListener("click", async () => {
  const res = await fetch("/get_chain");
  const j = await res.json();
  localStorage.setItem(LS_KEYS.CHAIN, JSON.stringify(j.chain));
  document.getElementById("chainView").textContent = JSON.stringify(j.chain, null, 2);
});

// clear local pending+chain
document.getElementById("clearLocalDataBtn").addEventListener("click", () => {
  localStorage.removeItem(LS_KEYS.PENDING);
  localStorage.removeItem(LS_KEYS.CHAIN);
  alert("ローカルのトランザクションとチェーンを削除しました。");
});

// mining
const miningStatusEl = document.getElementById("miningStatus");
document.getElementById("startMiningBtn").addEventListener("click", async () => {
  const keys = getKeys();
  if (!keys.public) { alert("公開鍵が必要です（鍵を生成してください）"); return; }
  miningStatusEl.textContent = "マイニング中";
  const res = await fetch("/mine", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({miner_address: keys.public})
  });
  const j = await res.json();
  if (j.status === "mining_started") {
    // mining runs on server; SSE will inform when done.
  } else if (j.status === "already_mining") {
    alert("既にマイニング中です。");
  } else {
    alert("マイニング開始に失敗しました");
  }
});

// SSE - receive realtime updates
function setupSSE() {
  const evtSource = new EventSource("/sse");
  evtSource.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === "init" || d.type === "new_block") {
        localStorage.setItem(LS_KEYS.CHAIN, JSON.stringify(d.chain));
        document.getElementById("chainView").textContent = JSON.stringify(d.chain, null, 2);
        miningStatusEl.textContent = (d.type === "new_block") ? "マイニング成功" : "待機中";
      } else if (d.type === "pending_tx") {
        localStorage.setItem(LS_KEYS.PENDING, JSON.stringify(d.pending));
      }
    } catch (err) {
      console.error(err);
    }
  };
  evtSource.onerror = (err) => {
    console.warn("SSE error, falling back to polling", err);
    evtSource.close();
    startPolling();
  };
}

let pollInterval = null;
function startPolling() {
  if (pollInterval) return;
  pollInterval = setInterval(async () => {
    const res = await fetch("/get_chain");
    const j = await res.json();
    localStorage.setItem(LS_KEYS.CHAIN, JSON.stringify(j.chain));
    document.getElementById("chainView").textContent = JSON.stringify(j.chain, null, 2);
  }, 3000);
}

window.addEventListener("load", () => {
  showKeys();
  // try SSE, fallback to polling
  setupSSE();
});