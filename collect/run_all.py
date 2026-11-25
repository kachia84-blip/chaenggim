import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collect import benefits, events
from collect.common import DATA_DIR, atomic_write_json, kst_now, log


def _previous_count(data_dir, source):
    if source == "benefits":
        try:
            index = json.loads((data_dir / "benefits" / "index.json").read_text(encoding="utf-8"))
            return sum(index.values())
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    try:
        rows = json.loads((data_dir / f"{source}.json").read_text(encoding="utf-8"))
        return len(rows) if isinstance(rows, list) else 0
    except (OSError, ValueError):
        return 0


def main(data_dir=DATA_DIR):
    data_dir = Path(data_dir)
    today = kst_now().date()
    sources = {}
    messages = []
    for name, collector in (("benefits", benefits.collect), ("events", events.collect)):
        try:
            count = collector(data_dir, today)
        except Exception as error:
            sources[name] = {"count": _previous_count(data_dir, name), "ok": False}
            messages.append(f"{name}: {error}")
        else:
            sources[name] = {"count": count, "ok": True}
            messages.append(f"{name}: collected {count}")

    failed = not all(source["ok"] for source in sources.values())
    if any(source["ok"] for source in sources.values()):
        try:
            atomic_write_json(data_dir / "meta.json", {
                "updated": kst_now().isoformat(timespec="seconds"), "sources": sources,
            })
        except OSError as error:
            failed = True
            messages.append(f"meta: {error}")
    try:
        for message in messages:
            log(message)
    except OSError:
        print("수집 기록을 저장하지 못했습니다.", file=sys.stderr)
        failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
