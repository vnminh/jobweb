import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const Ctx = createContext(null);
export const useTaxonomy = () => useContext(Ctx);
export const SEN_VI = { entry: "Mới đi làm", mid: "Nhân viên", senior: "Chuyên viên cao cấp", manager: "Quản lý", executive: "Giám đốc" };
export const STATUS_VI = { submitted: "Đã nộp", viewed: "NTD đã xem", shortlisted: "Phù hợp – mời phỏng vấn", rejected: "Chưa phù hợp", hired: "Đã nhận việc" };

export function TaxonomyProvider({ children }) {
  const [tax, setTax] = useState(null);
  useEffect(() => { api("/meta/taxonomy").then(setTax).catch(() => setTax(null)); }, []);
  return <Ctx.Provider value={tax}>{children}</Ctx.Provider>;
}
