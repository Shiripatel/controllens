// Thin API client. Token is kept in sessionStorage (cleared when the tab closes).
export type User = { id: number; email: string; name: string; role: string; active: boolean };

const TOKEN_KEY = "cl_token";
export const auth = {
  get token() { return sessionStorage.getItem(TOKEN_KEY); },
  set(t: string | null) { t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY); },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (res.status === 401 && path !== "/auth/login") {
    auth.set(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail
        : Array.isArray(j.detail) ? j.detail.map((d: any) => d.msg?.replace("Value error, ", "")).join("; ")
        : msg;
    } catch { /* not json */ }
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const api = {
  get: <T = any>(p: string) => request<T>("GET", p),
  post: <T = any>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  patch: <T = any>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: <T = any>(p: string) => request<T>("DELETE", p),
  async download(p: string, filename: string) {
    const res = await fetch(`/api${p}`, { headers: { Authorization: `Bearer ${auth.token}` } });
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).detail; } catch { /* */ }
      throw new ApiError(res.status, msg);
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  },
};

export const LABELS: Record<string, string> = {
  not_started: "Not started",
  design_in_progress: "Design in progress", design_prepared: "Design prepared", design_reviewed: "Design reviewed",
  operating_in_progress: "Operating in progress", operating_prepared: "Operating prepared", operating_reviewed: "Complete",
  effective: "Effective", not_effective: "Not effective", insufficient_evidence: "Needs more evidence",
  implemented: "Implemented", not_implemented: "Not implemented",
  operating_effectively: "Operating effectively", not_operating_effectively: "Not operating effectively",
  adequate: "Adequate", inadequate: "Inadequate", unable_to_assess: "Unable to assess",
  yes: "Yes", no: "No", pass: "Pass", fail: "Fail",
  APD: "Access to Programs & Data", PC: "Program Change", CO: "Computer Operations", PD: "Program Development",
};
export const label = (k?: string | null) => (k ? LABELS[k] ?? k.replace(/_/g, " ") : "—");

export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
export const fmtSize = (n: number) =>
  n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
