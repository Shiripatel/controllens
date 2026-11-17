import { useState } from "react";
import { api } from "../api";
import { Loading, useLoad } from "../components/ui";

export default function LibraryPage() {
  const [lib] = useLoad<any>(() => api.get("/library"), []);
  const [open, setOpen] = useState<string | null>(null);
  if (!lib) return <Loading />;
  return (
    <div className="page">
      <div className="page-head"><div><h1>ITGC control library</h1><p className="muted">{lib.controls.length} standard controls across 4 domains. Add them to an engagement from its Controls tab, then tailor.</p></div></div>
      {Object.entries(lib.domains).map(([d, name]) => (
        <div key={d} className="libgroup">
          <h3>{d} — {name as string}</h3>
          {lib.controls.filter((c: any) => c.domain === d).map((c: any) => (
            <div key={c.ref} className="card lib">
              <button className="lib-h" onClick={() => setOpen(open === c.ref ? null : c.ref)}>
                <span className="mono ref">{c.ref}</span><b>{c.title}</b><span className="muted small">{c.frequency} · {c.nature}</span><span className="spacer" />{open === c.ref ? "−" : "+"}
              </button>
              {open === c.ref && (
                <div className="lib-b">
                  <p>{c.description}</p>
                  <p className="muted"><b>Risk:</b> {c.risk}</p>
                  <div className="grid3">
                    <div><h4>Attributes</h4><ol>{c.attributes.map((a: any) => <li key={a.id}>{a.text}</li>)}</ol></div>
                    <div><h4>D&I procedures</h4><ul>{c.dni_procedures.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul></div>
                    <div><h4>TOE procedures</h4><ul>{c.toe_procedures.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul></div>
                  </div>
                  <p className="small"><b>Evidence to request:</b> {c.expected_evidence.join(" · ")}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
