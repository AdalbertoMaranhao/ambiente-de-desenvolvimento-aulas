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
        self.patches = [patch.object(runtime, "ROOT", self.root),
                        patch.object(runtime, "STATE", self.root / "estado/linux-x64"),
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

    def test_never_shuts_down_foreign_database(self):
        with patch.object(self.lab, "owns_server", return_value=False), patch.object(self.lab, "port_used", return_value=True), patch.object(runtime, "run") as execute:
            with self.assertRaises(RuntimeError):
                self.lab.stop()
            execute.assert_not_called()

    def test_busy_port_prevents_initialization_and_releases_lock(self):
        with patch.object(self.lab, "owns_server", return_value=False), patch.object(self.lab, "port_used", return_value=True), patch.object(runtime, "run") as execute:
            with self.assertRaises(RuntimeError):
                self.lab.start()
            execute.assert_not_called()
        self.assertFalse(self.lab.data.exists())
        self.assertFalse((runtime.STATE / "inicio.lock").exists())

    def test_failed_export_leaves_no_completed_backup(self):
        with patch.object(self.lab, "owns_server", return_value=True), patch.object(runtime, "run", side_effect=subprocess.CalledProcessError(1, "dump")):
            with self.assertRaises(subprocess.CalledProcessError):
                self.lab.backup()
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_offline_paths_are_local_even_with_spaces(self):
        self.assertEqual(self.lab.env["PIP_NO_INDEX"], "1")
        self.assertEqual(self.lab.env["COMPOSER_DISABLE_NETWORK"], "1")
        self.assertEqual(self.lab.env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(Path(self.lab.env["PIP_FIND_LINKS"]), self.root / "dependencias/python")
        config = json.loads((runtime.STATE / "composer-home/config.json").read_text())
        self.assertFalse(config["repositories"]["packagist.org"])
        self.assertNotIn("password", self.lab.client.name)


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


if __name__ == "__main__":
    unittest.main()
