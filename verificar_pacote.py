#!/usr/bin/env python3
"""Inspeção estática dos pacotes modulares (ELF para Linux e PE para Windows)."""
import json
import os
from pathlib import Path
import re
import struct
import sys

BASE = Path(__file__).resolve().parent


def to_long_path(path):
    if sys.platform != "win32":
        return path
    s = os.path.abspath(str(path))
    if s.startswith("\\\\?\\"):
        return Path(s)
    if s.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + s[2:])
    return Path("\\\\?\\" + s)


def elf_needed(path):
    with path.open("rb") as f:
        h = f.read(64)
        if h[:6] != b"\x7fELF\x02\x01":
            return []
        offset = struct.unpack_from("<Q", h, 32)[0]
        size, count = struct.unpack_from("<HH", h, 54)
        f.seek(offset)
        segments = [struct.unpack("<IIQQQQQQ", f.read(size)[:56]) for _ in range(count)]
        dynamic = next((s for s in segments if s[0] == 2), None)
        if not dynamic:
            return []
        f.seek(dynamic[2])
        entries = [struct.unpack("<qQ", f.read(16)) for _ in range(dynamic[5] // 16)]
        address = next(value for tag, value in entries if tag == 5)
        segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3] + s[5])
        f.seek(segment[2] + address - segment[3])
        strings = f.read(next(value for tag, value in entries if tag == 10))
        return [strings[value:].split(b"\0")[0].decode() for tag, value in entries if tag == 1]


def pe_needed(path):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 60)[0]
    sections = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (112 if magic == 0x20b else 96)
    imports = struct.unpack_from("<I", data, directories + 8)[0]
    table = optional + optional_size
    ranges = []
    for i in range(sections):
        header = table + i * 40
        virtual_size, address, raw_size, raw_offset = struct.unpack_from("<IIII", data, header + 8)
        ranges.append((address, max(virtual_size, raw_size), raw_offset))

    def raw(rva):
        address, _, offset = next(s for s in ranges if s[0] <= rva < s[0] + s[1])
        return offset + rva - address

    if not imports:
        return []
    pos = raw(imports)
    names = []
    while any(data[pos:pos + 20]):
        name_address = struct.unpack_from("<I", data, pos + 12)[0]
        start = raw(name_address)
        names.append(data[start:].split(b"\0")[0].decode().lower())
        pos += 20
    return names


def inspect_kit(kit_path):
    failures = []
    print(f"\n🔍 Inspecionando pacote: {kit_path.name}")
    linux = kit_path / "tools/linux-x64"
    if linux.exists():
        locations = [linux / "sysroot/usr/lib/x86_64-linux-gnu", linux / "sysroot/lib/x86_64-linux-gnu"]
        if (linux / "mariadb/lib").exists():
            locations.append(linux / "mariadb/lib")
        available = {p.name: p for folder in locations for p in folder.glob("*.so*") if p.is_file()}
        host = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1", "libresolv.so.2", "libutil.so.1", "ld-linux-x86-64.so.2"}
        queue = [linux / "sysroot/usr/bin/git"]
        if (linux / "mariadb/bin").exists():
            queue.extend([linux / "mariadb/bin" / name for name in ["mariadbd", "mariadb", "mariadb-admin", "mariadb-dump"]])
        seen = set()
        while queue:
            file = queue.pop()
            if file in seen:
                continue
            seen.add(file)
            if not file.is_file():
                failures.append("Ausente: " + str(file))
                continue
            for soname in elf_needed(file):
                if soname in available:
                    queue.append(available[soname])
                elif soname not in host:
                    failures.append(file.name + ": biblioteca Linux ausente " + soname)
        print("  ✅ ELF: bibliotecas dinâmicas conferidas.")

    win = kit_path / "tools/windows-x64"
    if win.exists():
        check_groups = []
        if (win / "mariadb/bin").exists():
            check_groups.append((win / "mariadb/bin", ["mariadbd.exe", "mariadb.exe", "mariadb-install-db.exe"]))
        if (win / "php").exists():
            check_groups.append((win / "php", ["php.exe", "php8.dll"]))
        if (win / "python").exists():
            check_groups.append((win / "python", ["python.exe", "python313.dll"]))

        for home, binaries in check_groups:
            queue = [home / b for b in binaries]
            local = {p.name.lower(): p for p in home.glob("*.dll")}
            seen = set()
            while queue:
                file = queue.pop()
                if file in seen:
                    continue
                seen.add(file)
                if not file.is_file():
                    failures.append("Ausente: " + str(file))
                    continue
                for name in pe_needed(file):
                    if name in local:
                        queue.append(local[name])
                    elif name.startswith(("vcruntime", "msvcp", "concrt", "libssl", "libcrypto", "libssh", "libsqlite", "php")):
                        failures.append(file.name + ": DLL privada ausente " + name)
        print("  ✅ PE: imports privados de Windows conferidos.")

    if (kit_path / "dependencias/python/requirements.txt").exists():
        for target in ["windows-x64", "linux-x64"]:
            python = kit_path / "tools" / target / "python"
            if python.exists() and not list(python.glob("**/site-packages/pip/__init__.py")):
                failures.append("pip ausente: " + target)

    size = sum(p.stat().st_size for p in to_long_path(kit_path).rglob("*") if p.is_file())
    if size > 4_000_000_000:
        failures.append(f"Tamanho de {size/1e9:.2f} GB excede o limite máximo recomendado de 4 GB para o kit modular.")
    print(f"  ✅ Tamanho extraído: {size / 1e9:.3f} GB (folga de {8.0 - (size/1e9):.2f} GB no pendrive de 8 GB)")

    if failures:
        print("  ❌ Falhas encontradas:\n    " + "\n    ".join(failures), file=sys.stderr)
        return False
    return True


def main():
    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1]).resolve()]
    else:
        dist_dir = BASE / "dist"
        targets = [p for p in dist_dir.glob("kit-*") if p.is_dir() and not p.name.endswith(".zip") and not p.name.endswith(".tar.gz")]

    if not targets:
        print("Nenhum kit encontrado em dist/ para inspeção. Execute preparar.py montar primeiro.")
        return 1

    all_passed = True
    for target in targets:
        if not inspect_kit(target):
            all_passed = False

    if all_passed:
        print("\n🎉 Todos os pacotes inspecionados passaram na verificação estática!")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
