#!/usr/bin/env python3
"""gen-image - OpenAI Images API engine (GPT Image 2.x, billed to YOUR API key).

Standard library only (Python 3.8+), so the stock macOS python3 is enough.
  no -i            -> POST {base}/images/generations  (JSON)
  -i ref.png ...   -> POST {base}/images/edits        (multipart; up to 16 images, optional mask)

The key is read from <skill-root>/.env (copy .env.example) or the OPENAI_API_KEY environment
variable. It is never printed, logged or accepted on the command line.

stdout: one "SAVED: <path> (<w>x<h>)" line per image.  stderr: summary, notes, errors, hints.
Exit status: 0 = at least one image saved, 1 = API / network failure, 2 = usage or config error.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import http.client
import json
import math
import os
import re
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(SKILL_ROOT, ".env")
DEFAULTS = {
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "OPENAI_IMAGE_MODEL": "gpt-image-2.6-sunburst",
    "OPENAI_IMAGE_QUALITY": "high",
    "OPENAI_IMAGE_RESOLUTION": "2K",
    "OPENAI_IMAGE_FORMAT": "png",
    "OPENAI_IMAGE_TIMEOUT": "600",
}
DEFAULT_OUTDIR = os.path.join(os.path.expanduser("~"), "Pictures", "AI生图")

QUALITIES = ("low", "medium", "high", "xhigh", "max", "auto")
LEVELS = ("low", "medium", "high")
BACKGROUNDS = ("auto", "opaque", "transparent")
FORMATS = ("png", "jpeg", "webp", "gif", "svg")
MODERATIONS = ("auto", "low")
FIDELITIES = ("low", "high")

# 1K / 2K / 4K = pixel budgets; every aspect ratio gets (about) the same pixel count.
TIER_PIXELS = {"1K": 1024 * 1024, "2K": 2560 * 1440, "4K": 3840 * 2160}
MAX_EDGE = 3840
MIN_PIXELS = 655360
MAX_PIXELS = 3840 * 2160
STABLE_PIXELS = 2560 * 1440  # OpenAI marks anything larger as experimental
MAX_RATIO = 3.0
STANDARD_SIZES = ((1024, 1024), (1536, 1024), (1024, 1536))
MAX_N_PER_REQUEST = 10
MAX_INPUT_IMAGES = 16
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_MASK_BYTES = 4 * 1024 * 1024
EXT = {"png": ".png", "jpeg": ".jpg", "webp": ".webp", "gif": ".gif", "svg": ".svg"}
MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
VARIANT_RE = re.compile(r"^(gpt-image-\d+(?:\.\d+)?)-(sunburst|flare)(?:-\d{4}-\d{2}-\d{2})?$")
PROXY_EXAMPLE = "HTTPS_PROXY=http://127.0.0.1:7890"


class UsageError(Exception):
    """Bad arguments or configuration (exit status 2)."""


class NetworkError(Exception):
    def __init__(self, message, hints=()):
        super().__init__(message)
        self.hints = list(hints)


class ApiError(Exception):
    def __init__(self, status, message, code="", etype="", param="", request_id=""):
        super().__init__(message)
        self.status, self.message = status, message
        self.code, self.etype, self.param, self.request_id = code, etype, param, request_id

    @classmethod
    def from_response(cls, status, raw, headers):
        message = code = etype = param = ""
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
            err = payload.get("error", payload) if isinstance(payload, dict) else payload
            if isinstance(err, dict):
                message = str(err.get("message") or "")
                code = str(err.get("code") or "")
                etype = str(err.get("type") or "")
                param = str(err.get("param") or "")
            else:
                message = str(err)
        except ValueError:
            message = raw.decode("utf-8", "replace").strip()[:500]
        request_id = (headers.get("x-request-id") or "") if headers is not None else ""
        return cls(status, message or "HTTP %d" % status, code, etype, param, request_id)

    @property
    def retryable(self):
        if self.status == 429:
            return "insufficient_quota" not in (self.code, self.etype)
        return self.status in (500, 502, 503, 504)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- configuration

def read_env_file(path):
    """Minimal .env reader: KEY=value, optional `export`, quotes, trailing ` # comments`."""
    values = {}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return values
    except (OSError, UnicodeDecodeError) as exc:
        log("NOTE: cannot read %s: %s" % (path, exc))
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if value[:1] in ("'", '"', "“", "‘"):  # also tolerate smart quotes from TextEdit
            closing = {"“": "”", "‘": "’"}.get(value[0], value[0])
            end = value.find(closing, 1)
            value = value[1:end] if end != -1 else value[1:]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key.strip()] = value.strip()
    return values


class Config:
    """Connection settings come as one unit: from .env when it holds a key, else the environment."""

    def __init__(self):
        self.file_values = read_env_file(ENV_FILE)
        fv = self.file_values
        if fv.get("OPENAI_API_KEY"):
            conn, self.key_source = fv, ENV_FILE
        else:
            conn = os.environ
            self.key_source = "environment variable OPENAI_API_KEY" if os.environ.get("OPENAI_API_KEY", "").strip() else ""
        self.api_key = (conn.get("OPENAI_API_KEY") or "").strip()
        self.base_url = (conn.get("OPENAI_BASE_URL") or "").strip().rstrip("/") or DEFAULTS["OPENAI_BASE_URL"]
        self.organization = (conn.get("OPENAI_ORG_ID") or conn.get("OPENAI_ORGANIZATION") or "").strip()
        self.project = (conn.get("OPENAI_PROJECT_ID") or conn.get("OPENAI_PROJECT") or "").strip()
        self.proxy = (fv.get("HTTPS_PROXY") or fv.get("https_proxy") or "").strip()

    def get(self, name):
        for source in (self.file_values, os.environ):
            value = (source.get(name) or "").strip()
            if value:
                return value
        return DEFAULTS.get(name, "")

    def require_key(self):
        if not self.api_key:
            raise UsageError(
                "no OpenAI API key configured. Put it in %s as OPENAI_API_KEY=sk-... "
                "(cp .env.example .env first), or export OPENAI_API_KEY." % ENV_FILE)
        if re.search(r"\s", self.api_key) or not self.api_key.isascii():
            raise UsageError("the API key from %s contains spaces or non-ASCII characters; "
                             "re-copy it from https://platform.openai.com/api-keys" % self.key_source)


def mask_key(key):
    m = re.match(r"^(sk-(?:[a-z]+-)?)", key)
    prefix = m.group(1) if m else key[:3]
    return "%s...%s" % (prefix, key[-4:]) if len(key) > len(prefix) + 8 else prefix + "..."


def mask_url(url):
    return re.sub(r"//[^/@]*@", "//***@", url)


def resolve_model(name, default_model):
    """`sunburst` / `flare` -> same generation as the default model; `2.6-flare` -> gpt-image-2.6-flare."""
    name = name.strip()
    if name.lower() in ("sunburst", "flare"):
        m = VARIANT_RE.match(default_model)
        return "%s-%s" % (m.group(1) if m else "gpt-image-2.6", name.lower())
    if re.match(r"^\d", name):
        return "gpt-image-" + name
    return name


def fixed_size_model(model):
    """Models that only take 1024x1024 / 1536x1024 / 1024x1536 / auto."""
    return model.startswith("gpt-image-1") or model.startswith("chatgpt-image")


def short_model(model):
    short = model[len("gpt-image-"):] if model.startswith("gpt-image-") else model
    return re.sub(r"[^A-Za-z0-9._-]+", "-", short).strip("-") or "model"


# ---------------------------------------------------------------- images

def sniff(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "heic"
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "svg"
    return None


def png_chunks(data):
    pos = 8
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        yield ctype, data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IEND":
            return


def png_has_alpha(data):
    if data[25:26] in (b"\x04", b"\x06"):  # IHDR colour type gray+alpha / RGBA
        return True
    try:
        return any(ctype == b"tRNS" for ctype, _ in png_chunks(data))
    except struct.error:
        return False


def image_dims(data):
    kind = sniff(data)
    try:
        if kind == "png" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if kind == "gif":
            return struct.unpack("<HH", data[6:10])
        if kind == "webp":
            chunk = data[12:16]
            if chunk == b"VP8X":
                return (int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1)
            if chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return (w & 0x3FFF, h & 0x3FFF)
        if kind == "jpeg":
            i = 2
            while i + 9 <= len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker == 0xFF:
                    i += 1
                    continue
                if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return (w, h)
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except (struct.error, IndexError):
        pass
    return None


def jpeg_orientation(data):
    """EXIF orientation tag of a JPEG (1 = normal; 5-8 = rotated by 90 degrees)."""
    try:
        i = 2
        while i + 4 <= len(data) and data[i] == 0xFF:
            marker = data[i + 1]
            if marker in (0xD9, 0xDA):
                break
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
                tiff = data[i + 10:i + 2 + length]
                order = "<" if tiff[:2] == b"II" else ">"
                ifd = struct.unpack(order + "I", tiff[4:8])[0]
                for k in range(struct.unpack(order + "H", tiff[ifd:ifd + 2])[0]):
                    entry = tiff[ifd + 2 + 12 * k:ifd + 14 + 12 * k]
                    if struct.unpack(order + "H", entry[:2])[0] == 0x0112:
                        return struct.unpack(order + "H", entry[8:10])[0]
                return 1
            i += 2 + length
    except (struct.error, IndexError):
        pass
    return 1


def oriented_dims(data):
    dims = image_dims(data)
    if dims and sniff(data) == "jpeg" and jpeg_orientation(data) in (5, 6, 7, 8):
        return (dims[1], dims[0])
    return dims


def dims_text(data):
    if sniff(data) == "svg":
        return "svg"
    dims = image_dims(data)
    return "%dx%d" % dims if dims else "?"


def load_input(path, what, limit=MAX_INPUT_BYTES):
    full = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(full):
        raise UsageError("%s not found: %s" % (what, path))
    if os.path.getsize(full) > limit:
        raise UsageError("%s is larger than %d MB: %s" % (what, limit // (1024 * 1024), path))
    with open(full, "rb") as fh:
        data = fh.read()
    kind = sniff(data)
    if kind in ("heic", "avif"):
        raise UsageError("%s is %s, which the API does not accept; convert it first, e.g. on macOS: "
                         "sips -s format jpeg '%s' --out '%s.jpg'" % (path, kind.upper(), path, os.path.splitext(path)[0]))
    if kind not in MIME:
        raise UsageError("%s must be png, jpg or webp (got %s): %s" % (what, kind or "unknown format", path))
    return {"path": full, "data": data, "kind": kind, "dims": oriented_dims(data)}


def save_image(raw, outdir, tag, label, index, fallback_kind):
    ext = EXT.get(sniff(raw) or fallback_kind, ".bin")
    base = os.path.join(outdir, "%s-%s-%d" % (tag, label, index))
    for attempt in range(1000):
        path = base + ("_%d" % attempt if attempt else "") + ext
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        return path
    raise OSError("could not find a free file name for " + base)


# ---------------------------------------------------------------- sizes

def parse_aspect(text):
    t = text.strip().lower().replace("：", ":").replace("×", "x")
    if t in ("auto", "自动"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[:x/]\s*(\d+(?:\.\d+)?)", t)
    if not m or float(m.group(1)) <= 0 or float(m.group(2)) <= 0:
        raise UsageError("cannot read aspect ratio %r (examples: 16:9, 9:16, 1:1, auto)" % text)
    return float(m.group(1)) / float(m.group(2))


def ratio_text(ratio):
    for a in range(1, 33):
        b = a / ratio
        if abs(b - round(b)) < 1e-6 and round(b) > 0:
            return "%d:%d" % (a, round(b))
    return "%.3g:1" % ratio


def compute_size(ratio, tier, model, notes):
    if ratio is None:
        return "auto"
    if fixed_size_model(model):
        w, h = min(STANDARD_SIZES, key=lambda s: abs(math.log(s[0] / s[1] / ratio)))
        if tier != "1K":
            notes.append("%s only supports 1024x1024 / 1536x1024 / 1024x1536; using %dx%d" % (model, w, h))
        return "%dx%d" % (w, h)
    target = min(max(ratio, 1 / MAX_RATIO), MAX_RATIO)
    if abs(target - ratio) > 1e-9:
        notes.append("aspect %s is outside the API's 1:3-3:1 range; using %s" % (ratio_text(ratio), ratio_text(target)))
    budget = TIER_PIXELS[tier]
    cap = STABLE_PIXELS if budget <= STABLE_PIXELS else MAX_PIXELS  # keep 1K / 2K out of the experimental range
    wide = max(target, 1 / target)  # solve landscape, transpose for portrait -> 3:4 mirrors 4:3 exactly
    best = None
    for h in range(16, MAX_EDGE + 1, 16):
        for units in {math.floor(h * wide / 16), math.ceil(h * wide / 16)}:
            w = units * 16
            if not h <= w <= MAX_EDGE or not MIN_PIXELS <= w * h <= cap or w / h > MAX_RATIO + 1e-9:
                continue
            score = (abs(math.log(w * h / budget)) + 4 * abs(math.log(w / h / wide)), -w * h, w)
            if best is None or score < best[0]:
                best = (score, w, h)
    if best is None:
        raise UsageError("no valid size for aspect %s at %s; pass -s WIDTHxHEIGHT" % (ratio_text(target), tier))
    _, w, h = best
    if target < 1:
        w, h = h, w
    if w * h > STABLE_PIXELS:
        notes.append("%dx%d is above 2560x1440, which OpenAI marks experimental (slower, less consistent)" % (w, h))
    return "%dx%d" % (w, h)


def check_explicit_size(text, model, notes):
    t = text.strip().lower().replace("×", "x")
    if t == "auto":
        return "auto"
    m = re.fullmatch(r"(\d+)\s*x\s*(\d+)", t)
    if not m or int(m.group(1)) == 0 or int(m.group(2)) == 0:
        raise UsageError("size must look like 1536x1024 or auto (got %r)" % text)
    w, h = int(m.group(1)), int(m.group(2))
    if fixed_size_model(model):
        if (w, h) not in STANDARD_SIZES:
            notes.append("%s normally only accepts 1024x1024, 1536x1024, 1024x1536 or auto" % model)
        return "%dx%d" % (w, h)
    problems = []
    if w % 16 or h % 16:
        problems.append("both edges must be multiples of 16")
    if max(w, h) > MAX_EDGE:
        problems.append("edges must be at most %dpx" % MAX_EDGE)
    if not MIN_PIXELS <= w * h <= MAX_PIXELS:
        problems.append("total pixels must be between %d and %d" % (MIN_PIXELS, MAX_PIXELS))
    if max(w, h) / min(w, h) > MAX_RATIO:
        problems.append("aspect ratio must stay within 1:3-3:1")
    if problems:
        notes.append("%dx%d will probably be rejected: %s" % (w, h, "; ".join(problems)))
    elif w * h > STABLE_PIXELS:
        notes.append("%dx%d is above 2560x1440, which OpenAI marks experimental (slower, less consistent)" % (w, h))
    return "%dx%d" % (w, h)


# ---------------------------------------------------------------- HTTP

def make_opener(cfg):
    ctx = ssl.create_default_context()
    try:  # python.org builds on macOS may lack system CAs; certifi fills the gap when installed
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    proxy = cfg.proxy or urllib.request.getproxies().get("https", "")
    if proxy.lower().startswith("socks"):
        raise UsageError("SOCKS proxies (%s) are not supported by Python's standard library; "
                         "use your proxy's HTTP port instead, e.g. %s" % (mask_url(proxy), PROXY_EXAMPLE))
    if cfg.proxy:
        explicit = cfg.proxy if "://" in cfg.proxy else "http://" + cfg.proxy
        handlers.append(urllib.request.ProxyHandler({"http": explicit, "https": explicit}))
    return urllib.request.build_opener(*handlers)


def api_headers(cfg, content_type=None):
    headers = {"Authorization": "Bearer " + cfg.api_key, "Accept": "application/json",
               "User-Agent": "gen-image-skill/1.0 (python-urllib)"}
    if content_type:
        headers["Content-Type"] = content_type
    if cfg.organization:
        headers["OpenAI-Organization"] = cfg.organization
    if cfg.project:
        headers["OpenAI-Project"] = cfg.project
    return headers


def retry_delay(headers, attempt):
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        value = headers.get(name) if headers is not None else None
        if value:
            try:
                return min(max(float(value) * scale, 0.5), 60.0)
            except ValueError:
                pass
    return float(min(2 ** attempt, 30))


def network_error(reason, cfg, timeout):
    host = urllib.parse.urlsplit(cfg.base_url).hostname or cfg.base_url
    via = " via proxy %s" % mask_url(cfg.proxy) if cfg.proxy else ""
    proxy_hint = "if you need a proxy to reach OpenAI, set it in %s, e.g. %s" % (ENV_FILE, PROXY_EXAMPLE)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return NetworkError("no response from %s within %.0fs" % (host, timeout), [
            "4K, max quality or high complexity can take several minutes: raise --timeout (or "
            "OPENAI_IMAGE_TIMEOUT in .env), or lower -r / -q.",
            "The image may still have been generated and billed; check https://platform.openai.com/usage "
            "before retrying again and again."])
    text = str(reason)
    if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        return NetworkError("TLS certificate verification failed for %s%s: %s" % (host, via, text), [
            "python.org Python on macOS: run '/Applications/Python 3.x/Install Certificates.command' "
            "(or: pip3 install certifi).",
            "Behind an SSL-inspecting proxy: point SSL_CERT_FILE at its CA bundle."])
    if isinstance(reason, socket.gaierror):
        return NetworkError("cannot resolve %s%s (%s)" % (host, via, text), ["check your network; " + proxy_hint])
    if isinstance(reason, ConnectionRefusedError):
        return NetworkError("connection refused%s" % (via or " by " + host),
                            ["is the proxy running?" if via else proxy_hint])
    return NetworkError("network error talking to %s%s: %s" % (host, via, text), [proxy_hint])


def send(opener, cfg, method, url, headers, body, timeout, retries=2):
    attempt = 0
    while True:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read()
            try:
                return json.loads(raw.decode("utf-8"))
            except ValueError:
                raise ApiError(200, "the server did not return JSON: %r" % raw[:200])
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            err = ApiError.from_response(exc.code, raw, exc.headers)
            if err.retryable and attempt < retries:
                attempt += 1
                delay = retry_delay(exc.headers, attempt)
                log("NOTE: HTTP %d %s- retrying in %.0fs (%d/%d)" % (exc.code, err.code + " " if err.code else "",
                                                                    delay, attempt, retries))
                time.sleep(delay)
                continue
            raise err
        except urllib.error.URLError as exc:
            raise network_error(exc.reason, cfg, timeout)
        except (socket.timeout, TimeoutError) as exc:
            raise network_error(exc, cfg, timeout)
        except (OSError, http.client.HTTPException) as exc:
            raise network_error(exc, cfg, timeout)


def encode_multipart(fields, files):
    boundary = "----gen-image-" + uuid.uuid4().hex
    out = []
    for name, value in fields.items():
        out.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n' % (boundary, name)).encode("ascii"))
        out.append(str(value).encode("utf-8") + b"\r\n")
    for number, (name, item) in enumerate(files, 1):
        filename = "%s%d%s" % (name.replace("[]", ""), number, EXT[item["kind"]])
        out.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: %s\r\n\r\n'
                    % (boundary, name, filename, MIME[item["kind"]])).encode("ascii"))
        out.append(item["data"] + b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode("ascii"))
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def api_hints(err, model, cfg):
    status, msg = err.status, err.message.lower()
    code = ("%s %s" % (err.code, err.etype)).lower()
    if status == 401:
        return ["The key was rejected (typo, revoked, or wrong org/project). Re-copy it from "
                "https://platform.openai.com/api-keys into %s." % (cfg.key_source or ENV_FILE)]
    if status == 403 and "verif" in msg:
        return ["GPT Image models need a verified organization: https://platform.openai.com/settings/"
                "organization/general -> Verify Organization (access can take ~15 minutes to appear)."]
    if "unsupported_country" in code or "country, region" in msg:
        return ["OpenAI does not serve the region your traffic comes from: route it through a proxy in a "
                "supported region (set %s in %s)." % (PROXY_EXAMPLE, ENV_FILE)]
    if status == 403:
        return ["Permission denied: a restricted key needs write access to Images, and the project must "
                "allow this model (project settings -> Limits)."]
    if status == 404 or "model_not_found" in code or ("model" in msg and "not exist" in msg):
        return ["This key cannot use %s (not available to your org/project yet, or a typo). "
                "Try -m gpt-image-2.5-sunburst or -m gpt-image-2.5-flare." % model]
    if "insufficient_quota" in code or "billing" in code or "hard_limit" in code:
        return ["No API credit or the budget limit is reached: add credit / raise the limit at "
                "https://platform.openai.com/settings/organization/billing (a ChatGPT subscription "
                "does not cover API usage)."]
    if status == 429:
        return ["Rate limited: wait a minute, lower -n, or check https://platform.openai.com/settings/organization/limits."]
    if status == 400 and ("moderation" in code or "safety" in code or "content_policy" in code or "safety system" in msg):
        return ["Blocked by OpenAI's safety system: rephrase the prompt or use a different reference image."]
    if status == 400 and (err.param == "size" or "size" in msg or "resolution" in msg):
        return ["This model rejected the size: try -r 2K or -r 1K, -s 1536x1024, or -m gpt-image-2.5-sunburst."]
    if status == 400 and (err.param == "quality" or "quality" in msg):
        return ["This model does not support that quality: try -q high."]
    if status == 400 and "mask" in msg:
        return ["The mask must be a PNG with transparency, the same size as the first -i image, under 4 MB."]
    if status >= 500:
        return ["OpenAI server error: try again shortly (https://status.openai.com)."]
    return []


def report_failure(exc, model, cfg):
    if isinstance(exc, ApiError):
        log("ERROR: OpenAI API HTTP %d%s: %s" % (exc.status, " " + exc.code if exc.code else "", exc.message))
        if exc.request_id:
            log("       request id: %s" % exc.request_id)
        hints = api_hints(exc, model, cfg)
    else:
        log("ERROR: %s" % exc)
        hints = exc.hints
    for hint in hints:
        log("HINT: " + hint)


# ---------------------------------------------------------------- request

class Job:
    pass


def normalize_format(value):
    fmt = value.strip().lower()
    fmt = "jpeg" if fmt == "jpg" else fmt
    if fmt not in FORMATS:
        raise UsageError("format must be one of %s (got %r)" % (", ".join(FORMATS), value))
    return fmt


def pick(value, allowed, what):
    value = (value or "").strip().lower()
    if value and value not in allowed:
        raise UsageError("%s must be one of %s (got %r)" % (what, ", ".join(allowed), value))
    return value or None


def prepare(cfg, args):
    job = Job()
    job.notes = notes = []
    job.prompt = (args.prompt or "").strip()
    if not job.prompt:
        raise UsageError("a prompt is required (-p)")
    if len(job.prompt) > 32000:
        raise UsageError("the prompt is longer than 32000 characters")
    default_model = cfg.get("OPENAI_IMAGE_MODEL")
    job.model = resolve_model(args.model or default_model, default_model)
    job.quality = pick(args.quality or cfg.get("OPENAI_IMAGE_QUALITY"), QUALITIES, "quality")
    job.complexity = pick(args.complexity or cfg.get("OPENAI_IMAGE_COMPLEXITY"), LEVELS, "complexity")
    job.moderation = pick(args.moderation or cfg.get("OPENAI_IMAGE_MODERATION"), MODERATIONS, "moderation")
    job.background = pick(args.background, BACKGROUNDS, "background")
    job.input_fidelity = pick(args.input_fidelity, FIDELITIES, "input fidelity")
    job.format = normalize_format(args.format or cfg.get("OPENAI_IMAGE_FORMAT"))
    tier = (args.resolution or cfg.get("OPENAI_IMAGE_RESOLUTION")).strip().upper()
    if tier not in TIER_PIXELS:
        raise UsageError("resolution must be 1K, 2K or 4K (got %r)" % tier)
    try:
        job.timeout = float(args.timeout or cfg.get("OPENAI_IMAGE_TIMEOUT"))
    except ValueError:
        raise UsageError("OPENAI_IMAGE_TIMEOUT must be a number of seconds")
    if job.background == "transparent" and job.format not in ("png", "webp"):
        notes.append("a transparent background needs png or webp; using png instead of %s" % job.format)
        job.format = "png"
    job.compression = args.compression
    if job.compression is not None:
        if not 0 <= job.compression <= 100:
            raise UsageError("--compression must be between 0 and 100")
        if job.format not in ("jpeg", "webp"):
            notes.append("--compression only applies to jpeg / webp; ignored")
            job.compression = None
    if args.count < 1:
        raise UsageError("-n must be at least 1")
    job.count = args.count

    job.images = [load_input(p, "image") for p in args.image]
    if len(job.images) > MAX_INPUT_IMAGES:
        raise UsageError("the API takes at most %d images per edit (got %d)" % (MAX_INPUT_IMAGES, len(job.images)))
    job.mask = job.markup = None
    if (args.mask or args.markup) and not job.images:
        raise UsageError("--mask / --markup need the image to edit (-i)")
    if args.mask and args.markup:
        raise UsageError("--mask and --markup cannot be combined")
    for attr, label, limit in (("mask", "mask", MAX_MASK_BYTES), ("markup", "markup", MAX_INPUT_BYTES)):
        path = getattr(args, attr)
        if not path:
            continue
        item = load_input(path, label, limit)
        if item["kind"] != "png" or not png_has_alpha(item["data"]):
            raise UsageError("the %s must be a PNG with transparency (alpha channel): %s" % (label, path))
        first = job.images[0]["dims"]
        if first and item["dims"] and tuple(item["dims"]) != tuple(first):
            notes.append("%s is %dx%d but the first image is %dx%d; the API expects the same size"
                         % (label, item["dims"][0], item["dims"][1], first[0], first[1]))
        setattr(job, attr, item)
    if job.format == "svg" and job.images:
        raise UsageError("SVG output does not support edits (-i)")

    if args.size:
        job.size = check_explicit_size(args.size, job.model, notes)
    else:
        if args.aspect is None and job.images and job.images[0]["dims"]:
            w, h = job.images[0]["dims"]
            ratio = w / h  # editing without -a: keep the first image's aspect ratio
        else:
            ratio = parse_aspect(args.aspect or "1:1")
        job.size = compute_size(ratio, tier, job.model, notes)

    job.outdir = os.path.abspath(os.path.expanduser(args.outdir))
    job.tag = args.tag or time.strftime("%Y%m%d-%H%M%S")
    job.label = args.label or "api-" + short_model(job.model)
    job.record = args.record
    return job


def build_request(job, n):
    fields = {"model": job.model, "prompt": job.prompt, "n": n, "size": job.size,
              "quality": job.quality, "output_format": job.format}
    for key, value in (("background", job.background), ("moderation", job.moderation),
                       ("output_compression", job.compression), ("complexity", job.complexity)):
        if value is not None:
            fields[key] = value
    if not job.images:
        return "/images/generations", json.dumps(fields, ensure_ascii=False).encode("utf-8"), "application/json", fields
    if job.input_fidelity:
        fields["input_fidelity"] = job.input_fidelity
    files = [("image[]", item) for item in job.images]
    if job.mask:
        files.append(("mask", job.mask))
    if job.markup:
        files.append(("markup", job.markup))
    body, content_type = encode_multipart(fields, files)
    return "/images/edits", body, content_type, fields


def call_api(cfg, opener, job, n):
    while True:
        endpoint, body, content_type, _ = build_request(job, n)
        try:
            return send(opener, cfg, "POST", cfg.base_url + endpoint, api_headers(cfg, content_type), body, job.timeout)
        except ApiError as exc:
            if job.complexity and exc.status == 400 and (exc.param == "complexity" or "complexity" in exc.message.lower()):
                log("NOTE: %s does not accept complexity=%s; retrying without it" % (job.model, job.complexity))
                job.complexity = None
                continue
            raise


def generate(cfg, job):
    opener = make_opener(cfg)
    os.makedirs(job.outdir, exist_ok=True)
    started = time.time()
    saved, failure, served = 0, None, {}
    tokens = {"input_tokens": 0, "output_tokens": 0}
    per_request = 1 if job.format == "svg" else MAX_N_PER_REQUEST
    remaining = job.count
    while remaining > 0:
        n = min(per_request, remaining)
        try:
            data = call_api(cfg, opener, job, n)
        except (ApiError, NetworkError) as exc:
            failure = exc
            break
        if not isinstance(data, dict):
            failure = ApiError(200, "unexpected response: %r" % (data,))
            break
        items = data.get("data") or []
        got = 0
        for item in items:
            b64 = item.get("b64_json") if isinstance(item, dict) else None
            if not b64:
                continue
            try:
                raw = base64.b64decode(b64)
            except (binascii.Error, ValueError):
                continue
            got += 1
            saved += 1
            path = save_image(raw, job.outdir, job.tag, job.label, saved, job.format)
            dims = dims_text(raw)
            print("SAVED: %s (%s)" % (path, dims), flush=True)
            if job.record:
                with open(job.record, "a", encoding="utf-8") as fh:
                    fh.write("%s\t%s\n" % (path, dims))
        for key in ("size", "quality"):
            if data.get(key):
                served[key] = data[key]
        usage = data.get("usage") or {}
        for key in tokens:
            if isinstance(usage.get(key), int):
                tokens[key] += usage[key]
        if not got:
            failure = ApiError(200, "the response contained no image data")
            break
        remaining -= n
    if saved:
        size = job.size if served.get("size") in (None, job.size) else "%s -> %s" % (job.size, served["size"])
        quality = job.quality if served.get("quality") in (None, job.quality) else "%s -> %s" % (job.quality, served["quality"])
        parts = ["api: %s" % job.model, size, "quality=%s" % quality]
        if job.complexity:
            parts.append("complexity=%s" % job.complexity)
        if job.background:
            parts.append("background=%s" % job.background)
        parts.append("%d image(s) in %.1fs" % (saved, time.time() - started))
        if tokens["output_tokens"]:
            parts.append("tokens in/out %d/%d" % (tokens["input_tokens"], tokens["output_tokens"]))
        log(" | ".join(parts))
    if failure:
        report_failure(failure, job.model, cfg)
    return 0 if saved else 1


# ---------------------------------------------------------------- modes

def dry_run(cfg, job):
    endpoint, _, _, fields = build_request(job, min(job.count, MAX_N_PER_REQUEST))
    batches = -(-job.count // (1 if job.format == "svg" else MAX_N_PER_REQUEST))
    print("DRY RUN - nothing sent, nothing billed")
    print("POST %s%s%s" % (cfg.base_url, endpoint, "  (x%d requests)" % batches if batches > 1 else ""))
    for key, value in fields.items():
        if key != "prompt":
            print("  %-18s %s" % (key + ":", value))
    print("  %-18s %s" % ("prompt:", job.prompt))
    for name, items in (("image[]", job.images), ("mask", [job.mask] if job.mask else []),
                        ("markup", [job.markup] if job.markup else [])):
        for item in items:
            dims = "%dx%d" % tuple(item["dims"]) if item["dims"] else "?"
            print("  %-18s %s (%s, %s)" % (name + ":", item["path"], item["kind"], dims))
    print("  %-18s %s" % ("api key:", "%s (from %s)" % (mask_key(cfg.api_key), cfg.key_source)
                          if cfg.api_key else "NOT SET - fill in %s" % ENV_FILE))
    print("  %-18s %s" % ("output:", os.path.join(job.outdir, "%s-%s-1%s" % (job.tag, job.label, EXT[job.format]))))
    for text in job.notes:
        print("NOTE: " + text)


def check(cfg, args):
    exists = os.path.isfile(ENV_FILE)
    print("config file : %s (%s)" % (ENV_FILE, "found" if exists else "missing - cp .env.example .env"))
    try:
        cfg.require_key()
    except UsageError as exc:
        print("ERROR: %s" % exc)
        return 2
    print("API key     : %s (from %s)" % (mask_key(cfg.api_key), cfg.key_source))
    if exists and cfg.key_source == ENV_FILE and os.stat(ENV_FILE).st_mode & 0o077:
        print("              tip: chmod 600 %s so other users on this machine cannot read it" % ENV_FILE)
    print("endpoint    : %s" % cfg.base_url)
    if cfg.organization or cfg.project:
        print("org/project : %s / %s" % (cfg.organization or "-", cfg.project or "-"))
    if cfg.proxy:
        print("proxy       : %s" % mask_url(cfg.proxy))
    default_model = cfg.get("OPENAI_IMAGE_MODEL")
    model = resolve_model(args.model or default_model, default_model)
    print("defaults    : model=%s quality=%s resolution=%s format=%s" % (
        model, cfg.get("OPENAI_IMAGE_QUALITY"), cfg.get("OPENAI_IMAGE_RESOLUTION"), cfg.get("OPENAI_IMAGE_FORMAT")))
    try:
        opener = make_opener(cfg)
        send(opener, cfg, "GET", "%s/models/%s" % (cfg.base_url, urllib.parse.quote(model, safe="")),
             api_headers(cfg), None, 30, retries=0)
    except ApiError as exc:
        if exc.status == 404 or "model_not_found" in exc.code:
            print("FAIL: the key works, but %s is not available to it. Try OPENAI_IMAGE_MODEL=gpt-image-2.5-sunburst." % model)
            return 1
        if exc.status == 403 and ("scope" in exc.message.lower() or "permission" in exc.message.lower()):
            print("OK (partly): the key is valid but may not read the model list (restricted key). "
                  "Generation works if the key has write access to Images.")
            return 0
        print("FAIL: HTTP %d %s: %s" % (exc.status, exc.code, exc.message))
        for hint in api_hints(exc, model, cfg):
            print("HINT: " + hint)
        return 1
    except NetworkError as exc:
        print("FAIL: %s" % exc)
        for hint in exc.hints:
            print("HINT: " + hint)
        return 1
    except UsageError as exc:
        print("ERROR: %s" % exc)
        return 2
    print("OK: the key works and %s is available. If generation answers 403 'organization must be "
          "verified', verify it at https://platform.openai.com/settings/organization/general." % model)
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="openai_image.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Generate or edit images with the OpenAI Images API (GPT Image 2.x) using your own API key.",
        epilog="Setup: cp .env.example .env, put OPENAI_API_KEY=sk-... in it, then run --check (free).\n"
               "Sizes: 1K/2K/4K keep about 1024x1024 / 2560x1440 / 3840x2160 pixels for any aspect ratio.")
    p.add_argument("-p", "--prompt", help="image prompt (required)")
    p.add_argument("-i", "--image", action="append", default=[], metavar="FILE",
                   help="reference / source image (png, jpg, webp; repeatable, max 16) -> edits endpoint")
    p.add_argument("-M", "--mask", metavar="PNG", help="inpainting mask: transparent = area to change (first -i image)")
    p.add_argument("--markup", metavar="PNG", help="transparent PNG overlay (circles, arrows) that guides the edit")
    p.add_argument("-a", "--aspect", help="aspect ratio, e.g. 16:9, 9:16, 1:1, 21:9 or auto [1:1; edits: first image's ratio]")
    p.add_argument("-r", "--resolution", help="1K, 2K or 4K [.env OPENAI_IMAGE_RESOLUTION or 2K]")
    p.add_argument("-s", "--size", help="explicit WIDTHxHEIGHT or auto (overrides -a / -r)")
    p.add_argument("-m", "--model", help="model id, or sunburst / flare [.env OPENAI_IMAGE_MODEL or gpt-image-2.6-sunburst]")
    p.add_argument("-q", "--quality", help="low, medium, high, xhigh, max or auto [.env or high]")
    p.add_argument("-c", "--complexity", help="planning effort ('thinking'): low, medium or high [model default]")
    p.add_argument("-b", "--background", help="auto, opaque or transparent")
    p.add_argument("-f", "--format", help="png, jpeg, webp (gif / svg need preview access) [png]")
    p.add_argument("--compression", type=int, metavar="0-100", help="jpeg / webp compression")
    p.add_argument("--moderation", help="auto (default) or low")
    p.add_argument("--input-fidelity", help="low or high (gpt-image-1.5 / 1-mini only)")
    p.add_argument("-n", "--count", type=int, default=1, help="number of images [1]")
    p.add_argument("-o", "--outdir", default=DEFAULT_OUTDIR, help="output directory [~/Pictures/AI生图]")
    p.add_argument("-t", "--tag", help="file-name prefix [timestamp]")
    p.add_argument("--label", help=argparse.SUPPRESS)
    p.add_argument("--timeout", type=float, help="seconds to wait per request [.env or 600]")
    p.add_argument("--record", help=argparse.SUPPRESS)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify the key and model access (no image, no cost)")
    mode.add_argument("--dry-run", action="store_true", help="show the request that would be sent, then stop")
    mode.add_argument("--preflight", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--dims", nargs="+", metavar="FILE", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.dims:
        for path in args.dims:
            try:
                with open(path, "rb") as fh:
                    print(dims_text(fh.read()))
            except OSError:
                print("?")
        return 0
    cfg = Config()
    try:
        if args.check:
            return check(cfg, args)
        job = prepare(cfg, args)
        if args.dry_run:
            dry_run(cfg, job)
            return 0
        cfg.require_key()
        make_opener(cfg)  # validates the proxy setting
        if args.preflight:
            return 0
        for text in job.notes:
            log("NOTE: " + text)
        return generate(cfg, job)
    except UsageError as exc:
        log("ERROR: %s" % exc)
        return 2
    except KeyboardInterrupt:
        log("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
