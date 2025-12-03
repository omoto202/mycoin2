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

// request server to generate keypair
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

// display chain in requested format
function displayChain(chain) {
  if (!Array.isArray(chain)) {
    document.getElementById("chainView").textContent = "(invalid chain)";
    return;
  }
  const lines = chain.map(b => {
    const txs = Array.isArray(b.transactions) ? b.transactions.map(t => {
      // show only sender -> recipient : amount
      const sender = t.sender || t.sender === undefined ? t.sender : t["sender"];
      const recipient = t.recipient || t.recipient === undefined ? t.recipient : t["recipient"];
      const amount = t.amount || t.amount === undefined ? t.amount : t["amount"];
      return `  ${sender} → ${recipient} : ${amount}`;
    }).join("\n") : "";

    // ensure keys exist (handle different naming if any)
    const idx = b.index ?? b.idx ?? "(no index)";
    const ts = b.timestamp ?? "(no timestamp)";
    const nonce = b.nonce ?? "(no nonce)";
    const hash = b.hash ?? "(no hash)";
    const prev = b.previous_hash ?? b.prev_hash ?? "(no previous_hash)";

    return [
      `Block #${idx}`,
      `Timestamp: ${ts}`,
      `Nonce: ${nonce}`,
      `Hash: ${hash}`,
      `Prev: ${prev}`,
      `Transactions:`,
      `${txs}`,
      `------------------------------`
    ].join("\n");
  });
  document.getElementById("chainView").textContent = lines.join("\n");
}

// refresh chain (use longer chain between server and local)
document.getElementById("refreshChainBtn").addEventListener("click", async () => {
  const res = await fetch("/get_chain");
  const j = await res.json();
  const serverChain = Array.isArray(j.chain) ? j.chain : [];
  const localChain = JSON.parse(localStorage.getItem(KEYS.CHAIN) || "[]");

  const longest = serverChain.length >= localChain.length ? serverChain : localChain;
  localStorage.setItem(KEYS.CHAIN, JSON.stringify(longest));

  displayChain(longest);
});

// clear local stored chain/pending
document.getElementById("clearLocalDataBtn").addEventListener("click", () => {
  localStorage.removeItem(KEYS.PENDING);
  localStorage.removeItem(KEYS.CHAIN);
  alert("ローカルストレージを削除しました。");
});

// mining status + start
const miningStatusEl = document.getElementById("miningStatus");
document.getElementById("startMiningBtn").addEventListener("click", async () => {
  const keys = getKeys();
  if (!keys.public) { alert("公開鍵が必要です（鍵を生成してください）"); return; }
  // set mining UI
  miningStatusEl.textContent = "マイニング中";
  const res = await fetch("/mine", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({miner_address: keys.public})
  });
  const j = await res.json();
  if (j.status === "mining_started") {
    // mining started on server; SSE will notify when finished
  } else if (j.status === "already_mining") {
    alert("既にマイニング中です。");
    miningStatusEl.textContent = "マイニング中";
  } else {
    alert("マイニング開始に失敗しました");
    miningStatusEl.textContent = "";
  }
});

// SSE - receive realtime updates (try SSE, fallback to polling)
function setupSSE() {
  const evtSource = new EventSource("/sse");
  evtSource.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === "init") {
        // merge longests: prefer longer chain
        const serverChain = Array.isArray(d.chain) ? d.chain : [];
        const localChain = JSON.parse(localStorage.getItem(KEYS.CHAIN) || "[]");
        const longest = serverChain.length >= localChain.length ? serverChain : localChain;
        localStorage.setItem(KEYS.CHAIN, JSON.stringify(longest));
        displayChain(longest);
        // clear mining status on init
        miningStatusEl.textContent = "";
      } else if (d.type === "new_block") {
        const serverChain = Array.isArray(d.chain) ? d.chain : [];
        const localChain = JSON.parse(localStorage.getItem(KEYS.CHAIN) || "[]");
        const longest = serverChain.length >= localChain.length ? serverChain : localChain;
        localStorage.setItem(KEYS.CHAIN, JSON.stringify(longest));
        displayChain(longest);
        // show success briefly then clear
        miningStatusEl.textContent = "マイニング成功";
        setTimeout(() => { miningStatusEl.textContent = ""; }, 2000);
      } else if (d.type === "pending_tx") {
        localStorage.setItem(KEYS.PENDING, JSON.stringify(d.pending));
      }
    } catch (err) {
      console.error(err);
    }
  };
  evtSource.onerror = (err) => {
    console.warn("SSE error, falling back to polling", err);
    try { evtSource.close(); } catch (_) {}
    startPolling();
  };
}

let pollInterval = null;
function startPolling() {
  if (pollInterval) return;
  pollInterval = setInterval(async () => {
    const res = await fetch("/get_chain");
    const j = await res.json();
    const serverChain = Array.isArray(j.chain) ? j.chain : [];
    const localChain = JSON.parse(localStorage.getItem(KEYS.CHAIN) || "[]");
    const longest = serverChain.length >= localChain.length ? serverChain : localChain;
    localStorage.setItem(KEYS.CHAIN, JSON.stringify(longest));
    displayChain(longest);
  }, 3000);
}

window.addEventListener("load", () => {
  showKeys();
  setupSSE();
});

