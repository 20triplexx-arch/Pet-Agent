import { type ReactNode, useId, useLayoutEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, PawPrint, ArrowUpRight } from "./icons";
import { Button } from "./components/ui/button";
import type { FieldIssue, Source } from "./api";
export function Panel({
  children,
  className = "",
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return <section id={id} className={"panel " + className}>{children}</section>;
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
  action: {
    busy: boolean;
    error: string;
    success: string;
    retry: () => void;
    fieldErrors?: FieldIssue[];
    validationRoot?: HTMLElement | null;
  };
}) {
  const id = useId();
  const [targets, setTargets] = useState<
    { host: HTMLElement; id: string; message: string }[]
  >([]);
  useLayoutEffect(() => {
    const root = action.validationRoot;
    if (!action.error || !root?.isConnected || !action.fieldErrors?.length) {
      setTargets([]);
      return;
    }
    const cleanups: (() => void)[] = [];
    const next: typeof targets = [];
    const controls = [
      ...root.querySelectorAll<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >("input[name], select[name], textarea[name]"),
    ];
    for (const [index, issue] of action.fieldErrors.entries()) {
      const path = issue.path.replace(/^profile\./, "");
      const field =
        [...controls].reverse().find((control) => control.name === path) ||
        controls.find((control) => path.startsWith(control.name + "."));
      if (!field) continue;
      const errorId = `${id}-field-${index}`;
      const previousInvalid = field.getAttribute("aria-invalid");
      const previousDescription = field.getAttribute("aria-describedby");
      const previousLabel = field.getAttribute("aria-label");
      const labelText = [...(field.labels?.[0]?.childNodes || [])]
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent)
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (!previousLabel && labelText) field.setAttribute("aria-label", labelText);
      const host = document.createElement("span");
      host.className = "field-error-host";
      // The explicit description remains readable without changing the label's name.
      host.setAttribute("aria-hidden", "true");
      field.after(host);
      field.setAttribute("aria-invalid", "true");
      field.setAttribute(
        "aria-describedby",
        [previousDescription, errorId].filter(Boolean).join(" "),
      );
      next.push({ host, id: errorId, message: issue.message });
      cleanups.push(() => {
        host.remove();
        for (const [attribute, previous] of [
          ["aria-invalid", previousInvalid],
          ["aria-describedby", previousDescription],
          ["aria-label", previousLabel],
        ]) {
          if (previous === null) field.removeAttribute(attribute!);
          else field.setAttribute(attribute!, previous!);
        }
      });
    }
    setTargets(next);
    const first = controls.find(
      (control) => control.getAttribute("aria-invalid") === "true",
    );
    if (first) {
      const details = first.closest("details");
      if (details) details.open = true;
      first.scrollIntoView({ block: "center", behavior: "instant" });
      first.focus({ preventScroll: true });
    }
    return () => cleanups.forEach((cleanup) => cleanup());
  }, [action.error, action.fieldErrors, action.validationRoot, id]);
  return (
    <>
      {targets.map((target) =>
        createPortal(
          <span id={target.id} className="field-error">
            {target.message}
          </span>,
          target.host,
          target.id,
        ),
      )}
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
    <details className="sources">
      <summary>本次实际检索来源 · {items.length} 条</summary>
        {items.map((s) => (
          <div key={s.id} className="source-entry">
          <a href={s.url} target="_blank" rel="noreferrer">
          {s.title}{" "}
          <span>
            · {s.organization} <ArrowUpRight size={14} />
          </span>
        </a>
          {s.sections?.map((heading) => <Link key={heading} to={`/knowledge/${s.id}#${encodeURIComponent(heading)}`} className="source-section">查看章节：{heading}</Link>)}
          {!!s.evidence?.length && <details className="source-evidence"><summary>核对本地知识片段</summary>{s.evidence.map(e => <div key={e.heading}><strong>{e.heading}</strong><p>{e.text}</p></div>)}<small>片段来自本次实际检索的中文摘要，未经兽医审核；片段匹配不代表整段回答已获专业核实。</small></details>}
          </div>
      ))}
    </details>
  ) : null;
}
export function PageTitle({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {desc && <p>{desc}</p>}
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
            {heading && <h2 id={heading}>{heading}</h2>}
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
