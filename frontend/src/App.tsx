import { createContext, useContext, useEffect, useState } from "react";
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
} from "lucide-react";
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
        <h1>
          把每一天的小事，
          <br />
          变成更好的陪伴。
        </h1>
        <p>
          懂一点它的需要，多一点照护的从容。
          <br />
          从一份档案开始，和宠伴一起照顾猫猫狗狗。
        </p>
        <div className="pet-art">
          <PetArtwork />
          <span>让照护有据可依</span>
        </div>
      </div>
      <Panel>
        <h2>{signup ? "建立你的宠伴账户" : "欢迎回到宠伴"}</h2>
        <p className="muted">从这里开始，照顾它的每一天。</p>
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
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={60}
              />
            </label>
          )}
          <label>
            邮箱
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            密码
            <input
              type="password"
              required
              minLength={8}
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
            <span>
              宠伴<small>每一天，有我陪伴</small>
            </span>
          </NavLink>
          <div className="nav-caption">我的照护空间</div>
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
            <div className="soft-card">
              <span>
                一点点记录
                <br />
                看见每天的变化
              </span>
              <PetArtwork />
            </div>
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
            <div className="top-label">
              <span>我的照护空间</span>
              <ChevronDown size={13} className="breadcrumb-chevron" />
              <strong>
                {{ "/nutrition": "营养管理", "/hospitals": "医院与就医资料", "/products": "产品比较" }[
                  location.pathname
                ] ||
                  nav.find(
                    ([path]) =>
                      path === location.pathname ||
                      (path !== "/" && location.pathname.startsWith(path)),
                  )?.[1] ||
                  "首页"}
              </strong>
            </div>
            <div className="top-right">
              <span
                className={
                  status.data?.mode === "live" ? "badge green" : "badge"
                }
              >
                {status.data?.mode === "live" ? "已连接模型" : "演示模式"}
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
      </div>
    </Ctx.Provider>
  );
}
