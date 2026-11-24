import { useEffect } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import { Avatar, Spinner } from "./components/ui";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Jobs from "./pages/seeker/Jobs";
import JobDetail from "./pages/seeker/JobDetail";
import Assistant from "./pages/seeker/Assistant";
import Applications from "./pages/seeker/Applications";
import Profile from "./pages/seeker/Profile";
import RecruiterJobs from "./pages/recruiter/RecruiterJobs";
import JobForm from "./pages/recruiter/JobForm";
import Applicants from "./pages/recruiter/Applicants";
import Company from "./pages/recruiter/Company";
import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminJobs from "./pages/admin/AdminJobs";
import AdminConversations from "./pages/admin/AdminConversations";

const ROLE_VI = { admin: "Quản trị viên", recruiter: "Nhà tuyển dụng", seeker: "Ứng viên" };
const LINKS = {
  guest: [["/jobs", "Việc làm"], ["/assistant", "Trợ lý tìm việc"], ["/register?role=recruiter", "Nhà tuyển dụng"]],
  seeker: [["/jobs", "Việc làm"], ["/assistant", "Trợ lý tìm việc"], ["/applications", "Việc đã ứng tuyển"], ["/profile", "Hồ sơ của tôi"]],
  recruiter: [["/recruiter", "Quản lý tin đăng"], ["/recruiter/jobs/new", "Đăng tin mới"], ["/recruiter/company", "Thông tin công ty"]],
  admin: [["/admin", "Tổng quan"], ["/admin/users", "Tài khoản"], ["/admin/jobs", "Tin tuyển dụng"], ["/admin/conversations", "Phiên tư vấn"]],
};

function Nav() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const links = LINKS[user?.role || "guest"];
  return (
    <header className="nav">
      <div className="nav-inner">
        <Link to="/" className="brand"><span className="logo">J</span><span>Job<b>Web</b></span></Link>
        <nav className="nav-links">{links.map(([to, label]) => <NavLink key={to} to={to} end>{label}</NavLink>)}</nav>
        <div className="nav-user">
          {user ? (
            <>
              <div className="user-chip">
                <Avatar name={user.company_name || user.full_name} round />
                <div className="who"><b style={{ color: "var(--text)" }}>{user.company_name || user.full_name}</b><small>{ROLE_VI[user.role]}</small></div>
              </div>
              <button className="btn btn-sm" onClick={() => { logout(); nav("/"); }}>Đăng xuất</button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-sm btn-outline">Đăng nhập</Link>
              <Link to="/register" className="btn btn-sm btn-primary">Đăng ký</Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div>
          <div className="brand"><span className="logo">J</span><span>Job<b>Web</b></span></div>
          <p style={{ margin: 0 }}>Nền tảng kết nối ứng viên và nhà tuyển dụng, với trợ lý tìm việc giúp bạn tìm đúng công việc chỉ sau vài câu trả lời.</p>
        </div>
        <div><h4>Ứng viên</h4><Link to="/jobs">Tìm việc làm</Link><Link to="/assistant">Trợ lý tìm việc</Link><Link to="/profile">Hồ sơ của tôi</Link></div>
        <div><h4>Nhà tuyển dụng</h4><Link to="/register?role=recruiter">Đăng ký tài khoản</Link><Link to="/recruiter/jobs/new">Đăng tin tuyển dụng</Link><Link to="/recruiter">Quản lý ứng viên</Link></div>
        <div><h4>Hỗ trợ</h4><a href="mailto:support@jobweb.demo">support@jobweb.demo</a><span>Thứ 2 – Thứ 6, 8:00 – 17:30</span></div>
      </div>
      <div className="footer-bottom">© {new Date().getFullYear()} JobWeb. Bảo lưu mọi quyền.</div>
    </footer>
  );
}

function Guard({ role, children }) {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <Spinner />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname)}`} replace />;
  if (role && user.role !== role) return <Navigate to="/" replace />;
  return children;
}

function HomeRoute() {
  const { user, ready } = useAuth();
  if (!ready) return <Spinner />;
  if (user?.role === "recruiter") return <Navigate to="/recruiter" replace />;
  if (user?.role === "admin") return <Navigate to="/admin" replace />;
  return <Home />;
}

function ScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

export default function App() {
  return (
    <>
      <ScrollTop />
      <Nav />
      <main className="container">
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/assistant" element={<Guard role="seeker"><Assistant /></Guard>} />
          <Route path="/applications" element={<Guard role="seeker"><Applications /></Guard>} />
          <Route path="/profile" element={<Guard role="seeker"><Profile /></Guard>} />
          <Route path="/recruiter" element={<Guard role="recruiter"><RecruiterJobs /></Guard>} />
          <Route path="/recruiter/jobs/new" element={<Guard role="recruiter"><JobForm /></Guard>} />
          <Route path="/recruiter/jobs/:id/edit" element={<Guard role="recruiter"><JobForm /></Guard>} />
          <Route path="/recruiter/jobs/:id" element={<Guard role="recruiter"><Applicants /></Guard>} />
          <Route path="/recruiter/company" element={<Guard role="recruiter"><Company /></Guard>} />
          <Route path="/admin" element={<Guard role="admin"><AdminDashboard /></Guard>} />
          <Route path="/admin/users" element={<Guard role="admin"><AdminUsers /></Guard>} />
          <Route path="/admin/jobs" element={<Guard role="admin"><AdminJobs /></Guard>} />
          <Route path="/admin/conversations" element={<Guard role="admin"><AdminConversations /></Guard>} />
          <Route path="*" element={<div className="empty">Không tìm thấy trang.</div>} />
        </Routes>
      </main>
      <Footer />
    </>
  );
}
