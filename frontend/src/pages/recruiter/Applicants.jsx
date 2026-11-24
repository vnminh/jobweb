import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { STATUS_VI } from "../../taxonomy";
import { Avatar, ErrorBox, FitBadge, Icon, Spinner, fmtDate, place } from "../../components/ui";
import ModelTest from "./ModelTest";

function Candidate({ s }) {
  return (
    <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
      <Avatar name={s.full_name} round />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600 }}>{s.full_name}</div>
        <div className="small text-2">{s.last_occ_name || "Chưa cập nhật vị trí"}{s.seniority_label ? ` · ${s.seniority_label}` : ""}</div>
        <div className="small muted">{[s.city, s.state_name].filter(Boolean).join(", ") || "—"} · {s.degree_label}{s.major ? ` (${s.major})` : ""} · {s.total_years_experience != null ? `${s.total_years_experience} năm kinh nghiệm` : "chưa rõ kinh nghiệm"}</div>
        {s.history?.length > 0 && <div className="small muted">Từng làm: {s.history.slice(0, 3).map((h) => h.job_title).join(" · ")}</div>}
      </div>
    </div>
  );
}

export default function Applicants() {
  const { id } = useParams();
  const [tab, setTab] = useState("apps");
  const [data, setData] = useState(null);
  const [sugg, setSugg] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => api(`/recruiter/jobs/${id}/applicants`).then(setData).catch(setErr);
  useEffect(() => { load(); }, [id]);
  useEffect(() => { if (tab === "sugg" && !sugg) api(`/recruiter/jobs/${id}/suggested`).then(setSugg).catch((e) => { setErr(e); setSugg([]); }); }, [tab]);
  const setStatus = async (a, status) => {
    try { await api(`/recruiter/applications/${a.id}/status`, { method: "PUT", body: { status } }); load(); } catch (e) { setErr(e); }
  };
  if (!data) return err ? <ErrorBox error={err} /> : <Spinner />;
  const j = data.job;
  return (
    <>
      <div className="small" style={{ marginBottom: 8 }}><Link to="/recruiter">← Quản lý tin đăng</Link></div>
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="row between">
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <Avatar name={j.company || j.title} />
            <div><h1 style={{ margin: 0, fontSize: 22 }}>{j.title}</h1>
              <div className="small text-2"><Icon name="pin" /> {place(j)} · <Icon name="calendar" /> Hạn nộp {fmtDate(j.end_date)} · {j.status === "open" ? <span className="tag brand">Đang tuyển</span> : <span className="tag red">Đã đóng</span>}</div></div>
          </div>
          <div className="row"><Link className="btn" to={`/jobs/${j.id}`}>Xem tin</Link><Link className="btn btn-primary" to={`/recruiter/jobs/${j.id}/edit`}>Chỉnh sửa</Link></div>
        </div>
      </div>
      <ErrorBox error={err} />
      <div className="tabs">
        <button className={tab === "apps" ? "active" : ""} onClick={() => setTab("apps")}>Hồ sơ ứng tuyển ({data.items.length})</button>
        <button className={tab === "sugg" ? "active" : ""} onClick={() => setTab("sugg")}>Ứng viên tiềm năng</button>
        <button className={tab === "test" ? "active" : ""} onClick={() => setTab("test")}>Mô phỏng tiếp cận</button>
      </div>
      {tab === "test" ? <ModelTest jobId={j.id} /> : tab === "apps" ? (
        data.items.length === 0 ? <div className="card empty">Chưa có ứng viên nào ứng tuyển. Hãy xem tab “Ứng viên tiềm năng”.</div> : (
          <div className="card table-wrap">
            <table>
              <thead><tr><th>Ứng viên</th><th>Ngày ứng tuyển</th><th>Đánh giá</th><th>Trạng thái</th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <td><Candidate s={a.seeker} /></td>
                    <td>{fmtDate(a.application_date)}</td>
                    <td><FitBadge fit={a.fit} /></td>
                    <td><select style={{ width: "auto" }} value={a.status} onChange={(e) => setStatus(a, e.target.value)}>{Object.entries(STATUS_VI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : !sugg ? <Spinner text="Đang tìm ứng viên phù hợp…" /> : (
        <div className="card">
          <p className="small text-2" style={{ marginTop: 0 }}>Những ứng viên có hồ sơ phù hợp nhất với tin này (ưu tiên cùng khu vực) và chưa ứng tuyển.</p>
          {sugg.length === 0 ? <div className="empty">Chưa tìm thấy ứng viên tiềm năng.</div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>#</th><th>Ứng viên</th><th>Đánh giá</th></tr></thead>
              <tbody>{sugg.map((r, i) => <tr key={r.seeker.id}><td>{i + 1}</td><td><Candidate s={r.seeker} /></td><td><FitBadge fit={r.fit} /></td></tr>)}</tbody>
            </table></div>
          )}
        </div>
      )}
    </>
  );
}
