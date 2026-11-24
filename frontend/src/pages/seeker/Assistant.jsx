import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { Avatar, ErrorBox, Icon, place } from "../../components/ui";

function answerText(step, ans) {
  if (step.type === "binary") return { yes: "Có", no: "Không", whatever: "Sao cũng được" }[ans];
  if (step.type === "choice" || step.type === "hier") {
    if (ans === "whatever") return "Sao cũng được";
    if (!ans.length) return "Không có lựa chọn nào phù hợp";
    return step.options.filter((o) => ans.includes(o.id)).map((o) => o.label).join(", ");
  }
  if (step.type === "range") return ans === "whatever" ? "Cấp bậc nào cũng được" : ans[0] === ans[1] ? step.options[ans[0]].label : `Từ ${step.options[ans[0]].label} đến ${step.options[ans[1]].label}`;
  if (step.type === "confirm") return ans === "yes" ? "Đúng vậy" : `Không, tôi muốn làm ở ${step.state_options.find((s) => s.id === ans)?.label}`;
  if (step.type === "rec") return ans ? `Tôi chọn “${step.jobs.find((j) => j.rank === ans)?.title}”` : "Chưa có việc nào ưng ý";
  return String(ans);
}

function BotMsg({ children }) {
  return <div className="msg-row"><div className="bot-ava"><Icon name="chat" /></div><div className="msg bot">{children}</div></div>;
}

function AnswerBox({ step, onAnswer, busy }) {
  const [sel, setSel] = useState([]);
  const [lo, setLo] = useState(0);
  const [hi, setHi] = useState(4);
  const [other, setOther] = useState("");
  useEffect(() => { setSel([]); setLo(0); setHi(4); setOther(""); }, [step]);
  const toggle = (id) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]);
  if (step.type === "binary") return (
    <div className="row">
      <button className="btn btn-primary" disabled={busy} onClick={() => onAnswer("yes")}>Có</button>
      <button className="btn" disabled={busy} onClick={() => onAnswer("no")}>Không</button>
      <button className="btn btn-ghost" disabled={busy} onClick={() => onAnswer("whatever")}>Sao cũng được</button>
    </div>
  );
  if (step.type === "choice" || step.type === "hier") return (
    <div>
      <div>{step.options.map((o) => <span key={o.id} className={`chip ${sel.includes(o.id) ? "on" : ""}`} onClick={() => toggle(o.id)}>{sel.includes(o.id) && <Icon name="check" />}{o.label}</span>)}</div>
      <div className="row" style={{ marginTop: 4 }}>
        <button className="btn btn-primary" disabled={busy || !sel.length} onClick={() => onAnswer(sel)}>Xác nhận{sel.length ? ` (${sel.length})` : ""}</button>
        <button className="btn" disabled={busy} onClick={() => onAnswer([])}>Không có cái nào</button>
        <button className="btn btn-ghost" disabled={busy} onClick={() => onAnswer("whatever")}>Sao cũng được</button>
      </div>
    </div>
  );
  if (step.type === "range") return (
    <div className="row">
      <span className="small text-2">Từ</span>
      <select style={{ width: "auto" }} value={lo} onChange={(e) => { const v = Number(e.target.value); setLo(v); if (hi < v) setHi(v); }}>{step.options.map((o, i) => <option key={o.id} value={i}>{o.label}</option>)}</select>
      <span className="small text-2">đến</span>
      <select style={{ width: "auto" }} value={hi} onChange={(e) => setHi(Number(e.target.value))}>{step.options.map((o, i) => <option key={o.id} value={i} disabled={i < lo}>{o.label}</option>)}</select>
      <button className="btn btn-primary" disabled={busy} onClick={() => onAnswer([lo, hi])}>Xác nhận</button>
      <button className="btn btn-ghost" disabled={busy} onClick={() => onAnswer("whatever")}>Cấp bậc nào cũng được</button>
    </div>
  );
  if (step.type === "confirm") return (
    <div className="row">
      <button className="btn btn-primary" disabled={busy} onClick={() => onAnswer("yes")}>Đúng vậy</button>
      <span className="small text-2">hoặc tôi muốn làm ở</span>
      <select style={{ width: "auto" }} value={other} onChange={(e) => setOther(e.target.value)}>
        <option value="">— chọn bang —</option>{step.state_options.filter((s) => s.id !== step.attr.id).map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
      </select>
      <button className="btn" disabled={busy || !other} onClick={() => onAnswer(Number(other))}>Chọn</button>
    </div>
  );
  if (step.type === "rec") return (
    <div>
      {step.jobs.map((j) => (
        <div className="rec-item" key={j.id}>
          <Avatar name={j.company || j.title} />
          <div style={{ minWidth: 0 }}>
            <Link to={`/jobs/${j.id}`} target="_blank" style={{ fontWeight: 600, color: "var(--text)" }}>{j.title}</Link>
            <div className="small text-2">{j.company} · {place(j)}</div>
            <div className="small muted">{[j.job_type_label, j.seniority_label, j.occ_group_name].filter(Boolean).join(" · ")}</div>
          </div>
          <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => onAnswer(j.rank)}>Tôi thích việc này</button>
        </div>
      ))}
      <div className="row" style={{ marginTop: 10 }}><button className="btn" disabled={busy} onClick={() => onAnswer(null)}>Chưa ưng ý — hỏi thêm giúp tôi</button></div>
    </div>
  );
  return null;
}

