import { useState } from "react";

/* Outline icons per Kujua iconography: 1.5px stroke, round caps and joins. */
const PATHS = {
  lock: "M7 11V8a5 5 0 0 1 10 0v3M6 11h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1z",
  file: "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4zM14 3v4h4",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z",
  arrow: "M7 17 17 7M8 7h9v9",
  check: "m5 12.5 4.5 4.5L19 7.5",
  x: "M7 7l10 10M17 7 7 17",
  bang: "M12 7v6M12 17h.01",
  plus: "M12 5v14M5 12h14",
  shield: "M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6l-7-3zM9 12l2 2 4-4",
};

export function Icon({ name, size = 20, stroke = 1.5 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

export function BrandGlyph() {
  return <span className="brand-glyph" aria-hidden="true" />;
}

export function Hash({ value, head = 10, tail = 6, full = false, label }) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className="label">none</span>;
  const shown = full || value.length <= head + tail + 1 ? value : `${value.slice(0, head)}…${value.slice(-tail)}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard refused; the full value is in the tooltip */
    }
  };
  return (
    <span className="hash" title={value}>
      <span className="hash-text">{shown}</span>
      <button type="button" className="copy" onClick={copy} aria-label={`Copy ${label || "value"}`}>
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}

export function Chip({ kind, children }) {
  return <span className={`chip chip-${kind}`}>{children}</span>;
}

const BADGES = {
  verified: ["pass", "Verified"],
  verified_with_warnings: ["warn", "Verified with warnings"],
  attestation_fetched: ["warn", "Not fully checked"],
  failed: ["fail", "Failed"],
};

export function BadgeChip({ badge }) {
  const [kind, text] = BADGES[badge] || ["na", badge];
  return <Chip kind={kind}>{text}</Chip>;
}

export function badgeKind(badge) {
  return (BADGES[badge] || ["na"])[0];
}

/* Kujua tickRing: 60 radial ticks; the passed share is ink, failures are danger,
   the rest stay faint. Centre shows passed / applicable checks. */
export function TickRing({ passed, failed, total }) {
  const N = 60;
  const passTicks = total ? Math.round((passed / total) * N) : 0;
  const failTicks = total ? Math.round((failed / total) * N) : 0;
  const ticks = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * 2 * Math.PI - Math.PI / 2;
    const r1 = 82, r2 = i % 5 === 0 ? 96 : 93;
    const lit = i < passTicks + failTicks;
    const color = i < passTicks ? "var(--on-pastel)" : lit ? "var(--danger)" : "var(--on-pastel)";
    ticks.push(
      <line key={i} x1={100 + r1 * Math.cos(a)} y1={100 + r1 * Math.sin(a)}
            x2={100 + r2 * Math.cos(a)} y2={100 + r2 * Math.sin(a)}
            stroke={color} strokeOpacity={lit ? 1 : 0.18} strokeWidth="2.5" strokeLinecap="round" />,
    );
  }
  return (
    <svg className="tick-ring" viewBox="0 0 200 200" role="img" aria-label={`${passed} of ${total} checks passed`}>
      {ticks}
      <text x="100" y="104" textAnchor="middle" fontSize="40" fontWeight="300" fill="var(--on-pastel)"
            style={{ letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums" }}>
        {passed}/{total}
      </text>
      <text x="100" y="128" textAnchor="middle" fontSize="12" fill="var(--on-pastel)" opacity="0.62">checks passed</text>
    </svg>
  );
}

const GROUPS = [
  ["On NEAR", ["root_committed", "attestation_available"]],
  ["TEE attestation", ["nonce_echo", "signer_format", "tdx_quote", "tdx_body", "tdx_not_debug", "signer_bound",
    "nonce_bound", "compose_measured", "event_log", "gpu_nonce", "gpu_nras", "signer_in_report"]],
  ["Signature", ["sig_kind", "sig_covers_exchange", "sig_valid", "sig_signer_attested"]],
  ["Your copy of the answer", ["bundle", "response_hash", "answer_in_response", "answer_hash", "question_hash"]],
  ["Founder-side", ["request_hash"]],
];
const DOT_ICON = { pass: "check", fail: "x", warn: "bang", error: "bang", skip: "bang" };

export function CheckGroups({ checks }) {
  const byId = new Map(checks.map((c) => [c.id, c]));
  const used = new Set();
  const groups = GROUPS.map(([title, ids]) => {
    const items = ids.map((id) => byId.get(id)).filter(Boolean);
    items.forEach((c) => used.add(c.id));
    return [title, items];
  });
  const rest = checks.filter((c) => !used.has(c.id));
  if (rest.length) groups.push(["Other", rest]);
  return groups.filter(([, items]) => items.length).map(([title, items], gi) => {
    const applicable = items.filter((c) => c.status !== "na");
    return (
      <section className="card enter" style={{ "--i": gi + 1 }} key={title}>
        <div className="section-head">
          <h3 className="title-s">{title}</h3>
          <span className="label num">
            {applicable.length ? `${applicable.filter((c) => c.status === "pass").length} of ${applicable.length} passed` : "Needs your copy"}
          </span>
        </div>
        <ul className="checklist">
          {items.map((c) => (
            <li key={c.id} className={`check ${c.status === "na" ? "is-na" : ""}`}>
              <span className={`check-dot ${c.status}`} aria-label={c.status}>
                {DOT_ICON[c.status] ? <Icon name={DOT_ICON[c.status]} size={14} stroke={2.2} /> : null}
              </span>
              <span>
                <span className="check-label">{c.label}</span>
                {c.detail ? <div className="check-detail">{c.detail}</div> : null}
              </span>
            </li>
          ))}
        </ul>
      </section>
    );
  });
}

export function ErrorBanner({ error }) {
  if (!error) return null;
  return (
    <div className="banner banner-fail" role="alert">
      <span className="title-s">That didn't work.</span>
      <span>{String(error.message || error)}</span>
    </div>
  );
}

/* The room's commitment as the page's one butter hero card (Kujua heroStatCard). */
export function CommitmentCard({ room }) {
  if (!room) {
    return <div className="hero-card hatched plain" aria-busy="true"><span className="label">Reading the room from NEAR…</span></div>;
  }
  const onchain = room.onchain;
  const ok = onchain && room.matches_chain;
  return (
    <div className="hero-card enter">
      <div className="corners">
        <span className="icon-circle"><Icon name="lock" /></span>
        {onchain ? (ok ? <Chip kind="pass">Matches NEAR</Chip> : <Chip kind="fail">Changed since commit</Chip>)
          : <Chip kind="todo">Not committed</Chip>}
      </div>
      <div className="corners-bottom">
        <div className="lv" style={{ maxWidth: "100%" }}>
          <span className="label">{onchain ? "On-chain root" : "Room"}</span>
          <span className="headline">
            {!onchain ? "Not sealed yet." : ok ? <>Sealed on <b>NEAR</b>.</> : <>Files <b>changed</b>.</>}
          </span>
          {onchain ? <Hash value={onchain.root_hash} label="on-chain root" /> : null}
        </div>
        <div className="lv" style={{ textAlign: "right" }}>
          <span className="display-xl">{onchain ? onchain.file_count : room.local?.file_count ?? "–"}</span>
          <span className="label">files committed</span>
        </div>
      </div>
    </div>
  );
}
