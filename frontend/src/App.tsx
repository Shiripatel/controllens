import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, auth, type User } from "./api";
import { ToastProvider, Loading } from "./components/ui";
import Login from "./pages/Login";
import Engagements from "./pages/Engagements";
import EngagementPage from "./pages/Engagement";
import ControlWorkspace from "./pages/ControlWorkspace";
import AuditLogPage from "./pages/AuditLog";
import UsersPage from "./pages/Users";
import LibraryPage from "./pages/Library";

type AuthCtx = { user: User | null; setUser: (u: User | null) => void };
const Ctx = createContext<AuthCtx>({ user: null, setUser: () => {} });
export const useUser = () => useContext(Ctx).user!;
export const useAuth = () => useContext(Ctx);
export const can = (u: User, min: "viewer" | "preparer" | "reviewer" | "manager" | "admin") =>
  ["viewer", "preparer", "reviewer", "manager", "admin"].indexOf(u.role) >=
  ["viewer", "preparer", "reviewer", "manager", "admin"].indexOf(min);

function Shell({ children }: { children: ReactNode }) {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const compact = useLocation().pathname.startsWith("/controls/");
  const [health, setHealth] = useState<{ ai_provider: string; model: string }>();
  useEffect(() => { api.get("/health").then(setHealth).catch(() => {}); }, []);
  if (!user) return <Navigate to="/login" />;
  return (
    <div className={`shell ${compact ? "compact" : ""}`}>
      <aside className="side">
        <div className="brand"><span className="logo">◎</span><span className="lbl"> ControlLens</span></div>
        <nav>
          <NavLink to="/engagements" title="Engagements"><span className="ico">▦</span><span className="lbl">Engagements</span></NavLink>
          <NavLink to="/library" title="Control library"><span className="ico">☰</span><span className="lbl">Control library</span></NavLink>
          {can(user, "manager") && <NavLink to="/audit" title="Audit trail"><span className="ico">⛨</span><span className="lbl">Audit trail</span></NavLink>}
          {user.role === "admin" && <NavLink to="/users" title="Users"><span className="ico">☺</span><span className="lbl">Users</span></NavLink>}
        </nav>
        <div className="side-foot">
          {health && (
            <div className={`ai-pill lbl ${health.ai_provider}`} title={health.model}>
              AI: {health.ai_provider === "mock" ? "offline demo mode" : health.model}
            </div>
          )}
          <div className="me">
            <div className="avatar">{user.name.split(" ").map((x) => x[0]).join("").slice(0, 2)}</div>
            <div className="lbl"><div className="me-name">{user.name}</div><div className="me-role">{user.role}</div></div>
          </div>
          <button className="ghost sm" onClick={() => { auth.set(null); setUser(null); nav("/login"); }} title="Sign out"><span className="ico">⏻</span><span className="lbl">Sign out</span></button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!auth.token) { setReady(true); return; }
    api.get<User>("/auth/me").then(setUser).catch(() => auth.set(null)).finally(() => setReady(true));
  }, []);
  if (!ready) return <Loading />;
  const S = (el: ReactNode) => <Shell>{el}</Shell>;
  return (
    <Ctx.Provider value={{ user, setUser }}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={user ? <Navigate to="/engagements" /> : <Login />} />
            <Route path="/engagements" element={S(<Engagements />)} />
            <Route path="/engagements/:eid" element={S(<EngagementPage />)} />
            <Route path="/controls/:cid" element={S(<ControlWorkspace />)} />
            <Route path="/library" element={S(<LibraryPage />)} />
            <Route path="/audit" element={S(<AuditLogPage />)} />
            <Route path="/users" element={S(<UsersPage />)} />
            <Route path="*" element={<Navigate to={user ? "/engagements" : "/login"} />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </Ctx.Provider>
  );
}
