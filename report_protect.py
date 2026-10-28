"""보고서 HTML 암호화 (비밀번호 로그인 화면).

생성된 보고서 HTML 전체를 AES-256-GCM으로 암호화하고, 비밀번호 입력 화면만 있는 HTML로 감싼다.
GitHub에는 암호문만 올라가며, 올바른 비밀번호를 입력해야 브라우저(Web Crypto)에서 복호화되어 보고서가 열린다.

비밀번호는 저장소에 넣지 않는다: .env 의 REPORT_PASSWORD (없으면 실행 시 입력).
키 유도: PBKDF2-HMAC-SHA256, 600,000회. 솔트는 고정값(공개되어도 무방), IV는 파일마다 무작위.
"""
import base64
import getpass
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

SALT = bytes.fromhex("cfa8408a704a49358574534627eb53f6")
ITERATIONS = 600_000
_key_cache = {}


def _password():
    load_dotenv()
    pw = os.getenv("REPORT_PASSWORD")
    if not pw:
        if os.getenv("CI") or not sys.stdin or not sys.stdin.isatty():
            raise SystemExit("REPORT_PASSWORD 가 설정되지 않았습니다 (.env 또는 GitHub Secrets).")
        pw = getpass.getpass("보고서 비밀번호: ")
    if len(pw) < 8:
        raise SystemExit("보고서 비밀번호는 8자 이상이어야 합니다.")
    return pw


def _key(password):
    if password not in _key_cache:
        _key_cache[password] = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, ITERATIONS, dklen=32)
    return _key_cache[password]


def encrypt_page(html, title, password=None):
    """보고서 HTML을 암호화해 로그인 화면 HTML을 돌려준다."""
    key = _key(password or _password())
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, html.encode("utf-8"), None)  # 암호문 + 인증태그(16바이트)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    payload = json.dumps({"s": b64(SALT), "i": ITERATIONS, "n": b64(iv), "c": b64(ct)})
    return LOGIN_HTML.replace("__TITLE__", title).replace("__PAYLOAD__", payload)


LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>__TITLE__ · 로그인</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f7fb;font-family:'Inter','Malgun Gothic',sans-serif;color:#0f172a}
.box{width:360px;max-width:92vw;background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:2rem 1.8rem;box-shadow:0 10px 30px rgba(15,23,42,.08)}
.lock{font-size:2rem}
h1{font-size:1.25rem;margin:.6rem 0 .3rem;color:#4f46e5}
p{color:#64748b;font-size:.85rem;margin:0 0 1.2rem;line-height:1.5}
input[type=password]{width:100%;padding:.75rem .9rem;border:1px solid #cbd5e1;border-radius:10px;font-size:1rem;font-family:inherit}
input[type=password]:focus{outline:none;border-color:#4f46e5;box-shadow:0 0 0 3px rgba(79,70,229,.15)}
label{display:flex;align-items:center;gap:.4rem;font-size:.82rem;color:#475569;margin:.8rem 0 1rem;cursor:pointer}
button{width:100%;padding:.75rem;border:0;border-radius:10px;background:#4f46e5;color:#fff;font-weight:700;font-size:.95rem;cursor:pointer;font-family:inherit}
button:disabled{opacity:.6;cursor:wait}
.err{color:#dc2626;font-size:.82rem;min-height:1.2em;margin-top:.7rem}
</style></head><body>
<form class="box" id="f" autocomplete="off">
  <div class="lock">🔒</div>
  <h1>__TITLE__</h1>
  <p>내부 자료입니다. 비밀번호를 입력해 주세요.</p>
  <input type="password" id="pw" placeholder="비밀번호" autofocus required>
  <label><input type="checkbox" id="keep"> 이 브라우저에서 7일간 로그인 유지</label>
  <button id="go" type="submit">열기</button>
  <div class="err" id="err"></div>
</form>
<script>
(function () {
  var P = __PAYLOAD__;
  var KEY = 'foiReportKey', DAYS = 7;
  function b64d(s) { return Uint8Array.from(atob(s), function (c) { return c.charCodeAt(0); }); }
  function b64e(u) { var s = ''; for (var i = 0; i < u.length; i++) s += String.fromCharCode(u[i]); return btoa(s); }
  function clearKey() { try { sessionStorage.removeItem(KEY); localStorage.removeItem(KEY); } catch (e) {} }
  // 보고서 화면의 '잠금' 버튼에서 호출
  window.__reportLock = function () { clearKey(); location.reload(); };

  function derive(pw) {
    return crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveBits'])
      .then(function (base) { return crypto.subtle.deriveBits({ name: 'PBKDF2', salt: b64d(P.s), iterations: P.i, hash: 'SHA-256' }, base, 256); })
      .then(function (bits) { return new Uint8Array(bits); });
  }
  function decrypt(raw) {
    return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt'])
      .then(function (k) { return crypto.subtle.decrypt({ name: 'AES-GCM', iv: b64d(P.n) }, k, b64d(P.c)); })
      .then(function (pt) { return new TextDecoder().decode(pt); });
  }
  function show(html) { document.open(); document.write(html); document.close(); }
  function savedKey() {
    try {
      var s = sessionStorage.getItem(KEY);
      if (s) return s;
      var l = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (l && l.exp > Date.now()) return l.k;
      localStorage.removeItem(KEY);
    } catch (e) {}
    return null;
  }

  var form = document.getElementById('f'), err = document.getElementById('err'), go = document.getElementById('go');
  if (!window.crypto || !crypto.subtle) {
    err.textContent = '이 브라우저에서는 복호화를 지원하지 않습니다 (https 주소로 접속해 주세요).';
    go.disabled = true;
    return;
  }
  var k0 = savedKey();
  if (k0) {
    form.style.visibility = 'hidden';
    decrypt(b64d(k0)).then(show).catch(function () { clearKey(); form.style.visibility = 'visible'; });
  }
  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    err.textContent = '';
    go.disabled = true; go.textContent = '확인 중...';
    var raw;
    derive(document.getElementById('pw').value)
      .then(function (r) { raw = r; return decrypt(r); })
      .then(function (html) {
        try {
          var k = b64e(raw);
          sessionStorage.setItem(KEY, k);
          if (document.getElementById('keep').checked) localStorage.setItem(KEY, JSON.stringify({ k: k, exp: Date.now() + DAYS * 864e5 }));
        } catch (e) {}
        show(html);
      })
      .catch(function () {
        err.textContent = '비밀번호가 올바르지 않습니다.';
        go.disabled = false; go.textContent = '열기';
        document.getElementById('pw').select();
      });
  });
})();
</script>
</body></html>
"""
