import { Link } from "react-router-dom";
import { api, label } from "../api";
import { can, useUser } from "../App";
import { Badge, ErrorBox, Loading, useLoad } from "../components/ui";

function Section({ title, hint, items, empty, render }: { title: string; hint: string; items: any[]; empty: string; render: (x: any) => any }) {
  return (
    <section className="work">
      <div className="work-h"><h3>{title}</h3><span className="work-n">{items.length}</span><span className="muted small">{hint}</span></div>
      {items.length === 0 ? <div className="work-empty muted">{empty}</div> : (
        <div className="work-list">{items.map((x, i) => (
          <Link key={i} to={`/controls/${x.id}`} className="work-item">
            <span className="work-ref">{x.ref}</span>
            <span className="work-main">{render(x)}</span>
            <span className="muted small work-eng">{x.engagement}</span>
          </Link>
        ))}</div>
      )}
    </section>
  );
}

export default function Home() {
  const user = useUser();
  const [w, , err] = useLoad<any>(() => api.get("/me/work"), []);
  if (err) return <ErrorBox msg={err} />;
  if (!w) return <Loading />;
  const reviewer = can(user, "reviewer");
  const total = w.to_prepare.length + w.to_review.length + w.notes.length + w.requests.length;
  return (
    <div className="page home">
      <div className="page-head">
        <div><h1>My work</h1><p className="muted">{total === 0 ? "Nothing is waiting for you right now." : `${total} item(s) need your attention, ${user.name.split(" ")[0]}.`}</p></div>
        <Link to="/engagements"><button className="ghost">All engagements</button></Link>
      </div>
      <div className="work-grid">
        <div className="work-col">
          {reviewer && <Section title="To review" hint="Prepared and waiting for your sign-off" items={w.to_review} empty="No controls are waiting for your review."
            render={(x) => <><b>{x.title}</b><Badge v={x.status} /></>} />}
          <Section title="To prepare" hint="Controls assigned to you" items={w.to_prepare} empty="You have no controls to prepare."
            render={(x) => <><b>{x.title}</b><Badge v={x.status} /></>} />
        </div>
        <div className="work-col">
          <Section title="Review notes" hint="Open notes on your controls" items={w.notes} empty="No open review notes."
            render={(x) => <><span>{x.note}</span><Badge v={x.severity} text={`${label(x.severity)} · ${x.note_status}`} /></>} />
          <Section title="Open requests" hint="Evidence you are waiting on" items={w.requests} empty="No open evidence requests."
            render={(x) => <><span>{x.request}</span>{x.due_date && <span className="muted small">Due {x.due_date}</span>}</>} />
          {w.waiting.length > 0 && <Section title="With the reviewer" hint="You prepared these; nothing to do yet" items={w.waiting} empty=""
            render={(x) => <><b>{x.title}</b><Badge v={x.status} /></>} />}
        </div>
      </div>
    </div>
  );
}