export default function Assistant() {
  const { user } = useAuth();
  const [conv, setConv] = useState(null);
  const [step, setStep] = useState(null);
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [applied, setApplied] = useState(false);
  const end = useRef(null);
  useEffect(() => { if (conv) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [log, step, busy]);

  const start = async () => {
    setBusy(true); setErr(null); setLog([]); setApplied(false); setStep(null);
    try { const r = await api("/assistant/start", { method: "POST" }); setConv(r.conv_id); setStep(r.step); } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const answer = async (ans) => {
    setBusy(true); setErr(null);
    const prev = step;
    setLog((l) => [...l, { step: prev, text: answerText(prev, ans) }]);
    setStep(null);
    try {
      const r = await api(`/assistant/${conv}/answer`, { method: "POST", body: { answer: ans } });
      setStep(r.step);
    } catch (e) { setErr(e); setStep(prev); setLog((l) => l.slice(0, -1)); } finally { setBusy(false); }
  };
  const applyJob = async (id) => {
    try { await api(`/jobs/${id}/apply`, { method: "POST", params: { source: "assistant" } }); setApplied(true); } catch (e) { setErr(e); }
  };
  const done = step?.done;
  const first = !user?.full_name || user.full_name.includes("#") ? "bạn" : user.full_name.split(" ").slice(-1)[0];
  return (
    <div className="layout-main-side">
      <div className="card chat-shell">
        <div className="row between" style={{ marginBottom: 16 }}>
          <div className="row" style={{ flexWrap: "nowrap" }}><div className="bot-ava" style={{ width: 42, height: 42 }}><Icon name="chat" size={22} /></div>
            <div><h2 style={{ margin: 0 }}>Trợ lý tìm việc</h2><div className="small muted">Luôn sẵn sàng giúp bạn tìm đúng công việc</div></div></div>
          {conv && <button className="btn btn-sm" onClick={start} disabled={busy}>Bắt đầu lại</button>}
        </div>
        <ErrorBox error={err} />
        {!conv ? (
          <div className="empty" style={{ margin: "auto 0" }}>
            <div className="bot-ava" style={{ width: 64, height: 64, margin: "0 auto 16px" }}><Icon name="chat" size={32} /></div>
            <h2 style={{ color: "var(--text)" }}>Xin chào {first}!</h2>
            <p style={{ maxWidth: 480, margin: "0 auto 18px" }}>Mình sẽ hỏi bạn vài câu ngắn về công việc mong muốn rồi gợi ý những việc phù hợp nhất. Bạn có thể trả lời "Sao cũng được" nếu chưa chắc.</p>
            <button className="btn btn-primary btn-lg" onClick={start} disabled={busy}>{busy ? "Đang chuẩn bị…" : "Bắt đầu trò chuyện"}</button>
          </div>
        ) : (
          <div className="chat">
            <BotMsg>Chào {first}! Mình đã xem qua hồ sơ của bạn. Cùng tìm công việc phù hợp nhé.</BotMsg>
            {log.map((m, i) => (
              <div key={i} className="chat" style={{ gap: 10 }}>
                <BotMsg>{m.step.text}{m.step.type === "rec" && <div className="small muted" style={{ marginTop: 4 }}>{m.step.jobs.slice(0, 3).map((j) => j.title).join(" · ")}…</div>}</BotMsg>
                <div className="msg-row me"><div className="msg user">{m.text}</div></div>
              </div>
            ))}
            {busy && !step && <BotMsg><span className="typing"><i /><i /><i /></span></BotMsg>}
            {step && !done && (
              <>
                <BotMsg>{step.text}</BotMsg>
                <div className="answer-box"><AnswerBox step={step} onAnswer={answer} busy={busy} /></div>
              </>
            )}
            {done && (
              <BotMsg>
                {step.success ? (
                  <>
                    <b>Tuyệt vời! Chúc mừng bạn đã tìm được công việc ưng ý 🎉</b>
                    {step.accepted_job && (
                      <div className="card row" style={{ marginTop: 10, padding: 12, flexWrap: "nowrap", boxShadow: "none" }}>
                        <Avatar name={step.accepted_job.company || step.accepted_job.title} />
                        <div style={{ minWidth: 0, flex: 1 }}><Link to={`/jobs/${step.accepted_job.id}`} style={{ fontWeight: 600 }}>{step.accepted_job.title}</Link>
                          <div className="small text-2">{step.accepted_job.company} · {place(step.accepted_job)}</div></div>
                        {applied ? <span className="tag brand"><Icon name="check" />Đã ứng tuyển</span> : <button className="btn btn-primary btn-sm" onClick={() => applyJob(step.accepted_job.id)}>Ứng tuyển ngay</button>}
                      </div>
                    )}
                    <div className="row" style={{ marginTop: 10 }}><button className="btn btn-sm" onClick={start}>Tìm thêm việc khác</button></div>
                  </>
                ) : (
                  <>
                    Rất tiếc, lần này mình chưa tìm được việc bạn ưng ý. Bạn có thể bắt đầu lại, cập nhật hồ sơ hoặc tự tìm kiếm.
                    <div className="row" style={{ marginTop: 10 }}><button className="btn btn-sm btn-primary" onClick={start}>Bắt đầu lại</button><Link className="btn btn-sm" to="/jobs">Tìm kiếm việc làm</Link></div>
                  </>
                )}
              </BotMsg>
            )}
            <div ref={end} />
          </div>
        )}
      </div>
      <aside className="stack sticky">
        <div className="card stack">
          <h3 style={{ margin: 0 }}>Tiến trình</h3>
          {step && !done ? (
            <>
              <div><div className="row between small"><span className="text-2">Câu hỏi</span><b>{step.turn} / {step.max_turns}</b></div><div className="progress" style={{ marginTop: 6 }}><div style={{ width: `${(100 * step.turn) / step.max_turns}%` }} /></div></div>
              <div className="small text-2"><Icon name="briefcase" /> Đang chọn lọc trong <b>{step.n_candidates?.toLocaleString("vi-VN")}</b> việc làm phù hợp nhất với bạn</div>
            </>
          ) : <p className="small text-2" style={{ margin: 0 }}>{done ? "Phiên tư vấn đã kết thúc." : "Bấm “Bắt đầu trò chuyện” để bắt đầu."}</p>}
        </div>
        <div className="card">
          <h3>Mẹo để có gợi ý tốt</h3>
          <ul className="small text-2" style={{ paddingLeft: 18, margin: 0 }}>
            <li>Cập nhật đầy đủ <Link to="/profile">hồ sơ</Link>: công việc đã làm, kinh nghiệm, nơi ở.</li>
            <li>Chọn tất cả lựa chọn bạn thấy phù hợp, không chỉ một.</li>
            <li>Chưa chắc chắn? Hãy chọn “Sao cũng được”.</li>
            <li>Mở việc làm trong tab mới để xem chi tiết trước khi chọn.</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
