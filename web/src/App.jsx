import { useEffect, useState } from "react";
import { api } from "./api.js";
import { BrandGlyph, ErrorBanner } from "./components.jsx";
import Founder from "./pages/Founder.jsx";
import Investor from "./pages/Investor.jsx";
import NewRoom from "./pages/NewRoom.jsx";
import Verify from "./pages/Verify.jsx";
import { BuiltOnNear, NearMark } from "./near-logo.jsx";
import { WalletButton, WalletProvider } from "./wallet.jsx";

/* Hash routes: #ask, #ask-<room>, #founder, #founder-<room>, #new, #verify, #verify-12 */
function parseRoute() {
  const h = window.location.hash.replace(/^#/, "");
  const v = h.match(/^verify-(\d+)$/);
  if (v) return { page: "verify", receiptId: Number(v[1]) };
  const r = h.match(/^(ask|founder)-([a-z0-9_-]{1,64})$/);
  if (r) return { page: r[1], roomId: r[2] };
  if (h === "founder" || h === "verify" || h === "new") return { page: h };
  return { page: "ask" };
}

export default function App() {
  const [route, setRoute] = useState(parseRoute);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const on = () => { setRoute(parseRoute()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => { api.config().then(setConfig).catch(setError); }, []);

  const roomId = route.roomId || null;
  const link = (page, label) => {
    const href = page === "verify" || !roomId ? `#${page}` : `#${page}-${roomId}`;
    const current = route.page === page || (page === "founder" && route.page === "new");
    return <a href={href} aria-current={current ? "page" : undefined}>{label}</a>;
  };

  const shell = (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#ask" aria-label="Oathbox home" title="Oathbox"><BrandGlyph /></a>
          <nav className="nav" aria-label="Main">
            {link("founder", "Founder")}
            {link("ask", "Investor")}
            {link("verify", "Verify")}
          </nav>
          {config ? (
            <a className="meta-pill" href={config.contract_url} target="_blank" rel="noreferrer">
              <NearMark size={14} />
              <b>NEAR {config.network}</b>
              <span className="mono">{config.contract_id}</span>
            </a>
          ) : null}
          {config ? <WalletButton /> : null}
        </div>
      </header>

      {error ? <div className="page"><ErrorBanner error={error} /></div> : null}
      {config ? (
        route.page === "founder" ? <Founder key={roomId || "home"} config={config} roomId={roomId} />
          : route.page === "new" ? <NewRoom config={config} />
            : route.page === "verify" ? <Verify config={config} receiptId={route.receiptId} />
              : <Investor key={roomId || "home"} config={config} roomId={roomId} />
      ) : null}

      {config ? (
        <div className="page" style={{ paddingBlock: "0 40px" }}>
          <div className="footer">
            <BuiltOnNear />
            <span>Model <span className="mono">{config.model_id}</span> on NEAR AI Cloud, inside Intel TDX and NVIDIA confidential computing</span>
          </div>
        </div>
      ) : null}
    </>
  );
  return config ? <WalletProvider config={config}>{shell}</WalletProvider> : shell;
}
