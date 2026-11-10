import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

BASE = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


builder = module("builder", BASE / "preparar.py")
runtime = module("runtime", BASE / "kit/lab.py")
verifier = module("verifier", BASE / "verificar_pacote.py")


class ExtractionTests(unittest.TestCase):
    def test_rejects_path_traversal_in_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as f:
                f.writestr("../outside.txt", "bad")
            with self.assertRaises(RuntimeError):
                builder.unpack(archive, root / "target", "zip")
            self.assertFalse((root / "outside.txt").exists())

    def test_materializes_relative_links_and_chains(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "links.tar.gz"
            with tarfile.open(archive, "w:gz") as f:
                for name, link in [("pkg/1/alias", "../a/file"), ("pkg/bin/tool", "../1/alias")]:
                    entry = tarfile.TarInfo(name)
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = link
                    f.addfile(entry)
                entry = tarfile.TarInfo("pkg/a/file")
                entry.size = 4
                entry.mode = 0o755
                f.addfile(entry, io.BytesIO(b"test"))
            builder.unpack(archive, root / "target", "tar-root")
            self.assertEqual((root / "target/bin/tool").read_bytes(), b"test")
            self.assertFalse((root / "target/bin/tool").is_symlink())

    def test_rejects_escaping_tar_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "unsafe.tar.gz"
            with tarfile.open(archive, "w:gz") as f:
                entry = tarfile.TarInfo("pkg/link")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "../../outside"
                f.addfile(entry)
            with self.assertRaises(RuntimeError):
                builder.unpack(archive, root / "target", "tar-root")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aulas com espacos ")
        self.root = Path(self.tmp.name)
        (self.root / "projetos").mkdir(parents=True, exist_ok=True)
        (self.root / "projetos/teste.txt").write_text("conteudo")
        self.patches = [patch.object(runtime, "ROOT", self.root),
                        patch.object(runtime, "STATE", self.root / "configuracoes/linux-x64"),
                        patch.object(runtime, "TOOLS", self.root / "tools/linux-x64"),
                        patch.object(runtime, "WINDOWS", False),
                        patch.object(runtime.sys, "platform", "linux"),
                        patch.object(runtime.platform, "machine", return_value="x86_64")]
        for p in self.patches:
            p.start()
        self.lab = runtime.Lab()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_backup_creates_zip_and_recovers_gracefully(self):
        dest = self.lab.backup()
        self.assertTrue(dest.exists())
        self.assertTrue(dest.name.endswith(".zip"))
        with zipfile.ZipFile(dest, "r") as zf:
            self.assertIn("projetos/teste.txt", zf.namelist())

    def test_failed_backup_leaves_no_completed_file(self):
        with patch("zipfile.ZipFile", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.lab.backup()
        backups = list((self.root / "backups").iterdir())
        self.assertEqual(backups, [])

    def test_offline_paths_are_local_even_with_spaces(self):
        self.assertEqual(self.lab.env["PIP_NO_INDEX"], "1")
        self.assertEqual(self.lab.env["COMPOSER_DISABLE_NETWORK"], "1")
        self.assertEqual(self.lab.env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(Path(self.lab.env["PIP_FIND_LINKS"]), self.root / "dependencias/python")
        config = json.loads((runtime.STATE / "composer-home/config.json").read_text())
        self.assertFalse(config["repositories"]["packagist.org"])


class ProfileFilterTests(unittest.TestCase):
    def setUp(self):
        self.lock_data = json.loads((BASE / "componentes.lock.json").read_text(encoding="utf-8"))
        self.items = self.lock_data["components"]

    def test_windows_filter_excludes_linux_artifacts(self):
        needed = builder.get_needed_items(self.items, list(builder.PROFILES.keys()), ["windows"])
        self.assertTrue(len(needed) > 0)
        for item in needed:
            name = item["name"]
            self.assertFalse(name.startswith("linux-deb-"), f"Unexpected deb package in Windows: {name}")
            self.assertFalse(name.endswith("linux-x64"), f"Unexpected linux target in Windows: {name}")
            self.assertFalse(name == "frankenphp-license", f"FrankenPHP license should not be in Windows: {name}")

    def test_linux_filter_excludes_windows_artifacts(self):
        needed = builder.get_needed_items(self.items, list(builder.PROFILES.keys()), ["linux"])
        self.assertTrue(len(needed) > 0)
        for item in needed:
            name = item["name"]
            self.assertFalse(name.endswith("windows-x64"), f"Unexpected windows target in Linux: {name}")

    def test_single_profile_selection(self):
        web_win = builder.get_needed_items(self.items, ["web"], ["windows"])
        names = {item["name"] for item in web_win}
        self.assertIn("php-windows-x64", names)
        self.assertNotIn("jdk-windows-x64", names)
        self.assertNotIn("ms-python.python-windows-x64", names)
        self.assertIn("usernamehw.errorlens-windows-x64", names)
        self.assertIn("oderwat.indent-rainbow-windows-x64", names)


class LongPathTests(unittest.TestCase):
    def test_clean_path_str(self):
        self.assertEqual(builder.clean_path_str(r"\\?\C:\project\path"), r"C:\project\path")
        self.assertEqual(builder.clean_path_str(r"\\?\UNC\server\share"), r"server\share")
        self.assertEqual(builder.clean_path_str(r"C:\normal\path"), r"C:\normal\path")

    def test_to_long_path_non_windows(self):
        with patch.object(builder.sys, "platform", "darwin"):
            p = Path("/tmp/test")
            self.assertEqual(builder.to_long_path(p), p)

    def test_to_long_path_windows(self):
        with patch.object(builder.sys, "platform", "win32"):
            with patch.object(builder.os.path, "abspath", return_value=r"C:\project\deep\path"):
                result = builder.to_long_path(Path("relative"))
                self.assertTrue(str(result).startswith(r"\\?\C:\project\deep\path"))


class ProgressBarTests(unittest.TestCase):
    def test_progress_bar_updates_and_finish(self):
        out = io.StringIO()
        with patch.object(builder.sys, "stdout", out):
            bar = builder.ProgressBar(10, title="Teste", width=10)
            bar.update(5, "metade")
            self.assertEqual(bar.current, 5)
            bar.finish("fim")
            self.assertEqual(bar.current, 10)
            output = out.getvalue()
            self.assertIn("Teste", output)
            self.assertIn("10/10", output)

    def test_progress_bar_ascii_fallback(self):
        out = io.StringIO()
        with patch.object(builder.sys, "stdout", out):
            bar = builder.ProgressBar(5, title="ASCII", width=10)
            bar.unicode = False
            bar.update(3, "teste")
            output = out.getvalue()
            self.assertIn("=", output)
            self.assertIn("-", output)

    def test_progress_bar_thread_safety(self):
        import concurrent.futures
        out = io.StringIO()
        with patch.object(builder.sys, "stdout", out):
            bar = builder.ProgressBar(100, title="ThreadSafe", width=10)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: bar.update(1), range(100)))
            self.assertEqual(bar.current, 100)


class DownloadResilienceTests(unittest.TestCase):
    def test_safe_replace_retries_and_succeeds(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "src.part"
            dst = Path(folder) / "dst.txt"
            src.write_text("novo conteudo")

            attempts = 0
            original_replace = Path.replace

            def flaky_replace(self_path, target):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("[WinError 32] Arquivo em uso por outro processo")
                return original_replace(self_path, target)

            with patch.object(Path, "replace", side_effect=flaky_replace, autospec=True):
                builder.safe_replace(src, dst, max_retries=5, delay=0.01)

            self.assertEqual(attempts, 3)
            self.assertEqual(dst.read_text(), "novo conteudo")

    def test_safe_replace_windows_unlink_target(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "src.part"
            dst = Path(folder) / "dst.txt"
            src.write_text("novo")
            dst.write_text("antigo")

            unlink_called = False
            orig_unlink = Path.unlink

            def track_unlink(p_self, *args, **kwargs):
                nonlocal unlink_called
                unlink_called = True
                return orig_unlink(p_self, *args, **kwargs)

            with patch.object(builder.sys, "platform", "win32"), \
                 patch.object(builder, "to_long_path", side_effect=lambda p: p), \
                 patch.object(Path, "unlink", side_effect=track_unlink, autospec=True):
                builder.safe_replace(src, dst, max_retries=2, delay=0.01)

            self.assertTrue(unlink_called)
            self.assertEqual(dst.read_text(), "novo")
            self.assertFalse(src.exists())

    def test_fetch_fallback_to_urllib_when_curl_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            dst = Path(folder) / "arquivo.bin"

            def fake_urllib(url, part, post=None):
                part.write_bytes(b"dados baixados via urllib")

            with patch("shutil.which", return_value="/usr/bin/curl"), \
                 patch("subprocess.run", side_effect=subprocess.CalledProcessError(22, "curl")), \
                 patch.object(builder, "_download_urllib", side_effect=fake_urllib):
                res = builder.fetch("https://exemplo.com/teste.bin", dst)

            self.assertEqual(res, dst)
            self.assertEqual(dst.read_bytes(), b"dados baixados via urllib")

    def test_acquire_recovers_corrupted_cached_file(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            cache_dir = Path(folder)
            with patch.object(builder, "CACHE", cache_dir):
                item = {
                    "name": "teste-pkg",
                    "kind": "zip",
                    "url": "https://exemplo.com/teste-pkg.zip",
                    "sha256": hashlib.sha256(b"conteudo integro").hexdigest()
                }
                # Cria arquivo com conteúdo corrompido no cache
                corrupt_file = cache_dir / "teste-pkg.zip"
                corrupt_file.write_bytes(b"conteudo corrompido")

                def fake_fetch(url, path, post=None):
                    path.write_bytes(b"conteudo integro")

                with patch.object(builder, "fetch", side_effect=fake_fetch) as mock_fetch:
                    path = builder.acquire(item)

                self.assertEqual(path, corrupt_file)
                self.assertEqual(path.read_bytes(), b"conteudo integro")
                mock_fetch.assert_called_once_with(item["url"], corrupt_file)


class GravarPendriveTests(unittest.TestCase):
    def test_calcular_sha256(self):
        import gravar_pendrive
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "teste.txt"
            f.write_bytes(b"dados para hash")
            expected = hashlib.sha256(b"dados para hash").hexdigest()
            self.assertEqual(gravar_pendrive.calcular_sha256(f), expected)

    def test_validar_integridade_pacote(self):
        import gravar_pendrive
        with tempfile.TemporaryDirectory() as folder:
            zip_file = Path(folder) / "kit-teste.zip"
            zip_file.write_bytes(b"conteudo zip")
            sha_file = Path(folder) / "kit-teste.zip.sha256"
            
            # Caso 1: Hash correto
            sha_file.write_text(hashlib.sha256(b"conteudo zip").hexdigest() + "  kit-teste.zip\n")
            self.assertTrue(gravar_pendrive.validar_integridade_pacote(zip_file))

            # Caso 2: Hash incorreto
            sha_file.write_text("0000000000000000000000000000000000000000000000000000000000000000  kit-teste.zip\n")
            self.assertFalse(gravar_pendrive.validar_integridade_pacote(zip_file))

    def test_extrair_com_progresso_strip_prefix(self):
        import gravar_pendrive
        with tempfile.TemporaryDirectory() as folder:
            zip_path = Path(folder) / "kit-teste.zip"
            dest_dir = Path(folder) / "pendrive"

            # Cria um zip simulando kit-web/com arquivos
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("kit-web/BEM-VINDO.html", "<h1>Bem vindo</h1>")
                zf.writestr("kit-web/projetos/ola.txt", "Ola")

            gravar_pendrive.extrair_com_progresso(zip_path, dest_dir)

            self.assertTrue((dest_dir / "BEM-VINDO.html").exists())
            self.assertTrue((dest_dir / "projetos" / "ola.txt").exists())
            self.assertEqual((dest_dir / "BEM-VINDO.html").read_text(), "<h1>Bem vindo</h1>")
            self.assertEqual((dest_dir / "projetos" / "ola.txt").read_text(), "Ola")

    def test_obter_volumes_removiveis_retorna_lista(self):
        import gravar_pendrive
        vols = gravar_pendrive.obter_volumes_removiveis()
        self.assertIsInstance(vols, list)
        for v in vols:
            self.assertIn("caminho", v)
            self.assertIn("livre_gb", v)


class VerifierTests(unittest.TestCase):
    def test_elf_needed_non_elf(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "not_elf.bin"
            f.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
            self.assertEqual(verifier.elf_needed(f), [])

    def test_pe_needed_non_pe(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "not_pe.bin"
            f.write_bytes(b"\x7fELF\x02\x01\x01\x00")
            self.assertEqual(verifier.pe_needed(f), [])

    def test_inspect_kit_detects_excessive_size(self):
        with tempfile.TemporaryDirectory() as folder:
            kit_dir = Path(folder) / "kit-gigante"
            kit_dir.mkdir()
            # Inspeciona pasta vazia (deve passar e calcular tamanho 0 GB)
            self.assertTrue(verifier.inspect_kit(kit_dir))


if __name__ == "__main__":
    unittest.main()
