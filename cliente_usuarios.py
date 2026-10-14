import asyncio

class UsuarioNoEncontrado(Exception): pass
class ServicioUsuariosNoDisponible(Exception): pass
class ServicioUsuariosTimeout(Exception): pass

USUARIOS_MOCK = {
    1: {"usuario_id": 1, "nombre": "Juan Sebastián", "email": "juan@uni.edu",    "password": "1234", "carrera": "Ingeniería de Sistemas", "rol": "estudiante"},
    2: {"usuario_id": 2, "nombre": "Daniela",        "email": "daniela@uni.edu", "password": "1234", "carrera": "Medicina",               "rol": "estudiante"},
    3: {"usuario_id": 3, "nombre": "Gustavo",        "email": "gustavo@uni.edu", "password": "1234", "carrera": "Administración de Empresas", "rol": "estudiante"},
    4: {"usuario_id": 4, "nombre": "Administrador",  "email": "admin@uni.edu",   "password": "admin123", "carrera": "Todas",              "rol": "admin"},
}
_next_id = 5

def autenticar(email: str, password: str):
    for u in USUARIOS_MOCK.values():
        if u["email"].lower() == email.lower() and u["password"] == password:
            return u
    return None

def crear_usuario(nombre: str, email: str, password: str, carrera: str = "Ingeniería de Sistemas", rol: str = "estudiante") -> int:
    global _next_id
    if any(u["email"].lower() == email.lower() for u in USUARIOS_MOCK.values()):
        raise ValueError("El correo ya está registrado")
    uid = _next_id; _next_id += 1
    USUARIOS_MOCK[uid] = {"usuario_id": uid, "nombre": nombre, "email": email, "password": password, "carrera": carrera, "rol": rol}
    return uid

def obtener_usuario(uid: int):
    return USUARIOS_MOCK.get(uid)

async def consultar_usuario(usuario_id: int, *, latencia_ms=0,
                            simular_timeout=False, simular_caido=False):
    if latencia_ms and latencia_ms > 0:
        await asyncio.sleep(latencia_ms / 1000.0)
    if simular_caido:
        raise ServicioUsuariosNoDisponible("Servicio Usuarios no disponible temporalmente")
    if simular_timeout:
        await asyncio.sleep(6.0)
        raise ServicioUsuariosTimeout("No se pudo establecer comunicación con Servicio Usuarios (timeout)")
    if usuario_id not in USUARIOS_MOCK:
        raise UsuarioNoEncontrado(f"Usuario {usuario_id} no existe en Servicio Usuarios")
    return USUARIOS_MOCK[usuario_id]