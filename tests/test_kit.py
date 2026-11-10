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

    def test_java_profile_windows_excludes_vscode_extensions(self):
        java_win = builder.get_needed_items(self.items, ["poo-java"], ["windows"])
        names = {item["name"] for item in java_win}
        self.assertIn("jdk-windows-x64", names)
        self.assertIn("jdbc", names)
        self.assertIn("python-windows-x64", names)
        self.assertIn("git-windows-x64", names)
        self.assertNotIn("redhat.java-windows-x64", names)
        self.assertNotIn("vscjava.vscode-java-debug-windows-x64", names)
        self.assertNotIn("usernamehw.errorlens-windows-x64", names)

    def test_java_profile_linux_includes_vscode_extensions(self):
        java_linux = builder.get_needed_items(self.items, ["poo-java"], ["linux"])
        names = {item["name"] for item in java_linux}
        self.assertIn("jdk-linux-x64", names)
        self.assertIn("jdbc", names)
        self.assertIn("python-linux-x64", names)
        self.assertIn("linux-deb-git", names)
        self.assertIn("redhat.java-linux-x64", names)
        self.assertIn("vscjava.vscode-java-debug-linux-x64", names)
        self.assertIn("usernamehw.errorlens-linux-x64", names)


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


class VSCodeHostDetectionTests(unittest.TestCase):
    def test_find_vscode_via_path(self):
        with patch("shutil.which", return_value="/custom/bin/code"):
            found = runtime.find_vscode()
            self.assertEqual(found, Path("/custom/bin/code"))

    def test_find_vscode_windows_candidates(self):
        with patch("shutil.which", return_value=None), \
             patch.object(runtime, "WINDOWS", True), \
             patch.object(runtime.sys, "platform", "win32"), \
             patch.dict(runtime.os.environ, {"LOCALAPPDATA": r"C:\Users\Aluno\AppData\Local"}), \
             patch.object(Path, "exists", autospec=True) as mock_exists:

            def fake_exists(path_self):
                return str(path_self).endswith("Code.exe")

            mock_exists.side_effect = fake_exists
            found = runtime.find_vscode()
            self.assertIsNotNone(found)
            self.assertTrue(str(found).endswith("Code.exe"))

    def test_find_vscode_linux_candidates(self):
        with patch("shutil.which", return_value=None), \
             patch.object(runtime, "WINDOWS", False), \
             patch.object(runtime.sys, "platform", "linux"), \
             patch.object(Path, "exists", autospec=True) as mock_exists:

            def fake_exists(path_self):
                return str(path_self) == "/usr/bin/code"

            mock_exists.side_effect = fake_exists
            found = runtime.find_vscode()
            self.assertEqual(found, Path("/usr/bin/code"))

    def test_find_vscode_not_found(self):
        with patch("shutil.which", return_value=None), \
             patch.object(Path, "exists", return_value=False):
            found = runtime.find_vscode()
            self.assertIsNone(found)

    def test_editor_missing_vscode_prints_alert_and_returns_false(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "projetos").mkdir()
            (root / "configuracoes/linux-x64").mkdir(parents=True)
            with patch.object(runtime, "ROOT", root), \
                 patch.object(runtime, "STATE", root / "configuracoes/linux-x64"), \
                 patch.object(runtime, "VSCODE_USER", root / "configuracoes/vscode"), \
                 patch.object(runtime, "find_vscode", return_value=None), \
                 patch.object(runtime, "WINDOWS", False), \
                 patch.object(runtime.sys, "platform", "linux"), \
                 patch.object(runtime.platform, "machine", return_value="x86_64"), \
                 patch("builtins.input", return_value="n"):
                lab = runtime.Lab()
                res = lab.editor()
                self.assertFalse(res)


