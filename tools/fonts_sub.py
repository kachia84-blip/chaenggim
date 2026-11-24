"""프리텐다드(글자)·토스페이스(아이콘)를 앱에서 쓰는 글자만 남겨 fonts/ 에 넣는다.
원본: build/fontsrc/PretendardVariable.woff2, 토스페이스는 산안법검색기/tossface_src/ 캐시를 쓴다.
CDN 원본을 통째로 연결하면 폰에서 느려지므로 잘라 낸다. 사용: python tools/fonts_sub.py (fontTools·brotli 필요)"""
import glob, io, os, sys
from fontTools import subset
from fontTools.ttLib import TTFont

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = ROOT  # 챙김은 앱 파일이 폴더 맨 위에 있음
OUT = os.path.join(APP, "fonts")
PRETENDARD = os.path.join(os.path.dirname(ROOT), "지도사2차", "build", "fontsrc", "PretendardVariable.woff2")
TOSS = os.path.join(os.path.dirname(ROOT), "산안법검색기", "tossface_src", "TossFaceFontMac-%02d.woff2")
JOIN = (0xFE0F, 0x200D)


def is_emoji(o):
    return (o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF
            or 0x2300 <= o <= 0x23FF or o in (0x203C, 0x2049, 0x2122, 0x2139, 0x24C2, 0x3030, 0x303D, 0x3297, 0x3299))


def app_text():
    files = [f for f in glob.glob(os.path.join(APP, "**", "*.*"), recursive=True)
             if f.endswith((".js", ".html", ".json", ".css", ".webmanifest")) and os.sep + "fonts" + os.sep not in f and os.sep + ".git" + os.sep not in f]
    return "".join(open(f, encoding="utf-8").read() for f in files)


def ks_hangul():  # KS X 1001 상용 한글 2,350자: 메모에 새 글자를 쳐도 대부분 프리텐다드로 보이게
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try: out.append(bytes([hi, lo]).decode("euc-kr"))
            except UnicodeDecodeError: pass
    return out


def save(font, name):
    font.flavor = "woff2"
    buf = io.BytesIO(); font.save(buf)
    open(os.path.join(OUT, name), "wb").write(buf.getvalue())
    return len(buf.getvalue())


def options():
    opt = subset.Options()
    opt.flavor = "woff2"
    opt.layout_features = ["*"]
    opt.name_IDs = ["*"]  # 저작권·라이선스(OFL) 정보 유지
    return opt


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".woff2"): os.remove(os.path.join(OUT, f))
    text = app_text()
    emoji = sorted({ord(c) for c in text if is_emoji(ord(c))})
    chars = {ord(c) for c in text if not is_emoji(ord(c)) and ord(c) >= 0x20} | {ord(c) for c in ks_hangul()} | set(range(0x20, 0x7F))
    cmap = TTFont(PRETENDARD).getBestCmap()
    keep = sorted(c for c in chars if c in cmap)
    sub = subset.Subsetter(options()); sub.populate(unicodes=keep)
    font = TTFont(PRETENDARD); sub.subset(font)
    size = save(font, "pretendard.woff2")
    css = ["/* 프리텐다드(Pretendard, SIL OFL 1.1, https://github.com/orioncactus/pretendard)와"
           " 토스페이스(Tossface, https://github.com/toss/tossface) — 앱에서 쓰는 글자만 남긴 조각. tools/fonts_sub.py 가 만듦 */",
           '@font-face{font-family:"Pretendard";src:url("pretendard.woff2") format("woff2");font-weight:45 920;font-display:swap}']
    print(f"프리텐다드: 글자 {len(keep)}개 · {size // 1024} KB (원본 {os.path.getsize(PRETENDARD) // 1024} KB)")
    total, n = 0, 0
    for i in range(12):
        src = TOSS % i
        cm = TTFont(src).getBestCmap()
        have = [c for c in emoji if c in cm and c not in JOIN]
        if not have: continue
        extra = [c for c in JOIN if c in cm]
        sub = subset.Subsetter(options()); sub.populate(unicodes=have + extra)
        font = TTFont(src); sub.subset(font)
        name = f"tf{i:02d}.woff2"
        total += save(font, name); n += len(have)
        rng = ", ".join(f"U+{c:X}" for c in have + extra)
        css.append(f'@font-face{{font-family:"Tossface";src:url("{name}") format("woff2");font-display:swap;unicode-range:{rng}}}')
    missing = [chr(c) for c in emoji if not any(c in TTFont(TOSS % i).getBestCmap() for i in range(12))]
    open(os.path.join(OUT, "fonts.css"), "w", encoding="utf-8").write("\n".join(css) + "\n")
    print(f"토스페이스: 이모지 {n}개 · {total // 1024} KB" + (f" · 없는 이모지 {''.join(missing)}" if missing else ""))


main()
