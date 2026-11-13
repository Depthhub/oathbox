/* Founder wallet: NEAR Wallet Selector (MyNearWallet, Meteor) + NEP-413 sign-in.

   Connecting a wallet only tells the page an account name. To prove it to the
   server, the founder signs a one-time message (no transaction, no fee); the
   server checks the signature and that the key controls the account on NEAR.

   Wallet popups must open straight from a click, so each wallet action is its
   own button: Connect, then Confirm it's you, then Seal. */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { actionCreators, setupWalletSelector } from "@near-wallet-selector/core";
import { setupModal } from "@near-wallet-selector/modal-ui";
import { setupMyNearWallet } from "@near-wallet-selector/my-near-wallet";
import { setupMeteorWallet } from "@near-wallet-selector/meteor-wallet";
import "@near-wallet-selector/modal-ui/styles.css";
import { api, getToken, setToken } from "./api.js";

const WalletContext = createContext(null);

export function WalletProvider({ config, children }) {
  const selectorRef = useRef(null);
  const modalRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [accountId, setAccountId] = useState(null);   // connected in the wallet
  const [verified, setVerified] = useState(null);     // proven to the server
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // Restore a server session from an earlier visit.
  useEffect(() => {
    if (!getToken()) return;
    api.me().then((r) => {
      if (r.account_id) setVerified(r.account_id);
      else setToken(null);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    let sub;
    let cancelled = false;
    setupWalletSelector({
      network: config.network,
      modules: [setupMyNearWallet(), setupMeteorWallet()],
    }).then((selector) => {
      if (cancelled) return;
      selectorRef.current = selector;
      modalRef.current = setupModal(selector, {
        theme: "auto",
        description: "Connect the NEAR account that will own your data rooms.",
      });
      const sync = (state) => {
        const active = state.accounts.find((a) => a.active) || state.accounts[0];
        setAccountId(active ? active.accountId : null);
      };
      sync(selector.store.getState());
      sub = selector.store.observable.subscribe(sync);
      setReady(true);
    }).catch((e) => setError(e));
    return () => { cancelled = true; sub?.unsubscribe(); };
  }, [config.network]);

  const connect = useCallback(() => {
    setError(null);
    modalRef.current?.show();
  }, []);

  const wallet = useCallback(async () => {
    const selector = selectorRef.current;
    if (!selector?.isSignedIn()) throw new Error("Connect your wallet first.");
    return selector.wallet();
  }, []);

  /* Sign the server's challenge. Call directly from a click handler. */
  const verify = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const w = await wallet();
      if (!w.signMessage) throw new Error("This wallet can't sign messages. Try MyNearWallet or Meteor.");
      const ch = await api.challenge();
      const callbackUrl = window.location.href;
      const nonce = Buffer.from(ch.nonce, "base64");
      const signed = await w.signMessage({ message: ch.message, recipient: ch.recipient, nonce, callbackUrl });
      if (!signed?.signature) throw new Error("The wallet didn't return a signature.");
      const res = await api.verifyWallet({
        account_id: signed.accountId, public_key: signed.publicKey, signature: signed.signature,
        nonce: ch.nonce, callback_url: callbackUrl,
      });
      setToken(res.token);
      setVerified(res.account_id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, [wallet]);

  /* Send the transaction the server prepared: one transaction, one or more function calls. */
  const send = useCallback(async ({ receiver_id, calls }) => {
    const w = await wallet();
    return w.signAndSendTransaction({
      signerId: accountId || undefined,
      receiverId: receiver_id,
      actions: calls.map((c) => actionCreators.functionCall(c.method, c.args, BigInt(c.gas), BigInt(c.deposit))),
    });
  }, [wallet, accountId]);

  const disconnect = useCallback(async () => {
    setToken(null);
    setVerified(null);
    try {
      const selector = selectorRef.current;
      if (selector?.isSignedIn()) await (await selector.wallet()).signOut();
    } catch {
      /* already signed out */
    }
  }, []);

  // A session for a different account than the connected wallet is stale.
  useEffect(() => {
    if (verified && accountId && verified !== accountId) {
      setToken(null);
      setVerified(null);
    }
  }, [accountId, verified]);

  const value = { ready, accountId, verified, busy, error, connect, verify, send, disconnect, setError };
  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

export function useWallet() {
  return useContext(WalletContext);
}

const short = (a) => (a && a.length > 22 ? `${a.slice(0, 10)}…${a.slice(-8)}` : a);

/* Header control: Connect wallet → Confirm it's you → account pill. */
export function WalletButton() {
  const w = useWallet();
  if (!w) return null;
  if (w.verified) {
    return (
      <span className="wallet-pill">
        <span className="live-dot" aria-hidden="true" />
        <span className="mono" title={w.verified}>{short(w.verified)}</span>
        <button type="button" className="copy" onClick={w.disconnect}>Sign out</button>
      </span>
    );
  }
  if (w.accountId) {
    return (
      <button type="button" className="btn btn-small btn-action" onClick={w.verify} disabled={w.busy}>
        {w.busy ? "Check your wallet…" : `Confirm it's ${short(w.accountId)}`}
      </button>
    );
  }
  return (
    <button type="button" className="btn btn-small btn-action" onClick={w.connect} disabled={!w.ready}>
      Connect wallet
    </button>
  );
}

/* Shown in place of founder-only content until the wallet is connected and confirmed. */
export function WalletGate({ title = "Connect the wallet that owns your rooms.", children }) {
  const w = useWallet();
  if (w?.verified) return children;
  const step = w?.accountId ? 2 : 1;
  return (
    <div className="card enter">
      <h2 className="title">{title}</h2>
      <p className="body-s">
        Your rooms are owned on NEAR by your own account, not by Oathbox. Connecting proves which account is yours.
        Confirming signs a one-time message: no transaction and no fee.
      </p>
      <ol className="steps">
        <li className={step > 1 ? "done" : "current"}>
          <span className="step-n">1</span>
          <span>Connect a NEAR wallet {w?.accountId ? <span className="mono">({short(w.accountId)})</span> : null}</span>
        </li>
        <li className={step === 2 ? "current" : ""}>
          <span className="step-n">2</span>
          <span>Confirm it's you</span>
        </li>
      </ol>
      <div className="row">
        {step === 1 ? (
          <button type="button" className="btn btn-primary" onClick={w?.connect} disabled={!w?.ready}>Connect wallet</button>
        ) : (
          <>
            <button type="button" className="btn btn-primary" onClick={w.verify} disabled={w.busy}>
              {w.busy ? "Check your wallet…" : "Confirm it's you"}
            </button>
            <button type="button" className="link" onClick={w.disconnect}>Use another wallet</button>
          </>
        )}
      </div>
      {w?.error ? <p className="body-s" style={{ color: "var(--danger)" }}>{String(w.error.message || w.error)}</p> : null}
      <p className="label">Testnet wallets: MyNearWallet or Meteor. Your account must hold a little testnet NEAR to seal rooms.</p>
    </div>
  );
}

/* After the wallet sends a seal, NEAR needs a moment; retry the server's check. */
export async function confirmSealed(roomId, tries = 8) {
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      return await api.confirm(roomId);
    } catch (e) {
      last = e;
      if (e.status !== 409) throw e;
      await new Promise((r) => setTimeout(r, 2500));
    }
  }
  throw last;
}
