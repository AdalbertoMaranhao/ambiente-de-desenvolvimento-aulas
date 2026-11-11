#!/usr/bin/env python3
"""Prepara os kits de desenvolvimento portáteis (Web, POO Python, POO Java) para Windows e Linux."""
import argparse
import concurrent.futures
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
CACHE = BASE / "preparacao" / "downloads"
CAT = BASE / "preparacao" / "catalogos"
LOCK = BASE / "componentes.lock.json"
DIST = BASE / "dist"
DEFERRED_LINKS = []

PEDAGOGICAL_EXTENSIONS = [
    "usernamehw.errorlens",
    "oderwat.indent-rainbow",
    "aaron-bond.better-comments",
    "christian-kohler.path-intellisense",
    "formulahendry.auto-rename-tag",
    "MS-CEINTL.vscode-language-pack-pt-BR"
]

ALL_KNOWN_EXTENSIONS = [
    "redhat.java",
    "vscjava.vscode-java-debug",
    "bmewburn.vscode-intelephense-client",
    *PEDAGOGICAL_EXTENSIONS
]

PROFILES = {
    "web": {
        "title": "Desenvolvimento Web (PHP 8.5)",
        "launcher_name": "Web",
        "project_folder": "web",
        "has_php": True,
        "has_composer": True,
        "has_python": True,
        "has_python_dev": False,
        "has_java": False,
        "extensions": [
            "bmewburn.vscode-intelephense-client",
            *PEDAGOGICAL_EXTENSIONS
        ]
    },
    "poo-java": {
        "title": "POO com Java (Adoptium JDK 25)",
        "launcher_name": "Java",
        "project_folder": "java",
        "has_php": False,
        "has_composer": False,
        "has_python": True,
        "has_python_dev": False,
        "has_java": True,
        "extensions": [
            "redhat.java",
            "vscjava.vscode-java-debug",
            *PEDAGOGICAL_EXTENSIONS
        ]
    }
}

OS_TARGETS = {
    "windows": "windows-x64",
    "linux": "linux-x64"
}


def to_long_path(path):
    if sys.platform != "win32":
        return path
    s = os.path.abspath(str(path))
    if s.startswith("\\\\?\\"):
        return Path(s)
    if s.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)


def clean_path_str(path):
    s = str(path)
    return s.removeprefix("\\\\?\\UNC\\").removeprefix("\\\\?\\")


class ProgressBar:
    """Barra de progresso sem dependências externas, compatível com UTF-8 e ASCII."""
    def __init__(self, total, title="Progresso", width=25):
        self.total = max(1, total)
        self.current = 0
        self.title = title
        self.width = width
        self.lock = threading.Lock()
        self.is_tty = sys.stdout.isatty()
        self.unicode = True
        try:
            "█░".encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            self.unicode = False

    def update(self, step=1, detail=""):
        with self.lock:
            self.current = min(self.total, self.current + step)
            self._render(detail)

    def set_current(self, current, detail=""):
        with self.lock:
            self.current = min(self.total, current)
            self._render(detail)

    def _render(self, detail=""):
        fraction = self.current / self.total
        percent = int(fraction * 100)
        filled = int(fraction * self.width)
        empty = self.width - filled

        fill_char = "█" if self.unicode else "="
        empty_char = "░" if self.unicode else "-"
        bar = fill_char * filled + empty_char * empty

        detail_str = f" - {detail}" if detail else ""
        line = f"\r{self.title} [{bar}] {self.current}/{self.total} ({percent:3d}%){detail_str}"

        try:
            term_cols = shutil.get_terminal_size((80, 24)).columns
            if len(line) > term_cols - 1:
                line = line[:term_cols - 4] + "..."
        except Exception:
            pass

        if self.is_tty:
            sys.stdout.write(line + "\033[K")
            sys.stdout.flush()
        else:
            if self.current == self.total or percent % 20 == 0:
                sys.stdout.write(f"{self.title} [{bar}] {self.current}/{self.total} ({percent}%){detail_str}\n")
                sys.stdout.flush()

    def finish(self, message=""):
        with self.lock:
            self.current = self.total
            self._render(message)
            sys.stdout.write("\n")
            sys.stdout.flush()


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_replace(src, dst, max_retries=10, delay=0.5):
    """Substitui o arquivo de destino tratando locks transitórios de antivírus/indexador no Windows."""
    src = to_long_path(src)
    dst = to_long_path(dst)
    for attempt in range(max_retries):
        try:
            if sys.platform == "win32" and dst.exists():
                try:
                    dst.unlink()
                except OSError:
                    pass
            src.replace(dst)
            return
        except OSError:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)


def _download_urllib(url, part_path, post=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityPreparador/1.0"
    }
    data = None
    if post is not None:
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json;api-version=7.2-preview.1"
        data = json.dumps(post).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers)
    ctx = None
    try:
        ctx = ssl.create_default_context()
    except Exception:
        pass

    with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
        with open(part_path, "wb") as f:
            shutil.copyfileobj(response, f, length=1024 * 1024)


def fetch(url, path, post=None):
    path = to_long_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")

    urls = [url]
    if "windows.php.net/downloads/releases/" in url and "/archives/" not in url:
        urls.append(url.replace("/downloads/releases/", "/downloads/releases/archives/"))

    last_error = None
    for candidate_url in urls:
        # 1. Tentar via curl se disponível
        curl_bin = shutil.which("curl")
        if curl_bin:
            clean_part = clean_path_str(part)
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass

            args = [
                curl_bin,
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--retry", "5",
                "--retry-delay", "2",
                "--connect-timeout", "30",
                "--max-time", "1800",
                "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityPreparador/1.0",
            ]
            if sys.platform == "win32":
                args.append("--ssl-revoke-best-effort")

            args.extend([candidate_url, "-o", clean_part])

            if post is not None:
                args.extend([
                    "-H", "Content-Type: application/json",
                    "-H", "Accept: application/json;api-version=7.2-preview.1",
                    "--data", json.dumps(post)
                ])

            try:
                res = subprocess.run(args, capture_output=True, text=True)
                if res.returncode == 0 and part.exists() and part.stat().st_size > 0:
                    safe_replace(part, path)
                    return path
                else:
                    last_error = RuntimeError(f"curl falhou ({res.returncode}): {res.stderr.strip() or res.stdout.strip()}")
            except Exception as e:
                last_error = e

        # 2. Fallback para urllib
        try:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            _download_urllib(candidate_url, part, post)
            if part.exists() and part.stat().st_size > 0:
                safe_replace(part, path)
                return path
        except Exception as e:
            last_error = e

    raise RuntimeError(f"Falha ao baixar {url} para {path}: {last_error}")


