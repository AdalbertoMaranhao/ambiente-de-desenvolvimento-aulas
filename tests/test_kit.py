import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
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

    def test_obter_local_root_custom(self):
        with patch.dict(runtime.os.environ, {"LAB_LOCAL_ROOT": "/tmp/custom_lab"}):
            self.assertEqual(runtime.obter_local_root(), Path("/tmp/custom_lab"))

    def test_obter_local_root_windows(self):
        with patch.dict(runtime.os.environ, {"LAB_LOCAL_ROOT": "", "LOCALAPPDATA": r"C:\Users\Aluno\AppData\Local"}), \
             patch.object(runtime, "WINDOWS", True):
            res_str = str(runtime.obter_local_root()).replace("/", "\\")
            self.assertEqual(res_str, r"C:\Users\Aluno\AppData\Local\LaboratorioAulas")

    def test_obter_local_root_linux(self):
        with patch.dict(runtime.os.environ, {"LAB_LOCAL_ROOT": "", "XDG_DATA_HOME": "/home/aluno/.local/share"}), \
             patch.object(runtime, "WINDOWS", False), \
             patch.object(runtime.sys, "platform", "linux"):
            expected = Path("/home/aluno/.local/share/laboratorio-aulas")
            self.assertEqual(runtime.obter_local_root(), expected)

    def test_detectar_disciplina(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "projetos/web").mkdir(parents=True)
            self.assertEqual(runtime.detectar_disciplina(root), "web")

            shutil.rmtree(root / "projetos/web")
            (root / "projetos/java").mkdir(parents=True)
            self.assertEqual(runtime.detectar_disciplina(root), "java")

    def test_provisionar_ferramentas_locais_incremental(self):
        with tempfile.TemporaryDirectory() as d:
            kit_root = Path(d) / "pendrive"
            src_tools = kit_root / "tools/linux-x64"
            (src_tools / "bin").mkdir(parents=True)
            (src_tools / "bin/meu_bin").write_text("executavel")

            local_tools = Path(d) / "local/kits/web/linux-x64/tools"

            # 1. Primeira instalação
            res = runtime.provisionar_ferramentas_locais(kit_root, local_tools, "linux-x64", "web")
            self.assertEqual(res, local_tools)
            self.assertTrue((local_tools / "bin/meu_bin").exists())
            self.assertTrue((local_tools / "manifesto-instalacao.json").exists())

            # 2. Rechamada sem alteração de hash (deve reutilizar)
            mtime_antes = (local_tools / "manifesto-instalacao.json").stat().st_mtime
            res2 = runtime.provisionar_ferramentas_locais(kit_root, local_tools, "linux-x64", "web")
            self.assertEqual(res2, local_tools)
            self.assertEqual((local_tools / "manifesto-instalacao.json").stat().st_mtime, mtime_antes)


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

    def test_extrair_com_progresso_python_forcado(self):
        import gravar_pendrive
        with tempfile.TemporaryDirectory() as folder:
            zip_path = Path(folder) / "kit-py.zip"
            dest_dir = Path(folder) / "pendrive"

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("kit-web/sub/arquivo.txt", "conteudo teste")

            gravar_pendrive.extrair_com_progresso(zip_path, dest_dir, forcar_python=True)
            self.assertTrue((dest_dir / "sub" / "arquivo.txt").exists())
            self.assertEqual((dest_dir / "sub" / "arquivo.txt").read_text(), "conteudo teste")

    def test_copiar_pasta_direta(self):
        import gravar_pendrive
        with tempfile.TemporaryDirectory() as folder:
            origem = Path(folder) / "ssd_kit"
            (origem / "sub").mkdir(parents=True)
            (origem / "sub" / "teste.txt").write_text("direto ssd")
            destino = Path(folder) / "pendrive"

            gravar_pendrive.copiar_pasta_direta(origem, destino)
            self.assertTrue((destino / "sub" / "teste.txt").exists())
            self.assertEqual((destino / "sub" / "teste.txt").read_text(), "direto ssd")

    def test_calcular_pasta_destino(self):
        import gravar_pendrive
        base = Path("/Volumes/AULAS")
        self.assertEqual(gravar_pendrive.calcular_pasta_destino(base, "web"), base / "kit-web")
        self.assertEqual(gravar_pendrive.calcular_pasta_destino(base, "poo-java"), base / "kit-poo-java")
        self.assertEqual(gravar_pendrive.calcular_pasta_destino(base / "kit-web", "web"), base / "kit-web")
        self.assertEqual(gravar_pendrive.calcular_pasta_destino(base, "web", subpasta="meu-kit"), base / "meu-kit")
        self.assertEqual(gravar_pendrive.calcular_pasta_destino(base, "web", na_raiz=True), base)

    def test_eh_sistema_ideal(self):
        import gravar_pendrive
        self.assertTrue(gravar_pendrive.eh_sistema_ideal("exFAT"))
        self.assertTrue(gravar_pendrive.eh_sistema_ideal("ExFAT"))
        self.assertFalse(gravar_pendrive.eh_sistema_ideal("FAT32"))
        self.assertFalse(gravar_pendrive.eh_sistema_ideal("MS-DOS FAT32"))
        self.assertFalse(gravar_pendrive.eh_sistema_ideal("NTFS"))
        self.assertFalse(gravar_pendrive.eh_sistema_ideal(""))

    def test_confirmar_formatacao_segura(self):
        import gravar_pendrive
        with patch("builtins.input", return_value="FORMATAR"):
            self.assertTrue(gravar_pendrive.confirmar_formatacao_segura(Path("/Volumes/TESTE"), "FAT32"))
        with patch("builtins.input", return_value="formatar"):
            self.assertTrue(gravar_pendrive.confirmar_formatacao_segura(Path("/Volumes/TESTE"), "FAT32"))
        with patch("builtins.input", return_value="s"):
            self.assertFalse(gravar_pendrive.confirmar_formatacao_segura(Path("/Volumes/TESTE"), "FAT32"))
        with patch("builtins.input", return_value=""):
            self.assertFalse(gravar_pendrive.confirmar_formatacao_segura(Path("/Volumes/TESTE"), "FAT32"))

    def test_formatar_pendrive_macos(self):
        import gravar_pendrive
        import sys
        with patch.object(sys, "platform", "darwin"), \
             patch("subprocess.run") as mock_run, \
             patch.object(Path, "exists", return_value=True):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            res = gravar_pendrive.formatar_pendrive(Path("/Volumes/MEUPENDRIVE"), rotulo="AULAS")
            mock_run.assert_called_once()
            args, _ = mock_run.call_args
            self.assertEqual(args[0], ["diskutil", "eraseVolume", "ExFAT", "AULAS", "/Volumes/MEUPENDRIVE"])
            self.assertEqual(res, Path("/Volumes/AULAS"))

    def test_formatar_pendrive_windows(self):
        import gravar_pendrive
        import sys
        with patch.object(sys, "platform", "win32"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            res = gravar_pendrive.formatar_pendrive(Path(r"E:\lab"), rotulo="AULAS")
            mock_run.assert_called_once()
            args, _ = mock_run.call_args
            self.assertEqual(args[0][:5], ["format", "E:", "/FS:exFAT", "/Q", "/A:128K"])
            self.assertEqual(str(res), "E:\\")

    def test_criar_leia_me_raiz(self):
        import gravar_pendrive
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "kit-web").mkdir()
            gravar_pendrive.criar_leia_me_raiz(root, "web")
            leia_me = root / "LEIA-ME.txt"
            self.assertTrue(leia_me.exists())
            conteudo = leia_me.read_text(encoding="utf-8")
            self.assertIn("kit-web/", conteudo)
            self.assertIn("iniciar-windows.cmd", conteudo)
            self.assertIn("laboratorio.desktop", conteudo)

    def test_resolve_kit_target_unifica_extensions(self):
        import preparar
        kit_dir = Path("/tmp/teste_kit")
        item_win = {
            "name": "ext-teste-windows",
            "kind": "vsix",
            "target": "tools/windows-x64/extensions/minha-ext-1.0",
        }
        item_linux = {
            "name": "ext-teste-linux",
            "kind": "vsix",
            "target": "tools/linux-x64/extensions/minha-ext-1.0",
        }
        res_win = preparar.resolve_kit_target(item_win, kit_dir)
        res_linux = preparar.resolve_kit_target(item_linux, kit_dir)
        self.assertEqual(res_win, res_linux)
        self.assertTrue(str(res_win).endswith("tools/extensions/minha-ext-1.0"))

    def test_prune_kit_dead_weight(self):
        import preparar
        with tempfile.TemporaryDirectory() as folder:
            kit_dir = Path(folder)
            # Criar arquivos que devem ser podados
            terminfo = kit_dir / "tools" / "linux-x64" / "python" / "share" / "terminfo" / "x" / "xterm"
            terminfo.parent.mkdir(parents=True)
            terminfo.write_text("info")

            tcl = kit_dir / "tools" / "windows-x64" / "python" / "tcl" / "init.tcl"
            tcl.parent.mkdir(parents=True)
            tcl.write_text("tcl")

            inc = kit_dir / "tools" / "windows-x64" / "python" / "include" / "Python.h"
            inc.parent.mkdir(parents=True)
            inc.write_text("h")

            doc = kit_dir / "tools" / "linux-x64" / "sysroot" / "usr" / "share" / "doc" / "copyright"
            doc.parent.mkdir(parents=True)
            doc.write_text("doc")

            preparar.prune_kit_dead_weight(kit_dir)

            self.assertFalse(terminfo.exists())
            self.assertFalse(tcl.exists())
            self.assertFalse(inc.exists())
            self.assertFalse(doc.exists())


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

    def test_editor_vscode_launches_with_target_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "projetos/web").mkdir(parents=True)
            (root / "configuracoes/linux-x64").mkdir(parents=True)
            fake_code = root / "tools/code"
            fake_code.parent.mkdir(parents=True, exist_ok=True)
            fake_code.touch(mode=0o755)
            with patch.object(runtime, "ROOT", root), \
                 patch.object(runtime, "LOCAL_ROOT", root / "local"), \
                 patch.object(runtime, "STATE", root / "configuracoes/linux-x64"), \
                 patch.object(runtime, "VSCODE_USER", root / "configuracoes/vscode"), \
                 patch.object(runtime, "find_vscode", return_value=fake_code), \
                 patch.object(runtime, "WINDOWS", False), \
                 patch.object(runtime.sys, "platform", "linux"), \
                 patch.object(runtime.platform, "machine", return_value="x86_64"), \
                 patch("subprocess.Popen") as mock_popen:
                lab = runtime.Lab()
                res = lab.editor()
                self.assertTrue(res)
                mock_popen.assert_called_once()
                args, kwargs = mock_popen.call_args
                cmd = args[0]
                self.assertEqual(cmd[-1], str(lab.aluno.local_projetos / "web"))
                self.assertIn("--user-data-dir", cmd)
                self.assertIn("--new-window", cmd)
                self.assertEqual(cmd[cmd.index("--user-data-dir") + 1], str(lab.aluno.local_vscode_user_data))

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


