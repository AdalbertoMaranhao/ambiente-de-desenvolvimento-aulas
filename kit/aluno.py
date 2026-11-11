#!/usr/bin/env python3
"""
aluno.py — Gerenciamento de Identidade, Perfil do VS Code e Configurações Individuais.

Garante que cada aluno tenha um ambiente 100% isolado no computador e no pendrive:
  • Identificador validado ([a-zA-Z0-9_-]+).
  • Perfil individual do VS Code no SSD local com sincronização seletiva.
  • Identidade Git independente (GIT_CONFIG_GLOBAL).
  • Zero vazamento de caches ou telemetria para o pendrive.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys

try:
    from sincronizacao import sincronizar_projetos, RelatorioSincronizacao
except ImportError:
    try:
        from kit.sincronizacao import sincronizar_projetos, RelatorioSincronizacao
    except ImportError:
        sincronizar_projetos = None
        RelatorioSincronizacao = None

ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{2,32}$")

# Arquivos estritamente autorizados para sincronização entre computadores
ARQUIVOS_PERFIL_AUTORIZADOS = [
    "User/settings.json",
    "User/keybindings.json",
]


def validar_identificador(identificador: str) -> bool:
    """Valida se o identificador atende aos critérios de segurança (sem espaços, 2 a 32 chars)."""
    if not identificador or not isinstance(identificador, str):
        return False
    return bool(ID_REGEX.match(identificador.strip()))


class Aluno:
    """Representa a identidade de um aluno e seus diretórios isolados."""

    def __init__(self, identificador: str, kit_root: Path, local_root: Path):
        identificador = identificador.strip()
        if not validar_identificador(identificador):
            raise ValueError(
                f"Identificador inválido: '{identificador}'. "
                "Use apenas letras, números, hífen (-) ou sublinhado (_), entre 2 e 32 caracteres."
            )
        self.id = identificador
        self.kit_root = kit_root
        self.local_root = local_root

        # Estrutura no Pendrive (armazenamento persistente de transporte)
        self.pendrive_dir = self.kit_root / "alunos" / self.id
        self.pendrive_vscode = self.pendrive_dir / "vscode"
        self.pendrive_projetos = self.pendrive_dir / "projetos"
        self.pendrive_sync = self.pendrive_dir / "sincronizacao"

        # Estrutura no SSD Local (execução rápida na máquina do laboratório)
        self.local_dir = self.local_root / "alunos" / self.id
        self.local_vscode_user_data = self.local_dir / "vscode-user-data"
        self.local_projetos = self.local_dir / "projetos"
        self.local_estado = self.local_dir / "estado"
        self.local_gitconfig = self.local_dir / "gitconfig"

    def garantir_pastas(self) -> None:
        """Cria as estruturas de diretórios necessárias no computador e no pendrive."""
        self.pendrive_dir.mkdir(parents=True, exist_ok=True)
        self.pendrive_vscode.mkdir(parents=True, exist_ok=True)
        self.pendrive_projetos.mkdir(parents=True, exist_ok=True)
        self.pendrive_sync.mkdir(parents=True, exist_ok=True)

        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.local_vscode_user_data.mkdir(parents=True, exist_ok=True)
        (self.local_vscode_user_data / "User").mkdir(parents=True, exist_ok=True)
        self.local_projetos.mkdir(parents=True, exist_ok=True)
        self.local_estado.mkdir(parents=True, exist_ok=True)

        # Gravar metadados de identidade
        self.gravar_identidade()

    def gravar_identidade(self) -> None:
        """Registra o arquivo identidade.json no pendrive e localmente."""
        identidade_data = {
            "id": self.id,
            "criado_em": datetime.now().isoformat(),
            "versao_arquitetura": "2.0"
        }
        for base in [self.pendrive_dir, self.local_dir]:
            id_file = base / "identidade.json"
            if not id_file.exists():
                id_file.write_text(json.dumps(identidade_data, indent=2) + "\n", encoding="utf-8")

    def inicializar_perfil_vscode(self, template_settings_dir: Path | None = None) -> None:
        """
        Inicializa o perfil pessoal do VS Code:
          1. Se houver configurações salvas no pendrive do aluno, restaura-as.
          2. Senão, copia o modelo pedagógico do kit (settings.json pré-configurado).
          3. Não sobrescreve personalizações existentes.
        """
        local_user = self.local_vscode_user_data / "User"
        local_user.mkdir(parents=True, exist_ok=True)
        local_settings = local_user / "settings.json"

        # 1. Tentar restaurar do pendrive do aluno
        pendrive_user = self.pendrive_vscode / "User"
        pendrive_settings = pendrive_user / "settings.json"

        if not local_settings.exists():
            if pendrive_settings.exists():
                shutil.copy2(pendrive_settings, local_settings)
            elif template_settings_dir and (template_settings_dir / "User" / "settings.json").exists():
                shutil.copy2(template_settings_dir / "User" / "settings.json", local_settings)
            elif template_settings_dir and (template_settings_dir / "settings.json").exists():
                shutil.copy2(template_settings_dir / "settings.json", local_settings)
            else:
                # Configuração básica padrão com IAs desabilitadas e locale pt-br
                default_settings = {
                    "locale": "pt-br",
                    "telemetry.telemetryLevel": "off",
                    "update.mode": "none",
                    "editor.inlineSuggest.enabled": False,
                    "chat.disableAIFeatures": True,
                    "github.copilot.enable": {"*": False},
                    "editor.bracketPairColorization.enabled": True,
                    "editor.wordWrap": "on",
                    "errorlens.enabled": True,
                }
                local_settings.write_text(json.dumps(default_settings, indent=2) + "\n", encoding="utf-8")

        # Restaurar snippets pessoais se existirem
        pendrive_snippets = pendrive_user / "snippets"
        local_snippets = local_user / "snippets"
        if pendrive_snippets.exists() and not local_snippets.exists():
            shutil.copytree(pendrive_snippets, local_snippets, dirs_exist_ok=True)

        # Restaurar keybindings se existirem
        pendrive_kb = pendrive_user / "keybindings.json"
        local_kb = local_user / "keybindings.json"
        if pendrive_kb.exists() and not local_kb.exists():
            shutil.copy2(pendrive_kb, local_kb)

    def sincronizar_perfil_para_pendrive(self) -> None:
        """
        Exporta SOMENTE arquivos pessoais autorizados (settings, keybindings, snippets).
        Exclui categoricamente caches pesados (Cache, GPUCache, logs, workspaceStorage).
        """
        local_user = self.local_vscode_user_data / "User"
        pendrive_user = self.pendrive_vscode / "User"
        pendrive_user.mkdir(parents=True, exist_ok=True)

        if not local_user.exists():
            return

        # Sincronizar arquivos permitidos
        for rel_file in ARQUIVOS_PERFIL_AUTORIZADOS:
            src = self.local_vscode_user_data / rel_file
            dst = self.pendrive_vscode / rel_file
            if src.exists() and src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # Sincronizar snippets (pasta com arquivos .json)
        local_snippets = local_user / "snippets"
        pendrive_snippets = pendrive_user / "snippets"
        if local_snippets.exists() and local_snippets.is_dir():
            pendrive_snippets.mkdir(parents=True, exist_ok=True)
            for s in local_snippets.glob("*.json"):
                shutil.copy2(s, pendrive_snippets / s.name)

    def configurar_git(self, nome: str, email: str) -> None:
        """Define a identidade Git do aluno de forma estritamente isolada."""
        nome = nome.strip()
        email = email.strip()
        conteudo = (
            f"[user]\n"
            f"\tname = {nome}\n"
            f"\temail = {email}\n"
            f"[init]\n"
            f"\tdefaultBranch = main\n"
            f"[core]\n"
            f"\tautocrlf = input\n"
            f"\tlongpaths = true\n"
        )
        self.local_gitconfig.write_text(conteudo, encoding="utf-8")
        # Espelhar para o pendrive para portabilidade entre computadores
        (self.pendrive_dir / "gitconfig").write_text(conteudo, encoding="utf-8")

    def recuperar_git(self) -> None:
        """Restaura a identidade Git a partir do pendrive se não existir localmente."""
        pendrive_git = self.pendrive_dir / "gitconfig"
        if not self.local_gitconfig.exists() and pendrive_git.exists():
            shutil.copy2(pendrive_git, self.local_gitconfig)

    def inicializar_projetos_pedagogicos(self, disciplina: str) -> None:
        """
        Se o aluno ainda não possui projetos da disciplina nem no pendrive nem no local,
        copia o modelo inicial de projetos fornecido pelo kit.
        """
        pen_proj = self.pendrive_projetos / disciplina
        loc_proj = self.local_projetos / disciplina
        template_proj = self.kit_root / "projetos" / disciplina

        if template_proj.exists() and not any(pen_proj.iterdir() if pen_proj.exists() else []) and not any(loc_proj.iterdir() if loc_proj.exists() else []):
            loc_proj.mkdir(parents=True, exist_ok=True)
            pen_proj.mkdir(parents=True, exist_ok=True)
            shutil.copytree(template_proj, loc_proj, dirs_exist_ok=True)
            shutil.copytree(template_proj, pen_proj, dirs_exist_ok=True)

    def sincronizar_projetos(self, disciplina: str | None = None) -> RelatorioSincronizacao | None:
        """
        Executa sincronização bidirecional de 3 vias entre o pendrive e o SSD local.
        """
        if disciplina:
            self.inicializar_projetos_pedagogicos(disciplina)
        if sincronizar_projetos:
            return sincronizar_projetos(
                self.pendrive_projetos,
                self.local_projetos,
                self.pendrive_sync,
                disciplina=disciplina
            )
        return None


def obter_ou_solicitar_aluno(kit_root: Path, local_root: Path, interativo: bool = True) -> Aluno:
    """
    Obtém o aluno ativo ou solicita o identificador no terminal.
    Se já houver identificador registrado no pendrive, reutiliza automaticamente.
    """
    alunos_dir = kit_root / "alunos"
    alunos_dir.mkdir(parents=True, exist_ok=True)

    ativo_file = alunos_dir / "aluno_ativo.txt"
    aluno_id = None

    if ativo_file.exists():
        candidato = ativo_file.read_text(encoding="utf-8").strip()
        if validar_identificador(candidato):
            aluno_id = candidato

    # Se não há identificador ativo salvo, verificar se há apenas 1 pasta de aluno no pendrive
    if not aluno_id:
        pastas_alunos = [p.name for p in alunos_dir.iterdir() if p.is_dir() and validar_identificador(p.name)]
        if len(pastas_alunos) == 1:
            aluno_id = pastas_alunos[0]

    # Se ainda não possui ID, solicitar ao usuário (se interativo)
    if not aluno_id and interativo:
        print("\n" + "=" * 60)
        print("  👤 IDENTIFICAÇÃO DO ALUNO (PRIMEIRO USO)")
        print("=" * 60)
        print("Para que seu ambiente, extensões e projetos fiquem salvos")
        print("com segurança no seu pendrive, informe um identificador único.")
        print("Exemplo: 'joao-silva', 'maria123' ou sua matrícula.")
        print("-" * 60)

        while True:
            try:
                entrada = input("👉 Digite seu identificador [letras, números, hífen]: ").strip()
            except (EOFError, KeyboardInterrupt):
                entrada = "aluno"

            if validar_identificador(entrada):
                aluno_id = entrada
                break
            print("⚠️ Identificador inválido! Use apenas letras, números, '-' ou '_', sem espaços (2 a 32 caracteres).")

    if not aluno_id:
        aluno_id = "aluno"

    # Salvar aluno ativo no pendrive para as próximas execuções
    try:
        ativo_file.write_text(aluno_id + "\n", encoding="utf-8")
    except Exception:
        pass

    aluno = Aluno(aluno_id, kit_root, local_root)
    aluno.garantir_pastas()
    template_cfg = kit_root / "configuracoes" / "vscode"
    aluno.inicializar_perfil_vscode(template_cfg)
    aluno.recuperar_git()

    return aluno
