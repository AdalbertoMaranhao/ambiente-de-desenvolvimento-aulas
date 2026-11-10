📁 Projetos Java (POO)

Nesta pasta você desenvolve seus programas Java (.java).
Coloque seus arquivos de código-fonte dentro da pasta "src/".
O projeto já vem com a classe de demonstração em "src/OlaMundo.java".

Como executar:
  • No Windows (IntelliJ IDEA):
    Abra pelo menu do kit ("Iniciar Java.cmd").
    O IntelliJ instalado na máquina abrirá este projeto já com o JDK portátil (JDK-Kit) e a biblioteca sqlite-jdbc.
    Basta clicar no botão Run (▶) no canto superior direito para rodar a classe OlaMundo.

  • No Linux (VS Code):
    Abra pelo menu do kit ("iniciar-linux.sh").
    O VS Code instalado na máquina abrirá com as extensões e configurações do kit carregadas.
    Abra o arquivo src/OlaMundo.java e clique no botão "Run" acima de "public static void main".

  • No terminal do kit (Windows ou Linux):
    javac -cp "../../dependencias/java/sqlite-jdbc.jar;src" -d out src/OlaMundo.java   (Windows)
    javac -cp "../../dependencias/java/sqlite-jdbc.jar:src" -d out src/OlaMundo.java   (Linux)
    java -cp "../../dependencias/java/sqlite-jdbc.jar;out" OlaMundo                    (Windows)
    java -cp "../../dependencias/java/sqlite-jdbc.jar:out" OlaMundo                    (Linux)

Banco de Dados SQLite:
  Arquivo: banco.db (localizado nesta mesma pasta)
  No VS Code: Basta clicar no arquivo banco.db para abrir o SQLite Viewer integrado.
  No IntelliJ: Conecte o banco.db na aba Database (versão Ultimate) ou consulte as tabelas pelo menu do kit.
  Driver JDBC: dependencias/java/sqlite-jdbc.jar (já configurado no projeto)
  Conexão em Java:
    import java.sql.Connection;
    import java.sql.DriverManager;
    Connection conn = DriverManager.getConnection("jdbc:sqlite:banco.db");
