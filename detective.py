import pyodbc

candidatos = [
    r"DanielaBello",
    r"localhost",
    r".",
    r"DanielaBello\MSSQLSERVER01",
    r"localhost\MSSQLSERVER01",
    r"DanielaBello\SQLEXPRESS",
    r"localhost\SQLEXPRESS",
]

for servidor in candidatos:
    cadena = (f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={servidor};"
              f"DATABASE=StudyMatch;Trusted_Connection=yes;TrustServerCertificate=yes;")
    try:
        conn = pyodbc.connect(cadena, timeout=5)
        print(f"✅ ¡SÍ CONECTA! Usa SERVIDOR = r\"{servidor}\"")
        conn.close()
        break
    except Exception as e:
        print(f"❌ Falla con: {servidor}")