def metadata(name, url, post=None):
    path = CAT / (name + ".json")
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    fetch(url, path, post)
    return json.loads(path.read_text(encoding="utf-8"))


def resolve():
    items = []

    def add(name, version, url, target, kind, sha=None, prefix=""):
        items.append(dict(name=name, version=version, url=url.replace("http://", "https://", 1),
                          target=target, kind=kind, sha256=sha, prefix=prefix))

    py = metadata("python", "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest")
    for platform, triple in [("windows-x64", "x86_64-pc-windows-msvc"),
                             ("linux-x64", "x86_64-unknown-linux-gnu")]:
        asset = next(a for a in py["assets"] if a["name"].startswith("cpython-3.13.")
                     and a["name"].endswith(triple + "-install_only_stripped.tar.gz"))
        add("python-" + platform, asset["name"].split("+")[0], asset["browser_download_url"],
            "tools/" + platform + "/python", "tar", (asset.get("digest") or "").removeprefix("sha256:") or None, "python/")
        osname = "windows" if platform.startswith("windows") else "linux"
        jdk = metadata("jdk25-" + osname, "https://api.adoptium.net/v3/assets/latest/25/hotspot?architecture=x64&image_type=jdk&os=" + osname)[0]
        pkg = jdk["binary"]["package"]
        add("jdk-" + platform, jdk["version"]["semver"], pkg["link"], "tools/" + platform + "/jdk",
            "zip-root" if osname == "windows" else "tar-root", pkg["checksum"])

    php = metadata("phpwin", "https://windows.php.net/downloads/releases/releases.json")["8.5"]
    pkg = next(v["zip"] for k, v in php.items() if k.startswith("nts-") and k.endswith("-x64"))
    add("php-windows-x64", php["version"], "https://windows.php.net/downloads/releases/" + pkg["path"], "tools/windows-x64/php", "zip", pkg["sha256"])
    fp = metadata("frankenphp", "https://api.github.com/repos/php/frankenphp/releases/latest")
    a = next(a for a in fp["assets"] if a["name"] == "frankenphp-linux-x86_64")
    add("php-linux-x64", fp["tag_name"], a["browser_download_url"], "tools/linux-x64/php/frankenphp", "file", a["digest"].split(":")[1])
    add("frankenphp-license", fp["tag_name"], "https://raw.githubusercontent.com/php/frankenphp/" + fp["tag_name"] + "/LICENSE", "tools/linux-x64/php/LICENSE.txt", "file")

    git = metadata("git", "https://api.github.com/repos/git-for-windows/git/releases/latest")
    a = next(a for a in git["assets"] if re.match(r"MinGit-[\d.]+-64-bit.zip$", a["name"]))
    add("git-windows-x64", git["tag_name"], a["browser_download_url"], "tools/windows-x64/git", "zip", (a.get("digest") or "").removeprefix("sha256:") or None)

    packages = {}
    for label, suite in [("ubuntubase", "jammy"), ("ubuntu", "jammy-updates")]:
        index = CAT / (label + ".xz")
        if not index.exists():
            fetch("https://archive.ubuntu.com/ubuntu/dists/" + suite + "/main/binary-amd64/Packages.xz", index)
        for paragraph in lzma.decompress(index.read_bytes()).decode().split("\n\n"):
            fields = dict(line.split(": ", 1) for line in paragraph.splitlines() if ": " in line and not line.startswith(" "))
            if "Package" in fields and "Filename" in fields:
                packages[fields["Package"]] = fields
    queue = ["base-files", "git", "libncurses6", "libtinfo6", "libssl3", "libsystemd0", "libcrypt1", "libstdc++6", "libgcc-s1"]
    skip = {"libc6", "perl", "perl-base", "git-man", "debconf", "debconf-2.0", "dpkg", "tar"}
    seen = set(skip)
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        pkg = packages.get(name)
        if pkg is None:
            raise RuntimeError("Dependencia Ubuntu sem pacote: " + name)
        add("linux-deb-" + name, pkg["Version"], "https://archive.ubuntu.com/ubuntu/" + pkg["Filename"],
            "tools/linux-x64/sysroot" + ("/usr/share/common-licenses" if name == "base-files" else ""), "deb", pkg["SHA256"],
            "usr/share/common-licenses/" if name == "base-files" else "")
        if name == "base-files":
            continue
        for group in (pkg.get("Depends", "") + "," + pkg.get("Pre-Depends", "")).split(","):
            options = [re.split(r"[\s(:]", s.strip())[0] for s in group.split("|") if s.strip()]
            if options:
                queue.append(next((s for s in options if s in packages or s in skip), options[0]))

    comp = metadata("composer", "https://getcomposer.org/versions")["stable"][0]
    checksum = CAT / "composer.sha256"
    if not checksum.exists():
        fetch("https://getcomposer.org" + comp["path"] + ".sha256sum", checksum)
    add("composer", comp["version"], "https://getcomposer.org" + comp["path"], "dependencias/composer/composer.phar", "file", checksum.read_text().split()[0])

    extensions = ALL_KNOWN_EXTENSIONS
    for ext in extensions:
        data = metadata("ext-" + ext, "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery",
                        {"filters": [{"criteria": [{"filterType": 7, "value": ext}]}], "flags": 147})
        versions = data["results"][0]["extensions"][0]["versions"]
        for platform in ["windows-x64", "linux-x64"]:
            target = "win32-x64" if platform.startswith("windows") else "linux-x64"
            choices = [v for v in versions if not any(p["key"] == "Microsoft.VisualStudio.Code.PreRelease" and p["value"] == "true" for p in v.get("properties", []))]
            v = next((v for v in choices if v.get("targetPlatform") == (None if ext not in ("redhat.java", "vscjava.vscode-java-debug") else target)), None)
            if v is None:
                v = next(v for v in choices if not v.get("targetPlatform"))
            url = next(f["source"] for f in v["files"] if f["assetType"] == "Microsoft.VisualStudio.Services.VSIXPackage")
            add(ext + "-" + platform, v["version"], url,
                "tools/" + platform + "/extensions/" + ext + "-" + v["version"], "vsix", prefix="extension/")
    LOCK.write_text(json.dumps({"components": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return items


def acquire(item, verbose=False):
    extension = {"zip": ".zip", "zip-root": ".zip", "tar": ".tar.gz", "tar-root": ".tar.gz", "deb": ".deb", "vsix": ".vsix"}.get(item["kind"], ".bin")
    path = CACHE / (item["name"] + extension)
    if not path.exists() and (CACHE / (item["name"] + ".jar")).exists():
        path = CACHE / (item["name"] + ".jar")
    if not path.exists():
        if verbose:
            print("Baixando " + item["name"], flush=True)
        fetch(item["url"], path)
    actual = digest(path)
    if item.get("sha256") and item["sha256"] != actual:
        sys.stderr.write(
            f"\n⚠️  SHA256 incorreto para {path.name} (esperado: {item['sha256'][:8]}..., obtido: {actual[:8]}...). "
            f"Arquivo local corrompido ou incompleto. Baixando novamente...\n"
        )
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        fetch(item["url"], path)
        actual = digest(path)
        if item.get("sha256") and item["sha256"] != actual:
            raise RuntimeError(
                f"SHA256 incorreto para {path.name} após novo download. "
                f"Esperado: {item['sha256']}, obtido: {actual}. Remova este arquivo e tente novamente."
            )
    item["hash_origin"] = item.get("hash_origin") or ("upstream" if item.get("sha256") else "HTTPS-primeiro-download")
    item["sha256"] = actual
    return path


def safe_name(name):
    name = name.replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if name.startswith("/") or any(p == ".." or ":" in p for p in parts):
        raise RuntimeError("Caminho inseguro em arquivo: " + name)
    return "/".join(parts)


def unpack(path, target, kind, prefix=""):
    target = to_long_path(target)
    target.mkdir(parents=True, exist_ok=True)
    if kind in ("zip", "zip-root", "vsix"):
        with zipfile.ZipFile(path) as archive:
            names = [safe_name(x.filename) for x in archive.infolist() if safe_name(x.filename)]
            if kind == "zip-root":
                roots = {n.split("/")[0] for n in names}
                if len(roots) != 1:
                    raise RuntimeError("ZIP sem pasta raiz unica: " + str(path))
                prefix = next(iter(roots)) + "/"
            for info in archive.infolist():
                name = safe_name(info.filename)
                if prefix and not name.startswith(prefix):
                    continue
                name = name[len(prefix):] if prefix else name
                if not name:
                    continue
                out = to_long_path(target / name)
                if info.is_dir():
                    out.mkdir(parents=True, exist_ok=True)
                else:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as src, out.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    try:
                        out.chmod(((info.external_attr >> 16) & 0o777) or 0o644)
                    except OSError:
                        pass
        return
    if kind == "deb":
        with open(path, "rb") as f:
            if f.read(8) != b"!<arch>\n":
                raise RuntimeError("DEB invalido")
            while header := f.read(60):
                size = int(header[48:58].strip())
                data = f.read(size)
                if size % 2:
                    f.read(1)
                if header[:16].decode().strip().rstrip("/").startswith("data.tar"):
                    if data.startswith(b"\x28\xb5\x2f\xfd"):
                        if shutil.which("zstd"):
                            data = subprocess.run(["zstd", "-d", "--stdout"], input=data, capture_output=True, check=True).stdout
                        else:
                            try:
                                import zstandard
                            except ImportError:
                                raise RuntimeError("Preparacao de DEB requer zstd ou o modulo zstandard. No computador de preparo: python -m pip install zstandard")
                            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
                                data = reader.read()
                    return unpack_tar(io.BytesIO(data), target, prefix=prefix, deferred=DEFERRED_LINKS)
        raise RuntimeError("DEB sem data.tar")
    unpack_tar(path, target, kind == "tar-root", prefix)


def unpack_tar(path, target, strip_root=False, prefix="", deferred=None):
    with tarfile.open(fileobj=path if hasattr(path, "read") else None,
                      name=None if hasattr(path, "read") else str(path), mode="r:*") as archive:
        members = [m for m in archive.getmembers() if not m.name.removeprefix("./").startswith("usr/share/man/")]
        names = [safe_name(m.name) for m in members if safe_name(m.name)]
        if strip_root:
            roots = {n.split("/")[0] for n in names}
            if len(roots) != 1:
                raise RuntimeError("TAR sem pasta raiz unica")
            prefix = next(iter(roots)) + "/"
        links = []
        for member in members:
            name = safe_name(member.name)
            if prefix and not name.startswith(prefix):
                continue
            name = name[len(prefix):] if prefix else name
            if not name:
                continue
            out = target / name
            if member.isdir():
                out.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                out.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, out.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                out.chmod(member.mode & 0o777)
            elif member.issym() or member.islnk():
                link = member.linkname
                if os.path.isabs(link):
                    raise RuntimeError("Link absoluto no TAR: " + link)
                source = out.parent / link if member.issym() else target / safe_name(link.removeprefix(prefix))
                if not source.resolve().is_relative_to(target.resolve()):
                    raise RuntimeError("Link fora do componente: " + link)
                links.append((out, source.resolve()))
        materialize_links(links, deferred)


def materialize_links(links, deferred=None):
    for _ in range(len(links) + 1):
        pending = []
        for out, source in links:
            if source.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                if not out.exists() or not os.path.samefile(source, out):
                    shutil.copy2(source, out)
            elif source.is_dir():
                if not out.exists() or not os.path.samefile(source, out):
                    shutil.copytree(source, out, dirs_exist_ok=True)
            else:
                pending.append((out, source))
        if not pending:
            return
        if pending == links:
            if deferred is not None:
                deferred.extend(pending)
                return
            raise RuntimeError("Links sem destino: " + str(pending[:3]))
        links = pending


def filter_items_for_profile(items, perfil, osname):
    cfg = PROFILES[perfil]
    selected = []
    for item in items:
        name = item["name"]
        if name.startswith("vscode-") and not name.endswith(osname):
            continue
        if name.startswith("git-") and not name.endswith(osname):
            continue
        if name.startswith("linux-deb-") and osname != "linux-x64":
            continue
        if name.startswith("python-") and not name.endswith(osname):
            continue
        if name.startswith("php-"):
            if not cfg["has_php"] or not name.endswith(osname):
                continue
        if name == "frankenphp-license":
            if not cfg["has_php"] or osname != "linux-x64":
                continue
        if name == "composer" and not cfg["has_composer"]:
            continue
        if name.startswith("jdk-"):
            if not cfg["has_java"] or not name.endswith(osname):
                continue

        # Filtragem de extensoes
        is_extension = any(name.startswith(ext + "-") for ext in ALL_KNOWN_EXTENSIONS)
        if is_extension:
            if not any(name.startswith(ext + "-") and name.endswith(osname) for ext in cfg["extensions"]):
                continue

        selected.append(item)
    return selected


def get_needed_items(items, target_profiles, target_sos):
    needed_names = set()
    for p in target_profiles:
        for s in target_sos:
            for item in filter_items_for_profile(items, p, OS_TARGETS[s]):
                needed_names.add(item["name"])
    return [item for item in items if item["name"] in needed_names]


def setup_linux_executables(tools_dir, kit_dir):
    """Garante permissões de execução nos binários e scripts Linux e gera o manifesto linux-executaveis.json."""
    known_execs = {
        "code", "code-tunnel", "chrome-sandbox", "chrome_crashpad_handler",
        "python", "python3", "frankenphp", "git", "pip", "lab", "composer", "php"
    }
    executables = []
    for path in tools_dir.rglob("*"):
        if not path.is_file():
            continue
        is_exec = False
        magic = b""
        try:
            with path.open("rb") as f:
                magic = f.read(4)
        except OSError:
            pass

        if magic.startswith(b"\x7fELF") or magic.startswith(b"#!"):
            is_exec = True
        elif path.name in known_execs or path.parent.name in ("bin", "git-core"):
            is_exec = True
        elif hasattr(path.stat(), "st_mode") and (path.stat().st_mode & 0o111):
            is_exec = True

        if is_exec:
            if sys.platform != "win32":
                try:
                    path.chmod(path.stat().st_mode | 0o755)
                except OSError:
                    pass
            executables.append(str(path.relative_to(kit_dir)))

    executables.sort()
    manifest_data = json.dumps(executables, indent=2) + "\n"
    (tools_dir / "linux-executaveis.json").write_text(manifest_data, encoding="utf-8")
    (kit_dir / "linux-executaveis.json").write_text(manifest_data, encoding="utf-8")


def resolve_kit_target(item: dict, kit_dir: Path) -> Path:
    """Resolve o caminho de destino no kit, unificando extensões compartilhadas."""
    target_rel = item["target"]
    if item.get("kind") == "vsix" and "extensions/" in target_rel:
        ext_folder = target_rel.split("extensions/", 1)[1]
        target_rel = f"tools/extensions/{ext_folder}"
    return to_long_path(kit_dir / target_rel)


def prune_kit_dead_weight(kit_dir: Path) -> None:
    """Remove arquivos legados, documentações e resíduos não utilizados para acelerar a transferência para pendrive."""
    # 1. Poda de terminfo e man no Python do Linux (~2.850 arquivos)
    terminfo_dir = kit_dir / "tools" / "linux-x64" / "python" / "share" / "terminfo"
    if terminfo_dir.exists():
        shutil.rmtree(terminfo_dir, ignore_errors=True)
    man_dir = kit_dir / "tools" / "linux-x64" / "python" / "share" / "man"
    if man_dir.exists():
        shutil.rmtree(man_dir, ignore_errors=True)

    # 2. Poda de Tcl/Tk no Python do Windows (~1.270 arquivos)
    tcl_dir = kit_dir / "tools" / "windows-x64" / "python" / "tcl"
    if tcl_dir.exists():
        shutil.rmtree(tcl_dir, ignore_errors=True)

    # 3. Poda de cabeçalhos C (.h) nos runtimes Python (~528 arquivos)
    for os_dir in ["windows-x64", "linux-x64"]:
        inc_dir = kit_dir / "tools" / os_dir / "python" / "include"
        if inc_dir.exists():
            shutil.rmtree(inc_dir, ignore_errors=True)

    # 4. Poda de documentação em pacotes debian extraídos (~666 arquivos)
    doc_dir = kit_dir / "tools" / "linux-x64" / "sysroot" / "usr" / "share" / "doc"
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)


def assemble_universal_kit(perfil, items, item_paths):
    cfg = PROFILES[perfil]
    kit_name = f"kit-{perfil}"
    kit_dir = to_long_path(DIST / kit_name)
    print(f"\n========================================================")
    print(f"📦 Montando Kit Universal: {kit_name} ({cfg['title']})")
    print(f"   Compatível com Windows 11 e Linux Mint x64 no mesmo pendrive")
    print(f"========================================================")
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "PREPARACAO.json").unlink(missing_ok=True)
    DEFERRED_LINKS.clear()

    # Itens para ambos os SOs
    selected_items = []
    for os_key, osname in OS_TARGETS.items():
        selected_items.extend(filter_items_for_profile(items, perfil, osname))

    paths_dict = item_paths if isinstance(item_paths, dict) else {item["name"]: path for item, path in zip(items, item_paths)}

    bar = ProgressBar(len(selected_items), title=f"📦 {kit_name}")
    bar.set_current(0, "Iniciando...")

    for idx, item in enumerate(selected_items, 1):
        bar.set_current(idx - 1, f"Extraindo {item['name']}")
        path = paths_dict.get(item["name"])
        if path is None:
            path = acquire(item)
        target = resolve_kit_target(item, kit_dir)
        marker = to_long_path(kit_dir / ".preparacao" / (item["name"] + ".sha256"))
        if item["kind"] != "deb" and marker.exists() and marker.read_text() == item["sha256"] and target.exists():
            bar.set_current(idx, f"Cache {item['name']}")
            continue
        if item["kind"] == "vsix" and target.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(item["sha256"])
            bar.set_current(idx, f"Compartilhada {item['name']}")
            continue
        if item["kind"] == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            unpack(path, target, item["kind"], item.get("prefix", ""))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(item["sha256"])
        bar.set_current(idx, f"OK {item['name']}")

    bar.finish("Extração concluída!")
    materialize_links(DEFERRED_LINKS)
    prune_kit_dead_weight(kit_dir)

    # Copiar scripts de controle base
    shutil.copy2(BASE / "kit" / "lab.py", kit_dir / "lab.py")
    for extra_mod in ["aluno.py", "extensoes.py", "sincronizacao.py"]:
        if (BASE / "kit" / extra_mod).exists():
            shutil.copy2(BASE / "kit" / extra_mod, kit_dir / extra_mod)
    shutil.copy2(BASE / "kit" / "BEM-VINDO.html", kit_dir / "BEM-VINDO.html")
    shutil.copy2(BASE / "kit" / "LEIA-ME.html", kit_dir / "LEIA-ME.html")
    shutil.copy2(BASE / "kit" / "iniciar-windows.cmd", kit_dir / "iniciar-windows.cmd")
    shutil.copy2(BASE / "kit" / "iniciar-linux.sh", kit_dir / "iniciar-linux.sh")
    (kit_dir / "iniciar-linux.sh").chmod(0o755)
    shutil.copy2(BASE / "kit" / "laboratorio.desktop", kit_dir / "laboratorio.desktop")

    # Garante pasta de alunos no pendrive
    (kit_dir / "alunos").mkdir(parents=True, exist_ok=True)

    # Atalhos raiz com o nome específico da disciplina
    launcher_name = cfg.get("launcher_name", "Laboratorio")
    cmd_launcher = kit_dir / f"Iniciar {launcher_name}.cmd"
    cmd_launcher.write_bytes(f'@echo off\r\ncall "%~dp0iniciar-windows.cmd" %*\r\n'.encode())

    desktop_launcher = kit_dir / f"Iniciar {launcher_name}.desktop"
    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Iniciar {cfg['title']}
Comment=Abrir laboratório portátil de {cfg['title']}
Exec=sh -c '"$(dirname "$1")"/iniciar-linux.sh' dummy %k
Icon=utilities-terminal
Terminal=true
Categories=Education;Development;
StartupNotify=false
"""
    desktop_launcher.write_text(desktop_content, encoding="utf-8")
    desktop_launcher.chmod(0o755)

    # Diagnóstico
    shutil.copytree(BASE / "diagnostico", kit_dir / "diagnostico", dirs_exist_ok=True)

    # Projetos da disciplina (com o banco.db seed)
    proj_folder = cfg["project_folder"]
    src_proj = BASE / "kit" / "projetos" / proj_folder
    dest_proj = kit_dir / "projetos" / proj_folder
    if src_proj.exists():
        shutil.copytree(src_proj, dest_proj, dirs_exist_ok=True)
    else:
        dest_proj.mkdir(parents=True, exist_ok=True)

    (kit_dir / "aulas.code-workspace").unlink(missing_ok=True)

    # Arquivo .hidden para o Linux Mint (ocultar pastas/arquivos de infraestrutura no gerenciador de arquivos)
    hidden_entries = [
        "configuracoes",
        "tools",
        "dependencias",
        "diagnostico",
        "lab.py",
        "componentes.lock.json",
        "PREPARACAO.json",
        "linux-executaveis.json",
        "laboratorio.desktop",
        ".preparacao"
    ]
    (kit_dir / ".hidden").write_text("\n".join(hidden_entries) + "\n", encoding="utf-8")

    (kit_dir / "tools" / "extensions").mkdir(parents=True, exist_ok=True)
    # Configuração de executáveis e wrappers para Windows e Linux
    for os_key, osname in OS_TARGETS.items():
        tools = kit_dir / "tools" / osname
        bindir = tools / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        (tools / "extensions").mkdir(parents=True, exist_ok=True)

        if os_key == "windows":
            # Copiar DLLs VC runtime (vcruntime140) de Python para PHP se PHP existir
            if (tools / "php").exists() and (tools / "python").exists():
                for source in (tools / "python").glob("*140*.dll"):
                    shutil.copy2(source, tools / "php" / source.name)

            commands = {
                "python": '"%~dp0..\\python\\python.exe" %*',
                "python3": '"%~dp0..\\python\\python.exe" %*',
                "lab": '"%~dp0..\\python\\python.exe" "%~dp0..\\..\\..\\lab.py" %*'
            }
            if cfg["has_php"]:
                commands["php"] = '"%~dp0..\\php\\php.exe" %*'
                commands["composer"] = '"%~dp0..\\php\\php.exe" "%~dp0..\\..\\..\\dependencias\\composer\\composer.phar" %*'
                php_ini = (
                    "[PHP]\n"
                    "date.timezone = America/Fortaleza\n"
                    "default_charset = UTF-8\n"
                    "display_errors = On\n"
                    "display_startup_errors = On\n"
                    "error_reporting = E_ALL\n"
                    "memory_limit = 256M\n\n"
                    "extension_dir = \"ext\"\n"
                    "extension = mbstring\n"
                    "extension = openssl\n"
                    "extension = curl\n"
                    "extension = fileinfo\n"
                    "extension = zip\n"
                )
                if (tools / "php").exists():
                    (tools / "php" / "php.ini").write_text(php_ini, encoding="utf-8")
            for name, cmd in commands.items():
                (bindir / (name + ".cmd")).write_bytes(("@echo off\r\n" + cmd + "\r\n").encode())
        else:
            commands = {
                "python": 'exec "$TASK_DIR/python/bin/python3" "$@"',
                "python3": 'exec "$TASK_DIR/python/bin/python3" "$@"',
                "lab": 'exec "$TASK_DIR/python/bin/python3" "$TASK_DIR/../../lab.py" "$@"',
                "git": 'export LD_LIBRARY_PATH="$TASK_DIR/sysroot/usr/lib/x86_64-linux-gnu:$TASK_DIR/sysroot/lib/x86_64-linux-gnu"\nexport GIT_EXEC_PATH="$TASK_DIR/sysroot/usr/lib/git-core"\nexport GIT_TEMPLATE_DIR="$TASK_DIR/sysroot/usr/share/git-core/templates"\nexec "$TASK_DIR/sysroot/usr/bin/git" "$@"'
            }
            if cfg["has_php"]:
                commands["php"] = 'exec "$TASK_DIR/php/frankenphp" php-cli "$@"'
                commands["composer"] = 'exec "$TASK_DIR/bin/php" "$TASK_DIR/../../dependencias/composer/composer.phar" "$@"'
                if (tools / "php/frankenphp").exists():
                    (tools / "php/frankenphp").chmod(0o755)
            for name, cmd in commands.items():
                out = bindir / name
                out.write_text('#!/bin/sh\nset -eu\nTASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\n' + cmd + '\n')
                out.chmod(0o755)

            setup_linux_executables(tools, kit_dir)

    # Pre-configuração compartilhada do VS Code
    shared_user_dir = kit_dir / "configuracoes" / "vscode" / "User"
    shared_user_dir.mkdir(parents=True, exist_ok=True)
    settings = {
        "update.mode": "none",
        "extensions.autoUpdate": False,
        "extensions.autoCheckUpdates": False,
        "telemetry.telemetryLevel": "off",
        "workbench.enableExperiments": False,
        "git.autofetch": False,
        "editor.inlineSuggest.enabled": False,
        "github.copilot.enable": {"*": False},
        "chat.commandCenter.enabled": False,
        "chat.disableAIFeatures": True,
        "editor.bracketPairColorization.enabled": True,
        "editor.guides.bracketPairs": "active",
        "editor.wordWrap": "on",
        "errorlens.enabled": True,
        "locale": "pt-br",
        "files.exclude": {
            "**/.git": True,
            "**/.svn": True,
            "**/.hg": True,
            "**/CVS": True,
            "**/.DS_Store": True,
            "**/Thumbs.db": True,
            "**/tools": True,
            "**/configuracoes": True,
            "**/dependencias": True,
            "**/diagnostico": True,
            "**/lab.py": True,
            "**/iniciar-windows.cmd": True,
            "**/iniciar-linux.sh": True,
            "**/componentes.lock.json": True,
            "**/PREPARACAO.json": True,
            "**/linux-executaveis.json": True,
            "**/laboratorio.desktop": True,
            "**/.preparacao": True,
            "**/.hidden": True
        }
    }
    if cfg["has_php"]:
        settings["intelephense.environment.phpVersion"] = "8.4"
    if cfg["has_java"]:
        settings["java.import.maven.enabled"] = False
        settings["java.import.gradle.enabled"] = False
        settings["java.autobuild.enabled"] = False
        settings["java.jdt.ls.vmargs"] = "-Xmx512m -Xms64m"

    settings_json_str = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    (shared_user_dir / "settings.json").write_text(settings_json_str, encoding="utf-8")

    argv_str = json.dumps({"locale": "pt-br"}, indent=2) + "\n"
    (kit_dir / "configuracoes" / "vscode" / "argv.json").write_text(argv_str, encoding="utf-8")

    # Copiar lock reduzido para auditoria
    (kit_dir / "componentes.lock.json").write_text(json.dumps({"components": selected_items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    size = sum(p.stat().st_size for p in kit_dir.rglob("*") if p.is_file())
    report = {
        "perfil": perfil,
        "tipo": "universal-dual-os",
        "sistemas": ["windows-x64", "linux-x64"],
        "bytes_extraidos": size,
        "gb_decimal": round(size / 1e9, 2),
        "limite_recomendado_bytes": 4_000_000_000
    }
    (kit_dir / "PREPARACAO.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"✅ Kit Universal '{kit_name}' montado com sucesso! Tamanho extraído: {size / 1e9:.2f} GB")


def zip_universal_kit(perfil):
    kit_name = f"kit-{perfil}"
    kit_dir = to_long_path(DIST / kit_name)
    if not (kit_dir / "PREPARACAO.json").exists():
        raise RuntimeError(f"O kit {kit_name} ainda não foi montado. Execute 'montar' primeiro.")

    print(f"\n📦 Compactando Kit Universal {kit_name}...", flush=True)
    files_to_pack = sorted(list(kit_dir.rglob("*")))
    total_files = len(files_to_pack)

    zip_path = DIST / f"{kit_name}.zip"
    bar = ProgressBar(total_files, title=f"🗜️ {kit_name}.zip")
    with zipfile.ZipFile(clean_path_str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, p in enumerate(files_to_pack, 1):
            rel_path = os.path.relpath(clean_path_str(p), clean_path_str(DIST))
            arcname = rel_path.replace("\\", "/")
            if p.is_dir():
                zinfo = zipfile.ZipInfo(arcname + "/")
                zf.writestr(zinfo, "")
            else:
                zf.write(clean_path_str(p), arcname)
            if idx % 25 == 0 or idx == total_files:
                bar.set_current(idx, p.name)
    bar.finish("Concluído!")
    output = str(zip_path)
    checksum = digest(output)
    Path(output + ".sha256").write_text(checksum + "  " + Path(output).name + "\n")
    size_mb = os.path.getsize(output) / (1024 * 1024)
    print(f"🎉 Pacote gerado: {Path(output).name} ({size_mb:.1f} MB) | SHA256: {checksum[:16]}...")


def assemble_single_kit(perfil, os_key, items, item_paths):
    osname = OS_TARGETS[os_key]
    cfg = PROFILES[perfil]
    kit_name = f"kit-{perfil}-{os_key}"
    kit_dir = to_long_path(DIST / kit_name)
    print(f"\n========================================================")
    print(f"📦 Montando {kit_name}: {cfg['title']} ({os_key.upper()})")
    print(f"========================================================")
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "PREPARACAO.json").unlink(missing_ok=True)
    DEFERRED_LINKS.clear()

    selected_items = filter_items_for_profile(items, perfil, osname)
    paths_dict = item_paths if isinstance(item_paths, dict) else {item["name"]: path for item, path in zip(items, item_paths)}

    bar = ProgressBar(len(selected_items), title=f"📦 {kit_name}")
    bar.set_current(0, "Iniciando...")

    for idx, item in enumerate(selected_items, 1):
        bar.set_current(idx - 1, f"Extraindo {item['name']}")
        path = paths_dict.get(item["name"])
        if path is None:
            path = acquire(item)
        target = resolve_kit_target(item, kit_dir)
        marker = to_long_path(kit_dir / ".preparacao" / (item["name"] + ".sha256"))
        if item["kind"] != "deb" and marker.exists() and marker.read_text() == item["sha256"] and target.exists():
            bar.set_current(idx, f"Cache {item['name']}")
            continue
        if item["kind"] == "vsix" and target.exists():
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(item["sha256"])
            bar.set_current(idx, f"Compartilhada {item['name']}")
            continue
        if item["kind"] == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            unpack(path, target, item["kind"], item.get("prefix", ""))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(item["sha256"])
        bar.set_current(idx, f"OK {item['name']}")

    bar.finish("Extração concluída!")

    materialize_links(DEFERRED_LINKS)
    prune_kit_dead_weight(kit_dir)

    # Copiar scripts de controle base
    shutil.copy2(BASE / "kit" / "lab.py", kit_dir / "lab.py")
    for extra_mod in ["aluno.py", "extensoes.py", "sincronizacao.py"]:
        if (BASE / "kit" / extra_mod).exists():
            shutil.copy2(BASE / "kit" / extra_mod, kit_dir / extra_mod)
    shutil.copy2(BASE / "kit" / "BEM-VINDO.html", kit_dir / "BEM-VINDO.html")
    shutil.copy2(BASE / "kit" / "LEIA-ME.html", kit_dir / "LEIA-ME.html")

    # Garante pasta de alunos no pendrive
    (kit_dir / "alunos").mkdir(parents=True, exist_ok=True)

    if os_key == "windows":
        shutil.copy2(BASE / "kit" / "iniciar-windows.cmd", kit_dir / "iniciar-windows.cmd")
    else:
        shutil.copy2(BASE / "kit" / "iniciar-linux.sh", kit_dir / "iniciar-linux.sh")
        (kit_dir / "iniciar-linux.sh").chmod(0o755)
        shutil.copy2(BASE / "kit" / "laboratorio.desktop", kit_dir / "laboratorio.desktop")

    # Diagnostico
    shutil.copytree(BASE / "diagnostico", kit_dir / "diagnostico", dirs_exist_ok=True)

    # Projetos da disciplina
    proj_folder = cfg["project_folder"]
    src_proj = BASE / "kit" / "projetos" / proj_folder
    dest_proj = kit_dir / "projetos" / proj_folder
    if src_proj.exists():
        shutil.copytree(src_proj, dest_proj, dirs_exist_ok=True)
    else:
        dest_proj.mkdir(parents=True, exist_ok=True)

    (kit_dir / "aulas.code-workspace").unlink(missing_ok=True)

    # Arquivo .hidden para o Linux Mint (ocultar pastas/arquivos de infraestrutura no gerenciador de arquivos)
    hidden_entries = [
        "configuracoes",
        "tools",
        "dependencias",
        "diagnostico",
        "lab.py",
        "componentes.lock.json",
        "PREPARACAO.json",
        "linux-executaveis.json",
        "laboratorio.desktop",
        ".preparacao"
    ]
    (kit_dir / ".hidden").write_text("\n".join(hidden_entries) + "\n", encoding="utf-8")

    # Configuracao de ferramentas e wrappers
    tools = kit_dir / "tools" / osname
    bindir = tools / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    (tools / "extensions").mkdir(parents=True, exist_ok=True)

    if os_key == "windows":
        # Copiar DLLs VC runtime de Python para PHP se PHP existir
        if (tools / "php").exists() and (tools / "python").exists():
            for source in (tools / "python").glob("*140*.dll"):
                shutil.copy2(source, tools / "php" / source.name)

        commands = {
            "python": '"%~dp0..\\python\\python.exe" %*',
            "python3": '"%~dp0..\\python\\python.exe" %*',
            "lab": '"%~dp0..\\python\\python.exe" "%~dp0..\\..\\..\\lab.py" %*'
        }
        if cfg["has_php"]:
            commands["php"] = '"%~dp0..\\php\\php.exe" %*'
            commands["composer"] = '"%~dp0..\\php\\php.exe" "%~dp0..\\..\\..\\dependencias\\composer\\composer.phar" %*'
            php_ini = (
                "[PHP]\n"
                "date.timezone = America/Fortaleza\n"
                "default_charset = UTF-8\n"
                "display_errors = On\n"
                "display_startup_errors = On\n"
                "error_reporting = E_ALL\n"
                "memory_limit = 256M\n\n"
                "extension_dir = \"ext\"\n"
                "extension = mbstring\n"
                "extension = openssl\n"
                "extension = curl\n"
                "extension = fileinfo\n"
                "extension = zip\n"
            )
            if (tools / "php").exists():
                (tools / "php" / "php.ini").write_text(php_ini, encoding="utf-8")

        for name, cmd in commands.items():
            (bindir / (name + ".cmd")).write_bytes(("@echo off\r\n" + cmd + "\r\n").encode())
    else:
        root = 'TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)\n'
        commands = {
            "python": 'exec "$TASK_DIR/python/bin/python3" "$@"',
            "python3": 'exec "$TASK_DIR/python/bin/python3" "$@"',
            "lab": 'exec "$TASK_DIR/python/bin/python3" "$TASK_DIR/../../lab.py" "$@"',
            "git": 'export LD_LIBRARY_PATH="$TASK_DIR/sysroot/usr/lib/x86_64-linux-gnu:$TASK_DIR/sysroot/lib/x86_64-linux-gnu"\nexport GIT_EXEC_PATH="$TASK_DIR/sysroot/usr/lib/git-core"\nexport GIT_TEMPLATE_DIR="$TASK_DIR/sysroot/usr/share/git-core/templates"\nexec "$TASK_DIR/sysroot/usr/bin/git" "$@"'
        }
        if cfg["has_php"]:
            commands["php"] = 'exec "$TASK_DIR/php/frankenphp" php-cli "$@"'
            commands["composer"] = 'exec "$TASK_DIR/bin/php" "$TASK_DIR/../../dependencias/composer/composer.phar" "$@"'
            if (tools / "php/frankenphp").exists():
                (tools / "php/frankenphp").chmod(0o755)

        for name, cmd in commands.items():
            out = bindir / name
            out.write_text("#!/bin/sh\n" + root + cmd + "\n")
            out.chmod(0o755)

        setup_linux_executables(tools, kit_dir)

    # Pre-configuracao do settings.json do VS Code
    shared_user_dir = kit_dir / "configuracoes" / "vscode" / "User"
    shared_user_dir.mkdir(parents=True, exist_ok=True)
    settings_file = shared_user_dir / "settings.json"
    settings = {
        "update.mode": "none",
        "extensions.autoUpdate": False,
        "extensions.autoCheckUpdates": False,
        "telemetry.telemetryLevel": "off",
        "workbench.enableExperiments": False,
        "git.autofetch": False,
        "editor.inlineSuggest.enabled": False,
        "github.copilot.enable": {"*": False},
        "chat.commandCenter.enabled": False,
        "chat.disableAIFeatures": True,
        "editor.bracketPairColorization.enabled": True,
        "editor.guides.bracketPairs": "active",
        "editor.wordWrap": "on",
        "errorlens.enabled": True,
        "locale": "pt-br",
        "files.exclude": {
            "**/.git": True,
            "**/.svn": True,
            "**/.hg": True,
            "**/CVS": True,
            "**/.DS_Store": True,
            "**/Thumbs.db": True,
            "**/tools": True,
            "**/configuracoes": True,
            "**/dependencias": True,
            "**/diagnostico": True,
            "**/lab.py": True,
            "**/iniciar-windows.cmd": True,
            "**/iniciar-linux.sh": True,
            "**/componentes.lock.json": True,
            "**/PREPARACAO.json": True,
            "**/linux-executaveis.json": True,
            "**/laboratorio.desktop": True,
            "**/.preparacao": True,
            "**/.hidden": True
        }
    }
    if cfg["has_php"]:
        settings["intelephense.environment.phpVersion"] = "8.4"
    if cfg["has_java"]:
        settings["java.import.maven.enabled"] = False
        settings["java.import.gradle.enabled"] = False
        settings["java.autobuild.enabled"] = False
        settings["java.jdt.ls.vmargs"] = "-Xmx512m -Xms64m"

    settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    argv_str = json.dumps({"locale": "pt-br"}, indent=2) + "\n"
    (kit_dir / "configuracoes" / "vscode" / "argv.json").write_text(argv_str, encoding="utf-8")

    # Copiar lock reduzido para auditoria
    (kit_dir / "componentes.lock.json").write_text(json.dumps({"components": selected_items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    size = sum(p.stat().st_size for p in kit_dir.rglob("*") if p.is_file())
    report = {
        "perfil": perfil,
        "so": os_key,
        "bytes_extraidos": size,
        "gb_decimal": round(size / 1e9, 2),
        "limite_recomendado_bytes": 4_000_000_000
    }
    (kit_dir / "PREPARACAO.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"✅ Kit '{kit_name}' montado com sucesso! Tamanho extraído: {size / 1e9:.2f} GB")


def zip_single_kit(perfil, os_key):
    kit_name = f"kit-{perfil}-{os_key}"
    kit_dir = to_long_path(DIST / kit_name)
    if not (kit_dir / "PREPARACAO.json").exists():
        raise RuntimeError(f"O kit {kit_name} ainda não foi montado. Execute 'montar' primeiro.")
    if (kit_dir / "estado").exists() and any((kit_dir / "estado").iterdir()):
        raise RuntimeError(f"O kit {kit_name} contém estado de uso anterior. Remova a pasta estado/ antes de empacotar.")

    print(f"\n📦 Compactando {kit_name}...", flush=True)
    files_to_pack = sorted(list(kit_dir.rglob("*")))
    total_files = len(files_to_pack)

    if os_key == "windows":
        zip_path = DIST / f"{kit_name}.zip"
        bar = ProgressBar(total_files, title=f"🗜️ {kit_name}.zip")
        with zipfile.ZipFile(clean_path_str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, p in enumerate(files_to_pack, 1):
                rel_path = os.path.relpath(clean_path_str(p), clean_path_str(DIST))
                arcname = rel_path.replace("\\", "/")
                if p.is_dir():
                    zinfo = zipfile.ZipInfo(arcname + "/")
                    zf.writestr(zinfo, "")
                else:
                    zf.write(clean_path_str(p), arcname)
                if idx % 25 == 0 or idx == total_files:
                    bar.set_current(idx, p.name)
        bar.finish("Concluído!")
        output = str(zip_path)
    else:
        archive_path = DIST / f"{kit_name}.tar.gz"
        bar = ProgressBar(total_files, title=f"🗜️ {kit_name}.tar.gz")
        with tarfile.open(archive_path, "w:gz") as tar:
            for idx, p in enumerate(files_to_pack, 1):
                arcname = os.path.relpath(str(p), str(DIST))
                tar.add(p, arcname=arcname, recursive=False)
                if idx % 25 == 0 or idx == total_files:
                    bar.set_current(idx, p.name)
        bar.finish("Concluído!")
        output = str(archive_path)

    checksum = digest(output)
    Path(output + ".sha256").write_text(checksum + "  " + Path(output).name + "\n")
    size_mb = os.path.getsize(output) / (1024 * 1024)
    print(f"🎉 Pacote gerado: {Path(output).name} ({size_mb:.1f} MB) | SHA256: {checksum[:16]}...")


def interactive_menu():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  🛠️  PREPARAÇÃO DOS KITS DE DESENVOLVIMENTO PORTÁTIL          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Escolha a ação desejada:                                 ║
║     [1] Montar kits (extrair e configurar pastas)            ║
║     [2] Compactar kits (gerar .zip ou .tar.gz)               ║
║     [3] Montar E Compactar tudo                              ║
║     [4] Baixar apenas (cache de componentes)                 ║
║     [5] Gravar Kit diretamente em um Pendrive                ║
║     [0] Sair                                                 ║
╚══════════════════════════════════════════════════════════════╝""")
    acao_choice = input("👉 Escolha a ação (1-5): ").strip()
    if acao_choice == "0":
        sys.exit(0)
    acao_map = {"1": "montar", "2": "zip", "3": "tudo", "4": "baixar", "5": "gravar"}
    acao = acao_map.get(acao_choice, "montar")
    if acao == "gravar":
        return "gravar", None, None

    print("""
Perfis disponíveis:
  [1] web         - Desenvolvimento Web (PHP 8.5)
  [2] poo-java    - POO com Java (JDK 25)
  [3] todos       - Gerar os 2 perfis""")
    perfil_choice = input("👉 Escolha o perfil (1-3) [todos]: ").strip()
    perfil_map = {"1": "web", "2": "poo-java", "3": "todos", "": "todos"}
    perfil = perfil_map.get(perfil_choice, "todos")

    print("""
Modalidade do Kit:
  [1] universal - Kit Universal Híbrido (Dual-OS Windows + Linux no mesmo pendrive) [.zip]
  [2] windows   - Apenas Windows 11 x64 (.zip)
  [3] linux     - Apenas Linux Mint x64 (.tar.gz)""")
    so_choice = input("👉 Escolha a modalidade (1-3) [1]: ").strip()
    so_map = {"1": "ambos", "2": "windows", "3": "linux", "": "ambos"}
    so = so_map.get(so_choice, "ambos")

    return acao, perfil, so


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=["resolver", "baixar", "montar", "zip", "tudo", "menu", "gravar"], nargs="?", default=None)
    parser.add_argument("--perfil", choices=["web", "poo-java", "todos"], default=None)
    parser.add_argument("--so", choices=["windows", "linux", "ambos"], default=None)
    args = parser.parse_args()

    acao = args.acao
    perfil = args.perfil
    so = args.so

    if acao == "gravar":
        import gravar_pendrive
        sys.exit(gravar_pendrive.main())

    if acao is None or acao == "menu" or (acao in ("montar", "zip", "tudo") and perfil is None and so is None):
        if sys.stdin.isatty():
            acao, perfil, so = interactive_menu()
        else:
            acao = acao or "montar"
            perfil = perfil or "todos"
            so = so or "ambos"
    else:
        perfil = perfil or "todos"
        so = so or "ambos"

    if acao == "resolver":
        if LOCK.exists():
            raise RuntimeError("Lock já existe. Preserve-o e renomeie explicitamente para selecionar novas versões.")
        resolve()
        return

    items = json.loads(LOCK.read_text())["components"] if LOCK.exists() else resolve()

    # Mapear perfis e SOs selecionados
    target_profiles = list(PROFILES.keys()) if (perfil is None or perfil == "todos") else [perfil]
    target_sos = list(OS_TARGETS.keys()) if (so is None or so == "ambos") else [so]
    needed_items = get_needed_items(items, target_profiles, target_sos)

    if acao == "baixar":
        bar = ProgressBar(len(needed_items), title="📥 Downloads")
        bar.set_current(0, "Iniciando...")

        def _acquire_and_track(item):
            res = acquire(item)
            bar.update(1, item["name"])
            return res

        workers = 2 if sys.platform == "win32" else 4
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_acquire_and_track, needed_items))
        bar.finish("Concluído!")
        print(f"✅ Todos os componentes selecionados ({len(needed_items)}) foram baixados e verificados com sucesso!")
        return

    # Para montar ou tudo, certificar-se de ter os caminhos adquiridos
    if acao in ("montar", "tudo"):
        bar = ProgressBar(len(needed_items), title="📥 Componentes")
        bar.set_current(0, "Verificando...")

        def _acquire_and_track(item):
            res = acquire(item)
            bar.update(1, item["name"])
            return res

        workers = 2 if sys.platform == "win32" else 4
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            downloaded_paths = list(pool.map(_acquire_and_track, needed_items))
        bar.finish("Prontos!")
        paths_dict = {item["name"]: path for item, path in zip(needed_items, downloaded_paths)}

        if so is None or so == "ambos":
            for p in target_profiles:
                assemble_universal_kit(p, items, paths_dict)
        else:
            for p in target_profiles:
                for s in target_sos:
                    assemble_single_kit(p, s, items, paths_dict)

    if acao in ("zip", "tudo"):
        if so is None or so == "ambos":
            for p in target_profiles:
                zip_universal_kit(p)
        else:
            for p in target_profiles:
                for s in target_sos:
                    zip_single_kit(p, s)


if __name__ == "__main__":
    main()
