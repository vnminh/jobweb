import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { SEN_VI, useTaxonomy } from "../../taxonomy";
import { ErrorBox, Icon, Spinner } from "../../components/ui";
import { CitySelect, OccupationSelect } from "../seeker/Profile";

const EMPTY = { title: "", description: "", requirements: "", state: "", city_key: "", zip5: "", start_date: "", end_date: "", occupation_code: "",
  job_type: "", seniority: "", degree_req: "", years_req: "", salary_mentioned: false, skills: [] };

export default function JobForm() {
  const { id } = useParams();
  const tax = useTaxonomy();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [f, setF] = useState(id ? null : EMPTY);
  const [err, setErr] = useState(null);
  const [hint, setHint] = useState(null);
  const [skillQ, setSkillQ] = useState("");
  const [samples, setSamples] = useState([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api("/meta/samples").then((r) => setSamples(r.jobs)).catch(() => {}); }, []);
  useEffect(() => {
    if (!id) return;
    api(`/recruiter/jobs/${id}`).then((j) => setF({ title: j.title, description: j.description || "", requirements: j.requirements || "", state: j.state || "",
      city_key: j.city_key || "", zip5: j.zip5 || "", start_date: j.start_date?.slice(0, 10) || "", end_date: j.end_date?.slice(0, 10) || "",
      occupation_code: j.occupation_code || "", job_type: j.job_type || "", seniority: j.seniority || "", degree_req: j.degree_req ?? "",
      years_req: j.years_req ?? "", salary_mentioned: j.salary_mentioned, skills: j.skills.map((s) => s.key) })).catch(setErr);
  }, [id]);
  if (!f) return err ? <ErrorBox error={err} /> : <Spinner />;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const useSample = (i) => {
    const s = samples[i];
    if (!s) return;
    const today = new Date(), end = new Date(Date.now() + 30 * 864e5);
    setF({ title: s.title, description: s.description, requirements: s.requirements, state: s.state, city_key: s.city_key, zip5: s.zip5,
      start_date: today.toISOString().slice(0, 10), end_date: end.toISOString().slice(0, 10), occupation_code: s.occupation_code,
      job_type: s.job_type || "", seniority: s.seniority || "", degree_req: s.degree_req ?? "", years_req: s.years_req ?? "", salary_mentioned: false, skills: s.skills });
    setHint(null);
  };
  const suggest = async () => {
    setErr(null);
    try {
      const s = await api("/meta/suggest", { params: { title: f.title, text: `${f.description}\n${f.requirements}` } });
      setHint(s);
      setF({ ...f, occupation_code: s.occupation_code || f.occupation_code, job_type: s.job_type || f.job_type, seniority: s.seniority || f.seniority,
        degree_req: s.degree_req ?? f.degree_req, years_req: s.years_req ?? f.years_req, salary_mentioned: s.salary_mentioned || f.salary_mentioned,
        skills: [...new Set([...f.skills, ...s.skills.map((x) => x.key)])] });
    } catch (e) { setErr(e); }
  };
  const save = async (e) => {
    e.preventDefault(); setErr(null); setSaving(true);
    const body = { ...f, occupation_code: f.occupation_code || null, job_type: f.job_type || null, seniority: f.seniority || null,
      degree_req: f.degree_req === "" ? null : Number(f.degree_req), years_req: f.years_req === "" ? null : Number(f.years_req),
      start_date: f.start_date || null, end_date: f.end_date || null };
    try {
      const j = await api(id ? `/recruiter/jobs/${id}` : "/recruiter/jobs", { method: id ? "PUT" : "POST", body });
      nav(`/recruiter/jobs/${j.id}`);
    } catch (x) { setErr(x); window.scrollTo(0, 0); } finally { setSaving(false); }
  };
  const skillName = Object.fromEntries((tax?.skills || []).map((s) => [s.key, s.name]));
  const skillOpts = (tax?.skills || []).filter((s) => skillQ && s.name.toLowerCase().includes(skillQ.toLowerCase()) && !f.skills.includes(s.key)).slice(0, 12);
  return (
    <form onSubmit={save}>
      <div className="page-head">
        <div><h1>{id ? "Chỉnh sửa tin tuyển dụng" : "Đăng tin tuyển dụng"}</h1><p>Tin đăng rõ ràng, đầy đủ giúp bạn tiếp cận đúng ứng viên.</p></div>
        <div className="row">
          {!id && samples.length > 0 && (
            <select style={{ width: "auto" }} value="" onChange={(e) => useSample(Number(e.target.value))}>
              <option value="">Dùng tin mẫu…</option>{samples.map((s, i) => <option key={i} value={i}>{s.label}</option>)}
            </select>
          )}
          <button className="btn btn-primary" disabled={saving}>{saving ? "Đang lưu…" : id ? "Lưu thay đổi" : "Đăng tin"}</button>
        </div>
      </div>
      {sp.get("new") && <div className="alert ok">Tài khoản đã sẵn sàng! Hãy đăng tin tuyển dụng đầu tiên của bạn.</div>}
      <ErrorBox error={err} />
      <div className="layout-main-side">
        <div className="stack">
          <div className="card">
            <h3>Thông tin công việc</h3>
            <div className="field"><label>Tên vị trí *</label><input value={f.title} onChange={set("title")} required placeholder="Ví dụ: Nhân viên kinh doanh, Kế toán tổng hợp…" /></div>
            <div className="field"><label>Mô tả công việc *</label><textarea value={f.description} onChange={set("description")} required style={{ minHeight: 200 }} placeholder="Nhiệm vụ chính, môi trường làm việc, quyền lợi…" /></div>
            <div className="field"><label>Yêu cầu ứng viên</label><textarea value={f.requirements} onChange={set("requirements")} placeholder="Bằng cấp, kinh nghiệm, kỹ năng cần có…" /></div>
          </div>
          <div className="card">
            <h3>Địa điểm & thời hạn</h3>
            <div className="grid grid-3" style={{ gap: 12 }}>
              <div className="field"><label>Bang *</label><select value={f.state} onChange={(e) => setF({ ...f, state: e.target.value, city_key: "" })} required><option value="">—</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}</select></div>
              <div className="field"><label>Thành phố *</label><CitySelect state={f.state} value={f.city_key} onChange={(v) => setF({ ...f, city_key: v || "" })} /></div>
              <div className="field"><label>Mã bưu chính</label><input value={f.zip5} onChange={set("zip5")} maxLength={10} /></div>
            </div>
            <div className="grid grid-2" style={{ gap: 12 }}>
              <div className="field"><label>Ngày đăng</label><input type="date" value={f.start_date} onChange={set("start_date")} /></div>
              <div className="field"><label>Hạn nộp hồ sơ</label><input type="date" value={f.end_date} onChange={set("end_date")} /></div>
            </div>
          </div>
        </div>
        <aside className="card sticky">
          <div className="row between"><h3 style={{ margin: 0 }}>Phân loại</h3><button type="button" className="btn btn-sm btn-outline" onClick={suggest} disabled={!f.title}><Icon name="spark" />Tự động điền</button></div>
          <p className="small text-2">Bấm “Tự động điền” để hệ thống đọc tên vị trí và mô tả rồi gợi ý các mục bên dưới.</p>
          {hint && <div className="alert info small">Đã nhận diện vị trí <b>{hint.occupation || "—"}</b> và {hint.skills.length} kỹ năng.</div>}
          <div className="field"><label>Vị trí chuyên môn</label><OccupationSelect value={f.occupation_code} onChange={(v) => setF({ ...f, occupation_code: v || "" })} tax={tax} /></div>
          <div className="grid grid-2" style={{ gap: 10 }}>
            <div className="field"><label>Hình thức</label><select value={f.job_type} onChange={set("job_type")}><option value="">Không nêu</option>{tax?.job_types.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</select></div>
            <div className="field"><label>Cấp bậc</label><select value={f.seniority} onChange={set("seniority")}><option value="">Không nêu</option>{tax?.seniority.map((s) => <option key={s} value={s}>{SEN_VI[s]}</option>)}</select></div>
            <div className="field"><label>Học vấn tối thiểu</label><select value={f.degree_req} onChange={set("degree_req")}><option value="">Không yêu cầu</option>{tax?.degrees.slice(1).map((d) => <option key={d.ord} value={d.ord}>{d.name}</option>)}</select></div>
            <div className="field"><label>Kinh nghiệm (năm)</label><input type="number" min="0" max="40" step="0.5" value={f.years_req} onChange={set("years_req")} /></div>
          </div>
          <label className="check" style={{ marginBottom: 14 }}><input type="checkbox" checked={f.salary_mentioned} onChange={set("salary_mentioned")} /> Tin có công khai mức lương</label>
          <div className="field">
            <label>Kỹ năng yêu cầu ({f.skills.length})</label>
            <div className="tags" style={{ marginBottom: 8 }}>{f.skills.map((k) => <span key={k} className="tag brand" style={{ cursor: "pointer" }} onClick={() => setF({ ...f, skills: f.skills.filter((x) => x !== k) })}>{skillName[k] || k} ✕</span>)}</div>
            <input placeholder="Gõ để tìm và thêm kỹ năng" value={skillQ} onChange={(e) => setSkillQ(e.target.value)} />
            {skillOpts.length > 0 && <div style={{ marginTop: 8 }}>{skillOpts.map((s) => <span key={s.key} className="chip" onClick={() => { setF({ ...f, skills: [...f.skills, s.key] }); setSkillQ(""); }}>+ {s.name}</span>)}</div>}
          </div>
        </aside>
      </div>
    </form>
  );
}
