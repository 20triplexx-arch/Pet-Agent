import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError, type FieldIssue } from "./api";
export function useEditorFocus(open: boolean) {
  const formRef = useRef<HTMLFormElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const [request, setRequest] = useState(0);
  useLayoutEffect(() => {
    if (!open || !formRef.current) return;
    formRef.current
      .closest("section")
      ?.scrollIntoView({ block: "start", behavior: "instant" });
    formRef.current
      .querySelector<HTMLElement>("input, select, textarea")
      ?.focus({ preventScroll: true });
  }, [open, request]);
  return {
    formRef,
    beginEditing: (trigger: HTMLElement) => {
      triggerRef.current = trigger;
      setRequest((value) => value + 1);
    },
    returnFocus: () =>
      requestAnimationFrame(() => {
        if (triggerRef.current?.isConnected) triggerRef.current.focus();
      }),
  };
}
export function useRemote<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(!!path),
    [version, setVersion] = useState(0);
  const loadedPath = useRef<string | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    if (loadedPath.current !== path) {
      setData(null);
      loadedPath.current = path;
    }
    setError("");
    setLoading(!!path);
    if (path)
      api<T>(path, "GET", undefined, undefined, ctl.signal)
        .then(setData)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        })
        .finally(() => {
          if (!ctl.signal.aborted) setLoading(false);
        });
    return () => ctl.abort();
  }, [path, version]);
  return {
    data: loadedPath.current === path ? data : null,
    error,
    loading,
    reload: () => setVersion((v) => v + 1),
  };
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldIssue[]>([]);
  const [validationRoot, setValidationRoot] = useState<HTMLElement | null>(
    null,
  );
  const retryRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const run = (
    fn: (key: string) => Promise<void>,
    message = "已保存",
    validationScope?: HTMLElement | null,
  ) => {
    const key = crypto.randomUUID();
    const root =
      validationScope ||
      document.activeElement?.closest<HTMLElement>("form, .panel") ||
      null;
    const execute = async () => {
      setBusy(true);
      setError("");
      setSuccess("");
      setFieldErrors([]);
      setValidationRoot(root);
      try {
        await fn(key);
        setSuccess(message);
      } catch (e) {
        setError((e as Error).message);
        setFieldErrors(e instanceof ApiError ? e.fields : []);
      } finally {
        setBusy(false);
      }
    };
    retryRef.current = execute;
    void execute();
  };
  return {
    busy,
    error,
    success,
    run,
    fieldErrors,
    validationRoot,
    retry: () => void retryRef.current(),
  };
}
