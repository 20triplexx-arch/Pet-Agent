import { useEffect, useRef, useState } from "react";
import { api } from "./api";
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
  const retryRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const run = (fn: (key: string) => Promise<void>, message = "已保存") => {
    const key = crypto.randomUUID();
    const execute = async () => {
      setBusy(true);
      setError("");
      setSuccess("");
      try {
        await fn(key);
        setSuccess(message);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    };
    retryRef.current = execute;
    void execute();
  };
  return { busy, error, success, run, retry: () => void retryRef.current() };
}
