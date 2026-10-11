<div align="center">

#  OCS Browser

### Navegador ultraligero, seguro y sin publicidad

> AVISO: OCS Browser esta pensado para tener un navegador extra en tu PC por si en el tuyo valla

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-blue?style=for-the-badge)](https://github.com/David4524-maker)
[![Version](https://img.shields.io/badge/Version-1.5-orange?style=for-the-badge)](https://github.com/David4524-maker)

**Web GUI + Terminal CLI · AdBlock · Anti-Tracker · Anti-Phishing · Modo Incógnito · 4 idiomas**

[Características](#-características) ·
[Instalación](#-instalación) ·
[Uso](#-uso) ·
[Capturas](#-capturas) ·
[Contribuir](#-contribuir)

</div>

---

##  ¿Qué es OCS Browser?

**OCS Browser** es un navegador **ultraligero** desarrollado en **Python** que combina dos interfaces complementarias:

-  **Versión GUI** — ventana nativa con pestañas, basada en `pywebview`
-  **Versión CLI** — terminal con comandos tipo `osc://` y colores ANSI
-  **Version Web** — el OSC Browser normal hasta ahora

Ambas comparten un **proxy interno** que filtra publicidad y rastreadores, además de un motor de búsqueda propio llamado **[OSC Search](https://david4524-maker.github.io/OSC-Search/)** enfocado en contenido libre de derechos.

>  Diseñado para ser ligero, seguro y funcional sin depender de Chromium ni de instalaciones pesadas.

---

##  Características

###  Seguridad y privacidad
- **Bloqueador de Anuncios (AdBlock)** — Filtra dominios publicitarios conocidos (`doubleclick`, `googlesyndication`, ads de YouTube, etc.)
- **Anti-Rastreadores** — Bloquea Google Analytics, Facebook Pixel, Hotjar y otros servicios de tracking
- **Escudo Anti-Phishing** — Bloquea dominios maliciosos y descargas de ejecutables peligrosos (`.exe`, `.bat`, `.ps1`, `.msi`…)
- **Advertencia HTTP** — Avisa cuando navegas por sitios sin cifrado HTTPS
- **Modo Incógnito** — Sin cookies, sin historial, sin login, sin guardar webs
- **PIN de control parental** — Bloquea el acceso a la configuración y a la eliminación de webs guardadas

###  Interfaz web (GUI)
- **Multi-pestaña** — Abre varias webs a la vez con títulos personalizables
- **Pantalla de inicio** con buscador integrado
- **Fondo personalizable** — Sube una imagen desde tu PC o pégala desde una URL
- **Temas de color** — 5 presets (Azul, Morado, Verde Matrix, Rojo, Oscuro) + colores personalizados
- **Webs guardadas** — Guarda tus sitios favoritos como apps
- **Centro de Seguridad** — Panel con contadores de elementos bloqueados en tiempo real

###  Interfaz CLI
- **Prompt tipo navegador** — `osc://inicio>`
- **Banner ASCII gigante** en azul (OSC), verde (BROWSER) y blanco (CLI)
- **Lenguaje natural** — Escribe `Motor: Chrome` o `Navegador: Firefox`
- **Atajos tipo URL** — `<url https://youtube.com>` para abrir directo
- **Comandos disponibles** — `:help`, `:search`, `:save`, `:history`, `:test`, etc.
- **Render de HTML** — Convierte el HTML a texto legible en la terminal

###  Multi-idioma
Interfaz completamente traducible:
- 🇪🇸 Español
- 🇬🇧 English
- 🇵🇹 Português
- 🇫🇷 Français

Cambia de idioma **en caliente** — toda la interfaz (pestañas, modales, juegos, banners) se traduce al instante.

###  Extras
- **Minijuego Parkour** — Cuando una web se bloquea, ¡se abre un juego!
- **OSC Search** — Motor de búsqueda propio enfocado en contenido libre
- **Persistencia** — Todos los ajustes se guardan en `localStorage` / `~/.ocs_browser_cli.json`

---

##  Instalación

### Requisitos

- **Python 3.10+** (compatible con 3.14)
- **pip** (viene incluido con Python)
- **Sistema operativo**: Windows 10/11 · macOS 12+ · Linux (cualquier distro moderna)

###  Clonar el repositorio

```bash
git clone https://github.com/David4524-maker/OSC-Browser.git
cd OSC-Browser
```

## Otras alternativas

[Chrome](https://www.google.com/intl/es-419/chrome/) - El come RAM

[Edge](https://explore.microsoft.com/es-es/edge?form=MA13FJ&cs=176861153) - El insistor que lleva en los ojos de Windows

[Firefox](https://www.firefox.com/es-MX/) - El independiente que lleva en versiones de Linux

[Brave](https://www.brave.com) - El chad

[DuckDuckGo](https://duckduckgo.com/) - El Bloqueador
