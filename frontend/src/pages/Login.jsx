import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorBox } from "../components/ui";

const DEMO = [["Ứng viên", "user44@jobweb.demo", "demo123"], ["Nhà tuyển dụng", "recruiter.tx@jobweb.demo", "demo123"], ["Quản trị", "admin@jobweb.demo", "admin123"]];

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e?.preventDefault();
    setBusy(true); setErr(null);
    try {
      const a = await login(email, password);
      const next = sp.get("next");
      nav(next || (a.role === "admin" ? "/admin" : a.role === "recruiter" ? "/recruiter" : "/"));
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <div className="auth-wrap">
      <div className="card" style={{ padding: 28 }}>
        <h1>Chào mừng trở lại</h1>
        <p className="text-2" style={{ marginTop: -4 }}>Đăng nhập để tiếp tục tìm việc hoặc quản lý tin tuyển dụng.</p>
        <ErrorBox error={err} />
        <form onSubmit={submit}>
          <div className="field"><label>Email</label><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></div>
          <div className="field"><label>Mật khẩu</label><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          <button className="btn btn-primary btn-block btn-lg" disabled={busy}>{busy ? "Đang đăng nhập…" : "Đăng nhập"}</button>
        </form>
        <p className="small text-2" style={{ textAlign: "center", marginBottom: 0 }}>Chưa có tài khoản? <Link to="/register">Đăng ký miễn phí</Link></p>
        <hr className="divider" />
        <div className="small muted" style={{ marginBottom: 8 }}>Đăng nhập nhanh bằng tài khoản dùng thử</div>
        <div className="row">{DEMO.map(([r, e, p]) => <button key={e} className="btn btn-sm" onClick={() => { setEmail(e); setPassword(p); }}>{r}</button>)}</div>
      </div>
    </div>
  );
}
