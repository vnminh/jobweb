import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { useTaxonomy } from "../../taxonomy";
import { Avatar, ErrorBox, Icon, Spinner } from "../../components/ui";

export function OccupationSelect({ value, onChange, tax, placeholder = "— Chọn vị trí —" }) {
  if (!tax) return <select disabled><option>Đang tải…</option></select>;
  return (
    <select value={value || ""} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">{placeholder}</option>
      {tax.occ_groups.map((g) => (
        <optgroup key={g.key} label={g.name}>
          {tax.occupations.filter((o) => o.group_key === g.key).map((o) => <option key={o.key} value={o.key}>{o.name}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

export function CitySelect({ state, value, onChange }) {
  const [cities, setCities] = useState([]);
  useEffect(() => { if (state) api("/meta/cities", { params: { state } }).then(setCities).catch(() => setCities([])); else setCities([]); }, [state]);
  return (
    <select value={value || ""} onChange={(e) => onChange(e.target.value || null)} disabled={!state}>
      <option value="">{state ? "— Chọn thành phố —" : "Chọn bang trước"}</option>
      {cities.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
    </select>
  );
}

export default function Profile() {
  const tax = useTaxonomy();
  const [sp] = useSearchParams();
  const [p, setP] = useState(null);
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  const [ok, setOk] = useState(false);
  const [saving, setSaving] = useState(false);
  const [samples, setSamples] = useState([]);
  useEffect(() => { api("/meta/samples").then((r) => setSamples(r.seekers)).catch(() => {}); }, []);
  const init = (d) => {
    setP(d);
    setF({ full_name: d.full_name || "", state: d.state || "", city_key: d.city_key || "", zip5: d.zip5 || "", degree_ord: d.degree_ord || 0,
      major: d.major || "", graduation_date: d.graduation_date ? d.graduation_date.slice(0, 10) : "", total_years_experience: d.total_years_experience ?? "",
      currently_employed: d.currently_employed, managed_others: d.managed_others, managed_how_many: d.managed_how_many || 0, last_occ: d.last_occ || "",
      history: d.history.map((h) => h.job_title) });
  };
  useEffect(() => { api("/seeker/profile").then(init).catch(setErr); }, []);
  if (!f) return err ? <ErrorBox error={err} /> : <Spinner />;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const setHist = (i, v) => setF({ ...f, history: f.history.map((h, k) => (k === i ? v : h)) });
  const move = (i, d) => { const h = [...f.history]; const j = i + d; if (j < 0 || j >= h.length) return; [h[i], h[j]] = [h[j], h[i]]; setF({ ...f, history: h }); };
  const useSample = (i) => {
    const s = samples[i];
    if (!s) return;
    setF({ ...f, full_name: s.full_name, state: s.state, city_key: s.city_key, zip5: s.zip5, degree_ord: s.degree_ord, major: s.major,
      graduation_date: s.graduation_date, total_years_experience: s.total_years_experience, currently_employed: s.currently_employed,
      managed_others: s.managed_others, managed_how_many: s.managed_how_many, last_occ: s.last_occ, history: [...s.history] });
    setOk(false);
  };
  const save = async (e) => {
    e.preventDefault(); setErr(null); setOk(false); setSaving(true);
    try {
      const body = { ...f, degree_ord: Number(f.degree_ord), managed_how_many: Number(f.managed_how_many) || 0,
        total_years_experience: f.total_years_experience === "" ? null : Number(f.total_years_experience),
        graduation_date: f.graduation_date || null, city_key: f.city_key || null, state: f.state || null, last_occ: f.last_occ || null,
        history: f.history.filter((h) => h.trim()).map((h) => ({ job_title: h })) };
      init(await api("/seeker/profile", { method: "PUT", body }));
      setOk(true);
      window.scrollTo(0, 0);
    } catch (x) { setErr(x); } finally { setSaving(false); }
  };
  const filled = [f.full_name, f.city_key, f.total_years_experience !== "", f.history.some((h) => h.trim()), f.degree_ord > 0, f.major].filter(Boolean).length;
  const pct = Math.round((filled / 6) * 100);
  return (
    <form onSubmit={save}>
      <div className="page-head">
        <div><h1>Hồ sơ của tôi</h1><p>Hồ sơ càng đầy đủ, gợi ý việc làm càng chính xác.</p></div>
        <div className="row">
          {samples.length > 0 && (
            <select style={{ width: "auto" }} value="" onChange={(e) => useSample(Number(e.target.value))} title="Điền nhanh một hồ sơ mẫu">
              <option value="">Dùng hồ sơ mẫu…</option>{samples.map((s, i) => <option key={i} value={i}>{s.label}</option>)}
            </select>
          )}
          <button className="btn btn-primary" disabled={saving}>{saving ? "Đang lưu…" : "Lưu hồ sơ"}</button>
        </div>
      </div>
      <ErrorBox error={err} />
      {ok && <div className="alert ok">Đã lưu hồ sơ. <Link to="/">Xem việc làm dành cho bạn →</Link></div>}
      {sp.get("new") && !p.history.length && !ok && <div className="alert info">Chào mừng bạn đến với JobWeb! Hãy hoàn thiện hồ sơ để nhận gợi ý việc làm phù hợp.</div>}
      <div className="layout-main-side">
        <div className="stack">
          <div className="card">
            <h3>Thông tin cá nhân</h3>
            <div className="field"><label>Họ và tên</label><input value={f.full_name} onChange={set("full_name")} /></div>
            <div className="grid grid-3" style={{ gap: 12 }}>
              <div className="field"><label>Bang</label><select value={f.state} onChange={(e) => setF({ ...f, state: e.target.value, city_key: "" })}><option value="">—</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}</select></div>
              <div className="field"><label>Thành phố</label><CitySelect state={f.state} value={f.city_key} onChange={(v) => setF({ ...f, city_key: v || "" })} /></div>
              <div className="field"><label>Mã bưu chính</label><input value={f.zip5} onChange={set("zip5")} maxLength={10} /></div>
            </div>
          </div>
          <div className="card">
            <h3>Kinh nghiệm làm việc</h3>
            <div className="grid grid-2" style={{ gap: 12 }}>
              <div className="field"><label>Số năm kinh nghiệm</label><input type="number" min="0" max="50" step="0.5" value={f.total_years_experience} onChange={set("total_years_experience")} /></div>
              <div className="field"><label>Vị trí gần nhất</label><OccupationSelect value={f.last_occ} onChange={(v) => setF({ ...f, last_occ: v || "" })} tax={tax} placeholder="Tự nhận diện từ chức danh" /></div>
            </div>
            <div className="row" style={{ marginBottom: 14 }}>
              <label className="check"><input type="checkbox" checked={f.currently_employed} onChange={set("currently_employed")} /> Tôi đang đi làm</label>
              <label className="check"><input type="checkbox" checked={f.managed_others} onChange={set("managed_others")} /> Tôi từng quản lý nhân sự</label>
              {f.managed_others && <label className="check">Số người: <input type="number" min="0" style={{ width: 90 }} value={f.managed_how_many} onChange={set("managed_how_many")} /></label>}
            </div>
            <label>Các công việc đã làm (mới nhất trước)</label>
            {f.history.map((h, i) => (
              <div key={i} className="row" style={{ marginBottom: 8, flexWrap: "nowrap", gap: 6 }}>
                <input value={h} onChange={(e) => setHist(i, e.target.value)} placeholder="Chức danh, ví dụ: Kế toán viên, Sales Executive…" />
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => move(i, -1)} title="Lên">↑</button>
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => move(i, 1)} title="Xuống">↓</button>
                <button type="button" className="btn btn-sm btn-ghost" onClick={() => setF({ ...f, history: f.history.filter((_, k) => k !== i) })} title="Xoá">✕</button>
              </div>
            ))}
            <button type="button" className="btn btn-sm btn-outline" onClick={() => setF({ ...f, history: [...f.history, ""] })}>+ Thêm công việc</button>
          </div>
          <div className="card">
            <h3>Học vấn</h3>
            <div className="grid grid-3" style={{ gap: 12 }}>
              <div className="field"><label>Trình độ</label><select value={f.degree_ord} onChange={set("degree_ord")}>{tax?.degrees.map((d) => <option key={d.ord} value={d.ord}>{d.ord === 0 ? "Chưa có bằng cấp" : d.name}</option>)}</select></div>
              <div className="field"><label>Chuyên ngành</label><input value={f.major} onChange={set("major")} /></div>
              <div className="field"><label>Ngày tốt nghiệp</label><input type="date" value={f.graduation_date} onChange={set("graduation_date")} /></div>
            </div>
          </div>
        </div>
        <aside className="card sticky stack">
          <div className="row" style={{ flexWrap: "nowrap" }}><Avatar name={f.full_name || "?"} round size="lg" />
            <div><b style={{ fontSize: 16 }}>{f.full_name || "Chưa có tên"}</b><div className="small text-2">{p.last_occ_name || "Chưa có vị trí"}</div><div className="small muted">{[p.city, p.state_name].filter(Boolean).join(", ")}</div></div></div>
          <div><div className="row between small"><span className="text-2">Mức độ hoàn thiện</span><b>{pct}%</b></div><div className="progress" style={{ marginTop: 6 }}><div style={{ width: `${pct}%` }} /></div></div>
          {p.seniority_label && <div className="small text-2"><Icon name="level" /> Cấp bậc phù hợp: <b>{p.seniority_label}</b></div>}
          <Link to="/assistant" className="btn btn-primary btn-block"><Icon name="chat" />Tìm việc cùng trợ lý</Link>
        </aside>
      </div>
    </form>
  );
}
