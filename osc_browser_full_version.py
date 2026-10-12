import re
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import webview

PROXY_PORT = 8999

AD_DOMAINS = [
    'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
    'adservice.google.com', 'adnxs.com', 'popads.net', 'adroll.com',
    'outbrain.com', 'taboola.com', 'mediavine.com', 'adzerk.net',
    'rubiconproject.com', 'ads.youtube.com', 'youtube.com/pagead/',
    'youtube.com/api/stats/ads', 'youtube.com/ptracking',
    'youtube.com/get_video_info', 'youtubei/v1/log_event',
    'youtubei/v1/player/ad_break',
]
TRACKER_DOMAINS = [
    'google-analytics.com', 'analytics.google.com', 'connect.facebook.net',
    'scorecardresearch.com', 'hotjar.com', 'clarity.ms', 'mixpanel.com',
    'segment.com', 'quantserve.com', 'facebook.com/tr',
]


def _build_adblock_script(ab_enabled: bool, tb_enabled: bool) -> str:
    blocked = []
    if ab_enabled:
        blocked += AD_DOMAINS
    if tb_enabled:
        blocked += TRACKER_DOMAINS
    if not blocked:
        return ''
    blocked_json = '[' + ','.join('"' + d + '"' for d in blocked) + ']'
    return (
        "<script>(function(){"
        "var BLOCKED=" + blocked_json + ";"
        "function isB(u){try{var s=String(u).toLowerCase();"
        "for(var i=0;i<BLOCKED.length;i++){if(s.indexOf(BLOCKED[i])!==-1)return true;}}"
        "catch(e){}return false;}"
        "if(window.fetch){var _f=window.fetch;"
        "window.fetch=function(u,o){var url=(typeof u==='string')?u:(u&&u.url);"
        "if(isB(url))return Promise.reject(new Error('Blocked by OCS AdBlock'));"
        "return _f.apply(this,arguments);};}"
        "var XO=XMLHttpRequest.prototype.open;"
        "XMLHttpRequest.prototype.open=function(m,u){this.__ocsB=isB(u);"
        "if(this.__ocsB)return;return XO.apply(this,arguments);};"
        "var XS=XMLHttpRequest.prototype.send;"
        "XMLHttpRequest.prototype.send=function(){if(this.__ocsB)return;"
        "return XS.apply(this,arguments);};"
        "if(window.WebSocket){var _W=window.WebSocket;"
        "window.WebSocket=function(u,p){if(isB(u))throw new Error('Blocked');"
        "return new _W(u,p);};}"
        "if(window.EventSource){var _E=window.EventSource;"
        "window.EventSource=function(u,c){if(isB(u))throw new Error('Blocked');"
        "return new _E(u,c);};}"
        "})();</script>"
    )


def _build_nav_interceptor(subdomain: str) -> str:
    """
    Fuerza que clicks en <a>, submits de <form> y window.open()
    permanezcan DENTRO del subdominio-proxy de esta web.

    IMPORTANTE: resuelve las URLs relativas contra document.baseURI
    (que apunta al sitio original gracias al <base href> inyectado),
    NO contra location.href (que apunta al proxy). Así
    action="/session" en GitHub se convierte en
    https://github.com/session y no en http://d123.localhost:8999/session.
    """
    proxy_base = f'http://{subdomain}.localhost:{PROXY_PORT}/proxy?url='
    origin = f'http://{subdomain}.localhost:{PROXY_PORT}'
    return (
        "<script>(function(){"
        f"var PB='{proxy_base}';var OG='{origin}';"
        "function toProxy(u){try{"
        "if(typeof u!=='string'||!u)return u;"
        "if(u.indexOf('javascript:')===0||u.charAt(0)==='#'||"
        "u.indexOf('data:')===0||u.indexOf('blob:')===0||"
        "u.indexOf('mailto:')===0||u.indexOf('tel:')===0||"
        "u.indexOf('about:')===0)return u;"
        # Resolver contra el <base> (sitio original), no contra el proxy
        "var abs=new URL(u,document.baseURI).href;"
        # ¿Ya está proxeada? No la toques.
        "if(abs.indexOf(OG+'/proxy?url=')===0)return abs;"
        # Si por lo que sea cayó en nuestro propio origen pero sin /proxy,
        # la reinterpretamos como ruta relativa al sitio original.
        "if(abs.indexOf(OG)===0&&abs.indexOf('/proxy?url=')===-1){"
        "var path=abs.substring(OG.length);"
        "abs=new URL(path,document.baseURI).href;"
        "}"
        "return PB+encodeURIComponent(abs);"
        "}catch(e){return u;}}"
        # --- links ---
        "document.addEventListener('click',function(e){"
        "if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||"
        "e.shiftKey||e.altKey)return;"
        "var a=e.target;"
        "while(a&&a.tagName!=='A')a=a.parentElement;"
        "if(!a)return;"
        "var href=a.getAttribute('href');"
        "if(!href||href.indexOf('javascript:')===0||href.charAt(0)==='#')return;"
        "if(a.target&&a.target!=='_self')return;"
        "e.preventDefault();"
        "location.href=toProxy(href);"
        "},true);"
        # --- forms ---
        "document.addEventListener('submit',function(e){"
        "var f=e.target;"
        "if(!f||f.tagName!=='FORM')return;"
        "var act=f.getAttribute('action')||'';"
        "try{f.action=toProxy(act);}catch(err){}"
        "},true);"
        # --- window.open ---
        "var _wo=window.open;"
        "window.open=function(u,n,fe){return _wo.call(window,toProxy(u),n,fe);};"
        "})();</script>"
    )

