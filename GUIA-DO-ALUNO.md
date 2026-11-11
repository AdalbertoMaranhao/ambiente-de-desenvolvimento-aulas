# 📘 Guia do Aluno: Laboratório Portátil de Programação

Este guia contém tudo o que você precisa saber para utilizar seu ambiente de desenvolvimento portátil em sala de aula e em casa, funcionando tanto no **Windows 11** quanto no **Linux Mint**, diretamente do seu pendrive.

---

## 1. Preparação do Pendrive

* **Capacidade recomendada:** Pendrive de **8 GB** ou superior.
* **Formatação recomendada:** **exFAT** (suporta arquivos grandes e funciona nativamente em Windows, Linux e Mac) ou **FAT32**.
* **Rótulo do pendrive (opcional):** `AULAS`.

> [!TIP]
> Deixe os arquivos do kit descompactados diretamente na **raiz** do seu pendrive.

---

## 2. Como Abrir o Ambiente no Laboratório

Conecte o pendrive no computador e abra a pasta da unidade:

| Sistema Operacional | O que fazer |
| :--- | :--- |
| **Windows 11** | Dê duplo clique no atalho: <br> `Iniciar <Sua-Disciplina>.cmd` (ex: `Iniciar Web.cmd`) |
| **Linux Mint** | Dê duplo clique no atalho: <br> `Iniciar <Sua-Disciplina>.desktop` *(ou abra o terminal na pasta e execute `./iniciar-linux.sh`)* |

O **Visual Studio Code** abrirá automaticamente já em **Português (Brasil)**, com o seu projeto carregado, compilador/interpretador configurado e o banco de dados conectado.

---

## 3. Onde Ficam seus Códigos?

Seus trabalhos ficam sempre dentro da pasta `projetos/`:

* **Desenvolvimento Web:** `projetos/web/` (`.php`, `.html`, `.css`, `.js`)
* **POO com Java:** `projetos/java/` (`.java`)

---

## 4. Como Testar seu Primeiro Programa

Cada kit vem com um arquivo de teste pronto:

### 🌐 Web (PHP)
1. Pressione `Ctrl + Shift + B` (ou menu `Terminal -> Run Task`).
2. Selecione **"🌐 Iniciar Servidor Web PHP"**.
3. Abra seu navegador em: `http://127.0.0.1:8080/ola-mundo.php`.

### ☕ Java (POO)
1. Abra o arquivo `src/OlaMundo.java` (ou clique no botão ▶ no canto superior direito do IntelliJ).
2. Clique no botão **`Run`** que aparece logo acima do método `public static void main`.

---

## 6. Recursos Visuais Pedagógicos no VS Code

Para ajudar você a aprender a programar e encontrar erros com rapidez:

* **Error Lens:** Destaca erros de sintaxe e avisos diretamente ao lado da linha que precisa de ajuste.
* **Indent Rainbow:** Colore as colunas de indentação para você nunca se perder nos blocos de código e chaves `{}`.
* **Better Comments:** Torna seus comentários coloridos:
  * `// ! Alerta importante` (em vermelho)
  * `// ? Pergunta ou dúvida` (em azul)
  * `// TODO: Tarefa pendente` (em laranja)
* **Auto Rename Tag:** Ao renomear uma tag HTML de abertura, a de fechamento é atualizada automaticamente.

> [!IMPORTANT]
> **Integridade e Aprendizado:** Assistentes de inteligência artificial (como Copilot ou preenchimentos mágicos de código) foram **desabilitados propositalmente** neste ambiente. O objetivo das aulas práticas é desenvolver sua autonomia, raciocínio lógico e domínio sobre a sintaxe.

---

## 7. Regra de Ouro ao Final da Aula

1. Salve todos os seus arquivos abertos no VS Code (`Ctrl + S`).
2. Feche o VS Code normalmente.
3. **Ejetar com segurança:** No Windows, clique em *"Remover hardware com segurança"* na bandeja do sistema antes de puxar o pendrive. No Linux, clique na seta de ejetar ao lado do pendrive no gerenciador de arquivos.

---

## 8. Dúvidas Frequentes

* **O Linux Mint diz que o arquivo não tem permissão para executar:**  
  O atalho `iniciar-linux.sh` ajusta as permissões automaticamente. Caso o pendrive tenha sido montado com a opção restritiva `noexec`, copie a pasta do kit para a sua pasta pessoal (`~/aulas`) e execute de lá.

* **Fiz uma alteração errada e quero recuperar meu código:**  
  O kit possui Git integrado. Abra o terminal integrado no VS Code e use `git status` e `git checkout` para verificar ou desfazer alterações locais.

* **Preciso de internet para usar o kit em casa?**  
  Não! Todos os compiladores, interpretadores, extensões e documentações foram baixados para dentro do pendrive e funcionam de forma 100% offline.
