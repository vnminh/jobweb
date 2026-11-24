import { useEffect, useState } from "react";
import { api } from "../../api";
import { useTaxonomy } from "../../taxonomy";
import { Avatar, ErrorBox, Spinner } from "../../components/ui";

export default function Company() {
  const tax = useTaxonomy();
  const [f, setF] = useState(null);
  const [err, setErr] = useState(null);
  const [ok, setOk] = useState(false);
  useEffect(() => { api("/recruiter/company").then((c) => setF({ name: c.name, state: c.state || "", description: c.description || "" })).catch(setErr); }, []);
  if (!f) return err ? <ErrorBox error={err} /> : <Spinner />;
  const save = async (e) => {
    e.preventDefault(); setErr(null); setOk(false);
    try { await api("/recruiter/company", { method: "PUT", body: { ...f, state: f.state || null } }); setOk(true); } catch (x) { setErr(x); }
  };
  return (
    <form className="card" style={{ maxWidth: 720, margin: "0 auto", padding: 28 }} onSubmit={save}>
      <div className="row" style={{ marginBottom: 18, flexWrap: "nowrap" }}><Avatar name={f.name} size="lg" /><div><h1 style={{ margin: 0 }}>Thông tin công ty</h1><div className="text-2">Thông tin hiển thị với ứng viên trên mọi tin tuyển dụng.</div></div></div>
      <ErrorBox error={err} />
      {ok && <div className="alert ok">Đã lưu thông tin công ty.</div>}
      <div className="field"><label>Tên công ty</label><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
      <div className="field"><label>Trụ sở (bang)</label><select value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })}><option value="">—</option>{tax?.states.map((s) => <option key={s} value={s}>{tax.state_names[s]}</option>)}</select></div>
      <div className="field"><label>Giới thiệu công ty</label><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Lĩnh vực hoạt động, quy mô, văn hoá, phúc lợi…" /></div>
      <button className="btn btn-primary">Lưu thay đổi</button>
    </form>
  );
}
