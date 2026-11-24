import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { useTaxonomy } from "../taxonomy";
import { ErrorBox } from "../components/ui";

export default function Register() {
  const { register } = useAuth();
  const tax = useTaxonomy();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [f, setF] = useState({ role: sp.get("role") === "recruiter" ? "recruiter" : "seeker", full_name: "", email: "", password: "", company_name: "", state: "" });
  const [err, setErr] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    try {
      const a = await register({ ...f, state: f.state || null, company_name: f.company_name || null });
      nav(a.role === "recruiter" ? "/recruiter/jobs/new?new=1" : "/profile?new=1");
    } catch (x) { setErr(x); }
  };
  return (
    <div className="auth-wrap">
      <div className="card" style={{ padding: 28 }}>
        <h1>Tạo tài khoản</h1>
        <ErrorBox error={err} />
        <div className="grid grid-2" style={{ marginBottom: 16, gap: 8 }}>
          {[["seeker", "Tôi tìm việc"], ["recruiter", "Tôi tuyển dụng"]].map(([v, l]) => (
            <button key={v} type="button" className={`btn ${f.role === v ? "btn-primary" : ""}`} onClick={() => setF({ ...f, role: v })}>{l}</button>
          ))}
        </div>
        <form onSubmit={submit}>
          <div className="field"><label>Họ và tên</label><input value={f.full_name} onChange={set("full_name")} required /></div>
          {f.role === "recruiter" && <div className="field"><label>Tên công ty</label><input value={f.company_name} onChange={set("company_name")} required /></div>}
          <div className="field"><label>{f.role === "recruiter" ? "Trụ sở (bang)" : "Nơi bạn sống (bang)"}</label>
            <select value={f.state} onChange={set("state")}><option value="">— Chọn —</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}</select>
          </div>
          <div className="field"><label>Email</label><input type="email" value={f.email} onChange={set("email")} required /></div>
          <div className="field"><label>Mật khẩu (tối thiểu 6 ký tự)</label><input type="password" value={f.password} onChange={set("password")} required minLength={6} /></div>
          <button className="btn btn-primary btn-block btn-lg">Đăng ký</button>
        </form>
        <p className="small text-2" style={{ textAlign: "center", marginBottom: 0 }}>Đã có tài khoản? <Link to="/login">Đăng nhập</Link></p>
      </div>
    </div>
  );
}