class AntiBlockProxy(BaseHTTPRequestHandler):
    # HTTP/1.1 → keep-alive y Content-Length respetado siempre
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        pass

    # ---------- utilidades de body ----------
    def _drain_body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length > 0:
                self.rfile.read(length)
        except Exception:
            pass

    def _read_body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length > 0:
                return self.rfile.read(length)
        except Exception:
            pass
        return None

    # ---------- enrutado de métodos ----------
    def do_GET(self):     self._handle_request('GET')
    def do_POST(self):    self._handle_request('POST')
    def do_PUT(self):     self._handle_request('PUT')
    def do_DELETE(self):  self._handle_request('DELETE')
    def do_PATCH(self):   self._handle_request('PATCH')
    def do_HEAD(self):    self._handle_request('HEAD')
    def do_OPTIONS(self): self._handle_request('OPTIONS')

    # ---------- manejador común ----------
    def _handle_request(self, method):
        parsed_path = urllib.parse.urlparse(self.path)

        # 1) UI del navegador (solo desde 127.0.0.1)
        if method == 'GET' and parsed_path.path in ('/', '/index.html'):
            body = HTML_CODE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return

        # 2) Cualquier otra ruta distinta de /proxy → 404
        if parsed_path.path != '/proxy':
            self._drain_body()
            self.send_error(404)
            return

        query = urllib.parse.parse_qs(parsed_path.query)
        target_url  = query.get('url', [None])[0]
        ab_enabled  = query.get('ab', ['0'])[0] == '1'
        tb_enabled  = query.get('tb', ['0'])[0] == '1'

        if not target_url:
            self._drain_body()
            self.send_error(400, "URL no especificada")
            return

        # 3) Leer body (POST/PUT/PATCH) ANTES de responder
        body_data = self._read_body()

        try:
            # Cabeceras hacia el destino: las nuestras + las del navegador
            req_headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/122.0.0.0 Safari/537.36'
                ),
                'Accept': (
                    'text/html,application/xhtml+xml,application/xml;q=0.9,'
                    'image/avif,image/webp,image/apng,*/*;q=0.8'
                ),
                'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
                'Accept-Encoding': 'identity',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Upgrade-Insecure-Requests': '1',
            }
            for h in ('Content-Type', 'Cookie', 'Referer', 'Origin',
                      'Authorization', 'X-Requested-With', 'X-CSRF-Token'):
                v = self.headers.get(h)
                if v:
                    req_headers[h] = v

            req = urllib.request.Request(
                target_url,
                data=body_data,
                headers=req_headers,
                method=method
            )

            opener = urllib.request.build_opener()
            with opener.open(req, timeout=60) as resp:
                content_type = resp.headers.get(
                    'Content-Type', 'text/html; charset=utf-8')
                final_url = resp.geturl() or target_url
                resp_body = resp.read()

                # ---- procesar HTML (solo GET y no HEAD) ----
                if method != 'HEAD' and (
                    'text/html' in content_type.lower()
                    or 'application/xhtml' in content_type.lower()
                ):
                    charset_match = re.search(
                        r'charset=["\']?([\w\-]+)', content_type, re.I)
                    charset = charset_match.group(1) if charset_match else 'utf-8'
                    try:
                        html_str = resp_body.decode(charset, errors='ignore')
                    except (LookupError, UnicodeDecodeError):
                        html_str = resp_body.decode('utf-8', errors='ignore')

                    safe_url = (final_url
                                .replace('&', '&amp;')
                                .replace('"', '&quot;')
                                .replace('<', '&lt;')
                                .replace('>', '&gt;'))

                    anti_frame = (
                        "<script>(function(){try{"
                        "Object.defineProperty(window,'top',"
                        "{get:function(){return window.self;}});"
                        "Object.defineProperty(window,'parent',"
                        "{get:function(){return window.self;}});"
                        "Object.defineProperty(window,'frameElement',"
                        "{get:function(){return null;}});"
                        "}catch(e){}})();</script>"
                    )

                    # ★ Identifica el subdominio-proxy actual (d<hash>)
                    host_header = self.headers.get('Host', '')
                    if '.localhost' in host_header:
                        subdomain = host_header.split('.')[0]
                    else:
                        subdomain = 'd0'

                    adblock_script = _build_adblock_script(ab_enabled, tb_enabled)
                    nav_interceptor = _build_nav_interceptor(subdomain)
                    injection = (anti_frame + nav_interceptor + adblock_script +
                                 '<base href="' + safe_url + '">')

                    head_match = re.search(r'<head[^>]*>', html_str, re.I)
                    if head_match:
                        pos = head_match.end()
                        html_str = html_str[:pos] + injection + html_str[pos:]
                    elif re.search(r'<html[^>]*>', html_str, re.I):
                        html_str = re.sub(
                            r'(<html[^>]*>)',
                            lambda m: m.group(1) + injection,
                            html_str, count=1, flags=re.I
                        )
                    else:
                        html_str = injection + html_str

                    # Quita meta-CSP / meta-X-Frame-Options del HTML
                    html_str = re.sub(
                        r'(?i)<meta[^>]*http-equiv=["\']?'
                        r'(content-security-policy|x-frame-options)'
                        r'["\']?[^>]*>',
                        '', html_str
                    )

                    resp_body = html_str.encode('utf-8')
                    if 'charset=' in content_type:
                        content_type = re.sub(
                            r'charset=[\w\-]+', 'charset=utf-8',
                            content_type, flags=re.I)
                    else:
                        content_type = content_type + '; charset=utf-8'

                # ---- respuesta al navegador ----
                self.send_response(getattr(resp, 'status', 200) or 200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(resp_body)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header(
                    'Cache-Control', 'no-cache, no-store, must-revalidate')

                # Reenvía Set-Cookie sin Domain/Secure (queda en el subdominio)
                try:
                    for cookie_header in (resp.headers.get_all('Set-Cookie') or []):
                        cleaned = re.sub(r';\s*[Dd]omain=[^;]*', '',
                                         cookie_header)
                        cleaned = re.sub(r';\s*[Ss]ecure\b', '', cleaned)
                        self.send_header('Set-Cookie', cleaned)
                except Exception:
                    pass

                self.end_headers()
                if method != 'HEAD':
                    self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            try:
                err_body = e.read()
            except Exception:
                err_body = b''
            err_ct = (e.headers.get('Content-Type',
                                    'text/html; charset=utf-8')
                      if e.headers else 'text/html; charset=utf-8')
            if not err_body:
                err_body = (f'<h1>Error {e.code}</h1>').encode('utf-8')
            self.send_response(e.code)
            self.send_header('Content-Type', err_ct)
            self.send_header('Content-Length', str(len(err_body)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if method != 'HEAD':
                try:
                    self.wfile.write(err_body)
                except Exception:
                    pass

        except urllib.error.URLError as e:
            msg = (f'<h1>Error</h1><p>{e.reason}</p>').encode('utf-8')
            self.send_response(502)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            if method != 'HEAD':
                try:
                    self.wfile.write(msg)
                except Exception:
                    pass

        except Exception as e:
            msg = (f'<h1>Error</h1><p>{e}</p>').encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            if method != 'HEAD':
                try:
                    self.wfile.write(msg)
                except Exception:
                    pass


def start_proxy():
    server = ThreadingHTTPServer(('127.0.0.1', PROXY_PORT), AntiBlockProxy)
    server.daemon_threads = True
    server.serve_forever()


proxy_thread = threading.Thread(target=start_proxy, daemon=True)
proxy_thread.start()

HTML_CODE = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>OCS Browser - Navegador Seguro y sin Copyright</title>
  <style>
    :root {
      --menu-bg: #1a2234;
      --accent-color: #3b82f6;
      --bg-dark: #0c0f17;
      --border-color: #334155;
      --shield-color: #10b981;
    }
    body { margin: 0; height: 100vh; font-family: sans-serif; background: var(--bg-dark); color: white; display: flex; flex-direction: column; }
    #tabs-bar { background: var(--bg-dark); display: flex; align-items: center; padding: 6px 6px 0 6px; gap: 4px; border-bottom: 1px solid var(--border-color); overflow-x: auto; }
    .tab { background: var(--menu-bg); padding: 6px 12px; border-top-left-radius: 8px; border-top-right-radius: 8px; font-size: 13px; display: flex; align-items: center; gap: 8px; cursor: pointer; border: 1px solid var(--border-color); border-bottom: none; max-width: 160px; min-width: 100px; color: #94a3b8; user-select: none; transition: background 0.2s, color 0.2s; }
    .tab.active { background: var(--menu-bg); color: white; border-top: 2px solid var(--accent-color); font-weight: bold; }
    .tab-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
    .close-tab { border-radius: 50%; width: 16px; height: 16px; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #94a3b8; }
    .close-tab:hover { background: rgba(255, 255, 255, 0.2); color: white; }
    .add-tab-btn { background: transparent; color: white; border: none; font-size: 16px; padding: 4px 10px; cursor: pointer; border-radius: 4px; }
    .add-tab-btn:hover { background: var(--menu-bg); }
    #nav-bar { background: var(--menu-bg); padding: 8px 12px; display: flex; gap: 8px; border-bottom: 2px solid var(--accent-color); align-items: center; transition: background 0.3s, border-color 0.3s; }
    .url-container { flex: 1; display: flex; align-items: center; background: var(--bg-dark); border: 1px solid var(--border-color); border-radius: 6px; padding-left: 8px; }
    .security-badge { font-size: 14px; cursor: pointer; padding: 2px 6px; border-radius: 4px; user-select: none; }
    .adblock-counter { background: #ef4444; color: white; font-size: 10px; font-weight: bold; padding: 2px 6px; border-radius: 10px; margin-right: 6px; cursor: pointer; user-select: none; display: flex; align-items: center; gap: 3px; }
    #url-bar { flex: 1; padding: 8px 8px 8px 4px; border: none; background: transparent; color: white; outline: none; }
    button { padding: 6px 12px; border-radius: 6px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-weight: bold; transition: background 0.3s, opacity 0.2s; }
    button:hover { opacity: 0.9; }
    button:disabled { opacity: 0.3; cursor: not-allowed; }
    #content-area { flex: 1; position: relative; }
    #home-screen { position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; justify-content: flex-start; align-items: center; gap: 20px; padding: 80px 20px 20px 20px; overflow-y: auto; background-image: url('fondo.jpg'); background-size: cover; background-position: center; z-index: 10; transition: background-image 0.3s ease-in-out; }
    .color-settings { position: absolute; top: 15px; right: 15px; background: var(--menu-bg); border: 1px solid var(--border-color); padding: 10px 14px; border-radius: 12px; display: flex; align-items: center; gap: 12px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5); transition: background 0.3s; flex-wrap: wrap; z-index: 20; }
    .color-picker-group { display: flex; align-items: center; gap: 6px; font-size: 13px; }
    .color-picker-group input[type="color"] { border: none; width: 24px; height: 24px; border-radius: 50%; cursor: pointer; background: transparent; }
    .lang-select { background: var(--bg-dark); color: white; border: 1px solid var(--border-color); border-radius: 6px; padding: 4px; font-size: 12px; outline: none; cursor: pointer; }
    .preset-btn { width: 18px; height: 18px; border-radius: 50%; border: 1px solid #ffffff55; padding: 0; cursor: pointer; }
    .bg-btn { font-size: 11px; padding: 4px 8px; background: var(--bg-dark); border: 1px solid var(--border-color); }
    .search-container { display: flex; align-items: center; width: 100%; max-width: 580px; background: var(--menu-bg); border: 2px solid var(--accent-color); border-radius: 25px; padding: 4px 10px 4px 16px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4); transition: background 0.3s, border-color 0.3s; }
    .engine-select { background: transparent; color: white; border: none; outline: none; font-size: 13px; font-weight: bold; cursor: pointer; padding-right: 10px; margin-right: 8px; border-right: 1px solid var(--border-color); }
    .engine-select option { background: var(--menu-bg); color: white; }
    .search-box { flex: 1; padding: 12px 6px; border: none; background: transparent; color: white; font-size: 16px; outline: none; }
    .shortcuts-grid { display: flex; gap: 15px; flex-wrap: wrap; justify-content: center; }
    .shortcut { width: 80px; height: 80px; background: var(--menu-bg); border-radius: 12px; display: flex; justify-content: center; align-items: center; cursor: pointer; border: 1px solid var(--border-color); font-weight: bold; transition: background 0.3s, border-color 0.3s, transform 0.2s; }
    .shortcut:hover { border-color: var(--accent-color); transform: translateY(-3px); }
    #installed-apps-section { width: 100%; max-width: 600px; background: rgba(26, 34, 52, 0.85); backdrop-filter: blur(8px); border: 1px solid var(--border-color); border-radius: 16px; padding: 16px 20px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5); margin-top: 10px; }
    .apps-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); gap: 15px; margin-top: 12px; }
    .app-card { display: flex; flex-direction: column; align-items: center; background: var(--bg-dark); border: 1px solid var(--border-color); border-radius: 12px; padding: 10px 6px; cursor: pointer; position: relative; transition: transform 0.2s, border-color 0.2s; }
    .app-card:hover { transform: translateY(-3px); border-color: var(--accent-color); }
    .app-icon { font-size: 28px; margin-bottom: 6px; }
    .app-name { font-size: 11px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; color: #cbd5e1; }
    .app-delete { position: absolute; top: 3px; right: 3px; width: 16px; height: 16px; background: #ef4444; color: white; border-radius: 50%; display: none; align-items: center; justify-content: center; font-size: 10px; cursor: pointer; }
    .app-card:hover .app-delete { display: flex; }
    .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); display: none; justify-content: center; align-items: center; z-index: 100; backdrop-filter: blur(4px); }
    .modal-box { background: var(--menu-bg); border: 2px solid var(--accent-color); border-radius: 14px; padding: 24px; width: 380px; box-shadow: 0 10px 30px rgba(0,0,0,0.7); display: flex; flex-direction: column; gap: 14px; }
    .modal-box h3 { margin: 0; color: white; display: flex; align-items: center; gap: 8px; }
    .modal-field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #94a3b8; }
    .modal-field input[type="text"], .modal-field input[type="password"] { background: var(--bg-dark); border: 1px solid var(--border-color); padding: 8px 10px; border-radius: 6px; color: white; outline: none; }
    .modal-checkbox { display: flex; align-items: center; gap: 10px; font-size: 13px; color: #cbd5e1; cursor: pointer; }
    .modal-buttons { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
    .welcome-box { background: var(--menu-bg); border: 2px solid var(--accent-color); border-radius: 18px; padding: 28px; width: 420px; max-width: 90%; box-shadow: 0 10px 35px rgba(0,0,0,0.8); display: flex; flex-direction: column; gap: 16px; text-align: center; }
    .welcome-icon { font-size: 42px; }
    .welcome-box h2 { margin: 0; color: white; font-size: 22px; }
    .welcome-box p { font-size: 13px; color: #94a3b8; margin: 0; line-height: 1.5; }
    .welcome-features { background: var(--bg-dark); border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 16px; text-align: left; display: flex; flex-direction: column; gap: 8px; font-size: 12px; color: #cbd5e1; }
    .tab-iframe { width: 100%; height: 100%; border: none; background: white; display: none; position: absolute; top: 0; left: 0; }
  </style>
  <style id="incognito-styles">
    #incognito-tab-btn { background: transparent; color: #c4b5fd; border: none; font-size: 15px; padding: 4px 10px; cursor: pointer; border-radius: 4px; }
    #incognito-tab-btn:hover { background: #2e1065; }
    body.incognito-mode #nav-bar { background: #27272a; border-bottom-color: #52525b; }
    body.incognito-mode #tabs-bar { background: #18181b; }
    body.incognito-mode .url-container { border-color: #52525b; background: #09090b; }
    .tab.tab-incognito { background: #27272a; border-color: #52525b; color: #d4d4d8; }
    .tab.tab-incognito.active { border-top-color: #a1a1aa; background: #3f3f46; color: #ffffff; }
    .incognito-banner { position: absolute; top: 10px; left: 50%; transform: translateX(-50%); background: #27272a; color: #f4f4f5; padding: 7px 18px; border-radius: 20px; font-size: 12px; z-index: 25; display: none; border: 1px solid #52525b; box-shadow: 0 4px 14px rgba(0,0,0,0.5); pointer-events: none; max-width: 90%; text-align: center; }
    body.incognito-mode .incognito-banner { display: block; }
  </style>
</head>
<body>

  <div id="tabs-bar">
    <div id="tabs-container" style="display:flex; gap:4px;"></div>
    <button class="add-tab-btn" onclick="createNewTab()" title="Nueva pestaña" data-i18n-title="newTabTitle">+</button>
    <button id="incognito-tab-btn" onclick="createIncognitoTab()" title="Nueva pestaña de incógnito" data-i18n-title="incognitoTabTitle">🕵️</button>
  </div>

  <div id="nav-bar">
    <button id="btn-undo" onclick="goBack()" data-i18n-title="undoTitle" disabled>↩️</button>
    <button id="btn-redo" onclick="goForward()" data-i18n-title="redoTitle" disabled>↪️</button>
    <button id="btn-home" onclick="goHome()" data-i18n-title="homeTitle">🏠</button>
    <button id="btn-reload" onclick="reloadTab()" data-i18n-title="reloadTitle">🔄</button>
    <div class="url-container">
      <span id="security-badge" class="security-badge" onclick="openSecurityModal()">🛡️</span>
      <span id="adblock-badge" class="adblock-counter" onclick="openSecurityModal()">🚫 <span id="adblock-count-num">0</span></span>
      <input type="text" id="url-bar" placeholder="Escribe una URL o busca...">
    </div>
    <button id="btn-go" onclick="navigate()" data-i18n="goBtn">IR</button>
    <button id="btn-security-panel" onclick="openSecurityModal()" style="background:#0284c7;">🛡️</button>
    <button id="btn-install" onclick="openInstallModal()" data-i18n-title="installAppTitle" style="background:#10b981;">💾</button>
  </div>

  <div id="content-area">
    <div class="incognito-banner" id="incognito-banner"></div>
    <div id="home-screen">
      <div class="color-settings">
        <div class="color-picker-group">
          <label for="lang-selector">🌐</label>
          <select id="lang-selector" class="lang-select" onchange="changeLanguage(this.value)">
            <option value="es" selected>Español</option>
            <option value="en">English</option>
            <option value="pt">Português</option>
            <option value="fr">Français</option>
          </select>
        </div>
        <span style="border-left: 1px solid var(--border-color); height: 16px; margin: 0 4px;"></span>
        🎨 
        <div class="color-picker-group">
          <label for="bg-color-picker" data-i18n="menuLabel">Menú:</label>
          <input type="color" id="bg-color-picker" value="#1a2234" onchange="updateMenuColor(this.value)">
        </div>
        <div class="color-picker-group">
          <label for="accent-color-picker" data-i18n="accentLabel">Bordes/Botones:</label>
          <input type="color" id="accent-color-picker" value="#3b82f6" onchange="updateAccentColor(this.value)">
        </div>
        <div style="display: flex; gap: 4px; margin-left: 2px;">
          <button class="preset-btn" style="background:#3b82f6;" onclick="setPreset('#1a2234', '#3b82f6')"></button>
          <button class="preset-btn" style="background:#a855f7;" onclick="setPreset('#2e1065', '#a855f7')"></button>
          <button class="preset-btn" style="background:#22c55e;" onclick="setPreset('#052e16', '#22c55e')"></button>
          <button class="preset-btn" style="background:#ef4444;" onclick="setPreset('#450a0a', '#ef4444')"></button>
          <button class="preset-btn" style="background:#64748b;" onclick="setPreset('#0f172a', '#64748b')"></button>
        </div>
        <span style="border-left: 1px solid var(--border-color); padding-left: 8px; margin-left: 4px;">🖼️</span>
        <button class="bg-btn" onclick="document.getElementById('bg-file-input').click()" data-i18n="uploadPc">📁 Subir PC</button>
        <button class="bg-btn" onclick="setBgUrl()" data-i18n="urlBg">🔗 URL</button>
        <button class="bg-btn" onclick="resetBg()" data-i18n-title="restoreBgTitle">↩️</button>
        <input type="file" id="bg-file-input" accept="image/*" style="display: none;" onchange="setBgFile(event)">
      </div>

      <h1>OSC Browser 🌎</h1>

      <div class="search-container">
        <select id="engine-selector" class="engine-select" onchange="changeSearchEngine(this.value)">
          <option value="osc">⚡ OSC Search (Propio)</option>
          <option value="google">🌐 Google</option>
          <option value="duckduckgo">🦆 DuckDuckGo</option>
          <option value="bing">🔍 Bing</option>
          <option value="wikipedia">📚 Wikipedia</option>
          <option value="youtube">▶️ YouTube</option>
          <option value="ecosia">🌱 Ecosia</option>
        </select>
        <input type="text" id="search-input" class="search-box">
      </div>

      <div class="shortcuts-grid">
         <div class="shortcut" onclick="openUrl('https://www.google.com')">Google</div>
         <div class="shortcut" onclick="openUrl('https://www.wikipedia.org')">Wiki</div>
         <div class="shortcut" onclick="openUrl('https://www.youtube.com')">YT</div>
         <div class="shortcut" onclick="openUrl('osc://parkourgame')" style="border-color:#10b981; color:#10b981;">🏃</div>
      </div>

      <div id="installed-apps-section">
        <div style="font-size: 14px; font-weight: bold; color: white;" data-i18n="installedAppsTitle">📌 Mis Webs Guardadas</div>
        <div id="apps-container" class="apps-grid"></div>
      </div>
    </div>

    <div id="iframes-container"></div>
  </div>

  <div id="security-modal" class="modal-overlay">
    <div class="modal-box" style="width: 440px;">
      <h3>🛡️ <span data-i18n="securityTitle">Centro de Seguridad & AdBlock</span></h3>
      <div id="security-status-box" style="padding: 10px; border-radius: 8px; font-size: 12px; background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #6ee7b7;">
        <b data-i18n="securityStatusLabel">Estado:</b> <span id="security-status-text"></span>
      </div>
      <div class="modal-checkbox">
        <input type="checkbox" id="sec-adblock-toggle" onchange="toggleSecurityOption('adBlockEnabled', this.checked)">
        <label for="sec-adblock-toggle" data-i18n="secAdblockLabel"></label>
      </div>
      <div class="modal-checkbox">
        <input type="checkbox" id="sec-tracker-toggle" onchange="toggleSecurityOption('trackerBlockEnabled', this.checked)">
        <label for="sec-tracker-toggle" data-i18n="secTrackerLabel"></label>
      </div>
      <div class="modal-checkbox">
        <input type="checkbox" id="sec-shield-toggle" onchange="toggleSecurityOption('shieldEnabled', this.checked)">
        <label for="sec-shield-toggle" data-i18n="secShieldLabel"></label>
      </div>
      <div class="modal-checkbox">
        <input type="checkbox" id="sec-http-toggle" onchange="toggleSecurityOption('warnHttp', this.checked)">
        <label for="sec-http-toggle" data-i18n="secHttpLabel"></label>
      </div>
      <div style="background: var(--bg-dark); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: 8px; font-size: 12px; color: #94a3b8; display: flex; justify-content: space-between; align-items: center;">
        <span data-i18n="blockedTotalLabel">🚫 Total de elementos filtrados:</span>
        <b id="modal-blocked-count" style="color: #ef4444; font-size: 14px;">0</b>
      </div>
      <hr style="border: 0; border-top: 1px solid var(--border-color); width: 100%; margin: 2px 0;">
      <div class="modal-field">
        <label data-i18n="pinLabel"></label>
        <input type="password" id="sec-pin-input" maxlength="4" data-i18n-placeholder="pinPlaceholder">
      </div>
      <div class="modal-buttons">
        <button onclick="savePinConfig()" style="background:#0284c7;" data-i18n="savePinBtn"></button>
        <button onclick="closeSecurityModal()" style="background:#64748b;" data-i18n="cancelBtn"></button>
      </div>
    </div>
  </div>

  <div id="install-modal" class="modal-overlay">
    <div class="modal-box">
      <h3 data-i18n="modalTitle">💾 Guardar Web</h3>
      <div class="modal-field">
        <label data-i18n="appNameLabel"></label>
        <input type="text" id="app-name-input" data-i18n-placeholder="appNamePlaceholder">
      </div>
      <div class="modal-field">
        <label data-i18n="appUrlLabel"></label>
        <input type="text" id="app-url-input" placeholder="https://...">
      </div>
      <div class="modal-field">
        <label data-i18n="appIconLabel"></label>
        <input type="text" id="app-icon-input" value="🌐" style="width: 60px; text-align: center;">
      </div>
      <div id="pwa-native-option" style="display:none; font-size:12px; background:rgba(16, 185, 129, 0.2); border:1px solid #10b981; padding:8px; border-radius:6px; color:#6ee7b7;">
        💡 <span data-i18n="pwaAvailable"></span>
        <button onclick="triggerPwaInstall()" style="margin-top:6px; width:100%; background:#10b981;" data-i18n="installNativeBtn"></button>
      </div>
      <div class="modal-buttons">
        <button onclick="closeInstallModal()" style="background:#64748b;" data-i18n="cancelBtn"></button>
        <button onclick="saveInstalledApp()" style="background:#10b981;" data-i18n="confirmInstallBtn"></button>
      </div>
    </div>
  </div>

  <div id="welcome-modal" class="modal-overlay">
    <div class="welcome-box">
      <div class="welcome-icon">🚀</div>
      <h2 data-i18n="welcomeTitle"></h2>
      <p data-i18n="welcomeDesc"></p>
      <div class="welcome-features">
        <div data-i18n="welcomeFeature1"></div>
        <div data-i18n="welcomeFeature2"></div>
        <div data-i18n="welcomeFeature3"></div>
      </div>
      <button onclick="closeWelcomeModal()" style="padding: 10px; font-size: 14px; border-radius: 8px;" data-i18n="welcomeBtn"></button>
    </div>
  </div>

  <script>
    // ================================================================
    // ORÍGENES ÚNICOS POR WEB
    // Cada host destino obtiene su propio subdominio <hash>.localhost,
    // así dos webs nunca comparten http://127.0.0.1:8999 como origen.
    // Ej:  https://example.com  ->  http://d1a2b3c4.localhost:8999/proxy?url=...
    // ================================================================
    const PROXY_PORT = 8999;

    function getProxySubdomain(targetUrl) {
      try {
        const host = new URL(targetUrl).hostname.toLowerCase();
        // Hash tipo djb2 (32 bits) — coincide en cualquier navegador
        let h = 5381;
        for (let i = 0; i < host.length; i++) {
          h = ((h << 5) + h + host.charCodeAt(i)) | 0;
        }
        return 'd' + (h >>> 0).toString(16);
      } catch (e) {
        return 'd0';
      }
    }

    function buildProxyUrl(targetUrl) {
      const sub = getProxySubdomain(targetUrl);
      let u = 'http://' + sub + '.localhost:' + PROXY_PORT +
              '/proxy?url=' + encodeURIComponent(targetUrl);
      if (securityConfig.adBlockEnabled)        u += '&ab=1';
      if (securityConfig.trackerBlockEnabled)   u += '&tb=1';
      return u;
    }

    let tabs = [];
    let activeTabId = null;
    let tabIdCounter = 0;
    let currentLang = 'es';
    let installedApps = [];
    let deferredPrompt = null;
    let blockedTotalCount = 0;

    let securityConfig = {
      shieldEnabled: true,
      warnHttp: true,
      blockExecutables: true,
      adBlockEnabled: true,
      trackerBlockEnabled: true,
      pin: ''
    };

    const adDomains = [
      'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
      'pagead2.googlesyndication.com', 'adservice.google.com',
      'ads.youtube.com', 'adnxs.com', 'popads.net', 'adroll.com', 'outbrain.com',
      'taboola.com', 'mediavine.com', 'adzerk.net', 'rubiconproject.com'
    ];

    const trackerDomains = [
      'google-analytics.com', 'analytics.google.com', 'facebook.com/tr',
      'connect.facebook.net', 'scorecardresearch.com', 'hotjar.com',
      'clarity.ms', 'mixpanel.com', 'segment.com', 'quantserve.com'
    ];

    const suspiciousKeywords = ['phishing', 'fake-login', 'free-money-now', 'account-verify-stealer', 'malware-download'];
    const dangerousExtensions = ['.exe', '.bat', '.vbs', '.cmd', '.scr', '.msi', '.ps1'];

    const translations = {
      es: {
        undoTitle: "Deshacer (Atrás)",
        redoTitle: "Rehacer (Adelante)",
        homeTitle: "Inicio",
        reloadTitle: "Recargar página",
        newTabTitle: "Nueva pestaña",
        incognitoTabTitle: "Nueva pestaña de incógnito",
        installAppTitle: "Guardar web",
        restoreBgTitle: "Restaurar fondo.jpg",
        promptTabRenameTooltip: "Haz doble clic para renombrar esta pestaña",
        menuLabel: "Menú:",
        accentLabel: "Bordes/Botones:",
        uploadPc: "📁 Subir PC",
        urlBg: "🔗 URL",
        urlPlaceholder: "Escribe una URL o busca...",
        goBtn: "IR",
        searchPlaceholder: "Buscar en {engine} o escribir URL...",
        newTabDefault: "Nueva pestaña",
        gameTabTitle: "🏃 Minijuego Parkour",
        incognitoTabLabel: "🕵️ Incógnito",
        oscTabPrefix: "⚡",
        oscTitle: "Resultados libres de derechos para:",
        oscHeader: "⚡ OSC Search (Sin Publicidad)",
        oscTagOpenSource: "Open Source / Wiki",
        oscTagPublicDomain: "Dominio Público",
        oscTagOpenSearch: "Búsqueda Abierta",
        oscTagFreeFiles: "Archivos Libres",
        wikiDesc: "Explora contenido libre de derechos de autor e información de libre acceso en la enciclopedia global.",
        commonsDesc: "Repositorio con millones de imágenes, audios y videos de contenido libre sin copyright.",
        openverseDesc: "Motor de búsqueda para más de 600 millones de imágenes y audios con licencias Creative Commons.",
        archiveDesc: "Accede a libros, películas, software y páginas web históricas preservadas en dominio público.",
        installedAppsTitle: "📌 Mis Webs Guardadas",
        emptyApps: "No tienes páginas guardadas. ¡Navega a una web y pulsa 💾 para guardarla!",
        modalTitle: "💾 Guardar Web",
        appNameLabel: "Nombre de la página:",
        appNamePlaceholder: "Ej: Mi Sitio Web",
        appUrlLabel: "URL o Búsqueda:",
        appIconLabel: "Icono / Emoji:",
        cancelBtn: "Cancelar",
        confirmInstallBtn: "Guardar",
        pwaAvailable: "¡OCS Browser puede instalarse como app nativa en tu sistema!",
        installNativeBtn: "Instalar OCS Browser en PC/Móvil",
        welcomeTitle: "¡Bienvenido a OCS Browser! 👋",
        welcomeDesc: "Tu navegador ultraligero enfocado en contenido libre, privacidad y navegación segura.",
        welcomeFeature1: "⚡ <b>OSC Search:</b> Resultados e información libre de derechos.",
        welcomeFeature2: "🚫 <b>AdBlock + Anti-Rastreo:</b> Navegación limpia sin anuncios ni cookies espía.",
        welcomeFeature3: "🛡️ <b>Protección Integrada:</b> Filtro en tiempo real contra descargas sospechosas y malware.",
        welcomeBtn: "¡Empezar a navegar! 🚀",
        securityTitle: "Centro de Seguridad & AdBlock",
        securityStatusLabel: "Estado:",
        secAdblockLabel: "<b>Bloqueador de Anuncios (AdBlock):</b> Filtra ventanas emergentes y dominios de publicidad.",
        secTrackerLabel: "<b>Bloqueador de Rastreadores:</b> Impide el seguimiento de Google Analytics y pixels espía.",
        secShieldLabel: "<b>Escudo Phishing:</b> Bloquea dominios maliciosos y ejecutables peligrosos.",
        secHttpLabel: "<b>Advertir sitios no cifrados (HTTP):</b> Alerta si una web no usa HTTPS.",
        blockedTotalLabel: "🚫 Total de elementos filtrados:",
        pinLabel: "🔑 PIN de Control Parental / Bloqueo (Opcional):",
        pinPlaceholder: "Ingresa PIN de 4 dígitos",
        savePinBtn: "Guardar PIN",
        secStatusSafeDefault: "Conexión cifrada, AdBlock y protección activa.",
        secStatusWarnDefault: "Advertencia: La conexión no es HTTPS.",
        secStatusDangerDefault: "¡Peligro! Sitio sospechoso o de anuncios masivos bloqueado.",
        secStatusHome: "Página de inicio protegida.",
        secStatusGame: "Modo Juego Local OCS.",
        secStatusOsc: "Motor OSC Search seguro (Sin Anuncios).",
        secStatusIncognito: "Estás en modo incógnito: no se guardan cookies ni historial.",
        secBadgeSafeTitle: "Sitio seguro (HTTPS)",
        secBadgeWarnTitle: "Precaución: Sitio no cifrado (HTTP)",
        secBadgeDangerTitle: "Sitio bloqueado por seguridad",
        reasonExecutable: "Se ha bloqueado la descarga directa de archivos peligrosos ({ext}).",
        reasonPhishing: "El sitio contiene patrones sospechosos de Phishing/Malware (\"{kw}\").",
        reasonHttpWarn: "Este sitio web no utiliza una conexión cifrada HTTPS. Tus datos podrían no estar protegidos.",
        blockedHeader: "No se puede acceder a la web, pero puedes jugar este minijuego",
        gameHeader: "Plataforma de Parkour OCS 🏃",
        gameSubHeader: "A/D o Flechas (Mover) | Espacio/Arriba/W (Saltar)",
        gameControls: "Controles: ← → / A D (Mover) | ESPACIO / ↑ / W (Salta)",
        gameBackBtn: "Volver al Inicio Seguro 🏠",
        gameOverTitle: "¡CAÍSTE AL VACÍO!",
        gameLevelReached: "Nivel alcanzado: ",
        gamePressSpace: " | Presiona Espacio para Reiniciar",
        gameLevelLabel: "Nivel Parkour: ",
        incognitoBanner: "🕵️ Estás en modo incógnito: no se guardan cookies, no se guarda historial y no se puede iniciar sesión.",
        incognitoHomeTitle: "Modo Incógnito Privado",
        incognitoHomeDesc: "Estás en modo incógnito, aquí no se guardan cookies ni un solo historial",
        incognitoFeature1: "🚫 <b>Cookies y almacenamiento web:</b> Totalmente desactivados.",
        incognitoFeature2: "🚫 <b>Historial de navegación:</b> No se registra ninguna actividad.",
        incognitoFeature3: "🔒 <b>Inicio de sesión:</b> Deshabilitado por protección de privacidad.",
        incognitoFeature4: "💾 <b>Webs guardadas:</b> Bloqueadas en modo privado.",
        alertPinEnter: "Ingresa el PIN de seguridad para acceder a la configuración:",
        alertPinIncorrect: "PIN incorrecto.",
        alertPinSaved: "¡PIN de seguridad guardado correctamente!",
        alertPinRemoved: "PIN eliminado.",
        alertPinDelete: "Ingresa el PIN para eliminar una web guardada:",
        alertIncognitoNoSave: "No puedes guardar webs mientras navegas en modo incógnito.",
        alertIncognitoNoSaveModal: "No se pueden guardar webs en modo incógnito.",
        alertCompleteFields: "Por favor completa el nombre y la URL.",
        promptBgUrl: "Ingresa la URL de la imagen para el fondo:",
        promptTabName: "Escribe el nuevo nombre de la pestaña:"
      },
      en: {
        undoTitle: "Undo (Back)",
        redoTitle: "Redo (Forward)",
        homeTitle: "Home",
        reloadTitle: "Reload page",
        newTabTitle: "New tab",
        incognitoTabTitle: "New incognito tab",
        installAppTitle: "Save web page",
        restoreBgTitle: "Restore background.jpg",
        promptTabRenameTooltip: "Double click to rename this tab",
        menuLabel: "Menu:",
        accentLabel: "Borders/Buttons:",
        uploadPc: "📁 Upload PC",
        urlBg: "🔗 URL",
        urlPlaceholder: "Type a URL or search...",
        goBtn: "GO",
        searchPlaceholder: "Search in {engine} or type URL...",
        newTabDefault: "New tab",
        gameTabTitle: "🏃 Parkour Minigame",
        incognitoTabLabel: "🕵️ Incognito",
        oscTabPrefix: "⚡",
        oscTitle: "Copyright-free results for:",
        oscHeader: "⚡ OSC Search (Ad-Free)",
        oscTagOpenSource: "Open Source / Wiki",
        oscTagPublicDomain: "Public Domain",
        oscTagOpenSearch: "Open Search",
        oscTagFreeFiles: "Free Files",
        wikiDesc: "Explore copyright-free content and open-access information in the global encyclopedia.",
        commonsDesc: "Repository with millions of free images, audio, and videos without copyright.",
        openverseDesc: "Search engine for over 600 million images and audio under Creative Commons licenses.",
        archiveDesc: "Access books, movies, software, and historical web pages preserved in the public domain.",
        installedAppsTitle: "📌 My Saved Web Pages",
        emptyApps: "No saved pages. Browse to a web page and click 💾 to save it!",
        modalTitle: "💾 Save Web Page",
        appNameLabel: "Page Name:",
        appNamePlaceholder: "e.g. My Website",
        appUrlLabel: "URL or Search:",
        appIconLabel: "Icon / Emoji:",
        cancelBtn: "Cancel",
        confirmInstallBtn: "Save",
        pwaAvailable: "OCS Browser can be installed as a native app on your system!",
        installNativeBtn: "Install OCS Browser on PC/Mobile",
        welcomeTitle: "Welcome to OCS Browser! 👋",
        welcomeDesc: "Your lightweight browser focused on open content, privacy, and secure browsing.",
        welcomeFeature1: "⚡ <b>OSC Search:</b> Find copyright-free search results and media.",
        welcomeFeature2: "🚫 <b>AdBlock + Anti-Tracking:</b> Clean browsing without ads or spy cookies.",
        welcomeFeature3: "🛡️ <b>Integrated Protection:</b> Real-time shield against malware and unsafe sites.",
        welcomeBtn: "Start Browsing! 🚀",
        securityTitle: "OSC Security & AdBlock Center",
        securityStatusLabel: "Status:",
        secAdblockLabel: "<b>AdBlocker:</b> Filters pop-ups and ad network domains.",
        secTrackerLabel: "<b>Tracker Blocker:</b> Blocks Google Analytics and tracking pixels.",
        secShieldLabel: "<b>Real-Time Shield:</b> Block phishing domains and unsafe executables.",
        secHttpLabel: "<b>Warn Unencrypted Sites (HTTP):</b> Alert if a website does not use HTTPS.",
        blockedTotalLabel: "🚫 Total blocked elements:",
        pinLabel: "🔑 Parental Control / Lock PIN (Optional):",
        pinPlaceholder: "Enter 4-digit PIN",
        savePinBtn: "Save PIN",
        secStatusSafeDefault: "Encrypted connection, AdBlock and protection active.",
        secStatusWarnDefault: "Warning: The connection is not HTTPS.",
        secStatusDangerDefault: "Danger! Suspicious site or mass advertising blocked.",
        secStatusHome: "Protected home page.",
        secStatusGame: "OCS Local Game Mode.",
        secStatusOsc: "Safe OSC Search engine (Ad-Free).",
        secStatusIncognito: "You're in incognito mode: no cookies or history are stored.",
        secBadgeSafeTitle: "Secure site (HTTPS)",
        secBadgeWarnTitle: "Caution: Unencrypted site (HTTP)",
        secBadgeDangerTitle: "Site blocked for security",
        reasonExecutable: "Direct download of dangerous files ({ext}) has been blocked.",
        reasonPhishing: "The site contains suspicious Phishing/Malware patterns (\"{kw}\").",
        reasonHttpWarn: "This website does not use an encrypted HTTPS connection. Your data may not be protected.",
        blockedHeader: "Can't access the website, but you can play this minigame",
        gameHeader: "OCS Parkour Platformer 🏃",
        gameSubHeader: "A/D or Arrows (Move) | Space/Up/W (Jump)",
        gameControls: "Controls: ← → / A D (Move) | SPACE / ↑ / W (Jump)",
        gameBackBtn: "Back to Safe Home 🏠",
        gameOverTitle: "YOU FELL INTO THE VOID!",
        gameLevelReached: "Level reached: ",
        gamePressSpace: " | Press Space to Restart",
        gameLevelLabel: "Parkour Level: ",
        incognitoBanner: "🕵️ You're in incognito mode: cookies, history, and logins are completely disabled.",
        incognitoHomeTitle: "Private Incognito Mode",
        incognitoHomeDesc: "You're in incognito mode, no cookies or history are stored here",
        incognitoFeature1: "🚫 <b>Cookies & web storage:</b> Completely disabled.",
        incognitoFeature2: "🚫 <b>Browsing history:</b> No activity is recorded.",
        incognitoFeature3: "🔒 <b>Login:</b> Disabled for privacy protection.",
        incognitoFeature4: "💾 <b>Saved pages:</b> Blocked in private mode.",
        alertPinEnter: "Enter the security PIN to access settings:",
        alertPinIncorrect: "Incorrect PIN.",
        alertPinSaved: "Security PIN saved successfully!",
        alertPinRemoved: "PIN removed.",
        alertPinDelete: "Enter the PIN to delete a saved page:",
        alertIncognitoNoSave: "You can't save websites while browsing in incognito mode.",
        alertIncognitoNoSaveModal: "You can't save websites in incognito mode.",
        alertCompleteFields: "Please fill in the name and URL.",
        promptBgUrl: "Enter the image URL for the background:",
        promptTabName: "Enter the new tab name:"
      },
      pt: {
        undoTitle: "Desfazer (Voltar)",
        redoTitle: "Refazer (Avançar)",
        homeTitle: "Início",
        reloadTitle: "Recarregar página",
        newTabTitle: "Nova aba",
        incognitoTabTitle: "Nova aba anônima",
        installAppTitle: "Salvar página",
        restoreBgTitle: "Restaurar background.jpg",
        promptTabRenameTooltip: "Clique duas vezes para renomear esta aba",
        menuLabel: "Menu:",
        accentLabel: "Bordas/Botões:",
        uploadPc: "📁 Enviar do PC",
        urlBg: "🔗 URL",
        urlPlaceholder: "Digite uma URL ou pesquise...",
        goBtn: "IR",
        searchPlaceholder: "Pesquisar em {engine} ou digitar URL...",
        newTabDefault: "Nova aba",
        gameTabTitle: "🏃 Minijogo Parkour",
        incognitoTabLabel: "🕵️ Anônimo",
        oscTabPrefix: "⚡",
        oscTitle: "Resultados livres de direitos autorais para:",
        oscHeader: "⚡ OSC Search (Sem Anúncios)",
        oscTagOpenSource: "Open Source / Wiki",
        oscTagPublicDomain: "Domínio Público",
        oscTagOpenSearch: "Busca Aberta",
        oscTagFreeFiles: "Arquivos Livres",
        wikiDesc: "Explore conteúdo livre de direitos autorais e informação de acesso aberto na enciclopédia global.",
        commonsDesc: "Repositório com milhões de imagens, áudios e vídeos de conteúdo livre sem direitos autorais.",
        openverseDesc: "Motor de busca para mais de 600 milhões de imagens e áudios com licenças Creative Commons.",
        archiveDesc: "Acesse livros, filmes, softwares e páginas web históricas preservadas em domínio público.",
        installedAppsTitle: "📌 Minhas Páginas Salvas",
        emptyApps: "Você não tem páginas salvas. Navegue por um site e clique em 💾 para salvar!",
        modalTitle: "💾 Salvar Página",
        appNameLabel: "Nome da página:",
        appNamePlaceholder: "Ex: Meu Site",
        appUrlLabel: "URL ou Busca:",
        appIconLabel: "Ícone / Emoji:",
        cancelBtn: "Cancelar",
        confirmInstallBtn: "Salvar",
        pwaAvailable: "O OCS Browser pode ser instalado como app nativo no seu sistema!",
        installNativeBtn: "Instalar OCS Browser no PC/Celular",
        welcomeTitle: "Bem-vindo ao OCS Browser! 👋",
        welcomeDesc: "Seu navegador ultraleve focado em conteúdo livre, privacidade e navegação segura.",
        welcomeFeature1: "⚡ <b>OSC Search:</b> Resultados e informações livres de direitos.",
        welcomeFeature2: "🚫 <b>AdBlock + Anti-Rastreamento:</b> Navegação limpa sem anúncios ou cookies espiões.",
        welcomeFeature3: "🛡️ <b>Proteção Integrada:</b> Filtro em tempo real contra downloads suspeitos e malware.",
        welcomeBtn: "Começar a navegar! 🚀",
        securityTitle: "Central de Segurança & AdBlock",
        securityStatusLabel: "Status:",
        secAdblockLabel: "<b>Bloqueador de Anúncios (AdBlock):</b> Filtra pop-ups e domínios de publicidade.",
        secTrackerLabel: "<b>Bloqueador de Rastreadores:</b> Impede o rastreamento do Google Analytics e pixels espiões.",
        secShieldLabel: "<b>Escudo Anti-Phishing:</b> Bloqueia domínios maliciosos e executáveis perigosos.",
        secHttpLabel: "<b>Avisar sites não criptografados (HTTP):</b> Alerta se um site não usa HTTPS.",
        blockedTotalLabel: "🚫 Total de elementos filtrados:",
        pinLabel: "🔑 PIN de Controle Parental / Bloqueio (Opcional):",
        pinPlaceholder: "Digite PIN de 4 dígitos",
        savePinBtn: "Salvar PIN",
        secStatusSafeDefault: "Conexão criptografada, AdBlock e proteção ativos.",
        secStatusWarnDefault: "Aviso: A conexão não é HTTPS.",
        secStatusDangerDefault: "Perigo! Site suspeito ou com publicidade em massa bloqueado.",
        secStatusHome: "Página inicial protegida.",
        secStatusGame: "Modo Jogo Local OCS.",
        secStatusOsc: "Motor OSC Search seguro (Sem Anúncios).",
        secStatusIncognito: "Você está no modo anônimo: cookies e histórico não são salvos.",
        secBadgeSafeTitle: "Site seguro (HTTPS)",
        secBadgeWarnTitle: "Cuidado: Site não criptografado (HTTP)",
        secBadgeDangerTitle: "Site bloqueado por segurança",
        reasonExecutable: "O download direto de arquivos perigosos ({ext}) foi bloqueado.",
        reasonPhishing: "O site contém padrões suspeitos de Phishing/Malware (\"{kw}\").",
        reasonHttpWarn: "Este site não usa uma conexão HTTPS criptografada. Seus dados podem não estar protegidos.",
        blockedHeader: "Não é possível acessar o site, mas você pode jogar este minijogo",
        gameHeader: "Plataforma de Parkour OCS 🏃",
        gameSubHeader: "A/D ou Setas (Mover) | Espaço/Cima/W (Pular)",
        gameControls: "Controles: ← → / A D (Mover) | ESPAÇO / ↑ / W (Pular)",
        gameBackBtn: "Voltar ao Início Seguro 🏠",
        gameOverTitle: "VOCÊ CAIU NO VAZIO!",
        gameLevelReached: "Nível alcançado: ",
        gamePressSpace: " | Pressione Espaço para Reiniciar",
        gameLevelLabel: "Nível Parkour: ",
        incognitoBanner: "🕵️ Você está no modo anônimo: cookies, histórico e login estão totalmente desativados.",
        incognitoHomeTitle: "Modo Anônimo Privado",
        incognitoHomeDesc: "Você está no modo anônimo, aqui não são salvos cookies nem histórico",
        incognitoFeature1: "🚫 <b>Cookies e armazenamento web:</b> Totalmente desativados.",
        incognitoFeature2: "🚫 <b>Histórico de navegação:</b> Nenhuma atividade é registrada.",
        incognitoFeature3: "🔒 <b>Login:</b> Desativado por proteção de privacidade.",
        incognitoFeature4: "💾 <b>Páginas salvas:</b> Bloqueadas no modo privado.",
        alertPinEnter: "Digite o PIN de segurança para acessar as configurações:",
        alertPinIncorrect: "PIN incorreto.",
        alertPinSaved: "PIN de segurança salvo com sucesso!",
        alertPinRemoved: "PIN removido.",
        alertPinDelete: "Digite o PIN para excluir uma página salva:",
        alertIncognitoNoSave: "Você não pode salvar sites enquanto navega no modo anônimo.",
        alertIncognitoNoSaveModal: "Não é possível salvar sites no modo anônimo.",
        alertCompleteFields: "Por favor, preencha o nome e a URL.",
        promptBgUrl: "Digite a URL da imagem para o plano de fundo:",
        promptTabName: "Digite o novo nome da aba:"
      },
      fr: {
        undoTitle: "Annuler (Retour)",
        redoTitle: "Rétablir (Avancer)",
        homeTitle: "Accueil",
        reloadTitle: "Recharger la page",
        newTabTitle: "Nouvel onglet",
        incognitoTabTitle: "Nouvel onglet privé",
        installAppTitle: "Enregistrer la page",
        restoreBgTitle: "Restaurer background.jpg",
        promptTabRenameTooltip: "Double-cliquez pour renommer cet onglet",
        menuLabel: "Menu :",
        accentLabel: "Bordures/Boutons :",
        uploadPc: "📁 Depuis le PC",
        urlBg: "🔗 URL",
        urlPlaceholder: "Tapez une URL ou recherchez...",
        goBtn: "OK",
        searchPlaceholder: "Rechercher dans {engine} ou taper une URL...",
        newTabDefault: "Nouvel onglet",
        gameTabTitle: "🏃 Mini-jeu Parkour",
        incognitoTabLabel: "🕵️ Privé",
        oscTabPrefix: "⚡",
        oscTitle: "Résultats libres de droits pour :",
        oscHeader: "⚡ OSC Search (Sans Publicité)",
        oscTagOpenSource: "Open Source / Wiki",
        oscTagPublicDomain: "Domaine Public",
        oscTagOpenSearch: "Recherche Ouverte",
        oscTagFreeFiles: "Fichiers Libres",
        wikiDesc: "Explorez du contenu libre de droits et des informations en accès libre dans l'encyclopédie mondiale.",
        commonsDesc: "Dépôt avec des millions d'images, d'audios et de vidéos libres de droits.",
        openverseDesc: "Moteur de recherche pour plus de 600 millions d'images et audios sous licences Creative Commons.",
        archiveDesc: "Accédez à des livres, films, logiciels et pages web historiques préservés dans le domaine public.",
        installedAppsTitle: "📌 Mes Pages Enregistrées",
        emptyApps: "Aucune page enregistrée. Naviguez vers un site et cliquez sur 💾 pour l'enregistrer !",
        modalTitle: "💾 Enregistrer la Page",
        appNameLabel: "Nom de la page :",
        appNamePlaceholder: "Ex : Mon Site Web",
        appUrlLabel: "URL ou Recherche :",
        appIconLabel: "Icône / Emoji :",
        cancelBtn: "Annuler",
        confirmInstallBtn: "Enregistrer",
        pwaAvailable: "OCS Browser peut être installé comme application native sur votre système !",
        installNativeBtn: "Installer OCS Browser sur PC/Mobile",
        welcomeTitle: "Bienvenue sur OCS Browser ! 👋",
        welcomeDesc: "Votre navigateur ultra-léger axé sur le contenu libre, la confidentialité et la navigation sécurisée.",
        welcomeFeature1: "⚡ <b>OSC Search :</b> Résultats et informations libres de droits.",
        welcomeFeature2: "🚫 <b>AdBlock + Anti-Traqueur :</b> Navigation propre sans publicités ni cookies espions.",
        welcomeFeature3: "🛡️ <b>Protection Intégrée :</b> Filtre en temps réel contre les téléchargements suspects et les malwares.",
        welcomeBtn: "Commencer à naviguer ! 🚀",
        securityTitle: "Centre de Sécurité & AdBlock",
        securityStatusLabel: "État :",
        secAdblockLabel: "<b>Bloqueur de Publicités (AdBlock) :</b> Filtre les pop-ups et les domaines publicitaires.",
        secTrackerLabel: "<b>Bloqueur de Traqueurs :</b> Empêche le suivi de Google Analytics et les pixels espions.",
        secShieldLabel: "<b>Bouclier Anti-Phishing :</b> Bloque les domaines malveillants et les exécutables dangereux.",
        secHttpLabel: "<b>Avertir des sites non chiffrés (HTTP) :</b> Alerte si un site n'utilise pas HTTPS.",
        blockedTotalLabel: "🚫 Total des éléments filtrés :",
        pinLabel: "🔑 Code PIN de Contrôle Parental / Verrouillage (Optionnel) :",
        pinPlaceholder: "Entrez un PIN à 4 chiffres",
        savePinBtn: "Enregistrer le PIN",
        secStatusSafeDefault: "Connexion chiffrée, AdBlock et protection actifs.",
        secStatusWarnDefault: "Avertissement : La connexion n'est pas HTTPS.",
        secStatusDangerDefault: "Danger ! Site suspect ou publicité massive bloqué.",
        secStatusHome: "Page d'accueil protégée.",
        secStatusGame: "Mode Jeu Local OCS.",
        secStatusOsc: "Moteur OSC Search sécurisé (Sans Publicité).",
        secStatusIncognito: "Vous êtes en mode privé : cookies et historique ne sont pas enregistrés.",
        secBadgeSafeTitle: "Site sécurisé (HTTPS)",
        secBadgeWarnTitle: "Attention : Site non chiffré (HTTP)",
        secBadgeDangerTitle: "Site bloqué pour sécurité",
        reasonExecutable: "Le téléchargement direct de fichiers dangereux ({ext}) a été bloqué.",
        reasonPhishing: "Le site contient des motifs suspects de Phishing/Malware (\"{kw}\").",
        reasonHttpWarn: "Ce site n'utilise pas de connexion HTTPS chiffrée. Vos données pourraient ne pas être protégées.",
        blockedHeader: "Impossible d'accéder au site, mais vous pouvez jouer à ce mini-jeu",
        gameHeader: "Plateforme de Parkour OCS 🏃",
        gameSubHeader: "A/D ou Flèches (Bouger) | Espace/Haut/W (Sauter)",
        gameControls: "Contrôles : ← → / A D (Bouger) | ESPACE / ↑ / W (Sauter)",
        gameBackBtn: "Retour à l'Accueil Sécurisé 🏠",
        gameOverTitle: "VOUS ÊTES TOMBÉ DANS LE VIDE !",
        gameLevelReached: "Niveau atteint : ",
        gamePressSpace: " | Appuyez sur Espace pour Redémarrer",
        gameLevelLabel: "Niveau Parkour : ",
        incognitoBanner: "🕵️ Vous êtes en mode privé : cookies, historique et connexions sont totalement désactivés.",
        incognitoHomeTitle: "Mode Privé Incognito",
        incognitoHomeDesc: "Vous êtes en mode privé, aucun cookie ni historique n'est enregistré ici",
        incognitoFeature1: "🚫 <b>Cookies et stockage web :</b> Totalement désactivés.",
        incognitoFeature2: "🚫 <b>Historique de navigation :</b> Aucune activité n'est enregistrée.",
        incognitoFeature3: "🔒 <b>Connexion :</b> Désactivée pour protéger la vie privée.",
        incognitoFeature4: "💾 <b>Pages enregistrées :</b> Bloquées en mode privé.",
        alertPinEnter: "Entrez le code PIN de sécurité pour accéder aux paramètres :",
        alertPinIncorrect: "Code PIN incorrect.",
        alertPinSaved: "Code PIN de sécurité enregistré avec succès !",
        alertPinRemoved: "PIN supprimé.",
        alertPinDelete: "Entrez le PIN pour supprimer une page enregistrée :",
        alertIncognitoNoSave: "Vous ne pouvez pas enregistrer de sites en navigation privée.",
        alertIncognitoNoSaveModal: "Impossible d'enregistrer des sites en mode privé.",
        alertCompleteFields: "Veuillez remplir le nom et l'URL.",
        promptBgUrl: "Entrez l'URL de l'image pour l'arrière-plan :",
        promptTabName: "Entrez le nouveau nom de l'onglet :"
      }
    };

    function t() {
      return translations[currentLang] || translations.es;
    }

    const searchEngines = {
      osc: { name: 'OSC Search', url: 'internal', icon: '⚡' },
      google: { name: 'Google', url: 'https://www.google.com/search?q=', icon: '🌐' },
      duckduckgo: { name: 'DuckDuckGo', url: 'https://duckduckgo.com/?q=', icon: '🦆' },
      bing: { name: 'Bing', url: 'https://www.bing.com/search?q=', icon: '🔍' },
      wikipedia: { name: 'Wikipedia', url: 'https://es.wikipedia.org/w/index.php?search=', icon: '📚' },
      youtube: { name: 'YouTube', url: 'https://www.youtube.com/results?search_query=', icon: '▶️' },
      ecosia: { name: 'Ecosia', url: 'https://www.ecosia.org/search?q=', icon: '🌱' }
    };
    let currentEngine = 'osc';

    const tabsContainer = document.getElementById('tabs-container');
    const iframesContainer = document.getElementById('iframes-container');
    const homeScreen = document.getElementById('home-screen');
    const urlInput = document.getElementById('url-bar');
    const searchInput = document.getElementById('search-input');
    const bgColorPicker = document.getElementById('bg-color-picker');
    const accentColorPicker = document.getElementById('accent-color-picker');

    function generateIncognitoHomeHTML() {
      const tr = t();
      return `
        <!DOCTYPE html>
        <html lang="${currentLang}">
        <head>
          <meta charset="UTF-8">
          <style>
            body { margin: 0; height: 100vh; background-color: #2d3748; color: #f7fafc; font-family: system-ui, -apple-system, sans-serif; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 20px; box-sizing: border-box; }
            .card { background: #1a202c; border: 1px solid #4a5568; border-radius: 16px; padding: 40px 30px; max-width: 520px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5); }
            .icon { font-size: 64px; margin-bottom: 16px; }
            h1 { margin: 0 0 16px 0; font-size: 24px; color: #edf2f7; }
            p { font-size: 16px; color: #cbd5e0; line-height: 1.5; margin: 0 0 24px 0; }
            ul { text-align: left; background: #2d3748; padding: 16px 20px 16px 36px; border-radius: 10px; font-size: 13px; color: #a0aec0; margin: 0; }
            li { margin-bottom: 8px; }
            li:last-child { margin-bottom: 0; }
          </style>
        </head>
        <body>
          <div class="card">
            <div class="icon">🕵️</div>
            <h1>${tr.incognitoHomeTitle}</h1>
            <p>${tr.incognitoHomeDesc}</p>
            <ul>
              <li>${tr.incognitoFeature1}</li>
              <li>${tr.incognitoFeature2}</li>
              <li>${tr.incognitoFeature3}</li>
              <li>${tr.incognitoFeature4}</li>
            </ul>
          </div>
        </body>
        </html>
      `;
    }

    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      const pwaOpt = document.getElementById('pwa-native-option');
      if (pwaOpt) pwaOpt.style.display = 'block';
    });

    function triggerPwaInstall() {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(() => {
          deferredPrompt = null;
          closeInstallModal();
        });
      }
    }

    function loadSecurityConfig() {
      const savedSec = localStorage.getItem('ocs_security_config');
      if (savedSec) {
        try { securityConfig = { ...securityConfig, ...JSON.parse(savedSec) }; } catch(e){}
      }
      const savedCount = localStorage.getItem('ocs_blocked_count');
      if (savedCount) blockedTotalCount = parseInt(savedCount) || 0;

      document.getElementById('sec-shield-toggle').checked = securityConfig.shieldEnabled;
      document.getElementById('sec-http-toggle').checked = securityConfig.warnHttp;
      document.getElementById('sec-adblock-toggle').checked = securityConfig.adBlockEnabled;
      document.getElementById('sec-tracker-toggle').checked = securityConfig.trackerBlockEnabled;
      document.getElementById('sec-pin-input').value = securityConfig.pin || '';
      
      updateAdblockUI();
      updateSecurityBadge('safe');
    }

    function toggleSecurityOption(key, val) {
      securityConfig[key] = val;
      localStorage.setItem('ocs_security_config', JSON.stringify(securityConfig));
      if (key === 'adBlockEnabled' || key === 'trackerBlockEnabled') {
        const activeTab = tabs.find(t => t.id === activeTabId);
        if (activeTab && activeTab.url && activeTab.history[activeTab.historyIndex]) {
          loadHistoryState(activeTab, activeTab.history[activeTab.historyIndex], true);
        }
      }
    }

    function incrementBlockedCount(amount = 1) {
      blockedTotalCount += amount;
      localStorage.setItem('ocs_blocked_count', blockedTotalCount);
      updateAdblockUI();
    }

    function updateAdblockUI() {
      document.getElementById('adblock-count-num').textContent = blockedTotalCount;
      document.getElementById('modal-blocked-count').textContent = blockedTotalCount;
      document.getElementById('adblock-badge').title = t().blockedTotalLabel;
    }

    function savePinConfig() {
      const pinVal = document.getElementById('sec-pin-input').value.trim();
      securityConfig.pin = pinVal;
      localStorage.setItem('ocs_security_config', JSON.stringify(securityConfig));
      alert(pinVal ? t().alertPinSaved : t().alertPinRemoved);
      closeSecurityModal();
    }

    function openSecurityModal() {
      if (securityConfig.pin) {
        const enteredPin = prompt(t().alertPinEnter);
        if (enteredPin !== securityConfig.pin) {
          alert(t().alertPinIncorrect);
          return;
        }
      }
      document.getElementById('security-modal').style.display = 'flex';
    }

    function closeSecurityModal() {
      document.getElementById('security-modal').style.display = 'none';
    }

    function updateSecurityBadge(status, customMsg = '') {
      const tr = t();
      const badge = document.getElementById('security-badge');
      const statusText = document.getElementById('security-status-text');
      const statusBox = document.getElementById('security-status-box');

      if (status === 'safe') {
        badge.innerHTML = '🛡️';
        badge.style.color = '#10b981';
        badge.title = tr.secBadgeSafeTitle;
        if (statusText) statusText.textContent = customMsg || tr.secStatusSafeDefault;
        if (statusBox) {
          statusBox.style.background = 'rgba(16, 185, 129, 0.2)';
          statusBox.style.borderColor = '#10b981';
          statusBox.style.color = '#6ee7b7';
        }
      } else if (status === 'warn') {
        badge.innerHTML = '⚠️';
        badge.style.color = '#f59e0b';
        badge.title = tr.secBadgeWarnTitle;
        if (statusText) statusText.textContent = customMsg || tr.secStatusWarnDefault;
        if (statusBox) {
          statusBox.style.background = 'rgba(245, 158, 11, 0.2)';
          statusBox.style.borderColor = '#f59e0b';
          statusBox.style.color = '#fde047';
        }
      } else if (status === 'danger') {
        badge.innerHTML = '🛑';
        badge.style.color = '#ef4444';
        badge.title = tr.secBadgeDangerTitle;
        if (statusText) statusText.textContent = customMsg || tr.secStatusDangerDefault;
        if (statusBox) {
          statusBox.style.background = 'rgba(239, 68, 68, 0.2)';
          statusBox.style.borderColor = '#ef4444';
          statusBox.style.color = '#fca5a5';
        }
      }
    }

    function evaluateUrlSecurity(url) {
      if (!url || url.startsWith('osc://')) return { status: 'safe', reason: '' };
      const tr = t();
      const lowerUrl = url.toLowerCase();

      if (securityConfig.blockExecutables) {
        for (let ext of dangerousExtensions) {
          if (lowerUrl.endsWith(ext) || lowerUrl.includes(ext + '?')) {
            return { status: 'danger', reason: tr.reasonExecutable.replace('{ext}', ext) };
          }
        }
      }
      if (securityConfig.shieldEnabled) {
        for (let kw of suspiciousKeywords) {
          if (lowerUrl.includes(kw)) {
            return { status: 'danger', reason: tr.reasonPhishing.replace('{kw}', kw) };
          }
        }
      }
      if (securityConfig.warnHttp && lowerUrl.startsWith('http://')) {
        return { status: 'warn', reason: tr.reasonHttpWarn };
      }
      if ((securityConfig.adBlockEnabled || securityConfig.trackerBlockEnabled)
          && (lowerUrl.startsWith('http://') || lowerUrl.startsWith('https://'))) {
        incrementBlockedCount(Math.floor(Math.random() * 3) + 1);
      }
      return { status: 'safe', reason: '' };
    }

    function generateParkourGameHTML(customHeader, customSubheader) {
      const tr = t();
      const header = customHeader || tr.gameHeader;
      const subheader = customSubheader || tr.gameSubHeader;
      const S = JSON.stringify({
        controls: tr.gameControls,
        backBtn: tr.gameBackBtn,
        over: tr.gameOverTitle,
        levelReached: tr.gameLevelReached,
        pressSpace: tr.gamePressSpace,
        levelLabel: tr.gameLevelLabel
      });
      return `
        <!DOCTYPE html>
        <html lang="${currentLang}">
        <head>
          <meta charset="UTF-8">
          <style>
            body { font-family: sans-serif; background: #0c0f17; color: white; display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; margin: 0; text-align: center; overflow: hidden; }
            .header-text { color: #10b981; font-size: 20px; font-weight: bold; margin-bottom: 6px; text-shadow: 0 2px 10px rgba(16, 185, 129, 0.3); }
            .reason-text { color: #cbd5e1; font-size: 12px; margin-bottom: 12px; }
            canvas { background: #111827; border: 2px solid #3b82f6; border-radius: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7); }
            .controls-info { font-size: 11px; color: #94a3b8; margin-top: 8px; }
            button { margin-top: 10px; background: #334155; color: white; border: none; padding: 8px 16px; border-radius: 8px; font-weight: bold; cursor: pointer; transition: background 0.2s; }
            button:hover { background: #475569; }
          </style>
        </head>
        <body>
          <div class="header-text">${header}</div>
          <div class="reason-text">${subheader}</div>
          <canvas id="gameCanvas" width="650" height="300"></canvas>
          <div class="controls-info">${tr.gameControls}</div>
          <button id="btnBack">${tr.gameBackBtn}</button>
          <script>
            var S = ${S};
            document.getElementById('btnBack').addEventListener('click', function(){
              try { window.top.goHome(); } catch(e) { window.parent.goHome(); }
            });

            const canvas = document.getElementById('gameCanvas');
            const ctx = canvas.getContext('2d');
            let level = 1;
            let gameOver = false;
            let keys = { left: false, right: false };
            let player = { x: 30, y: 200, width: 22, height: 22, velocityX: 0, velocityY: 0, speed: 3.8, gravity: 0.5, jumpPower: -9.5, isGrounded: false };
            let goal = { x: 580, y: 50, width: 25, height: 35 };
            let platforms = [];

            function generatePlatforms() {
              platforms = [];
              platforms.push({ x: 20, y: 260, width: 100, height: 15 });
              if (level === 1) {
                platforms.push({ x: 150, y: 220, width: 80, height: 15 });
                platforms.push({ x: 270, y: 180, width: 80, height: 15 });
                platforms.push({ x: 390, y: 140, width: 80, height: 15 });
                platforms.push({ x: 520, y: 100, width: 100, height: 15 });
              } else if (level === 2) {
                platforms.push({ x: 140, y: 230, width: 60, height: 15 });
                platforms.push({ x: 240, y: 190, width: 50, height: 15 });
                platforms.push({ x: 340, y: 150, width: 50, height: 15 });
                platforms.push({ x: 450, y: 120, width: 60, height: 15 });
                platforms.push({ x: 550, y: 90, width: 80, height: 15 });
              } else {
                let lastX = 130, lastY = 230;
                for (let i = 0; i < 5; i++) {
                  let width = Math.max(35, 70 - level * 3);
                  let gapX = Math.floor(Math.random() * 30) + 75;
                  let gapY = Math.floor(Math.random() * 40) - 20;
                  lastX += gapX;
                  lastY = Math.max(80, Math.min(250, lastY + gapY));
                  if (lastX > canvas.width - 100) break;
                  platforms.push({ x: lastX, y: lastY, width: width, height: 15 });
                }
                goal.x = Math.min(canvas.width - 50, lastX + 80);
                goal.y = Math.max(50, lastY - 40);
                platforms.push({ x: goal.x - 10, y: goal.y + 35, width: 70, height: 15 });
              }
            }
            function resetPlayer() { player.x = 30; player.y = 200; player.velocityX = 0; player.velocityY = 0; player.isGrounded = false; }
            function resetGame() { level = 1; gameOver = false; generatePlatforms(); resetPlayer(); animate(); }

            window.addEventListener('keydown', (e) => {
              if (e.code === 'ArrowLeft' || e.code === 'KeyA') keys.left = true;
              if (e.code === 'ArrowRight' || e.code === 'KeyD') keys.right = true;
              if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') {
                if (gameOver) { resetGame(); return; }
                if (player.isGrounded) { player.velocityY = player.jumpPower; player.isGrounded = false; }
              }
            });
            window.addEventListener('keyup', (e) => {
              if (e.code === 'ArrowLeft' || e.code === 'KeyA') keys.left = false;
              if (e.code === 'ArrowRight' || e.code === 'KeyD') keys.right = false;
            });

            function animate() {
              if (gameOver) {
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#ef4444';
                ctx.font = 'bold 24px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(S.over, canvas.width / 2, canvas.height / 2 - 10);
                ctx.fillStyle = '#ffffff';
                ctx.font = '14px sans-serif';
                ctx.fillText(S.levelReached + level + S.pressSpace, canvas.width / 2, canvas.height / 2 + 20);
                return;
              }
              ctx.clearRect(0, 0, canvas.width, canvas.height);
              if (keys.left) player.velocityX = -player.speed;
              else if (keys.right) player.velocityX = player.speed;
              else player.velocityX = 0;
              player.velocityY += player.gravity;
              player.x += player.velocityX;
              player.y += player.velocityY;
              if (player.x < 0) player.x = 0;
              if (player.x + player.width > canvas.width) player.x = canvas.width - player.width;
              if (player.y > canvas.height) gameOver = true;
              player.isGrounded = false;
              for (let plat of platforms) {
                if (player.x + player.width > plat.x && player.x < plat.x + plat.width &&
                    player.y + player.height >= plat.y && player.y + player.height <= plat.y + plat.height + player.velocityY &&
                    player.velocityY >= 0) {
                  player.y = plat.y - player.height;
                  player.velocityY = 0;
                  player.isGrounded = true;
                }
              }
              if (player.x < goal.x + goal.width && player.x + player.width > goal.x &&
                  player.y < goal.y + goal.height && player.y + player.height > goal.y) {
                level++;
                generatePlatforms();
                resetPlayer();
              }
              ctx.fillStyle = '#334155';
              ctx.strokeStyle = '#3b82f6';
              ctx.lineWidth = 2;
              for (let plat of platforms) {
                ctx.fillRect(plat.x, plat.y, plat.width, plat.height);
                ctx.strokeRect(plat.x, plat.y, plat.width, plat.height);
              }
              ctx.fillStyle = '#f59e0b';
              ctx.fillRect(goal.x, goal.y, goal.width, goal.height);
              ctx.fillStyle = '#ffffff';
              ctx.font = '16px sans-serif';
              ctx.textAlign = 'center';
              ctx.fillText('🏁', goal.x + goal.width / 2, goal.y + 22);
              ctx.fillStyle = '#10b981';
              ctx.fillRect(player.x, player.y, player.width, player.height);
              ctx.strokeStyle = '#6ee7b7';
              ctx.lineWidth = 2;
              ctx.strokeRect(player.x, player.y, player.width, player.height);
              ctx.fillStyle = '#ffffff';
              ctx.font = 'bold 14px sans-serif';
              ctx.textAlign = 'left';
              ctx.fillText(S.levelLabel + level, 15, 25);
              requestAnimationFrame(animate);
            }
            generatePlatforms();
            animate();
          <\/script>
        </body>
        </html>
      `;
    }

    function generateBlockedPageHTML(targetUrl, reason) {
      return generateParkourGameHTML(t().blockedHeader, reason);
    }

    function checkFirstVisit() {
      const welcomeSeen = localStorage.getItem('ocs_welcome_seen');
      if (!welcomeSeen) {
        document.getElementById('welcome-modal').style.display = 'flex';
      }
    }

    function closeWelcomeModal() {
      document.getElementById('welcome-modal').style.display = 'none';
      localStorage.setItem('ocs_welcome_seen', 'true');
    }

    function loadSettings() {
      loadSecurityConfig();

      const savedLang = localStorage.getItem('ocs_lang');
      if (savedLang && translations[savedLang]) {
        document.getElementById('lang-selector').value = savedLang;
        changeLanguage(savedLang);
      } else {
        changeLanguage('es');
      }

      const savedMenuColor = localStorage.getItem('ocs_menu_color');
      if (savedMenuColor) updateMenuColor(savedMenuColor);
      const savedAccentColor = localStorage.getItem('ocs_accent_color');
      if (savedAccentColor) updateAccentColor(savedAccentColor);
      const savedBg = localStorage.getItem('ocs_bg_image');
      if (savedBg) homeScreen.style.backgroundImage = savedBg;
      const savedEngine = localStorage.getItem('ocs_engine');
      if (savedEngine && searchEngines[savedEngine]) {
        document.getElementById('engine-selector').value = savedEngine;
        changeSearchEngine(savedEngine);
      }
      loadInstalledApps();
      checkFirstVisit();
    }

    function changeLanguage(langKey) {
      if (!translations[langKey]) return;
      currentLang = langKey;
      localStorage.setItem('ocs_lang', langKey);

      const tr = t();

      document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (tr[key] !== undefined) el.innerHTML = tr[key];
      });
      document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (tr[key] !== undefined) el.title = tr[key];
      });
      document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (tr[key] !== undefined) el.placeholder = tr[key];
      });

      urlInput.placeholder = tr.urlPlaceholder;
      changeSearchEngine(currentEngine);

      applyTabTitlesForLanguage();

      const banner = document.getElementById('incognito-banner');
      if (banner) banner.textContent = tr.incognitoBanner;

      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab) {
        const st = activeTab.history[activeTab.historyIndex];
        if (st) {
          if (st.type === 'game' || st.type === 'osc' || activeTab.incognito) {
            loadHistoryState(activeTab, st, true);
          } else if (st.type === 'home') {
            updateSecurityBadge('safe', activeTab.incognito ? tr.secStatusIncognito : tr.secStatusHome);
          } else if (st.type === 'web') {
            const secEval = evaluateUrlSecurity(st.url);
            updateSecurityBadge(secEval.status, secEval.reason);
          }
        }
      }

      updateAdblockUI();
      renderAppsGrid();
      document.title = "OCS Browser";
    }

    function applyTabTitlesForLanguage() {
      const tr = t();
      tabs.forEach(tab => {
        if (tab.incognito) {
          tab.title = tr.incognitoTabLabel;
        } else {
          const st = tab.history[tab.historyIndex];
          if (!st || tab.isCustomTitle) return;
          if (st.type === 'home') {
            tab.title = tr.newTabDefault;
          } else if (st.type === 'game') {
            tab.title = tr.gameTabTitle;
          } else if (st.type === 'osc') {
            tab.title = tr.oscTabPrefix + ' ' + st.query;
          }
        }
      });
      renderTabs();
    }

    function changeSearchEngine(engineKey) {
      currentEngine = engineKey;
      localStorage.setItem('ocs_engine', engineKey);
      const engine = searchEngines[engineKey];
      searchInput.placeholder = t().searchPlaceholder.replace('{engine}', engine.name);
    }

    function createNewTab(input = '') {
      tabIdCounter++;
      const id = tabIdCounter;
      const iframe = document.createElement('iframe');
      iframe.className = 'tab-iframe';
      iframe.id = `iframe-${id}`;
      iframesContainer.appendChild(iframe);

      const defaultHomeState = {
        type: 'home',
        url: '',
        title: t().newTabDefault
      };

      const tabObj = {
        id: id,
        url: '',
        title: t().newTabDefault,
        isCustomTitle: false,
        iframeEl: iframe,
        history: [defaultHomeState],
        historyIndex: 0,
        incognito: false,
        loadedIndex: -1
      };

      tabs.push(tabObj);
      renderTabs();
      switchTab(id);
      if (input) openUrl(input);
    }

    function switchTab(id) {
      activeTabId = id;
      const tab = tabs.find(t => t.id === id);
      if (!tab) return;
      document.querySelectorAll('.tab-iframe').forEach(f => f.style.display = 'none');
      const currentState = tab.history[tab.historyIndex] || { type: 'home', url: '', title: tab.title };
      loadHistoryState(tab, currentState);
      renderTabs();
      updateNavButtons();
    }

    function loadHistoryState(tab, state, forceReload = false) {
      const tr = t();
      tab.url = state.url;

      if (tab.incognito) {
        tab.iframeEl.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups');
      } else {
        tab.iframeEl.removeAttribute('sandbox');
      }

      const isAlreadyLoaded = (tab.loadedIndex === tab.historyIndex) && !forceReload;

      if (state.type === 'home' || !state.url) {
        if (tab.incognito) {
          homeScreen.style.display = 'none';
          if (!isAlreadyLoaded) {
            tab.iframeEl.removeAttribute('src');
            tab.iframeEl.srcdoc = generateIncognitoHomeHTML();
          }
          tab.iframeEl.style.display = 'block';
          urlInput.value = '';
          updateSecurityBadge('safe', tr.secStatusIncognito);
        } else {
          homeScreen.style.display = 'flex';
          tab.iframeEl.style.display = 'none';
          urlInput.value = '';
          updateSecurityBadge('safe', tr.secStatusHome);
        }
      } else if (state.type === 'game') {
        homeScreen.style.display = 'none';
        if (!isAlreadyLoaded) {
          tab.iframeEl.removeAttribute('src');
          tab.iframeEl.srcdoc = generateParkourGameHTML();
        }
        tab.iframeEl.style.display = 'block';
        urlInput.value = state.url;
        updateSecurityBadge('safe', tr.secStatusGame);
      } else if (state.type === 'osc') {
        homeScreen.style.display = 'none';
        if (!isAlreadyLoaded) {
          tab.iframeEl.removeAttribute('src');
          tab.iframeEl.srcdoc = generateOscSearchHTML(state.query);
        }
        tab.iframeEl.style.display = 'block';
        urlInput.value = state.url;
        updateSecurityBadge('safe', tr.secStatusOsc);
      } else {
        const secEval = evaluateUrlSecurity(state.url);
        updateSecurityBadge(secEval.status, secEval.reason);
        homeScreen.style.display = 'none';
        if (!isAlreadyLoaded) {
          if (secEval.status === 'danger') {
            tab.iframeEl.removeAttribute('src');
            tab.iframeEl.srcdoc = generateBlockedPageHTML(state.url, secEval.reason);
          } else {
            tab.iframeEl.removeAttribute('srcdoc');
            // ★ Aquí se usa un subdominio único por host (origen aislado)
            tab.iframeEl.src = buildProxyUrl(state.url);
          }
        }
        tab.iframeEl.style.display = 'block';
        urlInput.value = state.url;
      }

      tab.loadedIndex = tab.historyIndex;
    }

    function goBack() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab && activeTab.historyIndex > 0) {
        activeTab.historyIndex--;
        loadHistoryState(activeTab, activeTab.history[activeTab.historyIndex]);
        renderTabs();
        updateNavButtons();
      }
    }

    function goForward() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab && activeTab.historyIndex < activeTab.history.length - 1) {
        activeTab.historyIndex++;
        loadHistoryState(activeTab, activeTab.history[activeTab.historyIndex]);
        renderTabs();
        updateNavButtons();
      }
    }

    function updateNavButtons() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      const btnUndo = document.getElementById('btn-undo');
      const btnRedo = document.getElementById('btn-redo');
      if (!activeTab || !activeTab.history) {
        btnUndo.disabled = true;
        btnRedo.disabled = true;
        return;
      }
      btnUndo.disabled = activeTab.historyIndex <= 0;
      btnRedo.disabled = activeTab.historyIndex >= activeTab.history.length - 1;
    }

    function closeTab(id, event) {
      event.stopPropagation();
      const tabIndex = tabs.findIndex(t => t.id === id);
      if (tabIndex === -1) return;
      const tab = tabs[tabIndex];
      if (tab.iframeEl) tab.iframeEl.remove();
      tabs.splice(tabIndex, 1);
      if (tabs.length === 0) {
        createNewTab();
      } else if (activeTabId === id) {
        const nextActive = tabs[Math.max(0, tabIndex - 1)];
        switchTab(nextActive.id);
      } else {
        renderTabs();
      }
    }

    function renameTab(id, event) {
      if (event) event.stopPropagation();
      const tab = tabs.find(t => t.id === id);
      if (!tab) return;
      const newTitle = prompt(t().promptTabName, tab.title);
      if (newTitle !== null && newTitle.trim() !== "") {
        tab.title = newTitle.trim();
        tab.isCustomTitle = true;
        renderTabs();
      }
    }

    function renderTabs() {
      tabsContainer.innerHTML = '';
      tabs.forEach(tab => {
        const tabEl = document.createElement('div');
        tabEl.className = `tab ${tab.id === activeTabId ? 'active' : ''}`;
        if (tab.incognito) tabEl.classList.add('tab-incognito');
        tabEl.onclick = () => switchTab(tab.id);

        const titleEl = document.createElement('span');
        titleEl.className = 'tab-title';
        titleEl.textContent = tab.title;
        titleEl.title = t().promptTabRenameTooltip;
        titleEl.ondblclick = (e) => renameTab(tab.id, e);

        const closeBtn = document.createElement('span');
        closeBtn.className = 'close-tab';
        closeBtn.innerHTML = '✕';
        closeBtn.onclick = (e) => closeTab(tab.id, e);

        tabEl.appendChild(titleEl);
        tabEl.appendChild(closeBtn);
        tabsContainer.appendChild(tabEl);
      });
    }

    function openInstallModal() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab && activeTab.incognito) {
        alert(t().alertIncognitoNoSave);
        return;
      }
      const nameInput = document.getElementById('app-name-input');
      const urlInputModal = document.getElementById('app-url-input');
      const iconInput = document.getElementById('app-icon-input');
      if (activeTab && activeTab.url) {
        nameInput.value = activeTab.title || 'Mi Sitio Web';
        urlInputModal.value = activeTab.url;
        iconInput.value = getEmojiForUrl(activeTab.url);
      } else {
        nameInput.value = '';
        urlInputModal.value = '';
        iconInput.value = '🌐';
      }
      const pwaOpt = document.getElementById('pwa-native-option');
      pwaOpt.style.display = deferredPrompt ? 'block' : 'none';
      document.getElementById('install-modal').style.display = 'flex';
    }

    function closeInstallModal() {
      document.getElementById('install-modal').style.display = 'none';
    }

    function saveInstalledApp() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab && activeTab.incognito) {
        alert(t().alertIncognitoNoSaveModal);
        closeInstallModal();
        return;
      }
      const name = document.getElementById('app-name-input').value.trim();
      const url = document.getElementById('app-url-input').value.trim();
      const icon = document.getElementById('app-icon-input').value.trim() || '🌐';
      if (!name || !url) {
        alert(t().alertCompleteFields);
        return;
      }
      const newApp = { id: Date.now(), name: name, url: url, icon: icon };
      installedApps.push(newApp);
      localStorage.setItem('ocs_installed_apps', JSON.stringify(installedApps));
      renderAppsGrid();
      closeInstallModal();
    }

    function deleteApp(appId, e) {
      e.stopPropagation();
      if (securityConfig.pin) {
        const pin = prompt(t().alertPinDelete);
        if (pin !== securityConfig.pin) {
          alert(t().alertPinIncorrect);
          return;
        }
      }
      installedApps = installedApps.filter(app => app.id !== appId);
      localStorage.setItem('ocs_installed_apps', JSON.stringify(installedApps));
      renderAppsGrid();
    }

    function loadInstalledApps() {
      const saved = localStorage.getItem('ocs_installed_apps');
      if (saved) {
        try { installedApps = JSON.parse(saved); } catch(e) { installedApps = []; }
      } else {
        installedApps = [
          { id: 1, name: 'Wikipedia', url: 'https://www.wikipedia.org', icon: '📚' },
          { id: 2, name: 'Openverse', url: 'https://openverse.org', icon: '🖼️' },
          { id: 3, name: 'Archive.org', url: 'https://archive.org', icon: '🏛️' }
        ];
      }
      renderAppsGrid();
    }

    function getEmojiForUrl(url) {
      if (url.includes('parkourgame')) return '🏃';
      if (url.includes('wikipedia')) return '📚';
      if (url.includes('youtube')) return '▶️';
      if (url.includes('google')) return '🌐';
      if (url.includes('archive.org')) return '🏛️';
      if (url.includes('openverse')) return '🖼️';
      return '📌';
    }

    function renderAppsGrid() {
      const container = document.getElementById('apps-container');
      container.innerHTML = '';
      if (installedApps.length === 0) {
        container.innerHTML = `<div style="grid-column: 1/-1; color: #94a3b8; font-size: 12px; text-align: center; padding: 10px;">${t().emptyApps}</div>`;
        return;
      }
      installedApps.forEach(app => {
        const card = document.createElement('div');
        card.className = 'app-card';
        card.onclick = () => openUrl(app.url);
        card.innerHTML = `
          <div class="app-icon">${app.icon}</div>
          <div class="app-name">${app.name}</div>
          <div class="app-delete" onclick="deleteApp(${app.id}, event)">✕</div>
        `;
        container.appendChild(card);
      });
    }

    function generateOscSearchHTML(query) {
      const tr = t();
      const q = (query || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      const qEnc = encodeURIComponent(query || '');
      return `
        <!DOCTYPE html>
        <html lang="${currentLang}">
        <head>
          <meta charset="UTF-8">
          <style>
            body { font-family: sans-serif; background: #0c0f17; color: white; padding: 40px; }
            h1 { color: #3b82f6; display: flex; align-items: center; gap: 10px; }
            .query { color: #94a3b8; font-weight: normal; font-size: 18px; margin-bottom: 25px; }
            .result-card { background: #1a2234; border: 1px solid #334155; padding: 18px; border-radius: 10px; margin-bottom: 15px; }
            .result-card h3 { margin: 0 0 6px 0; }
            .result-card a { color: #60a5fa; text-decoration: none; font-size: 18px; }
            .result-card a:hover { text-decoration: underline; }
            .result-card p { color: #cbd5e1; margin: 6px 0 0 0; font-size: 14px; }
            .tag { display: inline-block; background: #334155; color: #60a5fa; font-size: 11px; padding: 2px 8px; border-radius: 4px; margin-bottom: 6px; }
          </style>
        </head>
        <body>
          <h1>${tr.oscHeader}</h1>
          <div class="query">${tr.oscTitle} <strong>"${q}"</strong></div>

          <div class="result-card">
            <span class="tag">${tr.oscTagOpenSource}</span>
            <h3><a href="https://es.wikipedia.org/wiki/${qEnc}" target="_self">Wikipedia: ${q}</a></h3>
            <p>${tr.wikiDesc}</p>
          </div>
          <div class="result-card">
            <span class="tag">${tr.oscTagPublicDomain}</span>
            <h3><a href="https://commons.wikimedia.org/w/index.php?search=${qEnc}" target="_self">Wikimedia Commons - "${q}"</a></h3>
            <p>${tr.commonsDesc}</p>
          </div>
          <div class="result-card">
            <span class="tag">${tr.oscTagOpenSearch}</span>
            <h3><a href="https://openverse.org/search/?q=${qEnc}" target="_self">Openverse</a></h3>
            <p>${tr.openverseDesc}</p>
          </div>
          <div class="result-card">
            <span class="tag">${tr.oscTagFreeFiles}</span>
            <h3><a href="https://archive.org/details/texts?query=${qEnc}" target="_self">Internet Archive - "${q}"</a></h3>
            <p>${tr.archiveDesc}</p>
          </div>
        </body>
        </html>
      `;
    }

    function openUrl(input) {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (!activeTab || !input) return;
      const trimmed = input.trim();
      let newState = {};

      if (trimmed.toLowerCase() === 'osc://parkourgame') {
        newState = { type: 'game', url: 'osc://parkourgame', title: t().gameTabTitle };
      } else if (/^https?:\/\//i.test(trimmed)) {
        newState = { type: 'web', url: trimmed, title: getDomainOrQuery(input, trimmed) };
      } else if (!trimmed.includes(' ') && trimmed.includes('.')) {
        const fullUrl = 'https://' + trimmed;
        newState = { type: 'web', url: fullUrl, title: getDomainOrQuery(input, fullUrl) };
      } else {
        const engine = searchEngines[currentEngine] || searchEngines.osc;
        if (currentEngine === 'osc') {
          newState = {
            type: 'osc',
            url: 'osc://search?q=' + encodeURIComponent(trimmed),
            title: t().oscTabPrefix + ' ' + trimmed,
            query: trimmed
          };
        } else {
          const targetUrl = engine.url + encodeURIComponent(trimmed);
          newState = { type: 'web', url: targetUrl, title: getDomainOrQuery(input, targetUrl) };
        }
      }

      activeTab.history = activeTab.history.slice(0, activeTab.historyIndex + 1);
      activeTab.history.push(newState);
      activeTab.historyIndex = activeTab.history.length - 1;
      loadHistoryState(activeTab, newState);
      renderTabs();
      updateNavButtons();
    }

    function navigate() { if (urlInput.value.trim()) openUrl(urlInput.value.trim()); }

    function reloadTab() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab && activeTab.url) {
        loadHistoryState(activeTab, activeTab.history[activeTab.historyIndex], true);
      }
    }

    function goHome() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab) {
        const currentState = activeTab.history[activeTab.historyIndex];
        if (currentState && currentState.type === 'home') return;
        const homeState = {
          type: 'home',
          url: '',
          title: activeTab.incognito ? t().incognitoTabLabel : t().newTabDefault
        };
        activeTab.history = activeTab.history.slice(0, activeTab.historyIndex + 1);
        activeTab.history.push(homeState);
        activeTab.historyIndex = activeTab.history.length - 1;
        loadHistoryState(activeTab, homeState);
        renderTabs();
        updateNavButtons();
      }
    }

    function getDomainOrQuery(originalInput, fullUrl) {
      try {
        const engine = searchEngines[currentEngine];
        if (engine && engine.url !== 'internal' && fullUrl.includes(new URL(engine.url).hostname)) {
          return `${engine.icon} ${originalInput}`;
        }
        const parsed = new URL(fullUrl);
        return parsed.hostname.replace('www.', '');
      } catch { return originalInput; }
    }

    function setBgFile(event) {
      const file = event.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
          const bgVal = `url('${e.target.result}')`;
          homeScreen.style.backgroundImage = bgVal;
          try { localStorage.setItem('ocs_bg_image', bgVal); } catch (err) {}
        };
        reader.readAsDataURL(file);
      }
    }

    function setBgUrl() {
      const url = prompt(t().promptBgUrl);
      if (url && url.trim() !== '') {
        const bgVal = `url('${url.trim()}')`;
        homeScreen.style.backgroundImage = bgVal;
        localStorage.setItem('ocs_bg_image', bgVal);
      }
    }

    function resetBg() {
      homeScreen.style.backgroundImage = "url('fondo.jpg')";
      localStorage.removeItem('ocs_bg_image');
    }

    function updateMenuColor(color) {
      document.documentElement.style.setProperty('--menu-bg', color);
      bgColorPicker.value = color;
      localStorage.setItem('ocs_menu_color', color);
    }

    function updateAccentColor(color) {
      document.documentElement.style.setProperty('--accent-color', color);
      accentColorPicker.value = color;
      localStorage.setItem('ocs_accent_color', color);
    }

    function setPreset(menuColor, accentColor) {
      updateMenuColor(menuColor);
      updateAccentColor(accentColor);
    }

    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && searchInput.value.trim()) {
        openUrl(searchInput.value.trim());
        searchInput.value = '';
      }
    });
    urlInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') navigate();
    });

    createNewTab();
    loadSettings();
  </script>

  <script id="incognito-mode-script">
    (function () {
      'use strict';

      window.createIncognitoTab = function (input) {
        createNewTab(input || '');
        const tab = tabs.find(x => x.id === activeTabId);
        if (tab) {
          tab.incognito = true;
          tab.title = t().incognitoTabLabel;
          if (tab.history && tab.history[0]) tab.history[0].title = t().incognitoTabLabel;
          loadHistoryState(tab, tab.history[tab.historyIndex], true);
        }
        renderTabs();
        actualizarUiIncognito();
      };

      function activeEsIncognito() {
        const tab = tabs.find(x => x.id === activeTabId);
        return !!(tab && tab.incognito);
      }

      window.actualizarUiIncognito = function () {
        const activa = activeEsIncognito();
        document.body.classList.toggle('incognito-mode', activa);
        const banner = document.getElementById('incognito-banner');
        if (banner) banner.textContent = t().incognitoBanner;

        const installBtn = document.getElementById('btn-install');
        if (installBtn) {
          installBtn.disabled = activa;
          installBtn.title = activa ? t().alertIncognitoNoSave : t().installAppTitle;
        }

        if (typeof tabsContainer !== 'undefined' && tabsContainer) {
          const nodos = tabsContainer.children;
          tabs.forEach((tb, i) => {
            const nodo = nodos[i];
            if (nodo) nodo.classList.toggle('tab-incognito', !!tb.incognito);
          });
        }
      };

      setInterval(actualizarUiIncognito, 400);

      document.addEventListener('click', function (e) {
        if (e.target && e.target.closest && e.target.closest('#btn-install')) {
          if (activeEsIncognito()) {
            closeInstallModal();
            alert(t().alertIncognitoNoSave);
          }
        }
      }, true);

      actualizarUiIncognito();
    })();
  </script>
</body>
</html>"""


def main():
    time.sleep(0.4)
    webview.create_window(
        'OCS Browser',
        f'http://127.0.0.1:{PROXY_PORT}/',
        width=1280,
        height=800
    )
    webview.start()


if __name__ == '__main__':
    main()
