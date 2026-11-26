import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode
from urllib.request import urlopen
from xml.etree import ElementTree


COLLECT_DIR = Path(__file__).resolve().parent
DATA_DIR = COLLECT_DIR.parent / "data"
LOG_PATH = COLLECT_DIR / "last_run.log"
KST = timezone(timedelta(hours=9))
KEY_NAME = "DATA_GO_KR_KEY"


def get_key(name=KEY_NAME):
    key = os.environ.get(name)
    if key is None and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
                key, _ = winreg.QueryValueEx(env, name)
        except (ImportError, OSError):
            pass
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError(f"{name} is missing")
    return key.strip()


def kst_now():
    return datetime.now(KST)


def kst_today():
    return kst_now().date()


def _xml_value(element):
    if not len(element):
        return element.text or ""
    result = {}
    for child in element:
        name = child.tag.rsplit("}", 1)[-1]
        value = _xml_value(child)
        if name not in result:
            result[name] = value
        elif isinstance(result[name], list):
            result[name].append(value)
        else:
            result[name] = [result[name], value]
    return result


def http_get_json(url, params, retries=3, backoff=1.0):
    """Read a JSON or XML object, retrying transient or unreadable responses."""
    query = dict(params)
    if "serviceKey" in query:
        query["serviceKey"] = unquote(query["serviceKey"])
    request_url = f"{url}?{urlencode(query)}" if query else url

    for attempt in range(retries + 1):
        try:
            with urlopen(request_url, timeout=20) as response:
                payload = response.read()
                if payload.removeprefix(b"\xef\xbb\xbf").lstrip().startswith(b"<"):
                    result = _xml_value(ElementTree.fromstring(payload))
                else:
                    result = json.loads(payload)
                if not isinstance(result, dict):
                    raise ValueError("Expected a response object")
                return result
        except HTTPError as error:
            status = error.code
            error.close()
            failure = f"HTTP {status}"
            if status not in (408, 429) and not 500 <= status < 600:
                break
        except (OSError, ValueError, ElementTree.ParseError) as error:
            failure = type(error).__name__
        if attempt < retries:
            time.sleep(backoff * 2**attempt)
    raise RuntimeError(f"{url}: {failure}")


def _atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                prefix=f".{path.name}.", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path, obj):
    _atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def require_minimum(source, count, minimum):
    if count < minimum:
        raise RuntimeError(f"{source}: collected {count}, expected at least {minimum}")


def log(msg):
    msg = str(msg)
    try:
        key = get_key()
    except RuntimeError:
        key = ""
    if key:
        decoded = unquote(key)
        for variant in {key, decoded, quote(decoded, safe=""), urlencode({"k": decoded})[2:]}:
            msg = msg.replace(variant, "***")
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-299:]
    except FileNotFoundError:
        lines = []
    lines.append(f"{kst_now().isoformat(timespec='seconds')} {' '.join(msg.splitlines())}")
    _atomic_write(LOG_PATH, "\n".join(lines) + "\n")
