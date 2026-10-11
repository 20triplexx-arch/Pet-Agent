"""Optional local OCR: validated in-memory images, a killable CPU worker, no cloud."""
import hashlib
import importlib.util
import io
import json
import multiprocessing
import re
import threading
import warnings
from functools import lru_cache
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings

MAX_FILE = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
MANIFEST = Path(__file__).resolve().parents[1] / "data" / "ocr_models.json"
_slot = threading.BoundedSemaphore(1)


@lru_cache(maxsize=1)
def local_models():
    try:
        if version("rapidocr") != "3.10.0" or version("onnxruntime") != "1.31.0":
            return None
        spec = importlib.util.find_spec("rapidocr")
        root = Path(spec.origin).parent / "models"
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        paths = {}
        for item in manifest["models"]:
            path = root / item["file"]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                return None
            paths[item["task"]] = str(path)
        return paths if len(paths) == 3 else None
    except (PackageNotFoundError, ImportError, OSError, ValueError, AttributeError):
        return None


def status():
    ready = settings.OCR_ENABLED and bool(local_models())
    return {"available": ready, "engine": "RapidOCR 3.10.0 / ONNX Runtime CPU 1.31.0", "mode": "local",
        "max_files": 3, "max_file_bytes": MAX_FILE, "max_pixels": MAX_PIXELS, "timeout_seconds": settings.OCR_TIMEOUT_SECONDS,
        "message": "本地识别；结果需要核对，不代表厂家已核实。" if ready else "本地图片识别未安装、模型校验失败或已关闭；可继续手动输入。管理员可运行 setup.ps1 -WithOCR。"}


def sanitize_image(data):
    if not data or len(data) > MAX_FILE:
        raise HTTPException(413, "图片不能为空且每张最多5 MB")
    try:
        from PIL import Image, ImageOps
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP") or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("unsupported")
                if image.width * image.height > MAX_PIXELS:
                    raise HTTPException(413, "每张图片最多2000万像素")
                image.load()
                image = ImageOps.exif_transpose(image)
                rgba = image.convert("RGBA")
                clean = Image.new("RGB", image.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                clean.thumbnail((2000, 2000))
                buf = io.BytesIO()
                clean.save(buf, format="PNG")  # no EXIF, filename or other metadata
                return buf.getvalue()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "图片损坏或格式不支持，请使用静态 JPEG、PNG、WebP")


def _worker(conn, images, models):
    try:
        import socket
        def deny_network(*args, **kwargs):
            raise RuntimeError("OCR worker has no network access")
        socket.socket.connect = deny_network
        socket.create_connection = deny_network
        from rapidocr import RapidOCR
        engine = RapidOCR(params={"Det.model_path": models["det"], "Cls.model_path": models["cls"], "Rec.model_path": models["rec"],
            "Global.log_level": "critical", "EngineConfig.onnxruntime.intra_op_num_threads": 2, "EngineConfig.onnxruntime.inter_op_num_threads": 1})
        frames = []
        for data in images:
            result = engine(data)
            lines = [{"text": str(t)[:2000], "confidence": round(float(s), 4), "needs_review": float(s) < 0.9}
                     for t, s in zip(result.txts if result.txts is not None else (), result.scores if result.scores is not None else ())]
            frames.append({"lines": lines[:200]})
        conn.send({"images": frames})
    except Exception:
        # Do not emit source image, recognised label, user data or exception payload.
        conn.send({"error": "识别失败，可手动输入或重新拍摄后重试"})
    finally:
        conn.close()


def extract_suggestions(raw):
    raw = re.sub(r">\s*＝|>\s*=", ">=", raw)
    raw = re.sub(r"<\s*＝|<\s*=", "<=", raw)
    suggestions = {}
    energy = re.search(r"(\d+(?:\.\d+)?)\s*(kcal|kJ)\s*[/／]\s*(100\s*g|kg|1000\s*g|份|portion)", raw, re.I)
    if energy:
        denom = energy[3].replace(" ", "").lower()
        unit = "kj" if energy[2].lower() == "kj" else "kcal"
        suffix = "100g" if denom == "100g" else "kg" if denom in ("kg", "1000g") else "portion"
        suggestions.update(energy=float(energy[1]), energy_unit=unit + "_" + suffix)
    net = re.search(r"(?:净含量|净重|Net\s*(?:weight|wt))\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(kg|g|克|千克|公斤)", raw, re.I)
    if net:
        suggestions["net_grams"] = float(net[1]) * (1000 if net[2].lower() in ("kg", "千克", "公斤") else 1)
    analysis = []
    for match in re.finditer(r"(粗蛋白|粗脂肪|粗纤维|粗灰分|水分|protein|fat|moisture)\s*[:：]?\s*(≥|≤|>=|<=)\s*(\d+(?:\.\d+)?)\s*[%％]", raw, re.I):
        analysis.append({"nutrient": match[1], "qualifier": "min" if match[2] in ("≥", ">=") else "max", "value": float(match[3]), "unit": "percent"})
    if analysis:
        suggestions["analysis"] = analysis[:12]
    return suggestions


def recognize(images):
    if not status()["available"]:
        raise HTTPException(503, status()["message"])
    if not 1 <= len(images) <= 3:
        raise HTTPException(422, "每次上传1至3张图片")
    if not _slot.acquire(blocking=False):
        raise HTTPException(429, "正在识别另一组图片，请稍后手动重试")
    process = None
    try:
        clean = [sanitize_image(image) for image in images]
        mp = multiprocessing.get_context("spawn")
        parent, child = mp.Pipe(duplex=False)
        process = mp.Process(target=_worker, args=(child, clean, local_models()), daemon=True)
        process.start()
        child.close()
        try:
            if not parent.poll(settings.OCR_TIMEOUT_SECONDS):
                raise HTTPException(504, "本地识别超时，本次未保存图片或产品；可手动输入或重试")
            result = parent.recv()
        finally:
            parent.close()
        if "error" in result:
            raise HTTPException(502, result["error"])
        raw = "\n".join(line["text"] for frame in result["images"] for line in frame["lines"])[:12000]
        return {**result, "raw_text": raw, "suggestions": extract_suggestions(raw), "origin": "ocr", "confirmed": False,
            "status": "recognized" if raw.strip() else "empty", "message": "请核对热量、单位、净含量、适用声明及数值；用户确认不等于厂家核实。" if raw.strip() else "没有识别到文字，请拍摄清晰标签或手动输入。"}
    except (EOFError, OSError):
        raise HTTPException(502, "本地识别进程失败，请手动重试或输入")
    finally:
        if process:
            if process.is_alive():
                process.terminate()
            process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join(timeout=3)
            process.close()
        _slot.release()
