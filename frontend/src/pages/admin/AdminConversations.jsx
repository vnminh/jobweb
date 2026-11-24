import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { ErrorBox, Pager, Spinner } from "../../components/ui";

const ansText = (t) => {
  const a = t.answer, q = t.question;
  if (q.type === "rec") return a ? `chọn việc hạng ${a}` : "không chọn";
  if (Array.isArray(a)) {
    if (q.type === "range") return `${q.options[a[0]]?.label} → ${q.options[a[1]]?.label}`;
    return a.length ? q.options.filter((o) => a.includes(o.id)).map((o) => o.label).join(", ") : "không cái nào";
  }
  if (q.type === "confirm" && typeof a === "number") return `đổi sang ${a}`;
  return { yes: "có", no: "không", whatever: "sao cũng được" }[a] || String(a);
};

export default function AdminConversations() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api("/admin/conversations", { params: { page, size: 20 } }).then(setData).catch(setErr); }, [page]);
  return (
    <>
      <div className="page-head"><div><h1>Phiên tư vấn</h1><p>Các cuộc trò chuyện giữa ứng viên và Trợ lý tìm việc.</p></div></div>
      <ErrorBox error={err} />
      {!data ? <Spinner /> : data.items.length === 0 ? <div className="card empty">Chưa có hội thoại nào.</div> : (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Thời gian</th><th>Người dùng</th><th>Số lượt</th><th>Câu hỏi</th><th>Kết quả</th><th /></tr></thead>
            <tbody>{data.items.map((c) => (
              <Fragment key={c.id}>
                <tr>
                  <td>{new Date(c.started_at).toLocaleString("vi-VN")}</td>
                  <td>{c.seeker}</td>
                  <td>{c.turns}</td>
                  <td>{c.n_questions}</td>
                  <td>{c.success ? <span className="tag brand">Thành công ở lượt {c.success_turn}</span> : <span className="tag">Chưa thành công</span>}
                    {c.accepted_job_id && <div className="small"><Link to={`/jobs/${c.accepted_job_id}`}>Việc #{c.accepted_job_id}</Link></div>}</td>
                  <td><button className="btn btn-sm" onClick={() => setOpen(open === c.id ? null : c.id)}>{open === c.id ? "Ẩn" : "Xem"}</button></td>
                </tr>
                {open === c.id && (
                  <tr key={`${c.id}-t`}><td colSpan={6} style={{ background: "var(--surface-2)" }}>
                    <ol className="small" style={{ margin: 0, paddingLeft: 18 }}>
                      {c.transcript.map((t, i) => <li key={i}><b>{t.question.text}</b> → {ansText(t)}</li>)}
                    </ol>
                  </td></tr>
                )}
              </Fragment>
            ))}</tbody>
          </table>
          <Pager page={page} size={20} total={data.total} onPage={setPage} />
        </div>
      )}
    </>
  );
}