class AlunoTests(unittest.TestCase):
    def test_validar_identificador(self):
        from kit.aluno import validar_identificador
        self.assertTrue(validar_identificador("joao-silva"))
        self.assertTrue(validar_identificador("maria123"))
        self.assertTrue(validar_identificador("aluno_1"))
        self.assertTrue(validar_identificador("aluno"))

        self.assertFalse(validar_identificador(""))
        self.assertFalse(validar_identificador("a"))  # < 2 chars
        self.assertFalse(validar_identificador("nome com espaco"))
        self.assertFalse(validar_identificador("nome*invalido"))
        self.assertFalse(validar_identificador("aluno@escola.edu.br"))

    def test_aluno_pastas_e_identidade(self):
        from kit.aluno import Aluno
        with tempfile.TemporaryDirectory() as d:
            kit_root = Path(d) / "pendrive"
            local_root = Path(d) / "local"
            aluno = Aluno("maria-dev", kit_root, local_root)
            aluno.garantir_pastas()

            self.assertTrue(aluno.pendrive_dir.exists())
            self.assertTrue(aluno.local_dir.exists())
            self.assertTrue(aluno.local_vscode_user_data.exists())
            self.assertTrue((aluno.pendrive_dir / "identidade.json").exists())
            self.assertTrue((aluno.local_dir / "identidade.json").exists())

    def test_dois_alunos_na_mesma_maquina_isolados(self):
        from kit.aluno import Aluno
        with tempfile.TemporaryDirectory() as d:
            kit_root = Path(d) / "pendrive"
            local_root = Path(d) / "local"
            aluno1 = Aluno("aluno-a", kit_root, local_root)
            aluno2 = Aluno("aluno-b", kit_root, local_root)
            aluno1.garantir_pastas()
            aluno2.garantir_pastas()

            self.assertNotEqual(aluno1.local_vscode_user_data, aluno2.local_vscode_user_data)
            self.assertNotEqual(aluno1.local_gitconfig, aluno2.local_gitconfig)

            aluno1.configurar_git("Aluno A", "a@escola.com")
            aluno2.configurar_git("Aluno B", "b@escola.com")

            self.assertIn("Aluno A", aluno1.local_gitconfig.read_text())
            self.assertIn("Aluno B", aluno2.local_gitconfig.read_text())

    def test_perfil_vscode_sincroniza_apenas_autorizados(self):
        from kit.aluno import Aluno
        with tempfile.TemporaryDirectory() as d:
            kit_root = Path(d) / "pendrive"
            local_root = Path(d) / "local"
            aluno = Aluno("joao", kit_root, local_root)
            aluno.garantir_pastas()
            aluno.inicializar_perfil_vscode()

            # 1. Arquivos autorizados
            (aluno.local_vscode_user_data / "User" / "settings.json").write_text('{"editor.fontSize": 16}')
            (aluno.local_vscode_user_data / "User" / "keybindings.json").write_text('[]')
            (aluno.local_vscode_user_data / "User" / "snippets").mkdir(parents=True)
            (aluno.local_vscode_user_data / "User" / "snippets" / "php.json").write_text('{}')

            # 2. Arquivos de cache proibidos que NÃO devem ser sincronizados
            (aluno.local_vscode_user_data / "Cache").mkdir()
            (aluno.local_vscode_user_data / "Cache" / "lixo.bin").write_text('cache')
            (aluno.local_vscode_user_data / "GPUCache").mkdir()
            (aluno.local_vscode_user_data / "GPUCache" / "gpu.bin").write_text('gpu')
            (aluno.local_vscode_user_data / "logs").mkdir()
            (aluno.local_vscode_user_data / "logs" / "sessao.log").write_text('log')
            (aluno.local_vscode_user_data / "workspaceStorage").mkdir()
            (aluno.local_vscode_user_data / "workspaceStorage" / "db.vscdb").write_text('vscdb')

            aluno.sincronizar_perfil_para_pendrive()

            # No pendrive:
            self.assertTrue((aluno.pendrive_vscode / "User/settings.json").exists())
            self.assertTrue((aluno.pendrive_vscode / "User/keybindings.json").exists())
            self.assertTrue((aluno.pendrive_vscode / "User/snippets/php.json").exists())

            # Caches NÃO devem estar no pendrive:
            self.assertFalse((aluno.pendrive_vscode / "Cache").exists())
            self.assertFalse((aluno.pendrive_vscode / "GPUCache").exists())
            self.assertFalse((aluno.pendrive_vscode / "logs").exists())
            self.assertFalse((aluno.pendrive_vscode / "workspaceStorage").exists())


