import { type ReactNode } from "react";
import { AlertCircle, CheckCircle2, PawPrint } from "lucide-react";
import { Button } from "./components/ui/button";
import type { Source } from "./api";
export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={"panel " + className}>{children}</section>;
}
export function State({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error: string;
  retry: () => void;
}) {
  return loading ? (
    <div className="state" role="status">
      <span className="loading-paws" aria-hidden="true">
        <PawPrint size={20} />
      </span>
      <span>
        正在读取…
        <span className="loading-track" aria-hidden="true" />
      </span>
    </div>
  ) : error ? (
    <div className="alert" role="alert">
      <AlertCircle size={20} />
      <span>{error}</span>
      <Button onClick={retry}>重试</Button>
    </div>
  ) : null;
}
export function Feedback({
  action,
}: {
  action: { busy: boolean; error: string; success: string; retry: () => void };
}) {
  return (
    <>
      {action.busy && (
        <div className="mutating" role="status">
          正在处理，请稍候…
        </div>
      )}
      {action.error && (
        <div className="alert" role="alert">
          <AlertCircle size={18} />
          <span>{action.error}</span>
          <Button disabled={action.busy} onClick={action.retry}>
            重试本次请求
          </Button>
        </div>
      )}
      {action.success && (
        <div className="success" role="status">
          <CheckCircle2 size={18} />
          {action.success}
        </div>
      )}
    </>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <PetArtwork className="empty-art" />
      <p>{children}</p>
    </div>
  );
}
export function Sources({ items }: { items: Source[] }) {
  return items.length ? (
    <div className="sources">
      <small>本次实际检索来源</small>
      {items.map((s) => (
        <a key={s.id} href={s.url} target="_blank" rel="noreferrer">
          {s.title} <span>· {s.organization} ↗</span>
        </a>
      ))}
    </div>
  ) : null;
}
export function PageTitle({
  title,
  desc,
  children,
}: {
  eyebrow: string;
  title: string;
  desc: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
      {children}
    </div>
  );
}

export function PetArtwork({ className = "" }: { className?: string }) {
  return (
    <img
      className={"pet-artwork " + className}
      src="/assets/pet-companions.webp"
      alt=""
      width={960}
      height={640}
      draggable={false}
    />
  );
}

export function ArticleContent({ body }: { body: string }) {
  return (
    <div className="article-body">
      {body.split(/\n\s*\n/).map((block, index) => {
        const lines = block.trim().split("\n");
        const heading = lines[0]?.startsWith("## ")
          ? lines.shift()!.slice(3)
          : null;
        const steps =
          lines.length > 0 && lines.every((line) => /^\d+\.\s/.test(line));
        return (
          <section key={index}>
            {heading && <h2>{heading}</h2>}
            {steps ? (
              <ol>
                {lines.map((line, step) => (
                  <li key={step}>{line.replace(/^\d+\.\s/, "")}</li>
                ))}
              </ol>
            ) : lines.length > 0 ? (
              <p>{lines.join("\n")}</p>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

export function PetPortrait({ species }: { species: string }) {
  return (
    <span
      className={
        "pet-portrait " + (species === "dog" ? "portrait-dog" : "portrait-cat")
      }
      aria-hidden="true"
    >
      {["cat", "dog"].includes(species) ? (
        <img
          className="pet-artwork"
          src={`/assets/pet-portrait-${species}.webp`}
          alt=""
          width={512}
          height={512}
          draggable={false}
        />
      ) : (
        <PawPrint size={32} />
      )}
    </span>
  );
}
