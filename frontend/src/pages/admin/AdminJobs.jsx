import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { ErrorBox, Pager, Spinner, fmtDate } from "../../components/ui";

export default function AdminJobs() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => api("/admin/jobs", { params: { q, status, source, page, size: 25 } }).then(setData).catch(setErr);
  useEffect(() => { load(); }, [status, source, page]);
  const toggle = async (j) => {
    try { await api(`/admin/jobs/${j.id}/status`, { method: "POST", body: { status: j.status === "open" ? "closed" : "open" } }); load(); } catch (e) { setErr(e); }
  };
  return (
    <>
      <div className="page-head"><div><h1>Tin tuyển dụng</h1><p>{data ? `${data.total.toLocaleString("vi-VN")} tin` : ""} — đóng tin sẽ loại tin khỏi gợi ý của trợ lý ngay lập tức.</p></div></div>
      <ErrorBox error={err} />
      <div className="card">
        <form className="row" style={{ marginBottom: 12 }} onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }}>
          <input style={{ maxWidth: 300 }} placeholder="Chức danh" value={q} onChange={(e) => setQ(e.target.value)} />
          <select style={{ width: "auto" }} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">Mọi trạng thái</option><option value="open">Đang mở</option><option value="closed">Đã đóng</option></select>
          <select style={{ width: "auto" }} value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }}><option value="">Mọi nguồn</option><option value="dataset">Tin hệ thống</option><option value="web">Nhà tuyển dụng tự đăng</option></select>
          <button className="btn">Tìm</button>
        </form>
        {!data ? <Spinner /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Mã</th><th>Chức danh</th><th>Nhà tuyển dụng</th><th>Địa điểm</th><th>Ngày đăng</th><th>Nguồn</th><th>Trạng thái</th><th /></tr></thead>
            <tbody>{data.items.map((j) => (
              <tr key={j.id}>
                <td className="small muted">{j.id}</td>
                <td><Link to={`/jobs/${j.id}`}>{j.title}</Link><div className="small muted">{j.occupation || ""}</div></td>
                <td className="small">{j.company}</td>
                <td>{[j.city, j.state].filter(Boolean).join(", ")}</td>
                <td>{fmtDate(j.start_date)}</td>
                <td><span className={`tag ${j.source === "web" ? "new" : ""}`}>{j.source === "web" ? "Tự đăng" : "Hệ thống"}</span></td>
                <td>{j.status === "open" ? <span className="tag brand">Đang tuyển</span> : <span className="tag red">Đã đóng</span>}</td>
                <td><button className="btn btn-sm" onClick={() => toggle(j)}>{j.status === "open" ? "Đóng" : "Mở lại"}</button></td>
              </tr>
            ))}</tbody>
          </table><Pager page={page} size={data.size} total={data.total} onPage={setPage} /></div>
        )}
      </div>
    </>
  );
}
