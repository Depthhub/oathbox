import { useEffect, useState } from "react";
import { api, bundleFor, nsToDate } from "../api.js";
import { badgeKind, BadgeChip, CheckGroups, ErrorBanner, Hash, Icon, TickRing } from "../components.jsx";

const HEADLINE = {
  verified: <>This answer is <b>sworn</b>.</>,
  verified_with_warnings: <>Verified, <b>with warnings</b>.</>,
  attestation_fetched: <>Not <b>fully checked</b>.</>,
  failed: <>Do <b>not rely</b> on this.</>,
};

export default function Verify({ receiptId: initialId }) {
  const [receiptId, setReceiptId] = useState(initialId ?? "");
  const [bundle, setBundle] = useState(null);
  const [bundleSource, setBundleSource] = useState(null);
  const [useBundle, setUseBundle] = useState(true);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [over, setOver] = useState(false);

  const run = async (id, b) => {
    if (id === "" || id === null || Number.isNaN(Number(id))) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.verify(Number(id), b));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    setReceiptId(initialId ?? "");
    if (initialId === null || initialId === undefined) return;
    const saved = bundleFor(initialId);
    setBundle(saved);
    setBundleSource(saved ? "saved" : null);
    setUseBundle(true);
    run(initialId, saved);
  }, [initialId]);

  const readFile = async (file) => {
    try {
      const data = JSON.parse(await file.text());
      if (data.format !== "oathbox-receipt-bundle/1") throw new Error("That file isn't an Oathbox receipt.");
      setBundle(data);
      setBundleSource(file.name);
      setUseBundle(true);
      setReceiptId(String(data.receipt_id));
      run(data.receipt_id, data);
    } catch (e) {
      setError(e);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    run(receiptId, useBundle ? bundle : null);
  };

  const r = result?.receipt;
  const kind = result ? badgeKind(result.badge) : null;
  const when = r ? nsToDate(r.created_at) : null;
  const applicable = result ? result.checks.filter((c) => c.status !== "na") : [];
  const passed = applicable.filter((c) => c.status === "pass").length;
  const failed = applicable.filter((c) => c.status === "fail").length;
  const heroClass = kind === "pass" ? "lime" : kind === "warn" ? "" : "plain";

  return (
    <div className="page">
      <header className="hero-statement">
        <span className="label">Verify</span>
        <h1 className="display-l">Check any receipt. <b>Trust nothing.</b></h1>
        <p className="body-s">
          The receipt number is enough to check the hardware, the model and the seal. Add the investor's saved copy
          to also prove the question and answer.
        </p>
      </header>

      <form className="card enter" onSubmit={submit}>
        <div className="row" style={{ alignItems: "stretch" }}>
          <label className="field" htmlFor="receipt-id" style={{ width: 200 }}>
            <span className="label">Receipt number</span>
            <input id="receipt-id" type="number" min="0" value={receiptId}
                   onChange={(e) => { setReceiptId(e.target.value); setBundle(null); setBundleSource(null); }} />
          </label>
          <button type="submit" className="btn btn-primary" style={{ alignSelf: "center" }} disabled={busy || receiptId === ""}>
            Verify
          </button>
          {busy ? (
            <span className="working" role="status" style={{ alignSelf: "center" }}>
              <span className="spinner" aria-hidden="true" /> Re-checking the Intel and NVIDIA evidence
            </span>
          ) : null}
        </div>
        <div className={`drop dashed ${over ? "over" : ""}`}
             onDragOver={(e) => { e.preventDefault(); setOver(true); }}
             onDragLeave={() => setOver(false)}
             onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) readFile(f); }}>
          {bundle ? (
            <label className="toggle-tile" htmlFor="use-bundle" style={{ flex: "1 1 280px" }}>
              <span style={{ fontSize: 15 }}>
                Include my copy of receipt #{bundle.receipt_id}
                <span className="label"> {bundleSource === "saved" ? "saved in this browser" : bundleSource}</span>
              </span>
              <input id="use-bundle" type="checkbox" checked={useBundle} onChange={(e) => setUseBundle(e.target.checked)} />
              <span className="track track-ink" aria-hidden="true" />
            </label>
          ) : (
            <>
              <span className="icon-circle" style={{ background: "var(--surface-muted)" }}><Icon name="plus" /></span>
              <span style={{ flex: "1 1 220px" }}>Drop a downloaded receipt here to check the question and answer too.</span>
            </>
          )}
          <label className="btn" htmlFor="bundle-file">Choose file</label>
          <input id="bundle-file" type="file" accept="application/json,.json" hidden
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f); e.target.value = ""; }} />
        </div>
      </form>

      <ErrorBanner error={error} />

      {result ? (
        <div className="bento">
          <div className="stack">
            <div className={`hero-card ${heroClass} enter`}>
              <div className="corners">
                <span className="icon-circle"><Icon name="shield" /></span>
                <BadgeChip badge={result.badge} />
              </div>
              <div className="corners-bottom">
                <div className="lv" style={{ flex: "1 1 260px" }}>
                  <span className="label">Receipt #{r.id}</span>
                  <span className="display-m" style={{ fontVariantNumeric: "normal" }}>{HEADLINE[result.badge] || result.badge}</span>
                  <span className={kind === "fail" ? "" : "label"} style={kind === "fail" ? { color: "var(--danger)" } : undefined}>
                    {result.badge === "verified"
                      ? "The attested model answered inside a genuine TEE, over the room sealed on NEAR."
                      : result.badge === "failed"
                        ? `${failed} ${failed === 1 ? "check" : "checks"} failed.`
                        : "Some checks couldn't be completed."}
                  </span>
                </div>
                <TickRing passed={passed} failed={failed} total={applicable.length} />
              </div>
            </div>
            <CheckGroups checks={result.checks} />
          </div>

          <aside className="stack">
            <div className="card enter" style={{ "--i": 1 }}>
              <h2 className="title-s">On NEAR</h2>
              <dl className="meta-list">
                <div><dt>Data room</dt><dd className="mono">{r.dataroom_id}</dd></div>
                <div><dt>Root</dt><dd><Hash value={r.dataroom_root} label="root" /></dd></div>
                <div><dt>Model</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{r.model_id}</dd></div>
                <div><dt>Question</dt><dd><Hash value={r.question_hash} label="question hash" /></dd></div>
                <div><dt>Answer</dt><dd><Hash value={r.answer_hash} label="answer hash" /></dd></div>
                <div><dt>Request</dt><dd><Hash value={r.request_hash} label="request hash" /></dd></div>
                <div><dt>Response</dt><dd><Hash value={r.response_hash} label="response hash" /></dd></div>
                <div><dt>Nonce</dt><dd><Hash value={r.nonce} label="nonce" /></dd></div>
                <div><dt>Recorded</dt><dd className="num">{when ? when.toLocaleString() : "?"}</dd></div>
                <div><dt>By</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{r.recorded_by}</dd></div>
              </dl>
              <div className="row">
                <a className="link link-ink" href={result.links.attestation} target="_blank" rel="noreferrer">Attestation report ↗</a>
                <a className="link" href={result.links.contract} target="_blank" rel="noreferrer">Contract ↗</a>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
