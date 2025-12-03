const KEYS = {
  PRIVATE: "private",
  PUBLIC: "public",
  PENDING: "pending",
  CHAIN: "chain"
};

function saveKeys(priv, pub) {
  localStorage.setItem(KEYS.PRIVATE, priv);
  localStorage.setItem(KEYS.PUBLIC, pub);
  showKeys();
}

function resetKeysLocal() {
  localStorage.removeItem(KEYS.PRIVATE);
  localStorage.removeItem(KEYS.PUBLIC);
  showKeys();
}

function getKeys() {
  return {
    private: localStorage.getItem(KEYS.PRIVATE),
    public: localStorage.getItem(KEYS.PUBLIC)
  };
}

function showKeys() {
  const k = getKeys();
  const el = document.getElementById("keyInfo");
  el.textContent = `public: ${k.public || "(なし)"}\nprivate: ${k.private ? "(保存済)" : "(なし)"}`;
}

document.getElementById("genKeyBtn").addEventListener("click", async () => {
  const res = await fetch("/generate_key", {method: "POST"});
  const j = await res.json();
  saveKeys(j.private_key, j.public_key);
  alert("鍵ペアを生成しました。");
});

document.getElementById("resetKeysBtn").addEventListener("click", () => {
  resetKeysLocal();
  alert("鍵ペアを削除しました。");
});

document.getElementById("sendTxBtn").addEventListener("click", async () => {
  const recipient = document.getElementById("txRecipient").value.trim();
  const amount = Number(document.getElementById("txAmount").value);
  const keys = getKeys();
  if (!keys.private || !keys.public) {
    alert("先に鍵を生成してください。");
    return;
  }
  if (!recipient || !amount) {
    alert("受信者と金額を入力してください。");
    return;
  }
  const msg = `${keys.public}:${recipient}:${amount}`;
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

async function signWithPrivateOnServer(priv_hex, pub_hex, recipient, amount) {
  const res = await fetch("/local_sign", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({private_key: priv_hex, sender_pub: pub_hex, recipient, amount})
  });
  const j = await res.json();
  return j.signature;
}

document.getElementById("checkBalanceBtn").addEventListener("click", async () => {
  const pub = document.getElementById("balancePubkey").value.trim();
  if (!pub) { alert("公開鍵を入力してください"); return; }
  const res = await fetch(`/get_balance?pubkey=${encodeURIComponent(pub)}`);
  const j = await res.json();
  document.getElementById("balanceResult").textContent = JSON.stringify(j);
});

document.getElementById("refreshChainBtn").addEventListener("click", async () => {
  const res = await fetch("/get_chain");
  const j = await res.json();
  localStorage.setItem(KEYS.CHAIN, JSON.stringify(j.chain));
  document.getElementById("chainView").textContent = JSON.stringify(j.chain, null, 2);
});

document.getElementById("clearLocalDataBtn").addEventListener("click", () => {
  localStorage.removeItem(KEYS.PENDING);
  localStorage.removeItem(KEYS.CHAIN);
  alert("ローカルのトランザクションとチェーンを削除しました。");
});

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
        localStorage.setItem(KEYS.CHAIN, JSON.stringify(d.chain));
        document.getElementById("chainView").textContent = JSON.stringify(d.chain, null, 2);
        miningStatusEl.textContent = (d.type === "new_block") ? "マイニング成功" : "待機中";
      } else if (d.type === "pending_tx") {
        localStorage.setItem(KEYS.PENDING, JSON.stringify(d.pending));
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
    localStorage.setItem(KEYS.CHAIN, JSON.stringify(j.chain));
    document.getElementById("chainView").textContent = JSON.stringify(j.chain, null, 2);
  }, 3000);
}

window.addEventListener("load", () => {
  showKeys();
  // try SSE, fallback to polling
  setupSSE();
});
