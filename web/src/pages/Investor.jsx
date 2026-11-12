import { useEffect, useRef, useState } from "react";
import { api, downloadBundle, loadExchanges, saveExchanges } from "../api.js";
import { BadgeChip, Chip, CommitmentCard, ErrorBanner, Icon } from "../components.jsx";

export default function Investor({ roomId }) {
  return roomId ? <InvestorRoom roomId={roomId} /> : <InvestorHome />;
}

/* No room in the link: ask for the link the founder shared. */
function InvestorHome() {
  const [value, setValue] = useState("");
  const id = (value.trim().match(/#ask-([a-z0-9_-]{1,64})\s*$/) || [])[1] || value.trim().toLowerCase();
  const valid = /^[a-z0-9_-]{2,64}$/.test(id);
  return (
    <div className="page">
      <header className="hero-statement">
        <span className="label">Investor</span>
        <h1 className="display-l">Ask the room. <b>Never see the files.</b></h1>
        <p className="body-s">
          Open the link the founder sent you. Your question and their files go to a model running inside a trusted
          execution environment. You get the answer and a receipt on NEAR.
        </p>
      </header>
      <form className="card enter" style={{ maxWidth: 640 }}
            onSubmit={(e) => { e.preventDefault(); if (valid) window.location.hash = `ask-${id}`; }}>
        <label className="field" htmlFor="room-link">
          <span className="label">Room link or name</span>
          <input id="room-link" type="text" autoComplete="off" placeholder="Paste the link the founder shared"
                 value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <div className="row">
          <button type="submit" className="btn btn-primary" disabled={!valid}>Open room</button>
          <a className="link" href="#founder">I'm a founder ↗</a>
        </div>
      </form>
    </div>
  );
}

function InvestorRoom({ roomId }) {
  const [room, setRoom] = useState(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [refusal, setRefusal] = useState(null);
  const [exchanges, setExchanges] = useState(() => loadExchanges().filter((e) => e.roomId === roomId));
  const inputRef = useRef(null);

  const refreshRoom = () => api.room(roomId).then(setRoom).catch(setError);
  useEffect(() => { refreshRoom(); }, [roomId]);

  const remember = (entry) => {
    const all = [entry, ...loadExchanges()];
    saveExchanges(all);
    setExchanges(all.filter((e) => e.roomId === roomId));
  };

  const submit = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 3 || busy) return;
    setBusy(true);
    setError(null);
    setRefusal(null);
    try {
      const res = await api.ask(roomId, q);
      if (res.status === "room_changed" || res.status === "server_not_approved") {
        setRefusal(res);
      } else if (res.status === "withheld") {
        remember({ roomId, question: q, withheld: true, answer: res.answer, reason: res.reason, badge: res.badge, at: Date.now() });
        setQuestion("");
      } else {
        remember({
          roomId, question: q, answer: res.answer, receiptId: res.receipt_id, txUrl: res.tx_url,
          badge: res.badge, bundle: res.bundle, at: Date.now(),
        });
        setQuestion("");
      }
      refreshRoom();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="hero-statement">
        <span className="label">Investor · <span className="mono">{roomId}</span></span>
        <h1 className="display-l">Ask the room. <b>Never see the files.</b></h1>
        <p className="body-s">
          Your question and the founder's files go to a model running inside a trusted execution environment.
          You get the answer and a receipt on NEAR.
        </p>
      </header>

      <div className="bento">
        <div className="stack">
          <form className="card enter" onSubmit={submit}>
            <label className="field" htmlFor="question">
              <span className="label">Your question</span>
              <textarea
                id="question"
                ref={inputRef}
                rows={2}
                maxLength={500}
                placeholder="Ask about revenue, code or ownership"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e); }}
                disabled={busy}
              />
            </label>
            <div className="row">
              {busy ? (
                <span className="working" role="status">
                  <span className="spinner" aria-hidden="true" />
                  Checking the TEE, asking, and recording your receipt. About 15 seconds.
                </span>
              ) : (
                <span className="label">Ctrl + Enter to ask</span>
              )}
              <span className="spacer" />
              <button type="submit" className="btn btn-primary" disabled={busy || question.trim().length < 3}>
                Ask the room
              </button>
            </div>
          </form>

          {refusal?.status === "server_not_approved" ? (
            <div className="banner banner-fail" role="alert">
              <span className="title-s">This room isn't open for questions yet.</span>
              <span>The founder still has to approve this Oathbox server in their wallet. Nothing was asked and nothing was recorded.</span>
            </div>
          ) : refusal ? (
            <div className="banner banner-fail" role="alert">
              <span className="title-s">The files changed after they were sealed.</span>
              <span>
                Oathbox refused to answer. Nothing went to the model and nothing was recorded.
                {refusal.changed_files?.length ? ` Changed: ${refusal.changed_files.join(", ")}.` : ""}
              </span>
            </div>
          ) : null}
          <ErrorBanner error={error} />

          <section className="section" aria-label="Your answers" style={{ marginTop: 20 }}>
            <div className="section-head">
              <h2 className="title-s">Your answers</h2>
              <span className="label">Receipt copies stay in this browser</span>
            </div>
            {exchanges.length === 0 ? (
              <div className="card hatched dashed">
                <span className="icon-circle"><Icon name="plus" /></span>
                <p className="body-s">
                  No questions yet. Ask about anything in the founder's room. Each answer comes with a receipt.
                </p>
              </div>
            ) : (
              <div className="stack">
                {exchanges.map((x, i) => (
                  <article className={`card answer enter ${x.withheld ? "withheld" : ""}`} style={{ "--i": Math.min(i, 6) }} key={`${x.at}-${i}`}>
                    <span className="tag">Question</span>
                    <p className="answer-q">{x.question}</p>
                    <p className="answer-a">{x.answer}</p>
                    <div className="answer-foot">
                      {x.withheld ? (
                        <>
                          <Chip kind="warn">Withheld</Chip>
                          <span className="body-s">{x.reason}. No receipt was recorded.</span>
                        </>
                      ) : (
                        <>
                          <BadgeChip badge={x.badge} />
                          <a className="link link-ink" href={`#verify-${x.receiptId}`}>Receipt #{x.receiptId} ↗</a>
                          <a className="link" href={x.txUrl} target="_blank" rel="noreferrer">Transaction ↗</a>
                          <span className="spacer" />
                          <button type="button" className="link" onClick={() => downloadBundle(x.bundle)}>
                            Download receipt
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>

        <aside className="stack">
          <CommitmentCard room={room} />
          <div className="card enter" style={{ "--i": 1 }}>
            <span className="label">What a receipt proves</span>
            <p className="body-s">
              Which model answered, that it ran inside genuine Intel TDX and NVIDIA hardware, and that the files
              matched the sealed root.
            </p>
            <p className="body-s">
              It does not prove the answer is right, or that the founder put every relevant file in the room.
            </p>
            {room ? <a className="link" href={room.contract_url} target="_blank" rel="noreferrer">See the contract on NearBlocks ↗</a> : null}
          </div>
        </aside>
      </div>
    </div>
  );
}
