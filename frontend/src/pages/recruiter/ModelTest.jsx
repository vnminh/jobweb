import { Fragment, useEffect, useState } from "react";
import { api } from "../../api";
import { useTaxonomy } from "../../taxonomy";
import { Avatar, ErrorBox, Icon, Stat } from "../../components/ui";
import { CitySelect, OccupationSelect } from "../seeker/Profile";

const KIND = { sample: ["Ứng viên giả định", "blue"], applicant: ["Đã ứng tuyển", "brand"], candidate: ["Ứng viên tiềm năng", ""] };
const EMPTY = { label: "", last_occ: "", state: "", city_key: "", total_years_experience: "", degree_ord: "", title: "", managed_others: false };

export default function ModelTest({ jobId }) {
  const tax = useTaxonomy();
  const [nCand, setNCand] = useState(8);
  const [incApps, setIncApps] = useState(true);
  const [personas, setPersonas] = useState([]);
  const [samples, setSamples] = useState([]);
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(null);
  useEffect(() => { api("/meta/samples").then((r) => setSamples(r.seekers)).catch(() => {}); }, []);
  const setP = (i, k, v) => setPersonas(personas.map((p, j) => (j === i ? { ...p, [k]: v } : p)));
  const addSample = (i) => {
    const s = samples[i];
    if (s) setPersonas([...personas, { label: s.label, last_occ: s.last_occ, state: s.state, city_key: s.city_key, total_years_experience: s.total_years_experience,
      degree_ord: s.degree_ord, title: s.history[0] || "", managed_others: s.managed_others }]);
  };
  const run = async () => {
    setBusy(true); setErr(null); setRes(null); setOpen(null);
    try {
      const body = { n_candidates: Number(nCand), include_applicants: incApps, personas: personas.filter((p) => p.city_key).map((p) => ({
        label: p.label || null, last_occ: p.last_occ || null, city_key: p.city_key, title: p.title || null, managed_others: p.managed_others,
        total_years_experience: p.total_years_experience === "" ? null : Number(p.total_years_experience), degree_ord: p.degree_ord === "" ? null : Number(p.degree_ord) })) };
      setRes(await api(`/recruiter/jobs/${jobId}/simulate`, { method: "POST", body }));
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const S = res?.summary;
  return (
    <div className="stack">
      <div className="card">
        <h3>Tin của bạn có đến được đúng ứng viên?</h3>
        <p className="small text-2" style={{ marginTop: 0 }}>
          Hệ thống cho một nhóm ứng viên — giả sử họ đang tìm <b>chính công việc này</b> — trò chuyện với Trợ lý tìm việc, rồi cho bạn biết trợ lý có gợi ý tin
          của bạn cho họ không và sau bao nhiêu câu hỏi. Kết quả giúp bạn đánh giá tin đăng đã đủ rõ ràng (vị trí, kỹ năng, cấp bậc, địa điểm) hay chưa.
        </p>
        <div className="row" style={{ marginBottom: 14 }}>
          <label className="check" style={{ margin: 0 }}>Số ứng viên tiềm năng:
            <select style={{ width: "auto", marginLeft: 6 }} value={nCand} onChange={(e) => setNCand(e.target.value)}>{[0, 5, 8, 15, 25].map((n) => <option key={n}>{n}</option>)}</select>
          </label>
          <label className="check" style={{ margin: 0 }}><input type="checkbox" checked={incApps} onChange={(e) => setIncApps(e.target.checked)} /> Gồm cả ứng viên đã ứng tuyển</label>
        </div>
        <label>Ứng viên giả định (tuỳ chọn)</label>
        {personas.map((p, i) => (
          <div key={i} className="card" style={{ padding: 14, marginBottom: 10, background: "var(--surface-2)", boxShadow: "none" }}>
            <div className="grid grid-3" style={{ gap: 10 }}>
              <div><label>Tên gọi</label><input value={p.label} onChange={(e) => setP(i, "label", e.target.value)} placeholder={`Ứng viên ${i + 1}`} /></div>
              <div><label>Chức danh gần nhất</label><input value={p.title} onChange={(e) => setP(i, "title", e.target.value)} placeholder="Ví dụ: Registered Nurse" /></div>
              <div><label>Vị trí chuyên môn</label><OccupationSelect value={p.last_occ} onChange={(v) => setP(i, "last_occ", v || "")} tax={tax} /></div>
              <div><label>Bang</label><select value={p.state} onChange={(e) => setPersonas(personas.map((q, j) => (j === i ? { ...q, state: e.target.value, city_key: "" } : q)))}><option value="">—</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}</select></div>
              <div><label>Thành phố *</label><CitySelect state={p.state} value={p.city_key} onChange={(v) => setP(i, "city_key", v || "")} /></div>
              <div className="grid grid-2" style={{ gap: 8 }}>
                <div><label>Năm kinh nghiệm</label><input type="number" min="0" max="50" value={p.total_years_experience} onChange={(e) => setP(i, "total_years_experience", e.target.value)} /></div>
                <div><label>Học vấn</label><select value={p.degree_ord} onChange={(e) => setP(i, "degree_ord", e.target.value)}><option value="">—</option>{tax?.degrees.map((d) => <option key={d.ord} value={d.ord}>{d.name}</option>)}</select></div>
              </div>
            </div>
            <div className="row between" style={{ marginTop: 8 }}>
              <label className="check" style={{ margin: 0 }}><input type="checkbox" checked={p.managed_others} onChange={(e) => setP(i, "managed_others", e.target.checked)} /> Từng quản lý nhân sự</label>
              <button className="btn btn-sm btn-ghost" onClick={() => setPersonas(personas.filter((_, j) => j !== i))}>Xoá</button>
            </div>
          </div>
        ))}
        <div className="row">
          <button className="btn btn-sm btn-outline" onClick={() => setPersonas([...personas, { ...EMPTY }])}>+ Thêm ứng viên</button>
          {samples.length > 0 && (
            <select style={{ width: "auto" }} value="" onChange={(e) => addSample(Number(e.target.value))}>
              <option value="">+ Thêm từ hồ sơ mẫu…</option>{samples.map((s, i) => <option key={i} value={i}>{s.label}</option>)}
            </select>
          )}
          <span style={{ flex: 1 }} />
          <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? <><span className="spinner" style={{ borderTopColor: "#fff" }} /> Đang mô phỏng…</> : "Chạy mô phỏng"}</button>
        </div>
      </div>
      <ErrorBox error={err} />
      {res && (
        <>
          <div className="grid grid-4">
            <Stat label="Tin được gợi ý cho" value={`${S.found}/${S.n}`} sub={`${Math.round(S.success_rate * 100)}% ứng viên`} />
            <Stat label="Số lượt trung bình" value={S.avg_turn ? S.avg_turn.toFixed(1) : "—"} sub="để trợ lý tìm ra tin của bạn" />
            <Stat label="Câu hỏi trung bình" value={S.avg_questions.toFixed(1)} sub="mỗi ứng viên" />
            <Stat label="Lọt vào danh sách xem xét" value={`${res.results.filter((r) => r.initial_rank).length}/${S.n}`} sub="ngay từ đầu cuộc trò chuyện" />
          </div>
          <div className="card table-wrap">
            <table>
              <thead><tr><th>Ứng viên</th><th>Kết quả</th><th>Thứ hạng ban đầu</th><th>Số câu hỏi</th><th /></tr></thead>
              <tbody>
                {res.results.map((r, i) => (
                  <Fragment key={i}>
                    <tr>
                      <td><div className="row" style={{ flexWrap: "nowrap" }}><Avatar name={r.label} round /><div><div style={{ fontWeight: 600 }}>{r.label}</div><span className={`tag ${KIND[r.kind][1]}`}>{KIND[r.kind][0]}</span></div></div></td>
                      <td>{r.found ? <span className="tag brand"><Icon name="check" />Được gợi ý ở lượt {r.turn} (vị trí {r.rank}/10)</span> : <span className="tag red">Chưa được gợi ý</span>}</td>
                      <td className="small">{r.initial_rank ? `#${r.initial_rank.toLocaleString("vi-VN")}` : "Chưa lọt vào"}</td>
                      <td>{r.n_questions}</td>
                      <td><button className="btn btn-sm" onClick={() => setOpen(open === i ? null : i)}>{open === i ? "Ẩn" : "Xem hội thoại"}</button></td>
                    </tr>
                    {open === i && (
                      <tr><td colSpan={5} style={{ background: "var(--surface-2)" }}>
                        <ol className="small" style={{ margin: 0, paddingLeft: 18 }}>
                          {r.turns.map((t) => (
                            <li key={t.turn} style={{ marginBottom: 6 }}>
                              <b>{t.type === "rec" ? "Trợ lý gợi ý 10 việc làm" : t.question}</b> → <i>{t.answer}</i>
                              {t.jobs && <div className="muted">{t.jobs.map((j, k) => <span key={k} style={j.is_target ? { color: "var(--brand-dark)", fontWeight: 700 } : {}}>{k + 1}. {j.title}{k < t.jobs.length - 1 ? " · " : ""}</span>)}</div>}
                            </li>
                          ))}
                        </ol>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
