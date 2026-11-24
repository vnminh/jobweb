import { Link } from "react-router-dom";
import { STATUS_VI } from "../taxonomy";

export const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("vi-VN") : "—");
export const fmtNum = (n) => (n == null ? "—" : Number(n).toLocaleString("vi-VN"));
export const place = (o) => [o.city, o.state_name || o.state].filter(Boolean).join(", ");

const PATHS = {
  pin: "M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21zm0-9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  briefcase: "M9 6V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V6h4.5A1.5 1.5 0 0 1 21 7.5v10A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-10A1.5 1.5 0 0 1 4.5 6H9zm1.5 0h3V4.5h-3V6z",
  level: "M4 20h4v-6H4v6zm6 0h4V10h-4v10zm6 0h4V4h-4v16z",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm.75 4.5v4.19l3.03 1.75-.75 1.3-3.78-2.19V7.5h1.5z",
  users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm7 0a3 3 0 1 0 0-6M2 20c0-3.3 3.1-6 7-6s7 2.7 7 6M17 14c2.8.3 5 2.6 5 5.5",
  search: "M10.5 3a7.5 7.5 0 0 1 5.9 12.1l4.8 4.8-1.1 1.1-4.8-4.8A7.5 7.5 0 1 1 10.5 3zm0 1.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12z",
  chat: "M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4v-4H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm4 6.5a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5zm4 0a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5zm4 0a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5z",
  degree: "M12 3 1 9l11 6 9-4.9V17h2V9L12 3zM5 13.2V17l7 4 7-4v-3.8l-7 3.8-7-3.8z",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z",
  building: "M4 21V5a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v4h4a1 1 0 0 1 1 1v11h-6v-4h-4v4H4zm3-14v2h2V7H7zm4 0v2h2V7h-2zm-4 4v2h2v-2H7zm4 0v2h2v-2h-2zm6 2v2h2v-2h-2z",
  check: "M9.5 16.2 5.3 12l-1.4 1.4 5.6 5.6 11-11-1.4-1.4z",
  calendar: "M7 2v2H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2V2h-2v2H9V2H7zm-2 7h14v10H5V9z",
  spark: "M12 2l1.8 5.6L19.5 9l-5.7 1.5L12 16l-1.8-5.5L4.5 9l5.7-1.4L12 2zm7 12 .9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9L19 14z",
};
export function Icon({ name, size }) {
  const stroke = name === "users";
  return (
    <svg className="icon" viewBox="0 0 24 24" style={size ? { width: size, height: size } : undefined} aria-hidden="true"
      fill={stroke ? "none" : "currentColor"} stroke={stroke ? "currentColor" : "none"} strokeWidth={stroke ? 1.8 : 0} strokeLinecap="round">
      <path d={PATHS[name]} />
    </svg>
  );
}

const PALETTE = ["#0e9f6e", "#2a78d6", "#7c5cd6", "#e0703a", "#d4477e", "#1f8fa3", "#b8860b", "#4b5d6b"];
export function Avatar({ name = "?", size = "", round = false }) {
  const words = String(name).replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  const skip = new Set(["nhà", "tuyển", "dụng", "tại", "the", "of"]);
  const key = words.filter((w) => !skip.has(w.toLowerCase()));
  const ini = (key.length ? key : words).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return <div className={`avatar ${size} ${round ? "round" : ""}`} style={{ background: PALETTE[h % PALETTE.length] }}>{ini}</div>;
}

export function Spinner({ text = "Đang tải…" }) {
  return <div className="row muted" style={{ padding: 24, justifyContent: "center" }}><span className="spinner" /> {text}</div>;
}
export function ErrorBox({ error }) { return error ? <div className="alert error">{String(error.message || error)}</div> : null; }
export function Empty({ children }) { return <div className="empty">{children}</div>; }

export function JobMeta({ job }) {
  return (
    <div className="meta">
      <span><Icon name="pin" />{place(job) || "—"}</span>
      {job.job_type_label && <span><Icon name="briefcase" />{job.job_type_label}</span>}
      {job.seniority_label && <span><Icon name="level" />{job.seniority_label}</span>}
    </div>
  );
}

export function JobCard({ job, to, right }) {
  return (
    <Link to={to || `/jobs/${job.id}`} className="job-card">
      <Avatar name={job.company || job.title} />
      <div className="body">
        <div className="row between" style={{ alignItems: "flex-start", gap: 8 }}>
          <h3>{job.title}</h3>
          {job.is_new && <span className="tag new">Mới</span>}
        </div>
        <div className="company">{job.company}</div>
        <JobMeta job={job} />
        <div className="tags">
          {job.occ_group_name && <span className="tag brand">{job.occ_group_name}</span>}
          {job.status === "closed" && <span className="tag red">Đã đóng</span>}
        </div>
      </div>
      {right}
    </Link>
  );
}

export function MiniJob({ job }) {
  return (
    <Link to={`/jobs/${job.id}`} className="mini-job">
      <Avatar name={job.company || job.title} />
      <div style={{ minWidth: 0 }}>
        <b style={{ fontSize: 14, display: "block" }}>{job.title}</b>
        <div className="small text-2">{job.company}</div>
        <div className="small muted">{place(job)}</div>
      </div>
    </Link>
  );
}

export function Pager({ page, size, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <div className="pager">
      <button className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>‹ Trước</button>
      <span className="small text-2">Trang {page} / {fmtNum(pages)}</span>
      <button className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Sau ›</button>
    </div>
  );
}

export function StatusTag({ status }) {
  const cls = { submitted: "", viewed: "blue", shortlisted: "brand", rejected: "red", hired: "brand" }[status] || "";
  return <span className={`tag ${cls}`}>{STATUS_VI[status] || status}</span>;
}

export function Stat({ label, value, sub }) {
  return <div className="card stat"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}

export function Bars({ rows, nameKey, valueKey }) {
  const max = Math.max(1, ...rows.map((r) => r[valueKey]));
  return (
    <div>
      {rows.map((r, i) => (
        <div className="bar-row" key={i} title={`${r[nameKey]}: ${fmtNum(r[valueKey])}`}>
          <span className="name">{r[nameKey]}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(100 * r[valueKey]) / max}%` }} /></div>
          <span className="num">{fmtNum(r[valueKey])}</span>
        </div>
      ))}
    </div>
  );
}

export function FitBadge({ fit }) {
  if (!fit) return null;
  const p = Math.round(fit.prob * 100);
  const cls = p >= 60 ? "brand" : p >= 40 ? "blue" : "warn";
  return (
    <span className="row" style={{ gap: 6 }}>
      <span className={`tag ${cls}`}><Icon name="star" />Mức độ phù hợp {p}%</span>
      {fit.unqualified && <span className="tag red">Chưa đáp ứng yêu cầu bằng cấp/kinh nghiệm</span>}
    </span>
  );
}
