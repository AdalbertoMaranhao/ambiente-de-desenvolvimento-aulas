import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.io.File;

public class OlaMundo {
    public static void main(String[] args) {
        System.out.println("🚀 Laboratório Java (POO): Adoptium JDK + SQLite");
        
        File dbFile = new File("banco.db");
        String url = "jdbc:sqlite:" + dbFile.getAbsolutePath();

        try (Connection conn = DriverManager.getConnection(url)) {
            if (conn != null) {
                System.out.println("\n✓ Conexão com SQLite realizada com sucesso!");
                System.out.println("-------------------------------------------------------");
                System.out.printf("%-4s | %-15s | %-10s | %s%n", "ID", "Nome", "Matrícula", "Curso");
                System.out.println("-------------------------------------------------------");
                
                try (Statement stmt = conn.createStatement();
                     ResultSet rs = stmt.executeQuery("SELECT id, nome, matricula, curso FROM alunos ORDER BY id ASC")) {
                    while (rs.next()) {
                        System.out.printf("%-4d | %-15s | %-10s | %s%n",
                            rs.getInt("id"),
                            rs.getString("nome"),
                            rs.getString("matricula"),
                            rs.getString("curso")
                        );
                    }
                }
                System.out.println("-------------------------------------------------------");
            }
        } catch (Exception e) {
            System.out.println("Olá, mundo!");
            System.out.println("Nota: Para testar a conexão com o banco SQLite, inclua o driver sqlite-jdbc no classpath.");
            System.out.println("Detalhe: " + e.getMessage());
        }
    }
}
