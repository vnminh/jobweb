import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { SEN_VI, useTaxonomy } from "../../taxonomy";
import { ErrorBox, Icon, JobCard, Pager, Spinner, fmtNum } from "../../components/ui";

const KEYS = ["q", "state", "city", "job_type", "occ_group", "seniority"];

export default function Jobs() {
  const tax = useTaxonomy();
  const [sp, setSp] = useSearchParams();
  const [form, setForm] = useState(() => Object.fromEntries(KEYS.map((k) => [k, sp.get(k) || ""])));
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const page = Number(sp.get("page") || 1);
  useEffect(() => {
    setData(null); setErr(null);
    setForm(Object.fromEntries(KEYS.map((k) => [k, sp.get(k) || ""])));
    api("/jobs", { params: { ...Object.fromEntries(KEYS.map((k) => [k, sp.get(k) || ""])), page, size: 20 } }).then(setData).catch(setErr);
  }, [sp]);
  const apply = (next) => setSp(Object.fromEntries(Object.entries(next).filter(([, v]) => v)));
  const set = (k, auto = false) => (e) => { const n = { ...form, [k]: e.target.value }; setForm(n); if (auto) apply(n); };
  const groupName = tax?.occ_groups.find((g) => g.key === sp.get("occ_group"))?.name;
  return (
    <>
      <form className="searchbar" style={{ marginTop: 0, maxWidth: "none", marginBottom: 20, boxShadow: "var(--shadow)" }} onSubmit={(e) => { e.preventDefault(); apply(form); }}>
        <input placeholder="Vị trí, kỹ năng, từ khoá…" value={form.q} onChange={set("q")} />
        <select value={form.state} onChange={set("state", true)}><option value="">Tất cả địa điểm</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}</select>
        <input placeholder="Thành phố" value={form.city} onChange={set("city")} />
        <button className="btn btn-primary btn-lg"><Icon name="search" />Tìm kiếm</button>
      </form>
      <div className="layout-side">
        <aside className="card sticky">
          <h3>Lọc nâng cao</h3>
          <div className="field"><label>Ngành nghề</label><select value={form.occ_group} onChange={set("occ_group", true)}><option value="">Tất cả</option>{tax?.occ_groups.map((g) => <option key={g.key} value={g.key}>{g.name}</option>)}</select></div>
          <div className="field"><label>Hình thức làm việc</label><select value={form.job_type} onChange={set("job_type", true)}><option value="">Tất cả</option>{tax?.job_types.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</select></div>
          <div className="field"><label>Cấp bậc</label><select value={form.seniority} onChange={set("seniority", true)}><option value="">Tất cả</option>{tax?.seniority.map((s) => <option key={s} value={s}>{SEN_VI[s]}</option>)}</select></div>
          <button type="button" className="btn btn-ghost btn-block" onClick={() => setSp({})}>Xoá bộ lọc</button>
        </aside>
        <div>
          <div className="page-head" style={{ marginBottom: 14 }}>
            <div><h1 style={{ marginBottom: 0 }}>{groupName ? `Việc làm ${groupName}` : sp.get("q") ? `Kết quả cho “${sp.get("q")}”` : "Tất cả việc làm"}</h1>
              <p>{data ? `${fmtNum(data.total)} việc làm phù hợp` : "Đang tìm…"}</p></div>
          </div>
          <ErrorBox error={err} />
          {!data ? <Spinner /> : data.items.length === 0 ? <div className="card empty">Không tìm thấy việc làm phù hợp. Hãy thử bỏ bớt bộ lọc.</div> : (
            <>
              <div className="list">{data.items.map((j) => <JobCard key={j.id} job={j} />)}</div>
              <Pager page={page} size={data.size} total={data.total} onPage={(p) => { const n = new URLSearchParams(sp); n.set("page", p); setSp(n); window.scrollTo(0, 0); }} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