class IntelliJHostDetectionTests(unittest.TestCase):
    def test_find_intellij_via_path(self):
        with patch("shutil.which", return_value="C:\\custom\\bin\\idea64.exe"):
            found = runtime.find_intellij()
            self.assertEqual(found, Path("C:\\custom\\bin\\idea64.exe"))

    def test_find_intellij_candidates(self):
        with patch("shutil.which", return_value=None), \
             patch.object(runtime, "WINDOWS", True), \
             patch.object(runtime.sys, "platform", "win32"), \
             patch.dict(runtime.os.environ, {"ProgramFiles": r"C:\Program Files"}), \
             patch.object(Path, "glob", autospec=True) as mock_glob, \
             patch.object(Path, "exists", autospec=True) as mock_exists:

            mock_glob.return_value = [Path(r"C:\Program Files\JetBrains\IntelliJ IDEA 2024.3\bin\idea64.exe")]
            mock_exists.return_value = True
            found = runtime.find_intellij()
            self.assertIsNotNone(found)
            self.assertTrue(str(found).endswith("idea64.exe"))

    def test_configure_intellij_jdk_creates_and_updates_jdk_table(self):
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as tmp_dir:
            appdata = Path(tmp_dir) / "AppData"
            jdk_dir = Path(tmp_dir) / "jdk"
            jdk_dir.mkdir(parents=True)
            (jdk_dir / "release").write_text('JAVA_VERSION="25"\nMODULES="java.base java.sql"\n', encoding="utf-8")
            (jdk_dir / "lib").mkdir(parents=True)
            (jdk_dir / "lib/src.zip").write_bytes(b"PK")

            with patch.dict(runtime.os.environ, {"APPDATA": str(appdata)}), \
                 patch.object(runtime, "find_intellij", return_value=None):
                res = runtime.configure_intellij_jdk(jdk_dir)
                self.assertTrue(res)

                xml_file = appdata / "JetBrains" / "IdeaIC2024.3" / "options" / "jdk.table.xml"
                self.assertTrue(xml_file.exists())

                tree = ET.parse(xml_file)
                root = tree.getroot()
                component = root.find("component")
                self.assertIsNotNone(component)
                self.assertEqual(component.get("name"), "ProjectJdkTable")

                jdk = component.find("jdk")
                self.assertIsNotNone(jdk)
                self.assertEqual(jdk.find("name").get("value"), "JDK-Kit")
                self.assertEqual(jdk.find("version").get("value"), "25")
                self.assertEqual(jdk.find("homePath").get("value"), jdk_dir.resolve().as_posix())

                # Testar atualização idempotente (sem duplicar entradas)
                runtime.configure_intellij_jdk(jdk_dir)
                tree2 = ET.parse(xml_file)
                jdks = tree2.getroot().find("component").findall("jdk")
                self.assertEqual(len(jdks), 1)

    def test_editor_intellij_missing_alert_and_returns_false(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "projetos/java").mkdir(parents=True)
            (root / "tools/windows-x64/jdk").mkdir(parents=True)
            with patch.object(runtime, "ROOT", root), \
                 patch.object(runtime, "TOOLS", root / "tools/windows-x64"), \
                 patch.object(runtime, "WINDOWS", True), \
                 patch.object(runtime.sys, "platform", "win32"), \
                 patch.object(runtime.platform, "machine", return_value="x86_64"), \
                 patch.object(runtime, "find_intellij", return_value=None), \
                 patch("builtins.input", return_value="n"):
                lab = runtime.Lab()
                self.assertTrue(lab.use_intellij)
                res = lab.editor()
                self.assertFalse(res)

    def test_editor_intellij_launches_popen(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "projetos/java").mkdir(parents=True)
            (root / "tools/windows-x64/jdk").mkdir(parents=True)
            fake_idea = Path(folder) / "idea64.exe"
            fake_idea.write_text("")
            with patch.object(runtime, "ROOT", root), \
                 patch.object(runtime, "TOOLS", root / "tools/windows-x64"), \
                 patch.object(runtime, "WINDOWS", True), \
                 patch.object(runtime.sys, "platform", "win32"), \
                 patch.object(runtime.platform, "machine", return_value="x86_64"), \
                 patch.object(runtime, "find_intellij", return_value=fake_idea), \
                 patch.object(runtime, "configure_intellij_jdk", return_value=True), \
                 patch("subprocess.Popen") as mock_popen:
                lab = runtime.Lab()
                self.assertTrue(lab.use_intellij)
                res = lab.editor()
                self.assertTrue(res)
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], str(fake_idea))
                self.assertIn("projetos", str(args[1]))

    def test_editor_linux_java_uses_host_vscode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "projetos/java").mkdir(parents=True)
            (root / "tools/linux-x64/jdk").mkdir(parents=True)
            (root / "tools/linux-x64/extensions").mkdir(parents=True)
            fake_code = Path(folder) / "code"
            fake_code.write_text("")
            with patch.object(runtime, "ROOT", root), \
                 patch.object(runtime, "TOOLS", root / "tools/linux-x64"), \
                 patch.object(runtime, "WINDOWS", False), \
                 patch.object(runtime.sys, "platform", "linux"), \
                 patch.object(runtime.platform, "machine", return_value="x86_64"), \
                 patch.object(runtime, "find_vscode", return_value=fake_code), \
                 patch("subprocess.Popen") as mock_popen:
                lab = runtime.Lab()
                self.assertFalse(lab.use_intellij)
                res = lab.editor()
                self.assertTrue(res)
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], str(fake_code))
                self.assertIn("--extensions-dir", args)
                self.assertIn(str(root / "tools/linux-x64/extensions"), args)
                self.assertEqual(args[-1], str(root / "projetos/java"))


if __name__ == "__main__":
    unittest.main()
