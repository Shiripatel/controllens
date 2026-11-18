import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api";
import { useAuth } from "../App";

const DEMO = [
  ["Preparer", "shirish@controllens.local"],
  ["Reviewer", "ravi.reviewer@controllens.local"],
  ["Manager", "maya.manager@controllens.local"],
];

export default function Login() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api.post("/auth/login", { email, password });
      auth.set(r.token);
      setUser(r.user);
      nav("/engagements");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="login">
      <div className="login-art">
        <div className="brand big"><span className="logo">◎</span> ControlLens</div>
        <h1>Agentic ITGC testing,<br />with every decision traceable.</h1>
        <ul>
          <li>AI agents draft design, operating-effectiveness and review work</li>
          <li>Every claim is tied to a quote in your evidence, and checked</li>
          <li>People confirm conclusions and sign off — agents never do</li>
        </ul>
      </div>
      <form className="login-card" onSubmit={submit}>
        <h2>Sign in</h2>
        <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} autoFocus autoComplete="username" required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        {err && <div className="errorbox">{err}</div>}
        <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <div className="demo">
          <div className="muted small">Demo accounts (password <code>Demo#12345</code>)</div>
          {DEMO.map(([r, e]) => (
            <button type="button" key={e} className="ghost sm" onClick={() => { setEmail(e); setPassword("Demo#12345"); }}>{r}</button>
          ))}
        </div>
      </form>
    </div>
  );
}
