import { useState } from "react";
import { api } from "../api";
import { useUser } from "../App";
import { Badge, Loading, Modal, useAction, useLoad } from "../components/ui";

const ROLES = ["viewer", "preparer", "reviewer", "manager", "admin"];

export default function UsersPage() {
  const me = useUser();
  const [users, reload] = useLoad<any[]>(() => api.get("/users"), []);
  const [open, setOpen] = useState(false);
  const { run } = useAction();
  if (!users) return <Loading />;
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Users</h1><p className="muted">Roles: viewer (read only) · preparer · reviewer · manager (all engagements) · admin</p></div>
        <button className="primary" onClick={() => setOpen(true)}>Add user</button>
      </div>
      <table className="table">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
        <tbody>{users.map((u) => (
          <tr key={u.id}>
            <td>{u.name}</td><td className="muted">{u.email}</td>
            <td><select value={u.role} disabled={u.id === me.id} onChange={(e) => run(async () => { await api.patch(`/users/${u.id}`, { role: e.target.value }); reload(); }, "Role updated")}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></td>
            <td><Badge v={u.active ? "succeeded" : "low"} text={u.active ? "Active" : "Disabled"} /></td>
            <td>{u.id !== me.id && <button className="ghost sm" onClick={() => run(async () => { await api.patch(`/users/${u.id}`, { active: !u.active }); reload(); })}>{u.active ? "Disable" : "Enable"}</button>}</td>
          </tr>
        ))}</tbody>
      </table>
      {open && <NewUser onClose={() => setOpen(false)} onDone={() => { setOpen(false); reload(); }} />}
    </div>
  );
}

function NewUser({ onClose, onDone }: any) {
  const [f, setF] = useState({ name: "", email: "", role: "preparer", password: "" });
  const { busy, run } = useAction();
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title="Add user" onClose={onClose}>
      <form className="form" onSubmit={async (e) => { e.preventDefault(); if (await run(() => api.post("/users", f), "User created")) onDone(); }}>
        <label>Name<input value={f.name} onChange={set("name")} required /></label>
        <label>Email<input value={f.email} onChange={set("email")} required /></label>
        <label>Role<select value={f.role} onChange={set("role")}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></label>
        <label>Temporary password<input type="password" value={f.password} onChange={set("password")} required /></label>
        <div className="muted small">10+ characters with upper case, lower case and a number.</div>
        <div className="actions"><button type="button" className="ghost" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>Create</button></div>
      </form>
    </Modal>
  );
}
