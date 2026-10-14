from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus


SERVIDOR   = r"DanielaBello\MSSQLSERVER01"
BASE_DATOS = "StudyMatch"
DRIVER     = "ODBC Driver 17 for SQL Server"  


CADENA = (
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVIDOR};"
    f"DATABASE={BASE_DATOS};"
    f"Trusted_Connection=yes;"
    f"TrustServerCertificate=yes;"
)


DATABASE_URL = "mssql+pyodbc:///?odbc_connect=" + quote_plus(CADENA)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def probar_conexion():
    """Prueba rápida: python database.py"""
    with engine.connect() as conn:
        version = conn.execute(text("SELECT @@VERSION")).scalar()
        tablas = conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
        )).fetchall()
    print(" Conexión exitosa a SQL Server")
    print("   ", version.split("\n")[0])
    print(" Tablas encontradas en StudyMatch:", [t[0] for t in tablas])


if __name__ == "__main__":
    probar_conexion()