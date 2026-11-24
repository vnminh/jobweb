import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useTaxonomy } from "../taxonomy";
import { Icon, JobCard, Spinner, fmtNum } from "../components/ui";

export default function Home() {
  const { user } = useAuth();
  const tax = useTaxonomy();
  const nav = useNavigate();
  const [q, setQ] = useState({ q: "", state: "", occ_group: "" });
  const [stats, setStats] = useState(null);
  const [recs, setRecs] = useState(null);
  const [recErr, setRecErr] = useState(null);
  const [latest, setLatest] = useState(null);
  useEffect(() => { api("/meta/stats").then(setStats).catch(() => {}); api("/jobs", { params: { size: 6 } }).then((r) => setLatest(r.items)).catch(() => setLatest([])); }, []);
  useEffect(() => {
    if (user?.role !== "seeker") return;
    api("/seeker/recommendations").then(setRecs).catch((e) => { setRecErr(e); setRecs([]); });
  }, [user]);
  const search = (e) => { e.preventDefault(); nav(`/jobs?${new URLSearchParams(Object.entries(q).filter(([, v]) => v))}`); };
  return (
    <>
      <section className="hero">
        <h1>Tìm đúng việc, nhanh hơn bao giờ hết</h1>
        <p>Hàng chục nghìn việc làm mới đang chờ bạn. Tìm theo vị trí, ngành nghề, nơi làm việc — hoặc để trợ lý tìm việc hỏi bạn vài câu và gợi ý ngay việc phù hợp.</p>
        <form className="searchbar" onSubmit={search}>
          <input placeholder="Vị trí, kỹ năng, từ khoá…" value={q.q} onChange={(e) => setQ({ ...q, q: e.target.value })} />
          <select value={q.state} onChange={(e) => setQ({ ...q, state: e.target.value })}>
            <option value="">Tất cả địa điểm</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}
          </select>
          <select value={q.occ_group} onChange={(e) => setQ({ ...q, occ_group: e.target.value })}>
            <option value="">Tất cả ngành nghề</option>{tax?.occ_groups.map((g) => <option key={g.key} value={g.key}>{g.name}</option>)}
          </select>
          <button className="btn btn-primary btn-lg"><Icon name="search" />Tìm việc</button>
        </form>
        {stats && (
          <div className="hero-stats">
            <div><b>{fmtNum(stats.open_jobs)}</b><span>việc làm đang tuyển</span></div>
            <div><b>{fmtNum(stats.companies)}</b><span>nhà tuyển dụng</span></div>
            <div><b>{fmtNum(stats.seekers)}</b><span>ứng viên</span></div>
          </div>
        )}
      </section>

      {user?.role === "seeker" && (
        <>
          <div className="section-title"><h2>Việc làm dành cho bạn</h2><Link to="/assistant">Muốn chính xác hơn? Hỏi trợ lý →</Link></div>
          {recs == null ? <Spinner text="Đang tìm việc phù hợp với hồ sơ của bạn…" /> : recs.length === 0 ? (
            <div className="card empty">{recErr ? recErr.message : "Chưa có gợi ý."} <div style={{ marginTop: 10 }}><Link className="btn btn-primary" to="/profile">Hoàn thiện hồ sơ</Link></div></div>
          ) : <div className="grid grid-2">{recs.map((j) => <JobCard key={j.id} job={j} />)}</div>}
        </>
      )}

      <div className="cta" style={{ background: "linear-gradient(120deg,#0f2a3d,#163f5c)" }}>
        <div className="row" style={{ gap: 16, flexWrap: "nowrap" }}>
          <div className="bot-ava" style={{ width: 52, height: 52 }}><Icon name="chat" size={26} /></div>
          <div><h2 style={{ margin: 0 }}>Trợ lý tìm việc</h2><p>Không biết bắt đầu từ đâu? Trả lời vài câu hỏi ngắn về ngành nghề, kỹ năng, cấp bậc và nơi làm việc — trợ lý sẽ chọn ra 10 việc hợp nhất với bạn.</p></div>
        </div>
        <Link to="/assistant" className="btn btn-primary btn-lg">Trò chuyện ngay</Link>
      </div>

      <div className="section-title"><h2>Ngành nghề nổi bật</h2><Link to="/jobs">Xem tất cả việc làm →</Link></div>
      <div className="grid grid-4">
        {(stats?.groups || []).slice(0, 12).map((g) => (
          <Link key={g.key} to={`/jobs?occ_group=${g.key}`} className="cat-card">
            <span className="ic"><Icon name="briefcase" /></span>
            <div><b>{g.name}</b><span>{fmtNum(g.jobs)} việc làm</span></div>
          </Link>
        ))}
      </div>

      <div className="section-title"><h2>Việc làm mới nhất</h2><Link to="/jobs">Xem thêm →</Link></div>
      {!latest ? <Spinner /> : <div className="grid grid-2">{latest.map((j) => <JobCard key={j.id} job={j} />)}</div>}

      <div className="section-title"><h2>Địa điểm tuyển dụng nhiều</h2></div>
      <div className="tags">
        {(stats?.states || []).map((s) => <Link key={s.key} to={`/jobs?state=${s.key}`} className="tag" style={{ padding: "8px 14px", fontSize: 14 }}><Icon name="pin" />{s.name} · {fmtNum(s.jobs)}</Link>)}
      </div>

      {!user && (
        <div className="cta">
          <div><h2 style={{ margin: 0 }}>Bạn là nhà tuyển dụng?</h2><p>Đăng tin miễn phí, tiếp cận ứng viên phù hợp và quản lý hồ sơ ứng tuyển dễ dàng.</p></div>
          <Link to="/register?role=recruiter" className="btn btn-primary btn-lg">Đăng tin tuyển dụng</Link>
        </div>
      )}
    </>
  );
}
