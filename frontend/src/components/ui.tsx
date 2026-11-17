import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { label } from "../api";

// ---------- toasts
type Toast = { id: number; kind: "ok" | "err"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), kind === "err" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts">
        {items.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/** Run an async action with error toast + busy flag. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      if (ok) toast("ok", ok);
      return r;
    } catch (e: any) {
      toast("err", e.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return { busy, run };
}

/** Load data; returns [data, reload, error]. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): [T | undefined, () => void, string | null] {
  const [data, setData] = useState<T>();
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    fn().then((d) => live && (setData(d), setErr(null))).catch((e) => live && setErr(e.message));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return [data, () => setTick((t) => t + 1), err];
}

// ---------- small components
const TONE: Record<string, string> = {
  effective: "good", implemented: "good", operating_effectively: "good", adequate: "good", yes: "good",
  pass: "good", operating_reviewed: "good", design_reviewed: "info", closed: "muted", remediated: "good",
  succeeded: "good", not_effective: "bad", not_implemented: "bad", not_operating_effectively: "bad",
  inadequate: "bad", no: "bad", fail: "bad", failed: "bad", high: "bad", open: "warn",
  insufficient_evidence: "warn", unable_to_assess: "warn", medium: "warn", running: "info", queued: "info",
  design_in_progress: "info", operating_in_progress: "info", design_prepared: "info", operating_prepared: "info",
  low: "muted", not_started: "muted", addressed: "info", accepted: "muted", deficiency: "warn",
  significant: "bad", material: "bad",
};
export function Badge({ v, text }: { v?: string | null; text?: string }) {
  return <span className={`badge ${TONE[v ?? ""] ?? "muted"}`}>{text ?? label(v)}</span>;
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={onClose}>
      <div className={`modal ${wide ? "wide" : ""}`} onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="modal-head"><h3>{title}</h3><button className="icon" onClick={onClose} aria-label="Close">×</button></div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><strong>{title}</strong>{children && <div>{children}</div>}</div>;
}

export function Loading() { return <div className="loading">Loading…</div>; }
export function ErrorBox({ msg }: { msg: string }) { return <div className="errorbox">{msg}</div>; }

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string; count?: number }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={active === t.key} className={active === t.key ? "on" : ""} onClick={() => onChange(t.key)}>
          {t.label}{t.count ? <span className="count">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}
