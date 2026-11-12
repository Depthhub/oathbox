import { useEffect, useState } from "react";
import { api, nsToDate } from "../api.js";
import { Chip, CommitmentCard, ErrorBanner, Hash, Icon } from "../components.jsx";
import { NearMark } from "../near-logo.jsx";
import { confirmSealed, useWallet, WalletGate } from "../wallet.jsx";

export default function Founder({ config, roomId }) {
  const w = useWallet();
  if (!w?.verified) {
    return (
      <div className="page">
        <header className="hero-statement">
          <span className="label">Founder</span>
          <h1 className="display-l">Your rooms are <b>yours</b>.</h1>
          <p className="body-s">Only the NEAR account that sealed a room can manage it here.</p>
        </header>
        <WalletGate />
      </div>
    );
  }
  return roomId ? <FounderRoom config={config} roomId={roomId} /> : <FounderHome />;
}

function RoomTabs({ rooms, current }) {
  return (
    <nav className="room-tabs" aria-label="Your rooms">
      {rooms.map((r) => (
        <a key={r.id} href={`#founder-${r.id}`} aria-current={r.id === current ? "page" : undefined}>{r.id}</a>
      ))}
      <a href="#new"><Icon name="plus" size={16} />New room</a>
    </nav>
  );
}

/* The signed-in founder's rooms. */
function FounderHome() {
  const w = useWallet();
  const [rooms, setRooms] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.rooms().then(setRooms).catch(setError); }, [w?.verified]);

  return (
    <div className="page">
      <header className="hero-statement">
        <span className="label">Founder · <span className="mono">{w.verified}</span></span>
        <h1 className="display-l">
          {rooms === null ? "Your rooms." : rooms.length ? <>You have <b>{rooms.length} {rooms.length === 1 ? "room" : "rooms"}</b>.</> : <>Seal your <b>first room</b>.</>}
        </h1>
        <p className="body-s">
          Each room is sealed on NEAR under your account. Investors ask questions and get answers with receipts. They never see the files.
        </p>
      </header>
      <ErrorBanner error={error} />
      {rooms && rooms.length === 0 ? (
        <a className="card hatched dashed enter" href="#new" style={{ textDecoration: "none" }}>
          <span className="icon-circle"><Icon name="plus" /></span>
          <span className="title-s">Seal a new room</span>
          <span className="body-s">Upload the files investors can ask about, then seal them from your wallet.</span>
        </a>
      ) : null}
      {rooms && rooms.length ? (
        <div className="rows">
          {rooms.map((r, i) => (
            <a className="receipt-row enter" style={{ "--i": Math.min(i, 6), textDecoration: "none", color: "inherit" }}
               href={`#founder-${r.id}`} key={r.id}>
              <div className="date-badge"><Icon name="lock" /></div>
              <div className="lv">
                <span style={{ fontWeight: 500 }} className="mono">{r.id}</span>
                <span className="label">{r.status === "sealed" ? "Sealed on NEAR" : "Uploaded, not sealed yet"}</span>
              </div>
              <div className="row-end">
                {r.status === "sealed" ? <Chip kind="pass">Sealed</Chip> : <Chip kind="warn">Finish sealing</Chip>}
                <span className="icon-btn" aria-hidden="true"><Icon name="arrow" size={18} /></span>
              </div>
            </a>
          ))}
          <a className="btn" href="#new" style={{ alignSelf: "flex-start", marginTop: 8 }}><Icon name="plus" size={18} />New room</a>
        </div>
      ) : null}
    </div>
  );
}

