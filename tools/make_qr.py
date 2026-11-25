"""설치용 QR 생성: python make_qr.py [주소]  → QR.png"""
import sys
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M

URL = sys.argv[1] if len(sys.argv) > 1 else "https://kachia84-blip.github.io/chaenggim/"
img = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=14, border=3)
img.add_data(URL)
img.make(fit=True)
img.make_image(fill_color="#1F4E8C", back_color="white").save(Path(__file__).parent.parent / "QR.png")
print(URL)
