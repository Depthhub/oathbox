import { useRef, useState } from "react";
import { api } from "../api.js";
import { ErrorBanner, Icon } from "../components.jsx";
import { confirmSealed, useWallet, WalletGate } from "../wallet.jsx";

const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+/, "").slice(0, 40);
const isHidden = (path) => path.split("/").some((p) => p.startsWith(".")) || /(^|\/)(Thumbs\.db|desktop\.ini)$/i.test(path);
const kb = (n) => `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
const near = (yocto) => (Number(BigInt(yocto) / 10n ** 18n) / 1e6).toString();

async function isText(file) {
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
    return true;
  } catch {
    return false;
  }
}

export default function NewRoom({ config }) {
  const w = useWallet();
  const [name, setName] = useState("");
  const [files, setFiles] = useState([]); // {path, file, size, text}
  const [skipped, setSkipped] = useState(0);
  const [staged, setStaged] = useState(null); // server's reply: files stored, wallet transaction ready
  const [phase, setPhase] = useState("edit"); // edit | uploading | staged | sealing | confirming
  const [error, setError] = useState(null);
  const [over, setOver] = useState(false);
  const filesRef = useRef(null);
  const folderRef = useRef(null);

  const limit = config.max_upload_bytes;
  const maxFiles = config.max_upload_files;
  const total = files.reduce((s, f) => s + f.size, 0);
  const id = slugify(name).replace(/-+$/, "");
  const tooBig = total > limit;
  const tooMany = files.length > maxFiles;
  const unreadable = files.filter((f) => !f.text).length;
  const busy = phase === "uploading" || phase === "sealing" || phase === "confirming";
  const canUpload = id.length >= 2 && files.length > 0 && !tooBig && !tooMany && !busy;

  const invalidate = () => { setStaged(null); setPhase("edit"); };

  const add = async (list, fromFolder) => {
    setError(null);
    invalidate();
    const incoming = [];
    let hidden = 0;
    for (const file of list) {
      let path = fromFolder && file.webkitRelativePath ? file.webkitRelativePath.split("/").slice(1).join("/") : file.name;
      path = path.replace(/\\/g, "/");
      if (!path || isHidden(path)) { hidden += 1; continue; }
      incoming.push({ path, file, size: file.size, text: await isText(file) });
    }
    if (fromFolder && !name && list[0]?.webkitRelativePath) setName(slugify(list[0].webkitRelativePath.split("/")[0]));
    setSkipped((s) => s + hidden);
    setFiles((prev) => {
      const byPath = new Map(prev.map((f) => [f.path, f]));
      incoming.forEach((f) => byPath.set(f.path, f));
      return [...byPath.values()].sort((a, b) => (a.path < b.path ? -1 : 1));
    });
  };

  const remove = (path) => { invalidate(); setFiles((prev) => prev.filter((f) => f.path !== path)); };

  /* Step 1: store the files on this server. Nothing is sealed yet. */
  const upload = async (e) => {
    e.preventDefault();
    if (!canUpload) return;
    setPhase("uploading");
    setError(null);
    try {
      const form = new FormData();
      form.append("room_id", id);
      files.forEach((f) => form.append("files", f.file, f.path));
      setStaged(await api.upload(form));
      setPhase("staged");
    } catch (err) {
      setError(err);
      setPhase("edit");
    }
  };

  /* Step 2: the founder's own wallet seals the room and approves this server, in one transaction. */
  const seal = async () => {
    setPhase("sealing");
    setError(null);
    try {
      await w.send(staged.transaction);
      setPhase("confirming");
      await confirmSealed(staged.room_id);
      window.location.hash = `founder-${staged.room_id}`;
    } catch (err) {
      setError(err);
      setPhase("staged");
    }
  };

  const pct = Math.min(100, (total / limit) * 100);
  const deposit = staged ? staged.transaction.calls.reduce((s, c) => s + BigInt(c.deposit), 0n) : 0n;

  return (
    <div className="page">
      <header className="hero-statement">
        <span className="label">New room</span>
        <h1 className="display-l">Seal a room. <b>Share answers, not files.</b></h1>
        <p className="body-s">
          Pick the files investors can ask about. Your wallet writes their fingerprint to NEAR under your own account.
          After that, every answer is checked against exactly these files.
        </p>
      </header>

      {!w?.verified ? <WalletGate title="Connect your wallet to seal a room." /> : (
        <form className="bento" onSubmit={upload}>
          <div className="stack">
            <div className="card enter">
              <label className="field" htmlFor="room-name">
                <span className="label">Room name</span>
                <input id="room-name" type="text" autoComplete="off" placeholder="acme-seed-round"
                       value={name} onChange={(e) => { invalidate(); setName(e.target.value); }} disabled={busy} />
              </label>
              <span className="label">
                {id.length >= 2 ? <>Investors will use the link <span className="mono">#ask-{id}</span></> : "Lowercase letters, numbers and dashes."}
              </span>

              <div className={`drop dashed ${over ? "over" : ""}`}
                   onDragOver={(e) => { e.preventDefault(); setOver(true); }}
                   onDragLeave={() => setOver(false)}
                   onDrop={(e) => { e.preventDefault(); setOver(false); add(Array.from(e.dataTransfer.files || []), false); }}>
                <span className="icon-circle" style={{ background: "var(--surface-muted)" }}><Icon name="plus" /></span>
                <span style={{ flex: "1 1 200px" }}>Drop files here, or choose them.</span>
                <button type="button" className="btn" onClick={() => filesRef.current?.click()} disabled={busy}>Choose files</button>
                <button type="button" className="btn" onClick={() => folderRef.current?.click()} disabled={busy}>Choose a folder</button>
                <input ref={filesRef} id="pick-files" type="file" multiple hidden
                       onChange={(e) => { add(Array.from(e.target.files || []), false); e.target.value = ""; }} />
                <input ref={folderRef} id="pick-folder" type="file" multiple hidden webkitdirectory=""
                       onChange={(e) => { add(Array.from(e.target.files || []), true); e.target.value = ""; }} />
              </div>
            </div>

            {files.length ? (
              <div className="card enter" style={{ "--i": 1 }}>
                <div className="section-head">
                  <h2 className="title-s">{files.length} {files.length === 1 ? "file" : "files"}</h2>
                  <button type="button" className="link" onClick={() => { invalidate(); setFiles([]); setSkipped(0); }} disabled={busy}>Clear all</button>
                </div>
                <div className="dtable">
                  {files.map((f) => (
                    <div className="dt-row" key={f.path}>
                      <span className="path">{f.path}</span>
                      <span className="row" style={{ gap: 12, flexWrap: "nowrap" }}>
                        {f.text ? null : <span className="tag">Model can't read</span>}
                        <span className="size">{kb(f.size)}</span>
                        <button type="button" className="copy" onClick={() => remove(f.path)} aria-label={`Remove ${f.path}`} disabled={busy}>Remove</button>
                      </span>
                    </div>
                  ))}
                </div>
                {skipped ? <span className="label">Skipped {skipped} hidden {skipped === 1 ? "file" : "files"} like .DS_Store.</span> : null}
              </div>
            ) : null}

            <ErrorBanner error={error} />
          </div>

          <aside className="stack">
            <div className="hero-card enter">
              <div className="corners">
                <span className="icon-circle"><Icon name="lock" /></span>
                <span className="label num">{kb(total)} of {Math.round(limit / 1000)} KB</span>
              </div>
              <div className="lv">
                <span className="display-xl">{files.length}</span>
                <span className="label">{files.length === 1 ? "file to seal" : "files to seal"}</span>
              </div>
              <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={limit} aria-valuenow={total} aria-label="Room size">
                <span style={{ width: `${pct}%`, background: tooBig ? "var(--danger)" : "var(--on-pastel)" }} />
              </div>
            </div>

            <div className="card enter" style={{ "--i": 1 }}>
              <ol className="steps">
                <li className={staged ? "done" : "current"}><span className="step-n">1</span><span>Upload the files</span></li>
                <li className={staged ? "current" : ""}><span className="step-n">2</span><span>Seal in your wallet</span></li>
              </ol>
              {tooBig ? <p className="body-s" style={{ color: "var(--danger)" }}>The room is over the size limit. Remove some files.</p> : null}
              {tooMany ? <p className="body-s" style={{ color: "var(--danger)" }}>That's more than {maxFiles} files. Remove some.</p> : null}
              {unreadable && !staged ? (
                <p className="body-s">
                  {unreadable} {unreadable === 1 ? "file isn't" : "files aren't"} plain text. {unreadable === 1 ? "It is" : "They are"} sealed,
                  but the model can't read {unreadable === 1 ? "it" : "them"}. Export PDFs and spreadsheets as text or CSV.
                </p>
              ) : null}

              {!staged ? (
                <>
                  <p className="body-s">Uploading stores the files on this Oathbox server. Nothing is sealed until your wallet approves.</p>
                  <button type="submit" className="btn btn-primary" disabled={!canUpload}>
                    {phase === "uploading" ? <><span className="spinner" aria-hidden="true" /> Uploading</> : "Upload files"}
                  </button>
                </>
              ) : (
                <>
                  <p className="body-s">
                    Your wallet will ask you to approve one transaction from <span className="mono">{w.verified}</span> that
                    seals <span className="mono">{staged.room_id}</span> and lets this Oathbox server record receipts for it.
                  </p>
                  <dl className="meta-list">
                    <div><dt>Fingerprint</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{staged.root_hash.slice(0, 16)}…</dd></div>
                    <div><dt>Deposit</dt><dd>Up to {near(deposit.toString())} NEAR; the unused part comes back</dd></div>
                    <div><dt>Server</dt><dd className="mono" style={{ overflowWrap: "anywhere" }}>{config.backend_account}</dd></div>
                  </dl>
                  <p className="body-s">Sealing is permanent. To change a file later, seal a new room.</p>
                  <button type="button" className="btn btn-primary" onClick={seal} disabled={busy}>
                    {phase === "sealing" ? <><span className="spinner" aria-hidden="true" /> Waiting for your wallet</>
                      : phase === "confirming" ? <><span className="spinner" aria-hidden="true" /> Checking NEAR</>
                        : "Seal in wallet"}
                  </button>
                </>
              )}
            </div>
          </aside>
        </form>
      )}
    </div>
  );
}
