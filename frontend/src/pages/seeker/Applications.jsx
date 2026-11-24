import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { Avatar, Empty, ErrorBox, Spinner, StatusTag, fmtDate, place } from "../../components/ui";

export default function Applications() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => api("/seeker/applications").then(setRows).catch(setErr);
  useEffect(() => { load(); }, []);
  const withdraw = async (id) => {
    if (!confirm("Bạn chắc chắn muốn rút hồ sơ ứng tuyển này?")) return;
    try { await api(`/seeker/applications/${id}`, { method: "DELETE" }); load(); } catch (e) { setErr(e); }
  };
  return (
    <>
      <div className="page-head"><div><h1>Việc đã ứng tuyển</h1><p>Theo dõi trạng thái hồ sơ của bạn.</p></div><Link to="/jobs" className="btn btn-outline">Tìm thêm việc</Link></div>
      <ErrorBox error={err} />
      {!rows ? <Spinner /> : rows.length === 0 ? <div className="card"><Empty>Bạn chưa ứng tuyển việc nào. <div style={{ marginTop: 12 }}><Link className="btn btn-primary" to="/jobs">Khám phá việc làm</Link></div></Empty></div> : (
        <div className="list">
          {rows.map((a) => (
            <div key={a.id} className="card row" style={{ flexWrap: "nowrap", alignItems: "center", padding: 16 }}>
              <Avatar name={a.job.company || a.job.title} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <Link to={`/jobs/${a.job.id}`} style={{ fontWeight: 600, color: "var(--text)" }}>{a.job.title}</Link>
                <div className="small text-2">{a.job.company} · {place(a.job)}</div>
                <div className="small muted">Ứng tuyển ngày {fmtDate(a.application_date)}{a.source === "assistant" ? " · qua Trợ lý tìm việc" : ""}</div>
              </div>
              <StatusTag status={a.status} />
              <button className="btn btn-sm btn-ghost" onClick={() => withdraw(a.id)}>Rút hồ sơ</button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
