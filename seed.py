from sqlalchemy import text
from database import engine

# === DATOS QUEMADOS ===
# Cada tupla: (materia_id, nombre, carrera, dia, hora, salon)
MATERIAS_SEED = [
    # materia_id=1: Sistemas Distribuidos (2 grupos)
    (1, "Sistemas Distribuidos",     "Ingeniería de Sistemas", "Lunes",    "08:00 AM - 10:00 AM", "A-301"),
    (1, "Sistemas Distribuidos",     "Ingeniería de Sistemas", "Miércoles","02:00 PM - 04:00 PM", "B-105"),
    
    # materia_id=2: Bases de Datos (2 grupos)
    (2, "Bases de Datos",            "Ingeniería de Sistemas", "Martes",   "10:00 AM - 12:00 PM", "B-204"),
    (2, "Bases de Datos",            "Ingeniería de Sistemas", "Jueves",   "08:00 AM - 10:00 AM", "C-301"),
    
    # materia_id=3: Ingeniería de Software (1 grupo)
    (3, "Ingeniería de Software",    "Ingeniería de Sistemas", "Miércoles","02:00 PM - 04:00 PM", "C-105"),
    
    # materia_id=4: Redes de Computadores (2 grupos)
    (4, "Redes de Computadores",     "Ingeniería de Sistemas", "Jueves",   "08:00 AM - 10:00 AM", "L-201"),
    (4, "Redes de Computadores",     "Ingeniería de Sistemas", "Viernes",  "10:00 AM - 12:00 PM", "M-102"),
    
    # materia_id=5: Anatomía Humana (2 grupos)
    (5, "Anatomía Humana",           "Medicina",               "Lunes",    "10:00 AM - 12:00 PM", "M-302"),
    (5, "Anatomía Humana",           "Medicina",               "Miércoles","08:00 AM - 10:00 AM", "N-201"),
    
    # materia_id=6: Finanzas Corporativas (1 grupo)
    (6, "Finanzas Corporativas",     "Administración de Empresas", "Martes","02:00 PM - 04:00 PM", "A-108"),
    
    # materia_id=7: Termodinámica (1 grupo)
    (7, "Termodinámica",             "Ingeniería Mecánica",    "Miércoles","08:00 AM - 10:00 AM", "T-201"),
    
    # materia_id=8: Programación Web (2 grupos)
    (8, "Programación Web",          "Ingeniería de Sistemas", "Jueves",   "06:00 PM - 08:00 PM", "A-301"),
    (8, "Programación Web",          "Ingeniería de Sistemas", "Sábado",   "08:00 AM - 10:00 AM", "L-105"),
]

# Relaciones usuario-materia (usan grupo_id que se generará como 1, 3, 7, 11, 8, 10)
RELACIONES_SEED = [
    (1, 1, "2026-2"),   # Usuario 1 → Grupo 1
    (1, 3, "2026-2"),   # Usuario 1 → Grupo 3
    (1, 7, "2026-2"),   # Usuario 1 → Grupo 7
    (1, 11, "2026-2"),  # Usuario 1 → Grupo 11
    (2, 8, "2026-2"),   # Usuario 2 → Grupo 8
    (3, 10, "2026-2"),  # Usuario 3 → Grupo 10
]

def seed_database():
    """Limpia, reinicia contadores y repuebla SQL Server con los datos quemados."""
    with engine.begin() as conn:
        # 1. Eliminar datos existentes
        conn.execute(text("DELETE FROM UsuarioMaterias"))
        conn.execute(text("DELETE FROM Materias"))
        
        # 2. ¡LA CLAVE! Reiniciar el contador IDENTITY a 0 (para que el siguiente sea 1)
        conn.execute(text("DBCC CHECKIDENT ('Materias', RESEED, 0)"))
        
        # 3. Insertar materias (grupo_id se generará automáticamente: 1, 2, 3...)
        for mid, nom, car, dia, hora, salon in MATERIAS_SEED:
            conn.execute(
                text("INSERT INTO Materias (materia_id, nombre, carrera, dia, hora, salon) VALUES (:id, :n, :c, :d, :h, :s)"),
                {"id": mid, "n": nom, "c": car, "d": dia, "h": hora, "s": salon},
            )
        
        # 4. Insertar relaciones usuario-materia
        for uid, gid, per in RELACIONES_SEED:
            conn.execute(
                text("INSERT INTO UsuarioMaterias (usuario_id, materia_id, periodo) VALUES (:u, :m, :p)"),
                {"u": uid, "m": gid, "p": per},
            )
            
    print("[seed] Datos quemados insertados en SQL Server correctamente.")
    print("[seed] Grupos disponibles:")
    print("  - Sistemas Distribuidos: 2 grupos (Lunes 8AM, Miércoles 2PM)")
    print("  - Bases de Datos: 2 grupos (Martes 10AM, Jueves 8AM)")
    print("  - Redes de Computadores: 2 grupos (Jueves 8AM, Viernes 10AM)")
    print("  - Anatomía Humana: 2 grupos (Lunes 10AM, Miércoles 8AM)")
    print("  - Programación Web: 2 grupos (Jueves 6PM, Sábado 8AM)")

if __name__ == "__main__":
    seed_database()