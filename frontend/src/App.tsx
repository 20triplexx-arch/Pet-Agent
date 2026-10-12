import { createContext, useContext, useEffect, useState, useRef } from "react";
import {
  Routes,
  Route,
  NavLink,
  useNavigate,
  useLocation,
} from "react-router-dom";
import {
  PawPrint,
  House,
  Cat,
  MessageCircle,
  BookOpen,
  CalendarCheck,
  ChartNoAxesCombined,
  Settings,
  LogOut,
  ChevronDown,
  DotsThree,
  X,
} from "./icons";
import { Button } from "./components/ui/button";
import { api, login, token, type User, type Pet, petLabel } from "./api";
import { useRemote, useAction } from "./hooks";
import { State, Feedback, Panel, PetArtwork, PetPortrait } from "./components";
import { Products } from "./product-page";
import {
  Home,
  Pets,
  Chat,
  Knowledge,
  Plans,
  Logs,
  SettingsPage,
} from "./pages";
import { Nutrition, Hospitals } from "./care-pages";
type Context = {
  user: User;
  pet: Pet | null;
  pets: Pet[];
  refresh: () => void;
  refreshUser: () => void;
  logout: () => void;
};
const Ctx = createContext<Context | null>(null);
export function useApp() {
  return useContext(Ctx)!;
}
const nav = [
  ["/", "首页", House],
  ["/pets", "宠物档案", Cat],
  ["/chat", "AI 对话", MessageCircle],
  ["/knowledge", "知识库", BookOpen],
  ["/plans", "计划与提醒", CalendarCheck],
  ["/logs", "照护记录", ChartNoAxesCombined],
  ["/settings", "账户与设置", Settings],
] as const;
function Login({ done }: { done: () => void }) {
  const [signup, setSignup] = useState(false),
    [email, setEmail] = useState("demo@example.com"),
    [password, setPassword] = useState("Chongban2026!"),
    [name, setName] = useState("");
  const action = useAction();
  return (
    <div className="login-page">
      <div className="login-intro">
        <div className="brand">
          <span className="brand-mark">
            <PawPrint />
          </span>
          宠伴
        </div>
        <h1>照顾它的每一天。</h1>
        <p>档案、照护计划和日常记录，在这里慢慢积累。</p>
        <div className="pet-art">
          <PetArtwork />
        </div>
      </div>
      <Panel>
        <h2>{signup ? "建立你的宠伴账户" : "欢迎回到宠伴"}</h2>
        <p className="muted">
          {signup
            ? "创建账户，保存你的宠物与照护记录。"
            : "登录，继续今天的照护。"}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            action.run(async () => {
              if (signup)
                await api("/users/signup", "POST", {
                  email,
                  password,
                  full_name: name,
                });
              await login(email, password);
              done();
            }, "登录成功");
          }}
        >
          {signup && (
            <label>
              昵称
              <input
                name="full_name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={60}
              />
            </label>
          )}
          <label>
            邮箱
            <input
              name="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            密码
            <input
              name="password"
              type="password"
              required
              minLength={8}
              autoComplete={signup ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button className="primary wide" disabled={action.busy} type="submit">
            {signup ? "注册并登录" : "登录"}
          </Button>
        </form>
        <Feedback action={action} />
        <Button className="text-button" onClick={() => setSignup(!signup)}>
          {signup ? "已有账户？去登录" : "没有账户？创建账户"}
        </Button>
        <div className="note">
          示例账户仅供本机体验：demo@example.com
          <br />
          密码：Chongban2026!
          <br />
          首次启动请先执行数据库初始化。
        </div>
      </Panel>
    </div>
  );
}
export default function App() {
  const [authed, setAuthed] = useState(!!token()),
    [pid, setPid] = useState(sessionStorage.getItem("chongban_pet") || "");
  const user = useRemote<User>(authed ? "/users/me" : null),
    pets = useRemote<Pet[]>(authed ? "/pets" : null),
    status = useRemote<{ mode: string }>(authed ? "/status" : null);
  const navigate = useNavigate();
  const location = useLocation();
  const moreDialog = useRef<HTMLDialogElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  useEffect(() => {
    const dialog = moreDialog.current;
    if (moreOpen && dialog && !dialog.open) dialog.showModal();
    if (!moreOpen && dialog?.open) dialog.close();
  }, [moreOpen]);
  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname, authed]);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 768px)");
    const closeOnDesktop = () => {
      if (query.matches) setMoreOpen(false);
    };
    query.addEventListener("change", closeOnDesktop);
    return () => query.removeEventListener("change", closeOnDesktop);
  }, []);
  useEffect(() => {
    const handler = () => setAuthed(false);
    window.addEventListener("auth-expired", handler);
    return () => window.removeEventListener("auth-expired", handler);
  }, []);
  useEffect(() => {
    if (pets.data && pid && !pets.data.some((p) => p.id === pid)) {
      setPid("");
      sessionStorage.removeItem("chongban_pet");
    }
  }, [pets.data, pid]);
  if (!authed)
    return (
      <Login
        done={() => {
          setAuthed(true);
          setPid("");
          navigate("/");
        }}
      />
    );
  if (!user.data || !pets.data)
    return (
      <div className="initial">
        <State
          loading={user.loading || pets.loading}
          error={user.error || pets.error}
          retry={() => {
            user.reload();
            pets.reload();
          }}
        />
        <Button
          onClick={() => {
            sessionStorage.removeItem("chongban_token");
            setAuthed(false);
          }}
        >
          返回登录
        </Button>
      </div>
    );
  const pet = pets.data.find((p) => p.id === pid) || null;
  const context = {
    user: user.data,
    pet,
    pets: pets.data,
    refresh: pets.reload,
    refreshUser: user.reload,
    logout: () => {
      sessionStorage.removeItem("chongban_token");
      sessionStorage.removeItem("chongban_pet");
      setPid("");
      setAuthed(false);
      navigate("/");
    },
  };
  return (
    <Ctx.Provider value={context}>
      <div className="app">
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <aside className="sidebar">
          <NavLink to="/" className="brand">
            <span className="brand-mark">
              <PawPrint />
            </span>
            <span>宠伴</span>
          </NavLink>
          <nav aria-label="主要导航">
            {nav.map(([path, label, Icon], i) => (
              <NavLink
                key={path}
                to={path}
                end={path === "/"}
                aria-label={label}
                className={({ isActive }) =>
                  isActive ? "nav-item active" : "nav-item"
                }
              >
                <Icon size={19} />
                <span className="nav-label">{label}</span>
                <span className="nav-short" aria-hidden="true">
                  {["首页", "档案", "问答", "知识", "计划", "记录", "设置"][i]}
                </span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="account">
              <span className="avatar">{user.data.full_name[0] || "宠"}</span>
              <div>
                {user.data.full_name || "宠伴用户"}
                <small>本地账户</small>
              </div>
              <button aria-label="退出登录" onClick={context.logout}>
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <NavLink className="mobile-brand" to="/" aria-label="宠伴首页">
              <PawPrint size={24} />
              <span>宠伴</span>
            </NavLink>
            <span className="desktop-greeting">你的照护空间</span>
            <div className="top-right">
              <span
                className={
                  status.data?.mode === "live" ? "badge green" : "badge"
                }
              >
                {status.error
                  ? "模式读取失败"
                  : !status.data
                    ? "读取模式…"
                    : status.data.mode === "live"
                      ? "真实模型模式"
                      : status.data.mode === "configuration_error"
                        ? "模型配置待补充"
                        : "演示模式"}
              </span>
              <div className="pet-switch">
                {pet ? (
                  <PetPortrait species={pet.species} />
                ) : (
                  <PawPrint size={18} />
                )}
                <select
                  aria-label="当前宠物"
                  value={pid}
                  onChange={(e) => {
                    setPid(e.target.value);
                    sessionStorage.setItem("chongban_pet", e.target.value);
                    if (location.pathname === "/knowledge") navigate("/knowledge", {replace:true});
                  }}
                >
                  <option value="">普通知识 · 未选择宠物</option>
                  {pets.data.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} · {petLabel(p)}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} />
              </div>
            </div>
          </header>
          <main key={pid} id="main-content" tabIndex={-1}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/pets" element={<Pets />} />
              <Route path="/chat" element={<Chat />} />
              <Route path="/knowledge" element={<Knowledge />} />
              <Route path="/knowledge/:id" element={<Knowledge />} />
              <Route path="/plans" element={<Plans />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/nutrition" element={<Nutrition />} />
              <Route path="/hospitals" element={<Hospitals />} />
              <Route path="/products" element={<Products />} />
              <Route path="*" element={<Home />} />
            </Routes>
          </main>
          <footer>宠伴 · 首版支持猫与狗　健康建议用于观察和就医准备</footer>
        </div>
        <nav className="mobile-nav" aria-label="手机主要导航">
          {[
            ["/", "首页", House],
            ["/chat", "AI对话", MessageCircle],
            ["/plans", "计划", CalendarCheck],
            ["/knowledge", "知识", BookOpen],
          ].map(([path, label, Icon]) => {
            const Glyph = Icon as typeof House;
            return (
              <NavLink
                key={path as string}
                to={path as string}
                end={path === "/"}
                className={({ isActive }) =>
                  "mobile-nav-item" + (isActive ? " active" : "")
                }
              >
                <Glyph size={23} />
                <span>{label as string}</span>
              </NavLink>
            );
          })}
          <button
            ref={moreButton}
            className={
              "mobile-nav-item" +
              ([
                "/pets",
                "/logs",
                "/settings",
                "/nutrition",
                "/hospitals",
              ].includes(location.pathname)
                ? " active"
                : "")
            }
            aria-haspopup="dialog"
            aria-controls="more-navigation"
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen(true)}
          >
            <DotsThree size={24} />
            <span>更多</span>
          </button>
        </nav>
        <dialog
          id="more-navigation"
          ref={moreDialog}
          className="more-dialog"
          aria-labelledby="more-title"
          onCancel={() => setMoreOpen(false)}
          onClose={() => {
            setMoreOpen(false);
            moreButton.current?.focus();
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setMoreOpen(false);
          }}
        >
          <div className="more-sheet">
            <div className="section-heading">
              <h2 id="more-title">更多</h2>
              <Button
                aria-label="关闭更多"
                onClick={() => setMoreOpen(false)}
                autoFocus
              >
                <X size={20} />
              </Button>
            </div>
            <nav aria-label="更多导航">
              {nav
                .filter(([path]) =>
                  ["/pets", "/logs", "/settings"].includes(path),
                )
                .map(([path, label, Icon]) => (
                  <NavLink
                    key={path}
                    to={path}
                    onClick={() => setMoreOpen(false)}
                    className={({ isActive }) =>
                      "more-link" + (isActive ? " active" : "")
                    }
                  >
                    <Icon size={22} />
                    <span>{label}</span>
                  </NavLink>
                ))}
            </nav>
          </div>
        </dialog>
      </div>
    </Ctx.Provider>
  );
}
