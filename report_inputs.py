"""위탁운용 원본 자료(엑셀) 암호화/복호화.

공개 저장소에는 원본 엑셀을 올리지 않고, 보고서 비밀번호로 암호화한 파일만 report_data_enc/ 에 둔다.
  python report_inputs.py encrypt   # report_data/*.xls* → report_data_enc/*.enc (로컬에서 초기 등록용)
  python report_inputs.py decrypt   # report_data_enc/*.enc → report_data/ (GitHub Actions에서 보고서 생성 전)

파일 형식: b"FOIENC1\\n" + IV(12바이트) + AES-256-GCM 암호문
  평문 = 파일명 길이(2바이트, big-endian) + 파일명(UTF-8) + 파일 내용
키: report_protect 와 동일 (REPORT_PASSWORD → PBKDF2-HMAC-SHA256 60만 회)
저장 위치(슬롯): 같은 종류의 자료를 다시 올리면 덮어쓰도록 파일명 키워드로 정한다 — 브라우저 업로드(report_upload.js)와 동일 규칙.
"""
import glob
import hashlib
import os
import re
import sys
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from report_protect import _key, _password

MAGIC = b"FOIENC1\n"
SRC_DIR, ENC_DIR = "report_data", "report_data_enc"


def slot_for(name):
    """파일명 → 저장 슬롯. 인식할 수 없는 파일은 None."""
    name = unicodedata.normalize("NFC", name)
    if "기준가" in name:
        return "nav"
    if "매매" in name:
        return "trades"
    if "헤지" in name:
        m = re.search(r"\d+년\s*(\S+?)\s*헤지", name)
        mgr = m.group(1) if m else name
        return "hedge-" + hashlib.sha256(mgr.encode("utf-8")).hexdigest()[:8]
    if "취합본" in name:
        return "holdings"
    return None


def encrypt_bytes(key, name, data):
    nb = unicodedata.normalize("NFC", name).encode("utf-8")
    pt = len(nb).to_bytes(2, "big") + nb + data
    iv = os.urandom(12)
    return MAGIC + iv + AESGCM(key).encrypt(iv, pt, None)


def decrypt_bytes(key, blob):
    if not blob.startswith(MAGIC):
        raise ValueError("암호화 파일 형식이 아닙니다")
    iv, ct = blob[len(MAGIC):len(MAGIC) + 12], blob[len(MAGIC) + 12:]
    pt = AESGCM(key).decrypt(iv, ct, None)
    n = int.from_bytes(pt[:2], "big")
    name = os.path.basename(pt[2:2 + n].decode("utf-8"))  # 경로 조작 방지
    return name, pt[2 + n:]


def encrypt_all():
    key = _key(_password())
    os.makedirs(ENC_DIR, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(SRC_DIR, "*.xls*"))):
        base = os.path.basename(f)
        if base.startswith("~$"):
            continue
        slot = slot_for(base)
        if not slot:
            print("  건너뜀(종류 인식 불가):", base)
            continue
        with open(f, "rb") as fh:
            blob = encrypt_bytes(key, base, fh.read())
        with open(os.path.join(ENC_DIR, slot + ".enc"), "wb") as fh:
            fh.write(blob)
        print(f"  {slot}.enc ← {base}")


def decrypt_all():
    key = _key(_password())
    os.makedirs(SRC_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(ENC_DIR, "*.enc")))
    if not files:
        raise SystemExit(f"{ENC_DIR}/ 에 암호화된 자료가 없습니다.")
    for f in files:
        with open(f, "rb") as fh:
            try:
                name, data = decrypt_bytes(key, fh.read())
            except Exception:
                raise SystemExit(f"{os.path.basename(f)} 복호화 실패 — 업로드 시 비밀번호와 REPORT_PASSWORD 가 다릅니다.")
        with open(os.path.join(SRC_DIR, name), "wb") as fh:
            fh.write(data)
        print(f"  {os.path.basename(f)} → {SRC_DIR}/ ({len(data) / 1024:,.0f}KB)")  # 파일명은 로그(공개)에 남기지 않음


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "encrypt":
        encrypt_all()
    elif cmd == "decrypt":
        decrypt_all()
    else:
        raise SystemExit("사용법: python report_inputs.py encrypt|decrypt")