class ExtensoesTests(unittest.TestCase):
    def test_obter_extensoes_instaladas(self):
        from kit.extensoes import obter_extensoes_instaladas
        with tempfile.TemporaryDirectory() as d:
            ext_dir = Path(d)
            (ext_dir / "redhat.java-1.39.0").mkdir()
            (ext_dir / "bmewburn.vscode-intelephense-client-1.12.0").mkdir()

            instaladas = obter_extensoes_instaladas(ext_dir)
            self.assertIn("redhat.java", instaladas)
            self.assertIn("bmewburn.vscode-intelephense-client", instaladas)

    def test_instalar_extensoes_locais_fallback(self):
        from kit.extensoes import instalar_extensoes_locais
        with tempfile.TemporaryDirectory() as d:
            kit_root = Path(d) / "pendrive"
            local_ext = Path(d) / "local_ext"
            (kit_root / "tools/extensions/minha-ext-1.0").mkdir(parents=True)
            (kit_root / "tools/extensions/minha-ext-1.0/package.json").write_text('{"name": "minha-ext"}')

            res = instalar_extensoes_locais(kit_root, local_ext, "linux-x64", "web", code_bin=None)
            self.assertIn("minha-ext-1.0", res)
            self.assertTrue((local_ext / "minha-ext-1.0/package.json").exists())


