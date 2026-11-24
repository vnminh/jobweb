import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { Avatar, ErrorBox, FitBadge, Icon, MiniJob, Spinner, StatusTag, fmtDate, place } from "../../components/ui";

function Info({ icon, label, value }) {
  return <div className="info-item"><span className="ic"><Icon name={icon} /></span><div><small>{label}</small><b>{value}</b></div></div>;
}

export default function JobDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [job, setJob] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);
  const load = () => api(`/jobs/${id}`).then(setJob).catch(setErr);
  useEffect(() => { setJob(null); setMsg(null); load(); api(`/jobs/${id}/similar`).then(setSimilar).catch(() => setSimilar([])); }, [id, user]);
  const apply = async () => {
    setErr(null);
    try { await api(`/jobs/${id}/apply`, { method: "POST" }); setMsg("Ứng tuyển thành công! Nhà tuyển dụng sẽ liên hệ nếu hồ sơ phù hợp."); load(); } catch (e) { setErr(e); }
  };
  if (!job) return err ? <ErrorBox error={err} /> : <Spinner />;
  const applyBox = user?.role === "seeker" ? (
    job.applied ? <div className="row"><span className="tag brand"><Icon name="check" />Đã ứng tuyển</span><StatusTag status={job.application_status} /></div>
      : <button className="btn btn-primary btn-lg btn-block" disabled={job.status !== "open"} onClick={apply}>{job.status === "open" ? "Ứng tuyển ngay" : "Tin đã đóng"}</button>
  ) : !user ? <Link to={`/login?next=/jobs/${job.id}`} className="btn btn-primary btn-lg btn-block">Đăng nhập để ứng tuyển</Link> : null;
  return (
    <div className="layout-main-side">
      <div className="stack">
        <div className="card">
          <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: 16 }}>
            <Avatar name={job.company || job.title} size="lg" />
            <div style={{ minWidth: 0 }}>
              <h1 style={{ marginBottom: 4 }}>{job.title}</h1>
              <div className="text-2"><Icon name="building" /> {job.company}</div>
              <div className="text-2" style={{ marginTop: 2 }}><Icon name="pin" /> {place(job)}</div>
            </div>
          </div>
          <ErrorBox error={err} />
          {msg && <div className="alert ok" style={{ marginTop: 14 }}>{msg}</div>}
          <hr className="divider" />
          <div className="info-grid">
            <Info icon="briefcase" label="Hình thức" value={job.job_type_label || "Thoả thuận"} />
            <Info icon="level" label="Cấp bậc" value={job.seniority_label || "Không yêu cầu"} />
            <Info icon="clock" label="Kinh nghiệm" value={job.years_req != null ? `${job.years_req} năm` : "Không yêu cầu"} />
            <Info icon="degree" label="Học vấn" value={job.degree_req_label || "Không yêu cầu"} />
            <Info icon="star" label="Ngành nghề" value={job.occ_group_name || "Khác"} />
            <Info icon="calendar" label="Hạn nộp hồ sơ" value={fmtDate(job.end_date)} />
          </div>
        </div>
        <div className="card">
          <h2>Mô tả công việc</h2>
          <div className="desc">{job.description || "—"}</div>
          {job.requirements && <><h2 style={{ marginTop: 24 }}>Yêu cầu ứng viên</h2><div className="desc">{job.requirements}</div></>}
          {job.skills?.length > 0 && <><h2 style={{ marginTop: 24 }}>Kỹ năng</h2><div className="tags">{job.skills.map((s) => <span key={s.key} className="tag brand">{s.name}</span>)}</div></>}
        </div>
      </div>
      <aside className="stack sticky">
        <div className="card stack">
          {applyBox}
          {user?.role === "seeker" && <FitBadge fit={job.fit} />}
          <div className="small text-2"><Icon name="users" /> {job.n_applicants} người đã ứng tuyển</div>
        </div>
        <div className="card">
          <h3>Về nhà tuyển dụng</h3>
          <div className="row" style={{ flexWrap: "nowrap" }}><Avatar name={job.company || "?"} /><div><b>{job.company}</b><div className="small muted">{job.state_name}</div></div></div>
        </div>
        {similar.length > 0 && <div className="card"><h3>Việc làm tương tự</h3>{similar.map((j) => <MiniJob key={j.id} job={j} />)}</div>}
      </aside>
    </div>
  );
}