function FounderRoom({ config, roomId }) {
  const w = useWallet();
  const [walletStep, setWalletStep] = useState(null); // null | "sending" | "confirming"
  const [rooms, setRooms] = useState([]);
  const [linkCopied, setLinkCopied] = useState(false);
  const [room, setRoom] = useState(null);
  const [receipts, setReceipts] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const [r, rs] = await Promise.all([api.room(roomId), api.receipts(roomId)]);
      setRoom(r);
      setReceipts(rs);
    } catch (e) {
      setError(e);
    }
  };
  useEffect(() => { load(); }, [roomId, w?.verified]);
  useEffect(() => { api.rooms().then(setRooms).catch(() => {}); }, [w?.verified]);

  /* Finish a seal that was interrupted, or approve this server later. Runs from a click. */
  const finishInWallet = async () => {
    setError(null);
    setWalletStep("sending");
    try {
      await w.send(room.next_transaction);
      setWalletStep("confirming");
      if (room.status === "pending") await confirmSealed(roomId);
      else await new Promise((r) => setTimeout(r, 2500));
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setWalletStep(null);
    }
  };

  const investorLink = `${window.location.origin}${window.location.pathname}#ask-${roomId}`;
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(investorLink);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 1400);
    } catch {
      /* clipboard refused; the link is shown as selectable text */
    }
  };

  const count = receipts ? receipts.length : null;
  const changed = new Set(room?.changed_files || []);

  return (
    <div className="page">
      <header className="hero-statement">
        <RoomTabs rooms={rooms} current={roomId} />
        <span className="label" style={{ marginTop: 12 }}>Founder · <span className="mono">{roomId}</span></span>
        <h1 className="display-l">
          {count === null ? "Your data room." : <>Investors got <b>{count} {count === 1 ? "answer" : "answers"}</b>. They saw no files.</>}
        </h1>
        <p className="body-s">
          The room is sealed on NEAR before anyone asks. Every answer is checked against that seal and leaves a receipt.
        </p>
      </header>

      <div className="tiles">
        <div className="tile enter">
          <div className="tile-top"><span className="tint" style={{ background: "var(--tint-mint)" }}><Icon name="receipt" size={18} /></span><span className="label">Receipts</span></div>
          <span className="headline num">{count ?? "–"}</span>
        </div>
        <div className="tile enter" style={{ "--i": 1 }}>
          <div className="tile-top"><span className="tint" style={{ background: "var(--tint-lavender)" }}><Icon name="file" size={18} /></span><span className="label">Files in the room</span></div>
          <span className="headline num">{room?.local?.file_count ?? "–"}</span>
        </div>
        <div className="tile enter" style={{ "--i": 2 }}>
          <div className="tile-top"><span className="tint" style={{ background: "var(--tint-pink)" }}><NearMark size={16} title="NEAR" /></span><span className="label">Network</span></div>
          <span className="headline">NEAR {config.network}</span>
        </div>
      </div>

      <ErrorBanner error={error} />

      <div className="bento">
        <div className="stack">
          {room && !room.is_owner ? (
            <div className="card card-muted">
              <h2 className="title-s">This room belongs to {room.owner || "someone else"}.</h2>
              <p className="body-s">You're signed in as <span className="mono">{w?.verified}</span>. Only the owner sees its files and can manage it.</p>
            </div>
          ) : null}

          {room?.next_transaction ? (
            <div className="card enter">
              <h2 className="title">{room.status === "pending" ? "Finish sealing this room." : "Let Oathbox record receipts."}</h2>
              <p className="body-s">
                {room.status === "pending"
                  ? "The files are uploaded but not sealed yet. Approve one transaction to seal them under your account and let this server record receipts."
                  : `Investors can't get answers yet: this room hasn't approved the Oathbox server ${config.backend_account}. Approve one transaction to allow it.`}
              </p>
              <div className="row">
                <button className="btn btn-primary" onClick={finishInWallet} disabled={!!walletStep}>
                  {walletStep === "sending" ? <><span className="spinner" aria-hidden="true" /> Waiting for your wallet</>
                    : walletStep === "confirming" ? <><span className="spinner" aria-hidden="true" /> Checking NEAR</>
                      : room.status === "pending" ? "Seal in wallet" : "Approve in wallet"}
                </button>
              </div>
            </div>
          ) : null}

          <section className="section">
            <div className="section-head">
              <h2 className="title-s">Receipts</h2>
              <span className="label">Hashes only. Questions and answers stay with investors.</span>
            </div>
            {receipts && receipts.length === 0 ? (
              <div className="card hatched dashed"><p className="body-s">No receipts yet. They appear here as investors ask.</p></div>
            ) : null}
            <div className="rows">
              {(receipts || []).slice().reverse().map((r, i) => {
                const when = nsToDate(r.created_at);
                return (
                  <div className="receipt-row enter" style={{ "--i": Math.min(i, 6) }} key={r.id}>
                    <div className="date-badge">
                      <span className="n">#{r.id}</span>
                      <span className="d">{when ? when.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : ""}</span>
                    </div>
                    <div className="lv">
                      <span style={{ fontWeight: 500 }}>Answered {when ? when.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : ""}</span>
                      <span className="row" style={{ gap: "4px 14px" }}>
                        <span className="label">Q</span><Hash value={r.question_hash} head={8} tail={4} label="question hash" />
                        <span className="label">A</span><Hash value={r.answer_hash} head={8} tail={4} label="answer hash" />
                      </span>
                    </div>
                    <div className="row-end">
                      {r.attestation_checked_offchain ? <Chip kind="pass">TEE checked</Chip> : <Chip kind="warn">Unchecked</Chip>}
                      <a className="icon-btn" href={`#verify-${r.id}`} aria-label={`Verify receipt ${r.id}`}><Icon name="arrow" size={18} /></a>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="card card-muted" style={{ marginTop: 20 }}>
            <h2 className="title-s">What the model is allowed to say</h2>
            <p className="body-s">
              It follows these rules inside the TEE. A filter then blocks any answer that repeats file content or part of a secret.
            </p>
            <ol className="body-s" style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 8 }}>
              {config.disclosure_rules.map((r) => <li key={r}>{r}</li>)}
            </ol>
          </section>
        </div>

        <aside className="stack">
          <CommitmentCard room={room} />

          {room?.onchain && room.is_owner ? (
            <div className="card enter" style={{ "--i": 1 }}>
              <span className="label">Investor link</span>
              <span className="mono" style={{ overflowWrap: "anywhere", userSelect: "all" }}>{investorLink}</span>
              <div className="row">
                <button type="button" className="btn" onClick={copyLink}>{linkCopied ? "Copied" : "Copy link"}</button>
                <a className="link" href={`#ask-${roomId}`}>Open as an investor ↗</a>
              </div>
            </div>
          ) : null}

          {room?.local?.files ? (
            <div className="card enter" style={{ "--i": 2 }}>
              <div className="section-head">
                <h2 className="title-s">Files</h2>
                <span className="label">Investors never see this list</span>
              </div>
              <div className="dtable">
                {room.local.files.map((f) => (
                  <div className="dt-row" key={f.path}>
                    <span className={`path ${changed.has(f.path) ? "changed" : ""}`}>{f.path}</span>
                    <span className="size">{changed.has(f.path) ? "changed" : `${(f.size / 1024).toFixed(1)} KB`}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