class SincronizacaoTests(unittest.TestCase):
    def test_sincronizacao_criacao_bidirecional(self):
        from kit.sincronizacao import sincronizar_projetos
        with tempfile.TemporaryDirectory() as d:
            pen = Path(d) / "pendrive/projetos"
            loc = Path(d) / "local/projetos"
            sync_dir = Path(d) / "pendrive/sincronizacao"

            (pen / "web").mkdir(parents=True)
            (loc / "web").mkdir(parents=True)

            (pen / "web/index.php").write_text("echo 'ola';")
            (loc / "web/estilo.css").write_text("body { color: red; }")

            relatorio = sincronizar_projetos(pen, loc, sync_dir, disciplina="web")
            self.assertTrue(relatorio.sucesso)
            self.assertIn("index.php", relatorio.copiados_para_local)
            self.assertIn("estilo.css", relatorio.copiados_para_pendrive)

            self.assertEqual((loc / "web/index.php").read_text(), "echo 'ola';")
            self.assertEqual((pen / "web/estilo.css").read_text(), "body { color: red; }")
            self.assertTrue((sync_dir / "snapshot_web.json").exists())

    def test_sincronizacao_modificacao_e_delecao(self):
        from kit.sincronizacao import sincronizar_projetos
        with tempfile.TemporaryDirectory() as d:
            pen = Path(d) / "pendrive/projetos"
            loc = Path(d) / "local/projetos"
            sync_dir = Path(d) / "pendrive/sincronizacao"

            (pen / "web").mkdir(parents=True)
            (loc / "web").mkdir(parents=True)

            # Estado inicial
            (loc / "web/arquivo1.txt").write_text("v1")
            (loc / "web/arquivo2.txt").write_text("remover")
            sincronizar_projetos(pen, loc, sync_dir, disciplina="web")

            # 1. Modificar arquivo1 no local
            (loc / "web/arquivo1.txt").write_text("v2-modificado")
            # 2. Deletar arquivo2 no local
            (loc / "web/arquivo2.txt").unlink()

            rel = sincronizar_projetos(pen, loc, sync_dir, disciplina="web")
            self.assertTrue(rel.sucesso)
            self.assertIn("arquivo1.txt", rel.copiados_para_pendrive)
            self.assertIn("arquivo2.txt", rel.deletados_no_pendrive)

            self.assertEqual((pen / "web/arquivo1.txt").read_text(), "v2-modificado")
            self.assertFalse((pen / "web/arquivo2.txt").exists())

    def test_sincronizacao_conflito_isolamento(self):
        from kit.sincronizacao import sincronizar_projetos
        with tempfile.TemporaryDirectory() as d:
            pen = Path(d) / "pendrive/projetos"
            loc = Path(d) / "local/projetos"
            sync_dir = Path(d) / "pendrive/sincronizacao"

            (loc / "web").mkdir(parents=True)
            (loc / "web/codigo.js").write_text("versao original")
            sincronizar_projetos(pen, loc, sync_dir, disciplina="web")

            # Ambas as pontas modificam com conteúdos conflitantes
            (loc / "web/codigo.js").write_text("versao do local (SSD)")
            (pen / "web/codigo.js").write_text("versao do pendrive")

            rel = sincronizar_projetos(pen, loc, sync_dir, disciplina="web")
            self.assertTrue(rel.sucesso)
            self.assertEqual(len(rel.conflitos), 1)
            self.assertIn("codigo.js", rel.conflitos)

            # Verifica pasta de conflitos criada
            conflitos_pasta = sync_dir / "conflitos"
            self.assertTrue(conflitos_pasta.exists())
            subpastas = list(conflitos_pasta.iterdir())
            self.assertEqual(len(subpastas), 1)

            pasta_conflito = subpastas[0]
            self.assertTrue((pasta_conflito / "codigo.js.local").exists())
            self.assertTrue((pasta_conflito / "codigo.js.pendrive").exists())
            self.assertTrue((pasta_conflito / "codigo.js.conflito.json").exists())

    def test_sincronizacao_ignora_arquivos_volateis(self):
        from kit.sincronizacao import sincronizar_projetos
        with tempfile.TemporaryDirectory() as d:
            pen = Path(d) / "pendrive/projetos"
            loc = Path(d) / "local/projetos"
            sync_dir = Path(d) / "pendrive/sincronizacao"

            (loc / "java/node_modules/pacote").mkdir(parents=True)
            (loc / "java/node_modules/pacote/lixo.js").write_text("lixo")
            (loc / "java/target/classes").mkdir(parents=True)
            (loc / "java/target/classes/Main.class").write_text("byte")
            (loc / "java/.DS_Store").write_text("mac")
            (loc / "java/temp.tmp").write_text("temp")
            (loc / "java/App.java").write_text("class App {}")

            rel = sincronizar_projetos(pen, loc, sync_dir, disciplina="java")
            self.assertTrue(rel.sucesso)
            self.assertIn("App.java", rel.copiados_para_pendrive)

            # Voláteis NÃO devem ter ido para o pendrive
            self.assertTrue((pen / "java/App.java").exists())
            self.assertFalse((pen / "java/node_modules").exists())
            self.assertFalse((pen / "java/target").exists())
            self.assertFalse((pen / "java/.DS_Store").exists())
            self.assertFalse((pen / "java/temp.tmp").exists())

    def test_sincronizacao_preserva_repositorio_git(self):
        from kit.sincronizacao import sincronizar_projetos
        with tempfile.TemporaryDirectory() as d:
            pen = Path(d) / "pendrive/projetos"
            loc = Path(d) / "local/projetos"
            sync_dir = Path(d) / "pendrive/sincronizacao"

            repo_loc = loc / "web/meu-repo"
            repo_loc.mkdir(parents=True)

            # Inicializa repo Git real
            subprocess.run(["git", "init", str(repo_loc)], check=True, capture_output=True)
            (repo_loc / "index.php").write_text("<?php echo 'v1';")
            subprocess.run(["git", "-C", str(repo_loc), "add", "."], check=True, capture_output=True)
            subprocess.run([
                "git", "-C", str(repo_loc),
                "-c", "user.name=AlunoTeste", "-c", "user.email=aluno@teste.com",
                "commit", "-m", "Commit inicial"
            ], check=True, capture_output=True)

            # Criar uma branch secundária
            subprocess.run(["git", "-C", str(repo_loc), "branch", "feature-login"], check=True, capture_output=True)

            # Sincronizar para o pendrive
            rel = sincronizar_projetos(pen, loc, sync_dir, disciplina="web")
            self.assertTrue(rel.sucesso)

            # Simular um NOVO computador (loc2) onde o aluno conectou o pendrive
            loc2 = Path(d) / "outro_computador/projetos"
            rel2 = sincronizar_projetos(pen, loc2, sync_dir, disciplina="web")
            self.assertTrue(rel2.sucesso)

            repo_restaurado = loc2 / "web/meu-repo"
            self.assertTrue((repo_restaurado / ".git").is_dir())
            self.assertTrue((repo_restaurado / "index.php").exists())

            # Verificar integridade Git no repositório restaurado
            log_proc = subprocess.run(
                ["git", "-C", str(repo_restaurado), "log", "--oneline"],
                check=True, capture_output=True, text=True
            )
            self.assertIn("Commit inicial", log_proc.stdout)

            branch_proc = subprocess.run(
                ["git", "-C", str(repo_restaurado), "branch"],
                check=True, capture_output=True, text=True
            )
            self.assertIn("feature-login", branch_proc.stdout)

    def test_lock_concorrencia(self):
        from kit.sincronizacao import LockSincronizacao
        with tempfile.TemporaryDirectory() as d:
            lock_file = Path(d) / "sync.lock"
            with LockSincronizacao(lock_file):
                self.assertTrue(lock_file.exists())
                # Tentar adquirir novamente no mesmo processo
                with self.assertRaises(RuntimeError):
                    with LockSincronizacao(lock_file):
                        pass
            # Após o with, lock deve ter sido liberado
            self.assertFalse(lock_file.exists())


if __name__ == "__main__":
    unittest.main()
