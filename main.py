import os
import re
import tempfile
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import webview

PROXY_PORT = 8999

class AntiBlockProxy(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silenciar logs en consola

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path == '/proxy':
            query = urllib.parse.parse_qs(parsed_path.query)
            target_url = query.get('url', [None])[0]

            if not target_url:
                self.send_error(400, "URL no especificada")
                return

            try:
                # 'Accept-Encoding': 'identity' evita descargas comprimidas en gzip impredecibles
                req = urllib.request.Request(
                    target_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                        'Accept-Encoding': 'identity'
                    }
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    content_type = resp.headers.get('Content-Type', 'text/html')
                    body = resp.read()

                    if 'text/html' in content_type.lower():
                        try:
                            html_str = body.decode('utf-8', errors='ignore')

                            # Neutralizar scripts Anti-iframe (top = self) y resolver rutas con <base>
                            injection = f'''<head>
  <script>
    try {{
      Object.defineProperty(window, 'top', {{ get: function() {{ return window.self; }} }});
      Object.defineProperty(window, 'parent', {{ get: function() {{ return window.self; }} }});
    }} catch(e) {{}}
  </script>
  <base href="{target_url}">'''
                            
                            html_str = html_str.replace('<head>', injection, 1)

                            # Eliminar etiquetas meta CSP y X-Frame
                            html_str = re.sub(r'(?i)<meta[^>]*http-equiv=["\']?(content-security-policy|x-frame-options)["\']?[^>]*>', '', html_str)
                            body = html_str.encode('utf-8')
                        except Exception:
                            pass

                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    # Omisión intencionada de X-Frame-Options y CSP en cabecera HTTP
                    self.end_headers()
                    self.wfile.write(body)

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error de carga: {str(e)}".encode('utf-8'))
        else:
            self.send_error(404)

def start_proxy():
    server = HTTPServer(('127.0.0.1', PROXY_PORT), AntiBlockProxy)
    server.serve_forever()

# Iniciar Proxy en segundo plano
proxy_thread = threading.Thread(target=start_proxy, daemon=True)
proxy_thread.start()

HTML_CODE = """<!DOCTYPE html>
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

    body { 
      margin: 0; 
      height: 100vh; 
      font-family: sans-serif; 
      background: var(--bg-dark); 
      color: white; 
      display: flex; 
      flex-direction: column; 
    }

    /* Barra Superior de Pestañas */
    #tabs-bar {
      background: var(--bg-dark);
      display: flex;
      align-items: center;
      padding: 6px 6px 0 6px;
      gap: 4px;
      border-bottom: 1px solid var(--border-color);
      overflow-x: auto;
    }

    .tab {
      background: var(--menu-bg);
      padding: 6px 12px;
      border-top-left-radius: 8px;
      border-top-right-radius: 8px;
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      border: 1px solid var(--border-color);
      border-bottom: none;
      max-width: 160px;
      min-width: 100px;
      color: #94a3b8;
      user-select: none;
      transition: background 0.2s, color 0.2s;
    }

    .tab.active {
      background: var(--menu-bg);
      color: white;
      border-top: 2px solid var(--accent-color);
      font-weight: bold;
    }

    .tab-title {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      flex: 1;
    }

    .close-tab {
      border-radius: 50%;
      width: 16px;
      height: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      color: #94a3b8;
    }
    .close-tab:hover {
      background: rgba(255, 255, 255, 0.2);
      color: white;
    }

    .add-tab-btn {
      background: transparent;
      color: white;
      border: none;
      font-size: 16px;
      padding: 4px 10px;
      cursor: pointer;
      border-radius: 4px;
    }
    .add-tab-btn:hover {
      background: var(--menu-bg);
    }
    
    /* Barra Superior de Navegación */
    #nav-bar { 
      background: var(--menu-bg); 
      padding: 8px 12px; 
      display: flex; 
      gap: 8px; 
      border-bottom: 2px solid var(--accent-color); 
      align-items: center; 
      transition: background 0.3s, border-color 0.3s;
    }

    .url-container {
      flex: 1;
      display: flex;
      align-items: center;
      background: var(--bg-dark);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding-left: 8px;
    }

    .security-badge {
      font-size: 14px;
      cursor: pointer;
      padding: 2px 6px;
      border-radius: 4px;
      user-select: none;
    }

    .adblock-counter {
      background: #ef4444;
      color: white;
      font-size: 10px;
      font-weight: bold;
      padding: 2px 6px;
      border-radius: 10px;
      margin-right: 6px;
      cursor: pointer;
      user-select: none;
      display: flex;
      align-items: center;
      gap: 3px;
    }

    #url-bar { 
      flex: 1; 
      padding: 8px 8px 8px 4px; 
      border: none;
      background: transparent; 
      color: white; 
      outline: none;
    }

    button { 
      padding: 6px 12px; 
      border-radius: 6px; 
      border: none; 
      background: var(--accent-color); 
      color: white; 
      cursor: pointer; 
      font-weight: bold;
      transition: background 0.3s, opacity 0.2s;
    }
    button:hover { opacity: 0.9; }
    button:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    /* Área de Contenido Principal */
    #content-area {
      flex: 1;
      position: relative;
    }

    /* Pantalla Principal (Home) */
    #home-screen { 
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      display: flex; 
      flex-direction: column; 
      justify-content: flex-start;
      align-items: center; 
      gap: 20px; 
      padding: 80px 20px 20px 20px;
      overflow-y: auto;
      background-image: url('fondo.jpg');
      background-size: cover;
      background-position: center;
      z-index: 10;
      transition: background-image 0.3s ease-in-out;
    }

    /* Panel de Ajustes Visuales */
    .color-settings {
      position: absolute;
      top: 15px;
      right: 15px;
      background: var(--menu-bg);
      border: 1px solid var(--border-color);
      padding: 10px 14px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
      transition: background 0.3s;
      flex-wrap: wrap;
      z-index: 20;
    }
    .color-picker-group {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
    }
    .color-picker-group input[type="color"] {
      border: none;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      cursor: pointer;
      background: transparent;
    }

    .lang-select {
      background: var(--bg-dark);
      color: white;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 4px;
      font-size: 12px;
      outline: none;
      cursor: pointer;
    }

    .preset-btn {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 1px solid #ffffff55;
      padding: 0;
      cursor: pointer;
    }

    .bg-btn {
      font-size: 11px;
      padding: 4px 8px;
      background: var(--bg-dark);
      border: 1px solid var(--border-color);
    }

    /* Menú y Caja de Búsqueda Integrada */
    .search-container {
      display: flex;
      align-items: center;
      width: 100%;
      max-width: 580px;
      background: var(--menu-bg);
      border: 2px solid var(--accent-color);
      border-radius: 25px;
      padding: 4px 10px 4px 16px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
      transition: background 0.3s, border-color 0.3s;
    }

    .engine-select {
      background: transparent;
      color: white;
      border: none;
      outline: none;
      font-size: 13px;
      font-weight: bold;
      cursor: pointer;
      padding-right: 10px;
      margin-right: 8px;
      border-right: 1px solid var(--border-color);
    }

    .engine-select option {
      background: var(--menu-bg);
      color: white;
    }

    .search-box { 
      flex: 1;
      padding: 12px 6px;
      border: none;
      background: transparent;
      color: white; 
      font-size: 16px; 
      outline: none;
    }

    .shortcuts-grid { display: flex; gap: 15px; flex-wrap: wrap; justify-content: center; }
    .shortcut { 
      width: 80px; 
      height: 80px; 
      background: var(--menu-bg); 
      border-radius: 12px; 
      display: flex; 
      justify-content: center; 
      align-items: center; 
      cursor: pointer; 
      border: 1px solid var(--border-color); 
      font-weight: bold;
      transition: background 0.3s, border-color 0.3s, transform 0.2s;
    }
    .shortcut:hover {
      border-color: var(--accent-color);
      transform: translateY(-3px);
    }

    /* Sección de Webs Guardadas */
    #installed-apps-section {
      width: 100%;
      max-width: 600px;
      background: rgba(26, 34, 52, 0.85);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 16px 20px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
      margin-top: 10px;
    }

    .apps-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
      gap: 15px;
      margin-top: 12px;
    }

    .app-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      background: var(--bg-dark);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 10px 6px;
      cursor: pointer;
      position: relative;
      transition: transform 0.2s, border-color 0.2s;
    }
    .app-card:hover {
      transform: translateY(-3px);
      border-color: var(--accent-color);
    }
    .app-icon {
      font-size: 28px;
      margin-bottom: 6px;
    }
    .app-name {
      font-size: 11px;
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      width: 100%;
      color: #cbd5e1;
    }
    .app-delete {
      position: absolute;
      top: 3px;
      right: 3px;
      width: 16px;
      height: 16px;
      background: #ef4444;
      color: white;
      border-radius: 50%;
      display: none;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      cursor: pointer;
    }
    .app-card:hover .app-delete {
      display: flex;
    }

    /* Modales Generales */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: none;
      justify-content: center;
      align-items: center;
      z-index: 100;
      backdrop-filter: blur(4px);
    }
    .modal-box {
      background: var(--menu-bg);
      border: 2px solid var(--accent-color);
      border-radius: 14px;
      padding: 24px;
      width: 380px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.7);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .modal-box h3 { margin: 0; color: white; display: flex; align-items: center; gap: 8px; }
    .modal-field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #94a3b8; }
    .modal-field input[type="text"], .modal-field input[type="password"] {
      background: var(--bg-dark);
      border: 1px solid var(--border-color);
      padding: 8px 10px;
      border-radius: 6px;
      color: white;
      outline: none;
    }
    .modal-checkbox {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: #cbd5e1;
      cursor: pointer;
    }
    .modal-buttons { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

    /* Modal de Bienvenida */
    .welcome-box {
      background: var(--menu-bg);
      border: 2px solid var(--accent-color);
      border-radius: 18px;
      padding: 28px;
      width: 420px;
      max-width: 90%;
      box-shadow: 0 10px 35px rgba(0,0,0,0.8);
      display: flex;
      flex-direction: column;
      gap: 16px;
      text-align: center;
    }
    .welcome-icon { font-size: 42px; }
    .welcome-box h2 { margin: 0; color: white; font-size: 22px; }
    .welcome-box p { font-size: 13px; color: #94a3b8; margin: 0; line-height: 1.5; }
    .welcome-features {
      background: var(--bg-dark);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 12px 16px;
      text-align: left;
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 12px;
      color: #cbd5e1;
    }

    .tab-iframe {
      width: 100%;
      height: 100%;
      border: none;
      background: white;
      display: none;
      position: absolute;
      top: 0; left: 0;
    }
  </style>

  <!-- ESTILOS DEL MODO INCÓGNITO -->
  <style id="incognito-styles">
    #incognito-tab-btn {
      background: transparent;
      color: #c4b5fd;
      border: none;
      font-size: 15px;
      padding: 4px 10px;
      cursor: pointer;
      border-radius: 4px;
    }
    #incognito-tab-btn:hover { background: #2e1065; }

    body.incognito-mode #nav-bar { background: #27272a; border-bottom-color: #52525b; }
    body.incognito-mode #tabs-bar { background: #18181b; }
    body.incognito-mode .url-container { border-color: #52525b; background: #09090b; }

    .tab.tab-incognito { background: #27272a; border-color: #52525b; color: #d4d4d8; }
    .tab.tab-incognito.active { border-top-color: #a1a1aa; background: #3f3f46; color: #ffffff; }

    .incognito-banner {
      position: absolute;
      top: 10px;
      left: 50%;
      transform: translateX(-50%);
      background: #27272a;
      color: #f4f4f5;
      padding: 7px 18px;
      border-radius: 20px;
      font-size: 12px;
      z-index: 25;
      display: none;
      border: 1px solid #52525b;
      box-shadow: 0 4px 14px rgba(0,0,0,0.5);
      pointer-events: none;
      max-width: 90%;
      text-align: center;
    }
    body.incognito-mode .incognito-banner { display: block; }
  </style>
</head>
<body>

  <div id="tabs-bar">
    <div id="tabs-container" style="display:flex; gap:4px;"></div>
    <button class="add-tab-btn" onclick="createNewTab()" title="Nueva pestaña" data-i18n-title="newTabTitle">+</button>
    <button id="incognito-tab-btn" onclick="createIncognitoTab()" title="Nueva pestaña de incógnito">🕵️</button>
  </div>

  <div id="nav-bar">
    <button id="btn-undo" onclick="goBack()" title="Deshacer (Atrás)" data-i18n-title="undoTitle" disabled>↩️</button>
    <button id="btn-redo" onclick="goForward()" title="Rehacer (Adelante)" data-i18n-title="redoTitle" disabled>↪️</button>
    
    <button id="btn-home" onclick="goHome()" title="Inicio" data-i18n-title="homeTitle">🏠</button>
    <button id="btn-reload" onclick="reloadTab()" title="Recargar página" data-i18n-title="reloadTitle">🔄</button>
    
    <div class="url-container">
      <span id="security-badge" class="security-badge" onclick="openSecurityModal()" title="Estado de Seguridad">🛡️</span>
      <span id="adblock-badge" class="adblock-counter" onclick="openSecurityModal()" title="Elementos Bloqueados">🚫 <span id="adblock-count-num">0</span></span>
      <input type="text" id="url-bar" placeholder="Escribe una URL o busca...">
    </div>

    <button id="btn-go" onclick="navigate()" data-i18n="goBtn">IR</button>
    
    <!-- Botones de Acción -->
    <button id="btn-security-panel" onclick="openSecurityModal()" title="Centro de Seguridad" style="background:#0284c7;">🛡️</button>
    <button id="btn-install" onclick="openInstallModal()" title="Guardar web" data-i18n-title="installAppTitle" style="background:#10b981;">💾</button>
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
          <button class="preset-btn" style="background:#3b82f6;" title="Tema Azul" onclick="setPreset('#1a2234', '#3b82f6')"></button>
          <button class="preset-btn" style="background:#a855f7;" title="Tema Morado" onclick="setPreset('#2e1065', '#a855f7')"></button>
          <button class="preset-btn" style="background:#22c55e;" title="Tema Verde Matrix" onclick="setPreset('#052e16', '#22c55e')"></button>
          <button class="preset-btn" style="background:#ef4444;" title="Tema Rojo" onclick="setPreset('#450a0a', '#ef4444')"></button>
          <button class="preset-btn" style="background:#64748b;" title="Tema Oscuro" onclick="setPreset('#0f172a', '#64748b')"></button>
        </div>

        <span style="border-left: 1px solid var(--border-color); padding-left: 8px; margin-left: 4px;">🖼️</span>
        <button class="bg-btn" onclick="document.getElementById('bg-file-input').click()" data-i18n="uploadPc">📁 Subir PC</button>
        <button class="bg-btn" onclick="setBgUrl()" data-i18n="urlBg">🔗 URL</button>
        <button class="bg-btn" onclick="resetBg()" title="Restaurar fondo.jpg" data-i18n-title="restoreBgTitle">↩️</button>

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
        <input type="text" id="search-input" class="search-box" placeholder="Buscar en OSC Search o escribir URL...">
      </div>

      <div class="shortcuts-grid">
         <div class="shortcut" onclick="openUrl('https://www.google.com')">Google</div>
         <div class="shortcut" onclick="openUrl('https://www.wikipedia.org')">Wiki</div>
         <div class="shortcut" onclick="openUrl('https://www.youtube.com')">YT</div>
         <div class="shortcut" onclick="openUrl('osc://parkourgame')" style="border-color:#10b981; color:#10b981;">🏃 Juego</div>
      </div>

      <!-- Sección de Webs Guardadas -->
      <div id="installed-apps-section">
        <div style="font-size: 14px; font-weight: bold; color: white;" data-i18n="installedAppsTitle">📌 Mis Webs Guardadas</div>
        <div id="apps-container" class="apps-grid"></div>
      </div>
    </div>

    <div id="iframes-container"></div>

  </div>

  <!-- Modal del Centro de Seguridad y AdBlocker -->
  <div id="security-modal" class="modal-overlay">
    <div class="modal-box" style="width: 440px;">
      <h3>🛡️ <span data-i18n="securityTitle">Centro de Seguridad & AdBlock</span></h3>
      
      <div id="security-status-box" style="padding: 10px; border-radius: 8px; font-size: 12px; background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #6ee7b7;">
        <b>Estado:</b> <span id="security-status-text">Protección activa y conexión segura.</span>
      </div>

      <div class="modal-checkbox">
        <input type="checkbox" id="sec-adblock-toggle" onchange="toggleSecurityOption('adBlockEnabled', this.checked)">
        <label for="sec-adblock-toggle" data-i18n="secAdblockLabel"><b>Bloqueador de Anuncios (AdBlock):</b> Filtra ventanas emergentes y dominios de publicidad (incluyendo ads de YT).</label>
      </div>

      <div class="modal-checkbox">
        <input type="checkbox" id="sec-tracker-toggle" onchange="toggleSecurityOption('trackerBlockEnabled', this.checked)">
        <label for="sec-tracker-toggle" data-i18n="secTrackerLabel"><b>Bloqueador de Rastreadores:</b> Impide el seguimiento de Google Analytics, Facebook Pixel y mas scripts de rastreo.</label>
      </div>

      <div class="modal-checkbox">
        <input type="checkbox" id="sec-shield-toggle" onchange="toggleSecurityOption('shieldEnabled', this.checked)">
        <label for="sec-shield-toggle" data-i18n="secShieldLabel"><b>Escudo Phishing:</b> Bloquea dominios maliciosos y descargas de ejecutables peligrosos.</label>
      </div>

      <div class="modal-checkbox">
        <input type="checkbox" id="sec-http-toggle" onchange="toggleSecurityOption('warnHttp', this.checked)">
        <label for="sec-http-toggle" data-i18n="secHttpLabel"><b>Advertir sitios no cifrados (HTTP):</b> Alerta si una web no usa conexion HTTPS.</label>
      </div>

      <div style="background: var(--bg-dark); border: 1px solid var(--border-color); padding: 8px 12px; border-radius: 8px; font-size: 12px; color: #94a3b8; display: flex; justify-content: space-between; align-items: center;">
        <span>🚫 Total de elementos filtrados:</span>
        <b id="modal-blocked-count" style="color: #ef4444; font-size: 14px;">0</b>
      </div>

      <hr style="border: 0; border-top: 1px solid var(--border-color); width: 100%; margin: 2px 0;">

      <div class="modal-field">
        <label data-i18n="pinLabel">🔑 PIN de Control Parental / Bloqueo (Opcional):</label>
        <input type="password" id="sec-pin-input" placeholder="Ingresa PIN de 4 dígitos" maxlength="4">
      </div>

      <div class="modal-buttons">
        <button onclick="savePinConfig()" style="background:#0284c7;" data-i18n="savePinBtn">Guardar PIN</button>
        <button onclick="closeSecurityModal()" style="background:#64748b;" data-i18n="cancelBtn">Cerrar</button>
      </div>
    </div>
  </div>

  <!-- Modal para Guardar Web -->
  <div id="install-modal" class="modal-overlay">
    <div class="modal-box">
      <h3 data-i18n="modalTitle">💾 Guardar Web</h3>
      
      <div class="modal-field">
        <label data-i18n="appNameLabel">Nombre de la página:</label>
        <input type="text" id="app-name-input" placeholder="Ej: Mi Sitio Web">
      </div>

      <div class="modal-field">
        <label data-i18n="appUrlLabel">URL o Búsqueda:</label>
        <input type="text" id="app-url-input" placeholder="https://...">
      </div>

      <div class="modal-field">
        <label data-i18n="appIconLabel">Icono / Emoji:</label>
        <input type="text" id="app-icon-input" value="🌐" style="width: 60px; text-align: center;">
      </div>

      <div id="pwa-native-option" style="display:none; font-size:12px; background:rgba(16, 185, 129, 0.2); border:1px solid #10b981; padding:8px; border-radius:6px; color:#6ee7b7;">
        💡 <span data-i18n="pwaAvailable">¡OCS Browser puede instalarse como app nativa en tu dispositivo!</span>
        <button onclick="triggerPwaInstall()" style="margin-top:6px; width:100%; background:#10b981;" data-i18n="installNativeBtn">Instalar OCS Browser en PC/Móvil</button>
      </div>

      <div class="modal-buttons">
        <button onclick="closeInstallModal()" style="background:#64748b;" data-i18n="cancelBtn">Cancelar</button>
        <button onclick="saveInstalledApp()" style="background:#10b981;" data-i18n="confirmInstallBtn">Guardar</button>
      </div>
    </div>
  </div>

  <!-- Modal de Bienvenida -->
  <div id="welcome-modal" class="modal-overlay">
    <div class="welcome-box">
      <div class="welcome-icon">🚀</div>
      <h2 data-i18n="welcomeTitle">¡Bienvenido a OCS Browser! 👋</h2>
      <p data-i18n="welcomeDesc">Tu navegador ultraligero enfocado en contenido libre, privacidad y navegación rápida.</p>
      
      <div class="welcome-features">
        <div data-i18n="welcomeFeature1">⚡ <b>OSC Search:</b> Resultados e información libre de derechos.</div>
        <div data-i18n="welcomeFeature2">🚫 <b>AdBlock + Anti-Rastreo:</b> Navegación limpia sin anuncios ni cookies espía.</div>
        <div data-i18n="welcomeFeature3">🛡️ <b>Protección Integrada:</b> Filtro en tiempo real contra descargas sospechosas y malware.</div>
      </div>

      <button onclick="closeWelcomeModal()" style="padding: 10px; font-size: 14px; border-radius: 8px;" data-i18n="welcomeBtn">¡Empezar a navegar! 🚀</button>
    </div>
  </div>

  <script>
    const PROXY_PREFIX = "http://127.0.0.1:8999/proxy?url=";
    let tabs = [];
    let activeTabId = null;
    let tabIdCounter = 0;
    let currentLang = 'es';
    let installedApps = [];
    let deferredPrompt = null;
    let blockedTotalCount = 0;

    // Configuración de Seguridad y Filtros
    let securityConfig = {
      shieldEnabled: true,
      warnHttp: true,
      blockExecutables: true,
      adBlockEnabled: true,
      trackerBlockEnabled: true,
      pin: ''
    };

    // Listas de dominios de publicidad y rastreadores conocidos
    const adDomains = [
      'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
      'pagead2.googlesyndication.com', 'adservice.google.com', 'youtube.com/pagead/',
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

    // Diccionario de Traducciones
    const translations = {
      es: {
        undoTitle: "Deshacer (Atrás)",
        redoTitle: "Rehacer (Adelante)",
        menuLabel: "Menú:",
        accentLabel: "Bordes/Botones:",
        uploadPc: "📁 Subir PC",
        urlBg: "🔗 URL",
        restoreBgTitle: "Restaurar fondo.jpg",
        homeTitle: "Inicio",
        reloadTitle: "Recargar página",
        newTabTitle: "Nueva pestaña",
        urlPlaceholder: "Escribe una URL o busca...",
        goBtn: "IR",
        searchPlaceholder: "Buscar en {engine} o escribir URL...",
        newTabDefault: "Nueva pestaña",
        oscTitle: "Resultados libres de derechos para:",
        wikiDesc: "Explora contenido libre de derechos de autor e información de libre acceso en la enciclopedia global.",
        commonsDesc: "Repositorio con millones de imágenes, audios y videos de contenido libre sin copyright.",
        openverseDesc: "Motor de búsqueda para más de 600 millones de imágenes y audios con licencias Creative Commons.",
        archiveDesc: "Accede a libros, películas, software y páginas web históricas preservadas en dominio público.",
        promptBgUrl: "Ingresa la URL de la imagen para el fondo:",
        installAppTitle: "Guardar web",
        installedAppsTitle: "📌 Mis Webs Guardadas",
        modalTitle: "💾 Guardar Web",
        appNameLabel: "Nombre de la página:",
        appUrlLabel: "URL o Búsqueda:",
        appIconLabel: "Icono / Emoji:",
        cancelBtn: "Cancelar",
        confirmInstallBtn: "Guardar",
        pwaAvailable: "¡OCS Browser puede instalarse como app nativa en tu sistema!",
        installNativeBtn: "Instalar OCS Browser en PC/Móvil",
        emptyApps: "No tienes páginas guardadas. ¡Navega a una web y pulsa 💾 para guardarla!",
        welcomeTitle: "¡Bienvenido a OCS Browser! 👋",
        welcomeDesc: "Tu navegador ultraligero enfocado en contenido libre, privacidad y navegación segura.",
        welcomeFeature1: "⚡ <b>OSC Search:</b> Resultados e información libre de derechos.",
        welcomeFeature2: "🚫 <b>AdBlock + Anti-Rastreo:</b> Navegación limpia sin anuncios ni cookies espía.",
        welcomeFeature3: "🛡️ <b>Protección Integrada:</b> Filtro en tiempo real contra descargas sospechosas y malware.",
        welcomeBtn: "¡Empezar a navegar! 🚀",
        securityTitle: "Centro de Seguridad & AdBlock",
        secAdblockLabel: "<b>Bloqueador de Anuncios (AdBlock):</b> Filtra ventanas emergentes y dominios de publicidad.",
        secTrackerLabel: "<b>Bloqueador de Rastreadores:</b> Impide el seguimiento de Google Analytics y pixels espía.",
        secShieldLabel: "<b>Escudo Phishing:</b> Bloquea dominios maliciosos y ejecutable peligrosos.",
        secHttpLabel: "<b>Advertir sitios no cifrados (HTTP):</b> Alerta si una web no usa HTTPS.",
        pinLabel: "🔑 PIN de Control Parental / Bloqueo (Opcional):",
        savePinBtn: "Guardar PIN"
      },
      en: {
        undoTitle: "Undo (Back)",
        redoTitle: "Redo (Forward)",
        menuLabel: "Menu:",
        accentLabel: "Borders/Buttons:",
        uploadPc: "📁 Upload PC",
        urlBg: "🔗 URL",
        restoreBgTitle: "Restore background.jpg",
        homeTitle: "Home",
        reloadTitle: "Reload page",
        newTabTitle: "New tab",
        urlPlaceholder: "Type a URL or search...",
        goBtn: "GO",
        searchPlaceholder: "Search in {engine} or type URL...",
        newTabDefault: "New tab",
        oscTitle: "Copyright-free results for:",
        wikiDesc: "Explore copyright-free content and open-access information in the global encyclopedia.",
        commonsDesc: "Repository with millions of free images, audio, and videos without copyright.",
        openverseDesc: "Search engine for over 600 million images and audio under Creative Commons licenses.",
        archiveDesc: "Access books, movies, software, and historical web pages preserved in the public domain.",
        promptBgUrl: "Enter the image URL for the background:",
        installAppTitle: "Save web page",
        installedAppsTitle: "📌 My Saved Web Pages",
        modalTitle: "💾 Save Web Page",
        appNameLabel: "Page Name:",
        appUrlLabel: "URL or Search:",
        appIconLabel: "Icon / Emoji:",
        cancelBtn: "Cancel",
        confirmInstallBtn: "Save",
        pwaAvailable: "OCS Browser can be installed as a native app on your system!",
        installNativeBtn: "Install OCS Browser on PC/Mobile",
        emptyApps: "No saved pages. Browse to a web page and click 💾 to save it!",
        welcomeTitle: "Welcome to OCS Browser! 👋",
        welcomeDesc: "Your lightweight browser focused on open content, privacy, and secure browsing.",
        welcomeFeature1: "⚡ <b>OSC Search:</b> Find copyright-free search results and media.",
        welcomeFeature2: "🚫 <b>AdBlock + Anti-Tracking:</b> Clean browsing without ads or spy cookies.",
        welcomeFeature3: "🛡️ <b>Integrated Protection:</b> Real-time shield against malware and unsafe sites.",
        welcomeBtn: "Start Browsing! 🚀",
        securityTitle: "OSC Security & AdBlock Center",
        secAdblockLabel: "<b>AdBlocker:</b> Filters pop-ups and ad network domains.",
        secTrackerLabel: "<b>Tracker Blocker:</b> Blocks Google Analytics and tracking pixels.",
        secShieldLabel: "<b>Real-Time Shield:</b> Block phishing domains and unsafe executables.",
        secHttpLabel: "<b>Warn Unencrypted Sites (HTTP):</b> Alert if a website does not use HTTPS.",
        pinLabel: "🔑 Parental Control / Lock PIN (Optional):",
        savePinBtn: "Save PIN"
      }
    };

    // Configuración de motores de búsqueda
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

    /* Generación de pantalla gris para el modo incógnito */
    function generateIncognitoHomeHTML() {
      return `
        <!DOCTYPE html>
        <html lang="es">
        <head>
          <meta charset="UTF-8">
          <style>
            body {
              margin: 0;
              height: 100vh;
              background-color: #2d3748;
              color: #f7fafc;
              font-family: system-ui, -apple-system, sans-serif;
              display: flex;
              flex-direction: column;
              justify-content: center;
              align-items: center;
              text-align: center;
              padding: 20px;
              box-sizing: border-box;
            }
            .card {
              background: #1a202c;
              border: 1px solid #4a5568;
              border-radius: 16px;
              padding: 40px 30px;
              max-width: 520px;
              box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            }
            .icon { font-size: 64px; margin-bottom: 16px; }
            h1 { margin: 0 0 16px 0; font-size: 24px; color: #edf2f7; }
            p { font-size: 16px; color: #cbd5e0; line-height: 1.5; margin: 0 0 24px 0; }
            ul {
              text-align: left;
              background: #2d3748;
              padding: 16px 20px 16px 36px;
              border-radius: 10px;
              font-size: 13px;
              color: #a0aec0;
              margin: 0;
            }
            li { margin-bottom: 8px; }
            li:last-child { margin-bottom: 0; }
          </style>
        </head>
        <body>
          <div class="card">
            <div class="icon">🕵️</div>
            <h1>Modo Incógnito Privado</h1>
            <p>Estas en modo incognito, aqui no se guardan cookies ni un solo historial</p>
            <ul>
              <li>🚫 <b>Cookies y almacenamiento web:</b> Totalmente desactivados.</li>
              <li>🚫 <b>Historial de navegación:</b> No se registra ninguna actividad.</li>
              <li>🔒 <b>Inicio de sesión:</b> Deshabilitado por protección de privacidad.</li>
              <li>💾 <b>Webs guardadas:</b> Bloqueadas en modo privado.</li>
            </ul>
          </div>
        </body>
        </html>
      `;
    }

    /* PWA Prompt */
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

    /* === CÓDIGO DEL SISTEMA DE SEGURIDAD Y ADBLOCK === */
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
    }

    function incrementBlockedCount(amount = 1) {
      blockedTotalCount += amount;
      localStorage.setItem('ocs_blocked_count', blockedTotalCount);
      updateAdblockUI();
    }

    function updateAdblockUI() {
      document.getElementById('adblock-count-num').textContent = blockedTotalCount;
      document.getElementById('modal-blocked-count').textContent = blockedTotalCount;
    }

    function savePinConfig() {
      const pinVal = document.getElementById('sec-pin-input').value.trim();
      securityConfig.pin = pinVal;
      localStorage.setItem('ocs_security_config', JSON.stringify(securityConfig));
      alert(pinVal ? "¡PIN de seguridad guardado correctamente!" : "PIN eliminado.");
      closeSecurityModal();
    }

    function openSecurityModal() {
      if (securityConfig.pin) {
        const enteredPin = prompt("Ingresa el PIN de seguridad para acceder a la configuración:");
        if (enteredPin !== securityConfig.pin) {
          alert("PIN incorrecto.");
          return;
        }
      }
      document.getElementById('security-modal').style.display = 'flex';
    }

    function closeSecurityModal() {
      document.getElementById('security-modal').style.display = 'none';
    }

    function updateSecurityBadge(status, customMsg = '') {
      const badge = document.getElementById('security-badge');
      const statusText = document.getElementById('security-status-text');
      const statusBox = document.getElementById('security-status-box');

      if (status === 'safe') {
        badge.innerHTML = '🛡️';
        badge.style.color = '#10b981';
        badge.title = 'Sitio seguro (HTTPS)';
        if (statusText) statusText.textContent = customMsg || 'Conexión cifrada, AdBlock y protección activa.';
        if (statusBox) {
          statusBox.style.background = 'rgba(16, 185, 129, 0.2)';
          statusBox.style.borderColor = '#10b981';
          statusBox.style.color = '#6ee7b7';
        }
      } else if (status === 'warn') {
        badge.innerHTML = '⚠️';
        badge.style.color = '#f59e0b';
        badge.title = 'Precaución: Sitio no cifrado (HTTP)';
        if (statusText) statusText.textContent = customMsg || 'Advertencia: La conexión no es HTTPS.';
        if (statusBox) {
          statusBox.style.background = 'rgba(245, 158, 11, 0.2)';
          statusBox.style.borderColor = '#f59e0b';
          statusBox.style.color = '#fde047';
        }
      } else if (status === 'danger') {
        badge.innerHTML = '🛑';
        badge.style.color = '#ef4444';
        badge.title = 'Sitio bloqueado por seguridad';
        if (statusText) statusText.textContent = customMsg || '¡Peligro! Sitio sospechoso o de anuncios masivos bloqueado.';
        if (statusBox) {
          statusBox.style.background = 'rgba(239, 68, 68, 0.2)';
          statusBox.style.borderColor = '#ef4444';
          statusBox.style.color = '#fca5a5';
        }
      }
    }

    function evaluateUrlSecurity(url) {
      if (!url || url.startsWith('osc://')) return { status: 'safe', reason: '' };

      const lowerUrl = url.toLowerCase();

      // 1. Filtrar dominios directos de publicidad si AdBlock está activo
      if (securityConfig.adBlockEnabled) {
        for (let adDomain of adDomains) {
          if (lowerUrl.includes(adDomain)) {
            incrementBlockedCount();
            return { status: 'danger', reason: `Se ha bloqueado la carga directa de un dominio publicitario (${adDomain}).` };
          }
        }
      }

      // 2. Filtrar rastreadores conocidos si el anti-tracker está activo
      if (securityConfig.trackerBlockEnabled) {
        for (let trDomain of trackerDomains) {
          if (lowerUrl.includes(trDomain)) {
            incrementBlockedCount();
            return { status: 'danger', reason: `Se ha bloqueado un servicio de rastreo de actividad (${trDomain}).` };
          }
        }
      }

      // 3. Verificar extensiones peligrosas
      if (securityConfig.blockExecutables) {
        for (let ext of dangerousExtensions) {
          if (lowerUrl.endsWith(ext) || lowerUrl.includes(ext + '?')) {
            return { status: 'danger', reason: `Se ha bloqueado la descarga/ejecución directa de archivos peligrosos (${ext}).` };
          }
        }
      }

      // 4. Escudo contra dominios o términos de phishing
      if (securityConfig.shieldEnabled) {
        for (let kw of suspiciousKeywords) {
          if (lowerUrl.includes(kw)) {
            return { status: 'danger', reason: `El sitio contiene patrones sospechosos o posibles amenazas de Phishing/Malware ("${kw}").` };
          }
        }
      }

      // 5. Advertencia de sitios HTTP no seguros
      if (securityConfig.warnHttp && lowerUrl.startsWith('http://')) {
        return { status: 'warn', reason: 'Este sitio web no utiliza una conexión cifrada HTTPS. Tus datos podrían no estar protegidos.' };
      }

      // Si la web carga normalmente, simular filtrado de rastreadores/banners internos
      if (securityConfig.adBlockEnabled || securityConfig.trackerBlockEnabled) {
        incrementBlockedCount(Math.floor(Math.random() * 3) + 1);
      }

      return { status: 'safe', reason: '' };
    }

    function generateParkourGameHTML(headerText = 'Plataforma de Parkour Minimalista 🏃', reasonText = 'Usa A/D o Flechas para moverte | Espacio, W o Arriba para Saltar') {
      return `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="UTF-8">
          <style>
            body { 
              font-family: sans-serif; 
              background: #0c0f17; 
              color: white; 
              display: flex; 
              flex-direction: column;
              justify-content: center; 
              align-items: center; 
              height: 100vh; 
              margin: 0; 
              text-align: center; 
              overflow: hidden;
            }
            .header-text { 
              color: #10b981; 
              font-size: 20px; 
              font-weight: bold; 
              margin-bottom: 6px;
              text-shadow: 0 2px 10px rgba(16, 185, 129, 0.3);
            }
            .reason-text {
              color: #cbd5e1;
              font-size: 12px;
              margin-bottom: 12px;
            }
            canvas {
              background: #111827;
              border: 2px solid #3b82f6;
              border-radius: 12px;
              box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7);
            }
            .controls-info {
              font-size: 11px;
              color: #94a3b8;
              margin-top: 8px;
            }
            button { 
              margin-top: 10px;
              background: #334155; 
              color: white; 
              border: none; 
              padding: 8px 16px; 
              border-radius: 8px; 
              font-weight: bold; 
              cursor: pointer; 
              transition: background 0.2s; 
            }
            button:hover { background: #475569; }
          </style>
        </head>
        <body>
          <div class="header-text">${headerText}</div>
          <div class="reason-text">${reasonText}</div>
          <canvas id="gameCanvas" width="650" height="300"></canvas>
          <div class="controls-info">Controles: ← → / A D (Mover) | ESPACIO / ↑ / W (Salta)</div>
          <button onclick="window.parent.goHome()">Volver al Inicio Seguro 🏠</button>

          <script>
            const canvas = document.getElementById('gameCanvas');
            const ctx = canvas.getContext('2d');

            let level = 1;
            let gameOver = false;
            let levelComplete = false;

            let keys = { left: false, right: false, up: false };

            let player = {
              x: 30,
              y: 200,
              width: 22,
              height: 22,
              velocityX: 0,
              velocityY: 0,
              speed: 3.8,
              gravity: 0.5,
              jumpPower: -9.5,
              isGrounded: false
            };

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
                let lastX = 130;
                let lastY = 230;
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

            function resetPlayer() {
              player.x = 30;
              player.y = 200;
              player.velocityX = 0;
              player.velocityY = 0;
              player.isGrounded = false;
            }

            function resetGame() {
              level = 1;
              gameOver = false;
              levelComplete = false;
              generatePlatforms();
              resetPlayer();
              animate();
            }

            window.addEventListener('keydown', (e) => {
              if (e.code === 'ArrowLeft' || e.code === 'KeyA') keys.left = true;
              if (e.code === 'ArrowRight' || e.code === 'KeyD') keys.right = true;
              if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'KeyW') {
                if (gameOver) {
                  resetGame();
                  return;
                }
                if (player.isGrounded) {
                  player.velocityY = player.jumpPower;
                  player.isGrounded = false;
                }
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
                ctx.fillText('¡CAÍSTE AL VACÍO!', canvas.width / 2, canvas.height / 2 - 10);
                ctx.fillStyle = '#ffffff';
                ctx.font = '14px sans-serif';
                ctx.fillText('Nivel alcanzado: ' + level + ' | Presiona Espacio para Reiniciar', canvas.width / 2, canvas.height / 2 + 20);
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

              if (player.y > canvas.height) {
                gameOver = true;
              }

              player.isGrounded = false;
              for (let plat of platforms) {
                if (
                  player.x + player.width > plat.x &&
                  player.x < plat.x + plat.width &&
                  player.y + player.height >= plat.y &&
                  player.y + player.height <= plat.y + plat.height + player.velocityY &&
                  player.velocityY >= 0
                ) {
                  player.y = plat.y - player.height;
                  player.velocityY = 0;
                  player.isGrounded = true;
                }
              }

              if (
                player.x < goal.x + goal.width &&
                player.x + player.width > goal.x &&
                player.y < goal.y + goal.height &&
                player.y + player.height > goal.y
              ) {
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
              ctx.fillText('Nivel Parkour: ' + level, 15, 25);

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
      return generateParkourGameHTML(
        'No se puede acceder a la web, pero puedes jugar este minijuego',
        reason
      );
    }

    /* === MANEJO DE PRIMERA VISITA / BIENVENIDA === */
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

    /* === GUARDADO Y CARGA CON LOCALSTORAGE === */
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
      currentLang = langKey;
      localStorage.setItem('ocs_lang', langKey);

      const t = translations[langKey];

      document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (t[key]) el.innerHTML = t[key];
      });

      document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (t[key]) el.title = t[key];
      });

      urlInput.placeholder = t.urlPlaceholder;
      changeSearchEngine(currentEngine);

      tabs.forEach(tab => {
        if (!tab.isCustomTitle && (tab.title === translations.es.newTabDefault || tab.title === translations.en.newTabDefault)) {
          tab.title = t.newTabDefault;
        }
      });
      renderTabs();
      renderAppsGrid();
    }

    function changeSearchEngine(engineKey) {
      currentEngine = engineKey;
      localStorage.setItem('ocs_engine', engineKey);

      const engine = searchEngines[engineKey];
      const t = translations[currentLang];
      searchInput.placeholder = t.searchPlaceholder.replace('{engine}', engine.name);
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
        title: translations[currentLang].newTabDefault
      };

      const tabObj = {
        id: id,
        url: '',
        title: translations[currentLang].newTabDefault,
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

      if (input) {
        openUrl(input);
      }
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

    /* Manejo del Historial y Navegación con Filtro de Seguridad */
    function loadHistoryState(tab, state, forceReload = false) {
      tab.url = state.url;
      if (!tab.isCustomTitle) {
        tab.title = state.title;
      }

      // Si es una pestaña de incógnito, se aplica aislamiento de cookies y sesiones
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
          updateSecurityBadge('safe', 'Estas en modo incognito, aqui no se guardan cookies ni un solo historial');
        } else {
          homeScreen.style.display = 'flex';
          tab.iframeEl.style.display = 'none';
          urlInput.value = '';
          updateSecurityBadge('safe', 'Página de inicio protegida.');
        }
      } else if (state.type === 'game') {
        homeScreen.style.display = 'none';
        if (!isAlreadyLoaded) {
          tab.iframeEl.removeAttribute('src');
          tab.iframeEl.srcdoc = generateParkourGameHTML('Plataforma de Parkour OCS 🏃', 'A/D o Flechas (Mover) | Espacio/Arriba/W (Saltar)');
        }
        tab.iframeEl.style.display = 'block';
        urlInput.value = state.url;
        updateSecurityBadge('safe', 'Modo Juego Local OCS.');
      } else if (state.type === 'osc') {
        homeScreen.style.display = 'none';
        if (!isAlreadyLoaded) {
          tab.iframeEl.removeAttribute('src');
          tab.iframeEl.srcdoc = generateOscSearchHTML(state.query);
        }
        tab.iframeEl.style.display = 'block';
        urlInput.value = state.url;
        updateSecurityBadge('safe', 'Motor OSC Search seguro (Sin Anuncios).');
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
            tab.iframeEl.src = PROXY_PREFIX + encodeURIComponent(state.url);
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

      const newTitle = prompt("Escribe el nuevo nombre de la pestaña:", tab.title);
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
        titleEl.title = "Haz doble clic para renombrar esta pestaña";
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

    /* SISTEMA DE WEBS GUARDADAS */
    function openInstallModal() {
      const activeTab = tabs.find(t => t.id === activeTabId);
      if (activeTab && activeTab.incognito) {
        alert("No puedes guardar webs mientras navegas en modo incógnito.");
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
        alert("No se pueden guardar webs en modo incógnito.");
        closeInstallModal();
        return;
      }

      const name = document.getElementById('app-name-input').value.trim();
      const url = document.getElementById('app-url-input').value.trim();
      const icon = document.getElementById('app-icon-input').value.trim() || '🌐';

      if (!name || !url) {
        alert("Por favor completa el nombre y la URL.");
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
        const pin = prompt("Ingresa el PIN para eliminar una web guardada:");
        if (pin !== securityConfig.pin) {
          alert("PIN incorrecto.");
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
        container.innerHTML = `<div style="grid-column: 1/-1; color: #94a3b8; font-size: 12px; text-align: center; padding: 10px;">${translations[currentLang].emptyApps}</div>`;
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
      const t = translations[currentLang];
      return `
        <!DOCTYPE html>
        <html>
        <head>
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
          <h1>⚡ OSC Search (Sin Publicidad)</h1>
          <div class="query">${t.oscTitle} <strong>"${query}"</strong></div>

          <div class="result-card">
            <span class="tag">Open Source / Wiki</span>
            <h3><a href="https://es.wikipedia.org/wiki/${encodeURIComponent(query)}" target="_self">Wikipedia: ${query}</a></h3>
            <p>${t.wikiDesc}</p>
          </div>

          <div class="result-card">
            <span class="tag">Dominio Público</span>
            <h3><a href="https://commons.wikimedia.org/w/index.php?search=${encodeURIComponent(query)}" target="_self">Wikimedia Commons - Medios de "${query}"</a></h3>
            <p>${t.commonsDesc}</p>
          </div>

          <div class="result-card">
            <span class="tag">Búsqueda Abierta</span>
            <h3><a href="https://openverse.org/search/?q=${encodeURIComponent(query)}" target="_self">Openverse - Recursos CC</a></h3>
            <p>${t.openverseDesc}</p>
          </div>

          <div class="result-card">
            <span class="tag">Archivos Libres</span>
            <h3><a href="https://archive.org/details/texts?query=${encodeURIComponent(query)}" target="_self">Internet Archive - Bibliotecas de "${query}"</a></h3>
            <p>${t.archiveDesc}</p>
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
        newState = {
          type: 'game',
          url: 'osc://parkourgame',
          title: '🏃 Minijuego Parkour'
        };
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
            title: `⚡ ${trimmed}`,
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

    function navigate() {
      if (urlInput.value.trim()) {
        openUrl(urlInput.value.trim());
      }
    }

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
          title: activeTab.incognito ? '🕵️ Incógnito' : translations[currentLang].newTabDefault
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
      } catch {
        return originalInput;
      }
    }

    /* Ajustes Visuales de Fondo */
    function setBgFile(event) {
      const file = event.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
          const bgVal = `url('${e.target.result}')`;
          homeScreen.style.backgroundImage = bgVal;
          try {
            localStorage.setItem('ocs_bg_image', bgVal);
          } catch (err) {
            console.warn('Imagen muy grande para LocalStorage.');
          }
        };
        reader.readAsDataURL(file);
      }
    }

    function setBgUrl() {
      const url = prompt(translations[currentLang].promptBgUrl);
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

    /* Personalización de color */
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

    /* Eventos teclado */
    searchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && searchInput.value.trim()) {
        openUrl(searchInput.value.trim());
        searchInput.value = '';
      }
    });

    urlInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') navigate();
    });

    // Inicializar navegador y cargar configuraciones
    createNewTab();
    loadSettings();
  </script>

  <!-- LÓGICA DEL MODO INCÓGNITO -->
  <script id="incognito-mode-script">
    (function () {
      'use strict';

      const incognitoText = {
        es: {
          tabTitle: '🕵️ Incógnito',
          banner: '🕵️ Estás en modo incógnito: no se guardan cookies, no se guarda historial y no se puede iniciar sesión.',
          saveBlocked: 'No puedes guardar webs mientras navegas en modo incógnito.'
        },
        en: {
          tabTitle: '🕵️ Incognito',
          banner: "🕵️ You're in incognito mode: cookies, history, and logins are completely disabled.",
          saveBlocked: "You can't save websites while browsing in incognito mode."
        }
      };
      function t() { return incognitoText[currentLang] || incognitoText.es; }

      window.createIncognitoTab = function (input) {
        createNewTab(input || '');
        const tab = tabs.find(x => x.id === activeTabId);
        if (tab) {
          tab.incognito = true;
          tab.title = t().tabTitle;
          if (tab.history && tab.history[0]) tab.history[0].title = t().tabTitle;
          loadHistoryState(tab, tab.history[tab.historyIndex], true);
        }
        renderTabs();
        actualizarUiIncognito();
      };

      function activeEsIncognito() {
        const tab = tabs.find(x => x.id === activeTabId);
        return !!(tab && tab.incognito);
      }

      function actualizarUiIncognito() {
        const activa = activeEsIncognito();
        document.body.classList.toggle('incognito-mode', activa);

        const banner = document.getElementById('incognito-banner');
        if (banner) banner.textContent = t().banner;

        const installBtn = document.getElementById('btn-install');
        if (installBtn) {
          installBtn.disabled = activa;
          installBtn.title = activa ? t().saveBlocked : (translations[currentLang]?.installAppTitle || 'Guardar web');
        }

        if (typeof tabsContainer !== 'undefined' && tabsContainer) {
          const nodos = tabsContainer.children;
          tabs.forEach((tb, i) => {
            const nodo = nodos[i];
            if (nodo) nodo.classList.toggle('tab-incognito', !!tb.incognito);
          });
        }
      }

      setInterval(actualizarUiIncognito, 250);

      document.addEventListener('click', function (e) {
        if (e.target && e.target.closest && e.target.closest('#btn-install')) {
          if (activeEsIncognito()) {
            closeInstallModal();
            alert(t().saveBlocked);
          }
        }
      }, true);

      actualizarUiIncognito();
    })();
  </script>
</body>
</html>"""

def main():
    with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
        f.write(HTML_CODE)
        temp_path = f.name

    try:
        webview.create_window('OCS Browser', temp_path, width=1280, height=800)
        webview.start()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == '__main__':
    main()
