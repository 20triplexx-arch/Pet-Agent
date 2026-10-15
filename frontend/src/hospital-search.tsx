import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api";
import type { HospitalResult, Region, RegionResult } from "./care-api";
import { Button } from "./components/ui/button";
import { MapPin } from "./icons";

export function RegionInput({ label, value, onChange, onSelect, parent, city, kind, required = false, enabled = false }: {
  label: string; value: string; onChange: (value: string) => void; onSelect: (region: Region) => void;
  parent?: Region | null; city?: string; kind?: "street"; required?: boolean; enabled?: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [data, setData] = useState<RegionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const districtMode = city !== undefined;
  const streetMode = kind === "street";
  const keyword = districtMode ? parent?.adcode || city!.trim() : value.trim();
  useEffect(() => {
    setData(null); setError(""); setActive(-1); setBusy(false);
    if (!open || !enabled || keyword.length < 2) return;
    const controller = new AbortController();
    setBusy(true);
    const timer = setTimeout(() => {
      api<RegionResult>(`/hospitals/regions?keywords=${encodeURIComponent(keyword)}`, "GET", undefined, undefined, controller.signal)
        .then(result => { if (!controller.signal.aborted) setData(result); })
        .catch(e => { if (e.name !== "AbortError") setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }, districtMode ? 0 : 600);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [keyword, open, enabled, retry, districtMode]);
  const options = (data?.regions ?? []).flatMap(region => {
    if (streetMode) return region.children.filter(child => child.level === "street");
    if (districtMode) return region.level === "district" ? [region] : region.children.filter(child => child.level === "district");
    if (region.level === "province" && !["110000", "120000", "310000", "500000"].includes(region.adcode)) return region.children;
    return [region];
  }).filter(region => !districtMode || !value.trim() || region.name.includes(value.trim()));
  const unique = options.filter((region, index) => options.findIndex(item => item.adcode === region.adcode && item.name === region.name) === index);
  const choose = (region: Region) => { onSelect(region); setOpen(false); setActive(-1); input.current?.focus(); };
  return <div className="region-field" onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <label htmlFor={id}>{label}</label>
    <input id={id} ref={input} name={streetMode ? "street" : districtMode ? "district" : "city"} value={value} maxLength={80}
      role="combobox" aria-autocomplete="list" aria-expanded={open && enabled && keyword.length >= 2}
      aria-controls={`${id}-options`} aria-activedescendant={active >= 0 && unique[active] ? `${id}-option-${active}` : undefined}
      aria-describedby={`${id}-hint`} placeholder={streetMode ? "例如：天彭街道" : districtMode ? "例如：彭州市" : "例如：四川省 / 成都市"}
      required={required} autoComplete="off" onFocus={() => setOpen(true)}
      onChange={event => { onChange(event.target.value); setOpen(true); setActive(-1); }}
      onKeyDown={event => {
        if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault(); setOpen(true);
          setActive(current => unique.length ? (current + (event.key === "ArrowDown" ? 1 : -1) + unique.length) % unique.length : -1);
        }
        if (event.key === "Enter" && open && active >= 0 && unique[active]) { event.preventDefault(); choose(unique[active]); }
      }} />
    <p id={`${id}-hint`} className="small muted region-hint">{streetMode ? "选定区县后，继续选择所属街道/乡镇" : districtMode ? "选定城市后，可选择所属区县" : "可先输入省份，再选择下方城市"}</p>
    {open && enabled && keyword.length >= 2 && <div className="region-dropdown">
      {busy && <p role="status">正在查找区域…</p>}
      {!busy && <>
        {unique.length > 0 && <p className="small muted">{streetMode ? "所属街道 / 乡镇" : districtMode ? "所属区县" : data?.regions.some(region => region.level === "province") ? "选择下属城市" : "匹配的城市"}</p>}
        <div id={`${id}-options`} role="listbox" aria-label={`${label}候选`}>
          {unique.map((region, index) => <button type="button" role="option" tabIndex={-1} id={`${id}-option-${index}`} key={`${region.adcode}-${region.name}`}
            aria-selected={active === index} onMouseDown={event => event.preventDefault()} onClick={() => choose(region)}>
            <span>{region.name}</span><span className="small muted">{streetMode ? "街道 / 乡镇" : region.level === "province" ? "直辖市 / 省级" : districtMode ? "区县" : "市级区域"}</span>
          </button>)}
        </div>
        {!unique.length && <p role="status">{error || (data?.status === "unavailable" ? data.message : "没有匹配候选，可继续手动输入。")}</p>}
        {(error || data?.status === "unavailable") && <Button type="button" onClick={() => setRetry(current => current + 1)}>重试区域候选</Button>}
      </>}
    </div>}
  </div>;
}

export function HospitalMap({ result, onLoaded, available = true }: { result: HospitalResult | null; onLoaded: () => void; available?: boolean }) {
  const [image, setImage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const callback = useRef(onLoaded);
  callback.current = onLoaded;
  const token = result?.map_preview_token;
  useEffect(() => {
    setImage(""); setError(""); setBusy(false);
    if (!token) return;
    const controller = new AbortController();
    let objectUrl = "";
    setBusy(true);
    const timer = setTimeout(() => {
      api<Blob>("/hospitals/map", "POST", { token }, undefined, controller.signal, "blob")
        .then(blob => { if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setImage(objectUrl); } })
        .catch(e => { if (e.name !== "AbortError") setError(e.message); })
        .finally(() => { if (!controller.signal.aborted) { setBusy(false); callback.current(); } });
    }, 0);
    return () => { clearTimeout(timer); controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [token, retry]);
  if ((result && !token) || (!result && !available)) return <figure className="hospital-map" aria-label="医院地图入口">
    <p className="small muted">{result?.map_note || "当前暂无可用站内地图；查询后可按名称打开高德核对位置及导航。"}</p>
    {result && <a href={result.search_url} target="_blank" rel="noreferrer">按名称打开高德地图</a>}
  </figure>;
  return <figure className="hospital-map" aria-label="医院位置地图">
    <div className="hospital-map-frame">
      {image ? <img src={image} width={600} height={320} alt="高德地图：编号对应下方医院候选" onError={() => { setImage(""); setError("地图图片无法显示，医院列表仍可查看。"); }} /> : <div className="hospital-map-placeholder">
        <MapPin size={24} />
        <p role="status">{busy ? "正在加载医院位置地图…" : error || (result?.map_note || (result ? "当前查询暂无可用地图位置" : "查询后，在这里查看医院位置"))}</p>
        {error && <Button type="button" onClick={() => setRetry(current => current + 1)}>重试地图</Button>}
      </div>}
    </div>
    <figcaption className="small muted">{image ? result?.map_note || "高德静态地图 · 编号对应医院列表，点击下方打开可交互地图" : "地图加载与医院列表独立，出发前请核实接诊情况"}</figcaption>
    {result && <a href={result.search_url} target="_blank" rel="noreferrer">打开完整地图</a>}
  </figure>;
}
