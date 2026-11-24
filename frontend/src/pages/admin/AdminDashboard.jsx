import { useEffect, useState } from "react";
import { api } from "../../api";
import { STATUS_VI } from "../../taxonomy";
import { Bars, ErrorBox, Spinner, Stat, fmtNum } from "../../components/ui";

function DayChart({ rows }) {
  if (!rows.length) return null;
  const W = 760, H = 180, P = 28;
  const max = Math.max(...rows.map((r) => r.n));
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(1, rows.length - 1);
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const pts = rows.map((r, i) => `${x(i)},${y(r.n)}`).join(" ");
  const ticks = [0, Math.floor(rows.length / 2), rows.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Số đơn ứng tuyển theo ngày">
      <line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke="#e1e4e8" />
      <text x={P} y={14} fontSize="11" fill="#8b949e">tối đa {fmtNum(max)} đơn/ngày</text>
      <polyline points={pts} fill="none" stroke="#0e9f6e" strokeWidth="2" />
      {rows.map((r, i) => <circle key={i} cx={x(i)} cy={y(r.n)} r="6" fill="transparent"><title>{r.day}: {fmtNum(r.n)} đơn</title></circle>)}
      {ticks.map((i, k) => <text key={i} x={x(i)} y={H - 8} fontSize="11" fill="#8b949e" textAnchor={["start", "middle", "end"][k]}>{rows[i].day}</text>)}
    </svg>
  );
}

export default function AdminDashboard() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api("/admin/stats").then(setS).catch(setErr); }, []);
  if (!s) return err ? <ErrorBox error={err} /> : <Spinner />;
  const nJobs = Object.values(s.jobs_status).reduce((a, b) => a + b, 0);
  const nApps = Object.values(s.apps_status).reduce((a, b) => a + b, 0);
  return (
    <>
      <div className="page-head"><div><h1>Tổng quan hệ thống</h1><p>Số liệu hoạt động của toàn hệ thống.</p></div>
        <span className={`tag ${s.engine.loaded ? "brand" : "warn"}`}>{s.engine.loaded ? `Trợ lý tìm việc: hoạt động · ${s.engine.active_sessions} phiên đang mở` : "Trợ lý tìm việc: đang khởi động"}</span></div>
      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <Stat label="Ứng viên" value={fmtNum(s.accounts.seeker)} sub={`${fmtNum(s.accounts.recruiter)} nhà tuyển dụng · ${fmtNum(s.accounts.admin)} quản trị`} />
        <Stat label="Tin tuyển dụng" value={fmtNum(nJobs)} sub={`${fmtNum(s.jobs_status.open)} đang tuyển · ${fmtNum(s.jobs_source.web || 0)} tin mới tự đăng`} />
        <Stat label="Hồ sơ ứng tuyển" value={fmtNum(nApps)} sub={`${fmtNum(s.apps_source.assistant || 0)} hồ sơ nộp qua Trợ lý tìm việc`} />
        <Stat label="Phiên tư vấn" value={fmtNum(s.conversations.n)}
              sub={s.conversations.n ? `thành công ${Math.round((100 * s.conversations.success) / s.conversations.n)}% · TB ${s.conversations.avg_turns.toFixed(1)} lượt, ${s.conversations.avg_questions.toFixed(1)} câu hỏi` : "chưa có"} />
      </div>
      <div className="card"><h3>Hồ sơ ứng tuyển theo ngày</h3><DayChart rows={s.apps_per_day} /></div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card"><h3>Ngành nghề nhiều tin nhất</h3><Bars rows={s.top_groups} nameKey="name" valueKey="jobs" /></div>
        <div className="card"><h3>Bang nhiều tin nhất</h3><Bars rows={s.top_states} nameKey="state" valueKey="jobs" /></div>
        <div className="card"><h3>Trình độ học vấn của ứng viên</h3><Bars rows={s.degrees} nameKey="degree" valueKey="n" /></div>
        <div className="card"><h3>Trạng thái đơn ứng tuyển</h3><Bars rows={Object.entries(s.apps_status).map(([k, v]) => ({ k: STATUS_VI[k] || k, v }))} nameKey="k" valueKey="v" /></div>
      </div>
    </>
  );
}
