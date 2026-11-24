import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { ErrorBox, Icon, Pager, Spinner, Stat, fmtDate, fmtNum, place } from "../../components/ui";

export default function RecruiterJobs() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [err, setErr] = useState(null);
  const load = () => api("/recruiter/jobs", { params: { q, status, page, size: 20 } }).then(setData).catch(setErr);
  const loadStats = () => api("/recruiter/stats").then(setStats).catch(setErr);
  useEffect(() => { loadStats(); }, []);
  useEffect(() => { load(); }, [status, page]);
  const toggle = async (j) => {
    try { await api(`/recruiter/jobs/${j.id}/status`, { method: "POST", body: { status: j.status === "open" ? "closed" : "open" } }); load(); loadStats(); } catch (e) { setErr(e); }
  };
  const a = stats?.applications || {};
  return (
    <>
      <div className="page-head">
        <div><h1>Xin chào, {user.company_name}</h1><p>Quản lý tin tuyển dụng và hồ sơ ứng viên của bạn.</p></div>
        <Link to="/recruiter/jobs/new" className="btn btn-primary btn-lg">+ Đăng tin mới</Link>
      </div>
      <ErrorBox error={err} />
      {stats && (
        <div className="grid grid-4" style={{ marginBottom: 20 }}>
          <Stat label="Tin đang tuyển" value={fmtNum(stats.open)} sub={`${fmtNum(stats.closed)} tin đã đóng`} />
          <Stat label="Hồ sơ nhận được" value={fmtNum(stats.total_applications)} />
          <Stat label="Chờ xử lý" value={fmtNum((a.submitted || 0) + (a.viewed || 0))} />
          <Stat label="Mời phỏng vấn / nhận việc" value={fmtNum((a.shortlisted || 0) + (a.hired || 0))} />
        </div>
      )}
      <div className="card">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Tin tuyển dụng</h3>
          <form className="row" onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }}>
            <input style={{ width: 260 }} placeholder="Tìm theo tên vị trí" value={q} onChange={(e) => setQ(e.target.value)} />
            <select style={{ width: "auto" }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">Tất cả</option><option value="open">Đang tuyển</option><option value="closed">Đã đóng</option>
            </select>
            <button className="btn"><Icon name="search" /></button>
          </form>
        </div>
        {!data ? <Spinner /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Vị trí</th><th>Địa điểm</th><th>Hạn nộp</th><th>Hồ sơ</th><th>Trạng thái</th><th /></tr></thead>
              <tbody>
                {data.items.map((j) => (
                  <tr key={j.id}>
                    <td><Link to={`/recruiter/jobs/${j.id}`} style={{ fontWeight: 600, color: "var(--text)" }}>{j.title}</Link>
                      <div className="small muted">{[j.occ_group_name, j.job_type_label].filter(Boolean).join(" · ")}{j.is_new ? " · " : ""}{j.is_new && <span className="tag new" style={{ padding: "0 6px" }}>Mới</span>}</div></td>
                    <td>{place(j)}</td>
                    <td>{fmtDate(j.end_date)}</td>
                    <td><Link to={`/recruiter/jobs/${j.id}`}>{fmtNum(j.n_applicants)} hồ sơ</Link></td>
                    <td>{j.status === "open" ? <span className="tag brand">Đang tuyển</span> : <span className="tag red">Đã đóng</span>}</td>
                    <td><div className="row" style={{ flexWrap: "nowrap", gap: 6 }}>
                      <Link className="btn btn-sm" to={`/recruiter/jobs/${j.id}/edit`}>Sửa</Link>
                      <button className="btn btn-sm" onClick={() => toggle(j)}>{j.status === "open" ? "Đóng tin" : "Mở lại"}</button>
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.items.length === 0 && <div className="empty">Chưa có tin tuyển dụng nào. <Link to="/recruiter/jobs/new">Đăng tin đầu tiên</Link></div>}
            <Pager page={page} size={data.size} total={data.total} onPage={setPage} />
          </div>
        )}
      </div>
    </>
  );
}
