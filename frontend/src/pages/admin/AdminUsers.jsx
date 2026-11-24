import { useEffect, useState } from "react";
import { api } from "../../api";
import { ErrorBox, Pager, Spinner, fmtDate } from "../../components/ui";

const ROLE_VI = { admin: "Quản trị viên", recruiter: "Nhà tuyển dụng", seeker: "Người tìm việc" };

export default function AdminUsers() {
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => api("/admin/accounts", { params: { q, role, page, size: 25 } }).then(setData).catch(setErr);
  useEffect(() => { load(); }, [role, page]);
  const patch = async (a, body) => {
    try { await api(`/admin/accounts/${a.id}`, { method: "PATCH", body }); load(); } catch (e) { setErr(e); }
  };
  return (
    <div className="layout-main-side">
      <div>
        <div className="page-head"><div><h1>Tài khoản</h1><p>{data ? `${data.total.toLocaleString("vi-VN")} tài khoản` : ""}</p></div></div>
        <ErrorBox error={err} />
        <div className="card">
          <form className="row" style={{ marginBottom: 12 }} onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }}>
            <input style={{ maxWidth: 300 }} placeholder="Email hoặc tên" value={q} onChange={(e) => setQ(e.target.value)} />
            <select style={{ width: "auto" }} value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }}>
              <option value="">Mọi vai trò</option>{Object.entries(ROLE_VI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <button className="btn">Tìm</button>
          </form>
          {!data ? <Spinner /> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Tài khoản</th><th>Vai trò</th><th>Bang</th><th>Tạo lúc</th><th>Trạng thái</th><th /></tr></thead>
              <tbody>{data.items.map((a) => (
                <tr key={a.id}>
                  <td><a href="#" onClick={(e) => { e.preventDefault(); api(`/admin/accounts/${a.id}`).then(setDetail).catch(setErr); }} style={{ fontWeight: 600 }}>{a.company_name || a.full_name}</a><div className="small muted">{a.email}</div></td>
                  <td><span className="tag">{ROLE_VI[a.role]}</span></td>
                  <td>{a.state || "—"}</td>
                  <td>{fmtDate(a.created_at)}</td>
                  <td>{a.active ? <span className="tag brand">Hoạt động</span> : <span className="tag red">Đã khoá</span>}</td>
                  <td>{a.role !== "admin" && <button className="btn btn-sm" onClick={() => patch(a, { active: !a.active })}>{a.active ? "Khoá" : "Mở khoá"}</button>}</td>
                </tr>
              ))}</tbody>
            </table><Pager page={page} size={data.size} total={data.total} onPage={setPage} /></div>
          )}
        </div>
      </div>
      <aside className="card">
        <h3>Chi tiết</h3>
        {!detail ? <p className="small muted">Chọn một tài khoản để xem chi tiết.</p> : (
          <div className="small">
            <div style={{ fontWeight: 700, fontSize: 15 }}>{detail.company_name || detail.full_name}</div>
            <div className="muted">{detail.email} · {ROLE_VI[detail.role]}</div>
            {detail.profile && (
              <dl className="kv" style={{ gridTemplateColumns: "120px 1fr", marginTop: 10 }}>
                <dt>Mã ứng viên</dt><dd>#{detail.profile.id}</dd>
                <dt>Địa điểm</dt><dd>{[detail.profile.city, detail.profile.state].filter(Boolean).join(", ") || "—"}</dd>
                <dt>Học vấn</dt><dd>{detail.profile.degree_label}</dd>
                <dt>Ngành</dt><dd>{detail.profile.major || "—"}</dd>
                <dt>Kinh nghiệm</dt><dd>{detail.profile.total_years_experience ?? "—"} năm</dd>
                <dt>Vị trí gần nhất</dt><dd>{detail.profile.last_occ_name || "—"}</dd>
                <dt>Số đơn</dt><dd>{detail.n_applications}</dd>
                <dt>Lịch sử</dt><dd>{detail.profile.history.map((h) => h.job_title).join(" → ") || "—"}</dd>
              </dl>
            )}
            {detail.n_jobs != null && <p>Số tin tuyển dụng: <b>{detail.n_jobs.toLocaleString("vi-VN")}</b></p>}
          </div>
        )}
      </aside>
    </div>
  );
}
