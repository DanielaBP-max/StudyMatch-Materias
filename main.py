from fastapi import FastAPI, Depends, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import asyncio, json, time, uuid

import database, schemas, seed
import cliente_usuarios as cu
from cliente_usuarios import (UsuarioNoEncontrado, ServicioUsuariosNoDisponible, ServicioUsuariosTimeout)

app = FastAPI(title="Servicio Materias - StudyMatch", version="1.5")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ============ CONSTANTES ============
PERIODOS_HABILITADOS = ["2026-2"]
TODOS_LOS_PERIODOS = ["2025-2", "2026-1", "2026-2", "2027-1"]
PERIODO_ACTIVO = "2026-2"

HORARIOS_MOCK = {
    1: {"dia": "Lunes",     "hora": "08:00 AM - 10:00 AM", "salon": "A-301"},
    2: {"dia": "Martes",    "hora": "10:00 AM - 12:00 PM", "salon": "B-204"},
    3: {"dia": "Miércoles", "hora": "02:00 PM - 04:00 PM", "salon": "C-105"},
    4: {"dia": "Jueves",    "hora": "08:00 AM - 10:00 AM", "salon": "L-201"},
    5: {"dia": "Viernes",   "hora": "08:00 AM - 10:00 AM", "salon": "M-001"},
    6: {"dia": "Lunes",     "hora": "04:00 PM - 06:00 PM", "salon": "D-402"},
    7: {"dia": "Miércoles", "hora": "08:00 AM - 10:00 AM", "salon": "T-110"},
}
SESSIONS = {}

@app.on_event("startup")
def _seed():
    try:
        seed.seed_database()
    except Exception as e:
        print("[seed] AVISO:", e)

# ============ ERRORES SEGÚN CONTRATO (Paso 7) ============
def err(status, code, msg):
    raise HTTPException(status_code=status, detail={"error": code, "mensaje": msg})

@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    payload = {"codigo": exc.status_code}
    if isinstance(exc.detail, dict):
        payload.update(exc.detail)
    else:
        payload.update({"error": "ERROR", "mensaje": str(exc.detail)})
    return JSONResponse(status_code=exc.status_code, content=payload)

@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"codigo": 400, "error": "DATOS_INVALIDOS",
                        "mensaje": "La solicitud contiene datos inválidos o incompletos"})

def _validar_usuario_remoto(usuario_id, lat=0, to=False, caido=False):
    return asyncio.run(cu.consultar_usuario(usuario_id, latencia_ms=lat, simular_timeout=to, simular_caido=caido))

def _traducir_fallo_usuarios(e):
    if isinstance(e, UsuarioNoEncontrado):          err(404, "USUARIO_NO_ENCONTRADO", str(e))
    if isinstance(e, ServicioUsuariosTimeout):      err(503, "USUARIOS_TIMEOUT", str(e))
    if isinstance(e, ServicioUsuariosNoDisponible): err(503, "USUARIOS_NO_DISPONIBLE", str(e))
    raise e

def usuario_session(request: Request):
    return SESSIONS.get(request.cookies.get("sm_session"))

def _o_login(request):
    uid = usuario_session(request)
    return uid if uid is not None else RedirectResponse("/login", status_code=303)

# Función auxiliar para leer catálogo
def _catalogo(db):
    rows = db.execute(text("SELECT grupo_id, materia_id, nombre, carrera, dia, hora, salon FROM Materias ORDER BY carrera, materia_id, grupo_id")).fetchall()
    catalogo_completo = []
    for x in rows:
        gid, mid, nom, car = x[0], x[1], x[2], x[3]
        catalogo_completo.append({
            "grupo_id": gid, "materia_id": mid, "nombre": nom, "carrera": car,
            "dia": x[4] or "Por asignar", "hora": x[5] or "Por asignar", "salon": x[6] or "Por asignar",
        })
    return catalogo_completo

# ============ API DEL CONTRATO (Paso 4 y 5) ============
@app.get("/api/v1/materias", tags=["Materias"])
def listar_materias(db: Session = Depends(database.get_db),
                    simular_latencia: int = Query(0, ge=0), simular_fallo: bool = Query(False)):
    if simular_latencia > 0: time.sleep(simular_latencia / 1000.0)
    if simular_fallo: err(500, "ERROR_INTERNO", "Fallo interno simulado en el catálogo")
    rows = db.execute(text("SELECT materia_id, nombre FROM Materias ORDER BY materia_id")).fetchall()
    return [{"materia_id": r[0], "nombre": r[1]} for r in rows]

@app.get("/api/v1/materias/{materia_id}", tags=["Materias"])
def consultar_materia(materia_id: int, db: Session = Depends(database.get_db)):
    if materia_id <= 0: err(400, "ID_INVALIDO", "materia_id debe ser un entero positivo")
    r = db.execute(text("SELECT materia_id, nombre FROM Materias WHERE materia_id = :id"), {"id": materia_id}).fetchone()
    if not r: err(404, "MATERIA_NO_ENCONTRADA", "La materia solicitada no existe")
    return {"materia_id": r[0], "nombre": r[1]}

@app.get("/api/v1/usuarios/{usuario_id}/materias", tags=["Usuario-Materia"])
def obtener_materias_usuario(usuario_id: int, db: Session = Depends(database.get_db),
                             latencia_usuario: int = Query(0, ge=0),
                             simular_timeout_usuario: bool = Query(False),
                             simular_caido_usuario: bool = Query(False)):
    if usuario_id <= 0: err(400, "ID_INVALIDO", "usuario_id debe ser un entero positivo")
    try:
        _validar_usuario_remoto(usuario_id, latencia_usuario, simular_timeout_usuario, simular_caido_usuario)
    except Exception as e:
        _traducir_fallo_usuarios(e)
    rows = db.execute(text("SELECT m.materia_id, m.nombre FROM UsuarioMaterias um "
                           "JOIN Materias m ON um.materia_id = m.materia_id WHERE um.usuario_id = :uid"),
                      {"uid": usuario_id}).fetchall()
    return {"usuario_id": usuario_id, "materias": [{"materia_id": r[0], "nombre": r[1]} for r in rows]}

@app.post("/api/v1/usuarios/{usuario_id}/materias", status_code=201, tags=["Usuario-Materia"])
def asociar_materia(usuario_id: int, data: schemas.AsociarMateria, db: Session = Depends(database.get_db),
                    latencia_usuario: int = Query(0, ge=0),
                    simular_timeout_usuario: bool = Query(False),
                    simular_caido_usuario: bool = Query(False),
                    simular_fallo_bd: bool = Query(False)):
    if usuario_id <= 0 or data.materia_id <= 0: err(400, "ID_INVALIDO", "Los IDs deben ser positivos")
    m = db.execute(text("SELECT materia_id FROM Materias WHERE materia_id = :id"), {"id": data.materia_id}).fetchone()
    if not m: err(404, "MATERIA_NO_ENCONTRADA", "La materia solicitada no existe")
    try:
        _validar_usuario_remoto(usuario_id, latencia_usuario, simular_timeout_usuario, simular_caido_usuario)
    except Exception as e:
        db.rollback(); _traducir_fallo_usuarios(e)
    try:
        db.execute(text("INSERT INTO UsuarioMaterias (usuario_id, materia_id, periodo) VALUES (:u, :m, :p)"),
                   {"u": usuario_id, "m": data.materia_id, "p": PERIODO_ACTIVO})
        if simular_fallo_bd: raise RuntimeError("Caída simulada de BD antes del commit")
        db.commit()
    except IntegrityError:
        db.rollback(); err(400, "ASOCIACION_DUPLICADA", "La materia ya está asociada a este usuario")
    except Exception:
        db.rollback(); err(500, "ERROR_INTERNO", "Fallo parcial: la asociación no se persistió")
    return {"usuario_id": usuario_id, "materia_id": data.materia_id, "mensaje": "Materia asociada correctamente"}

@app.delete("/api/v1/usuarios/{usuario_id}/materias/{materia_id}", tags=["Usuario-Materia"])
def retirar_asociacion(usuario_id: int, materia_id: int, db: Session = Depends(database.get_db)):
    if usuario_id <= 0 or materia_id <= 0: err(400, "ID_INVALIDO", "Los IDs deben ser positivos")
    res = db.execute(text("DELETE FROM UsuarioMaterias WHERE usuario_id = :u AND materia_id = :m"),
                     {"u": usuario_id, "m": materia_id})
    db.commit()
    if res.rowcount == 0: err(404, "ASOCIACION_NO_ENCONTRADA", "No existe esa asociación para eliminar")
    return {"mensaje": "Asociación eliminada correctamente"}

@app.post("/admin/seed", tags=["Admin"])
def re_seed():
    seed.seed_database(); return {"mensaje": "BD repoblada con datos quemados"}

# ============ PORTAL WEB ============
@app.get("/", include_in_schema=False)
def raiz(request: Request):
    return RedirectResponse("/tablero" if usuario_session(request) else "/login", status_code=303)

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def pagina_login(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login", include_in_schema=False)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    u = cu.autenticar(email, password)
    if not u:
        return templates.TemplateResponse(request=request, name="login.html",
                                          context={"error": "Credenciales inválidas"}, status_code=401)
    sid = uuid.uuid4().hex; SESSIONS[sid] = u["usuario_id"]
    resp = RedirectResponse("/tablero", status_code=303); resp.set_cookie("sm_session", sid)
    return resp

@app.get("/registro", response_class=HTMLResponse, include_in_schema=False)
def pagina_registro(request: Request):
    return templates.TemplateResponse(request=request, name="registro.html",
                                      context={"error": None, "nuevo_id": None,
                                               "todas_carreras": ["Ingeniería de Sistemas", "Medicina", 
                                                                  "Administración de Empresas", "Ingeniería Mecánica"]})
                                                                  

@app.post("/registro", include_in_schema=False)
def registro(request: Request, nombre: str = Form(...), email: str = Form(...), 
             password: str = Form(...), carrera: str = Form("Ingeniería de Sistemas")):
    try:
        uid = cu.crear_usuario(nombre, email, password, carrera)
    except ValueError as ve:
        return templates.TemplateResponse(request=request, name="registro.html",
                                          context={"error": str(ve), "nuevo_id": None,
                                                   "todas_carreras": ["Ingeniería de Sistemas", "Medicina", 
                                                                      "Administración de Empresas", "Ingeniería Mecánica"]})
    
    # ✅ Solo crear el usuario, SIN inscribir materias automáticamente
    return templates.TemplateResponse(request=request, name="registro.html",
                                      context={"error": None, "nuevo_id": uid, 
                                               "nuevo_email": email,
                                               "nuevo_nombre": nombre,
                                               "carrera": carrera})

@app.get("/tablero", response_class=HTMLResponse, include_in_schema=False)
def tablero(request: Request):
    r = _o_login(request)
    if not isinstance(r, int): return r
    return templates.TemplateResponse(request=request, name="tablero.html",
                                      context={"usuario": cu.obtener_usuario(r)})



@app.get("/planificacion", response_class=HTMLResponse, include_in_schema=False)
def planificacion(request: Request):
    r = _o_login(request)
    if not isinstance(r, int): return r
    return templates.TemplateResponse(request=request, name="planificacion.html",
                                      context={"usuario": cu.obtener_usuario(r)})

@app.get("/catalogo", response_class=HTMLResponse, include_in_schema=False)
def catalogo(request: Request, msg: str = None, ok: str = None, db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    es_admin = usuario.get("rol") == "admin"
    
    # Consultar TODAS las materias desde la BD (en tiempo real)
    rows = db.execute(text("SELECT grupo_id, materia_id, nombre, carrera, dia, hora, salon FROM Materias ORDER BY carrera, materia_id, grupo_id")).fetchall()
    catalogo_completo = []
    for x in rows:
        gid, mid, nom, car = x[0], x[1], x[2], x[3]
        catalogo_completo.append({
            "grupo_id": gid, "materia_id": mid, "nombre": nom, "carrera": car,
            "dia": x[4] or "Por asignar", "hora": x[5] or "Por asignar", "salon": x[6] or "Por asignar",
        })
    
    # Agrupar por carrera
    agrupado = {}
    for m in catalogo_completo:
        agrupado.setdefault(m["carrera"], []).append(m)
        
    return templates.TemplateResponse(
        request=request, name="catalogo.html",
        context={"usuario": usuario, "catalogo": agrupado, "periodo_activo": PERIODO_ACTIVO,
                 "msg": msg, "ok": ok == "1" if ok else False, "es_admin": es_admin}
    )
    
@app.post("/web/agregar_materia", include_in_schema=False)
def web_agregar_materia(request: Request, nombre: str = Form(...), carrera: str = Form(...),
                        dia: str = Form(...), hora: str = Form(...), salon: str = Form(...),
                        db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/catalogo?msg=Error:+solo+administradores+pueden+agregar+materias&ok=0", status_code=303)
    
    # ✅ VALIDACIÓN: Verificar conflicto de horario y salón (no por nombre)
    conflicto = db.execute(text("""
        SELECT grupo_id, nombre, dia, hora, salon FROM Materias 
        WHERE dia = :d AND hora = :h AND salon = :s
    """), {"d": dia, "h": hora, "s": salon}).fetchone()
    
    if conflicto:
        return RedirectResponse(
            f"/catalogo?msg=Error:+conflicto+de+horario.+Ya+existe+el+grupo+G{conflicto[0]}+'{conflicto[1]}'+"
            f"en+{conflicto[2]}+{conflicto[3]}+({conflicto[4]}).+Usa+otro+día,+hora+o+salón.&ok=0", 
            status_code=303
        )
    
    # ✅ CALCULAR materia_id: Si la materia ya existe, reutilizar su ID; si es nueva, asignar el siguiente
    materia_existente = db.execute(text("SELECT materia_id FROM Materias WHERE nombre = :n"), {"n": nombre}).fetchone()
    
    if materia_existente:
        # Si la materia ya existe, reutilizar su materia_id (para que todos los grupos compartan el mismo ID)
        nuevo_materia_id = materia_existente[0]
    else:
        # Si es una materia nueva, calcular el siguiente ID disponible
        max_id = db.execute(text("SELECT ISNULL(MAX(materia_id), 0) FROM Materias")).fetchone()[0]
        nuevo_materia_id = max_id + 1
    
    # ✅ SQL Server genera el grupo_id automáticamente (IDENTITY)
    result = db.execute(
        text("INSERT INTO Materias (materia_id, nombre, carrera, dia, hora, salon) OUTPUT INSERTED.grupo_id VALUES (:id, :n, :c, :d, :h, :s)"),
        {"id": nuevo_materia_id, "n": nombre, "c": carrera, "d": dia, "h": hora, "s": salon}
    )
    nuevo_grupo_id = result.fetchone()[0]
    db.commit()
    
    return RedirectResponse(f"/catalogo?msg=Grupo+G{nuevo_grupo_id}+de+'{nombre}'+agregado+exitosamente+(materia_id+{nuevo_materia_id})&ok=1", status_code=303)

@app.post("/web/actualizar_materia", include_in_schema=False)
def web_actualizar_materia(request: Request, materia_id: int = Form(...), nombre: str = Form(...),
                           carrera: str = Form(...), dia: str = Form(...), hora: str = Form(...),
                           salon: str = Form(...), db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/catalogo?msg=Error:+solo+administradores+pueden+actualizar+materias&ok=0", status_code=303)
    
    db.execute(text("UPDATE Materias SET nombre=:n, carrera=:c, dia=:d, hora=:h, salon=:s WHERE materia_id=:id"),
               {"n": nombre, "c": carrera, "d": dia, "h": hora, "s": salon, "id": materia_id})
    db.commit()
    
    return RedirectResponse(f"/catalogo?msg=Materia+actualizada+exitosamente+(ID+{materia_id})&ok=1", status_code=303)

@app.post("/web/eliminar_materia_catalogo", include_in_schema=False)
def web_eliminar_materia_catalogo(request: Request, materia_id: int = Form(...),
                                  db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/catalogo?msg=Error:+solo+administradores+pueden+eliminar+materias&ok=0", status_code=303)
    
    # materia_id aquí es en realidad el grupo_id
    grupo_id = materia_id
    
    # Verificar si hay estudiantes inscritos en este grupo
    inscritos = db.execute(text("SELECT COUNT(*) FROM UsuarioMaterias WHERE materia_id = :gid"), {"gid": grupo_id}).fetchone()[0]
    
    if inscritos > 0:
        return RedirectResponse(
            f"/catalogo?msg=Error:+no+se+puede+eliminar+el+grupo+G{grupo_id}+porque+tien+{inscritos}+estudiante(s)+inscrito(s).+Elimina+las+inscripciones+primero.&ok=0", 
            status_code=303
        )
    
    # Eliminar el grupo de la base de datos
    db.execute(text("DELETE FROM Materias WHERE grupo_id = :gid"), {"gid": grupo_id})
    db.commit()
    
    return RedirectResponse(f"/catalogo?msg=Grupo+G{grupo_id}+eliminado+correctamente+de+la+base+de+datos&ok=1", status_code=303)

@app.get("/inscripcion", response_class=HTMLResponse, include_in_schema=False)
def pagina_inscripcion(request: Request, db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    cat = _catalogo(db)
    
    estudiantes_lista = [
        {"usuario_id": uid, "nombre": u["nombre"], "carrera": u["carrera"]}
        for uid, u in cu.USUARIOS_MOCK.items()
        if u.get("rol") != "admin"
    ] if usuario.get("rol") == "admin" else []
    
    return templates.TemplateResponse(request=request, name="inscripcion.html",
                                      context={"usuario": usuario, "periodos": PERIODOS_HABILITADOS,
                                               "periodo_activo": PERIODO_ACTIVO, "catalogo": cat,
                                               "catalogo_json": json.dumps(cat), "msg": None, "ok": False,
                                               "carrera_usuario": usuario.get("carrera", "Desconocida"),
                                               "estudiantes": estudiantes_lista})

@app.post("/web/inscripcion", include_in_schema=False)
def web_inscripcion(request: Request, periodo: str = Form(...), grupo_id: int = Form(...),
                    usuario_destino: int = Form(None),
                    db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario_logueado = cu.obtener_usuario(r)
    
    estudiantes_lista = [
        {"usuario_id": uid, "nombre": u["nombre"], "carrera": u["carrera"]}
        for uid, u in cu.USUARIOS_MOCK.items()
        if u.get("rol") != "admin"
    ] if usuario_logueado.get("rol") == "admin" else []
    
    if usuario_logueado.get("rol") == "admin" and usuario_destino:
        uid = usuario_destino
        usuario_dest = cu.obtener_usuario(uid)
        if not usuario_dest:
            return RedirectResponse("/inscripcion?msg=Error:+estudiante+no+encontrado&ok=0", status_code=303)
        carrera_usuario = usuario_dest.get("carrera", "Desconocida")
    else:
        uid = r
        carrera_usuario = usuario_logueado.get("carrera", "Desconocida")

    cat = _catalogo(db)
    ctx = {"usuario": usuario_logueado, "periodos": PERIODOS_HABILITADOS,
           "periodo_activo": PERIODO_ACTIVO, "catalogo": cat, "catalogo_json": json.dumps(cat),
           "carrera_usuario": carrera_usuario,
           "estudiantes": estudiantes_lista}
    def render(msg, ok):
        ctx.update({"msg": msg, "ok": ok})
        return templates.TemplateResponse(request=request, name="inscripcion.html", context=ctx)

    if periodo not in PERIODOS_HABILITADOS:
        return render(f"Error 400: El periodo '{periodo}' no está habilitado.", False)

    g = db.execute(text("SELECT grupo_id, materia_id, nombre, carrera, dia, hora, salon FROM Materias WHERE grupo_id = :gid"), {"gid": grupo_id}).fetchone()
    if not g:
        return render("Error 404: el grupo no existe en el catálogo.", False)

    if g[3] != carrera_usuario:
        return render(f"Error 400: No puedes inscribir '{g[2]}' (pertenece a {g[3]}) porque la carrera del estudiante es {carrera_usuario}.", False)

    # VALIDACIÓN: No permitir inscribirse en múltiples grupos de la misma materia
    ya_inscrito = db.execute(text("""
        SELECT COUNT(*) FROM UsuarioMaterias um 
        JOIN Materias m ON um.materia_id = m.grupo_id 
        WHERE um.usuario_id = :u AND m.materia_id = :mid
    """), {"u": uid, "mid": g[1]}).fetchone()[0]
    
    if ya_inscrito > 0:
        grupo_actual = db.execute(text("""
            SELECT m.dia, m.hora, m.salon FROM UsuarioMaterias um 
            JOIN Materias m ON um.materia_id = m.grupo_id 
            WHERE um.usuario_id = :u AND m.materia_id = :mid
        """), {"u": uid, "mid": g[1]}).fetchone()
        
        return render(
            f"Error 400: Ya estás inscrito en '{g[2]}' (Grupo actual: {grupo_actual[0]} {grupo_actual[1]} - {grupo_actual[2]}). "
            f"No puedes inscribirte en otro grupo de la misma materia, aunque tenga diferente horario o salón.", 
            False
        )

    try:
        _validar_usuario_remoto(uid)
    except Exception as e:
        if isinstance(e, UsuarioNoEncontrado):          return render("Error 404: usuario no existe.", False)
        if isinstance(e, ServicioUsuariosTimeout):      return render("Error 503: timeout con servicio Usuarios.", False)
        if isinstance(e, ServicioUsuariosNoDisponible): return render("Error 503: servicio Usuarios no disponible.", False)

    # INSERTAR en la base de datos
    try:
        db.execute(text("INSERT INTO UsuarioMaterias (usuario_id, materia_id, periodo) VALUES (:u, :m, :p)"),
                   {"u": uid, "m": grupo_id, "p": periodo})
        db.commit()
    except IntegrityError:
        db.rollback()
        return render(f"Error 400: ya estás inscrito en este grupo específico ({g[2]} - {g[4]} {g[5]}).", False)
    
    nombre_estudiante = cu.obtener_usuario(uid)["nombre"] if cu.obtener_usuario(uid) else "Estudiante"
    return render(f"Inscripción exitosa: {g[2]} ({g[4]} {g[5]} - {g[6]}) en el periodo {periodo} para {nombre_estudiante}.", True)


@app.get("/perfil", response_class=HTMLResponse, include_in_schema=False)
def perfil(request: Request, estudiante_id: int = None, msg: str = None, ok: str = None, 
           db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    
    if usuario.get("rol") == "admin":
        # Lista dinámica de estudiantes
        estudiantes_info = [
            {"usuario_id": uid, "nombre": u["nombre"], "email": u["email"], "carrera": u["carrera"]}
            for uid, u in cu.USUARIOS_MOCK.items()
            if u.get("rol") != "admin"
        ]
        
        estudiante_seleccionado = None
        materias_estudiante = []
        catalogo_materias = []
        
        # ✅ Obtener TODAS las materias del catálogo para el formulario de inscripción
        rows_catalogo = db.execute(text("SELECT grupo_id, materia_id, nombre, carrera, dia, hora, salon FROM Materias ORDER BY carrera, materia_id, grupo_id")).fetchall()
        for x in rows_catalogo:
            catalogo_materias.append({
                "grupo_id": x[0], "materia_id": x[1], "nombre": x[2], "carrera": x[3],
                "dia": x[4] or "Por asignar", "hora": x[5] or "Por asignar", "salon": x[6] or "Por asignar",
            })
        
        if estudiante_id and estudiante_id in cu.USUARIOS_MOCK:
            u = cu.USUARIOS_MOCK[estudiante_id]
            estudiante_seleccionado = {
                "usuario_id": u["usuario_id"],
                "nombre": u["nombre"],
                "email": u["email"],
                "carrera": u["carrera"]
            }
            
            # Obtener materias inscritas del estudiante
            rows = db.execute(text("""
            SELECT m.grupo_id, m.materia_id, m.nombre, m.dia, m.hora, m.salon, um.periodo
            FROM UsuarioMaterias um
            JOIN Materias m ON um.materia_id = m.grupo_id
            WHERE um.usuario_id = :u
            ORDER BY m.materia_id, m.grupo_id
            """), {"u": estudiante_id}).fetchall()
            
            for x in rows:
                materias_estudiante.append({
                    "grupo_id": x[0], "materia_id": x[1], "nombre": x[2],
                    "dia": x[3] or "Por asignar",
                    "hora": x[4] or "Por asignar", 
                    "salon": x[5] or "Por asignar",
                    "periodo": x[6]
                })
        
        return templates.TemplateResponse(request=request, name="perfil.html",
                                          context={
                                              "usuario": usuario, 
                                              "estudiantes_info": estudiantes_info,
                                              "estudiante_seleccionado": estudiante_seleccionado,
                                              "materias_estudiante": materias_estudiante,
                                              "catalogo_materias": catalogo_materias,
                                              "todos_los_periodos": TODOS_LOS_PERIODOS,
                                              "periodo_activo": PERIODO_ACTIVO,
                                              "msg": msg, 
                                              "ok": ok == "1" if ok else False
                                          })
    else:
        return templates.TemplateResponse(request=request, name="perfil.html",
                                          context={"usuario": usuario})

@app.get("/horario", response_class=HTMLResponse, include_in_schema=False)
def horario(request: Request, periodo: str = None, ok: str = None, error: str = None,
            db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)

    periodo_consulta = periodo or PERIODO_ACTIVO
    error_msg = error
    clases = []

    if periodo_consulta not in PERIODOS_HABILITADOS:
        error_msg = f"⚠️ El periodo '{periodo_consulta}' no está habilitado. El periodo activo es {PERIODO_ACTIVO}."
    else:
        if usuario.get("rol") == "admin":
            # ✅ CONSULTA CORREGIDA
            rows = db.execute(text("""
            SELECT um.usuario_id, m.grupo_id, m.materia_id, m.nombre, m.carrera, m.dia, m.hora, m.salon, um.periodo, u.nombre AS estudiante_nombre
            FROM UsuarioMaterias um
            JOIN Materias m ON um.materia_id = m.grupo_id
            JOIN (VALUES (1, 'Juan Sebastián'), (2, 'Daniela'), (3, 'Gustavo')) AS u(usuario_id, nombre) 
            ON um.usuario_id = u.usuario_id
            WHERE um.periodo = :p ORDER BY um.usuario_id, m.materia_id
            """), {"p": periodo_consulta}).fetchall()
            
            for x in rows:
                c = {"usuario_id": x[0], "grupo_id": x[1], "materia_id": x[2], "nombre": x[3], "carrera": x[4], "periodo": x[8], "estudiante_nombre": x[9]}
                c["dia"] = x[5] or "Por asignar"
                c["hora"] = x[6] or "Por asignar"
                c["salon"] = x[7] or "Por asignar"
                clases.append(c)
        else:
            rows = db.execute(text("""
            SELECT m.grupo_id, m.materia_id, m.nombre, m.carrera, m.dia, m.hora, m.salon, um.periodo 
            FROM UsuarioMaterias um 
            JOIN Materias m ON um.materia_id = m.grupo_id 
            WHERE um.usuario_id = :u AND um.periodo = :p 
            ORDER BY m.materia_id
            """), {"u": r, "p": periodo_consulta}).fetchall()
            
            for x in rows:
                c = {"grupo_id": x[0], "materia_id": x[1], "nombre": x[2], "carrera": x[3], "periodo": x[7]}
                c["dia"] = x[4] or "Por asignar"
                c["hora"] = x[5] or "Por asignar"
                c["salon"] = x[6] or "Por asignar"
                clases.append(c)

    return templates.TemplateResponse(request=request, name="horario.html",
                                      context={"usuario": usuario, "periodo": periodo_consulta,
                                               "clases": clases, "ok": ok, "error": error_msg,
                                               "periodos_habilitados": PERIODOS_HABILITADOS,
                                               "todos_los_periodos": TODOS_LOS_PERIODOS})

@app.post("/web/eliminar_materia", include_in_schema=False)
def web_eliminar_materia(request: Request, materia_id: int = Form(...),
                         db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    uid = r
    if uid <= 0 or materia_id <= 0:
        return RedirectResponse("/horario?error=ID+invalido", status_code=303)
    res = db.execute(text("DELETE FROM UsuarioMaterias WHERE usuario_id = :u AND materia_id = :m"),
                     {"u": uid, "m": materia_id})
    db.commit()
    if res.rowcount == 0:
        return RedirectResponse("/horario?error=No+encontrada", status_code=303)
    return RedirectResponse("/horario?ok=Eliminada", status_code=303)

@app.get("/salir", include_in_schema=False)
def salir(request: Request):
    SESSIONS.pop(request.cookies.get("sm_session"), None)
    resp = RedirectResponse("/login", status_code=303); resp.delete_cookie("sm_session")
    return resp

@app.get("/pruebas", response_class=HTMLResponse, include_in_schema=False)
def panel_pruebas(request: Request):
    return templates.TemplateResponse(request=request, name="pruebas.html", context={})

# ============ PANEL DE ADMINISTRACIÓN ============
@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def panel_admin(request: Request, msg: str = None, ok: str = None, db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    # ✅ CONSULTA CORREGIDA: incluir grupo_id
    materias_rows = db.execute(text("SELECT grupo_id, materia_id, nombre, carrera, dia, hora, salon FROM Materias ORDER BY carrera, materia_id, grupo_id")).fetchall()
    materias = [{"grupo_id": x[0], "materia_id": x[1], "nombre": x[2], "carrera": x[3], 
                 "dia": x[4] or "Por asignar", "hora": x[5] or "Por asignar", "salon": x[6] or "Por asignar"} for x in materias_rows]
    
    return templates.TemplateResponse(request=request, name="admin.html",
                                      context={"usuario": usuario, "materias": materias,
                                               "periodos_habilitados": PERIODOS_HABILITADOS,
                                               "todos_los_periodos": TODOS_LOS_PERIODOS,
                                               "periodo_activo": PERIODO_ACTIVO,
                                               "msg": msg, "ok": ok == "1" if ok else False})

@app.post("/admin/agregar_periodo", include_in_schema=False)
def admin_agregar_periodo(request: Request, nuevo_periodo: str = Form(...)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    if nuevo_periodo not in TODOS_LOS_PERIODOS:
        TODOS_LOS_PERIODOS.append(nuevo_periodo)
        return RedirectResponse(f"/admin?msg=Periodo+{nuevo_periodo}+agregado+correctamente&ok=1", status_code=303)
    else:
        return RedirectResponse("/admin?msg=Error:+el+periodo+ya+existe&ok=0", status_code=303)

@app.post("/admin/actualizar_estudiante", include_in_schema=False)
def admin_actualizar_estudiante(request: Request, usuario_id: int = Form(...),
                                nombre: str = Form(...), email: str = Form(...),
                                carrera: str = Form(...)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    # Validar que el estudiante exista
    if usuario_id not in cu.USUARIOS_MOCK:
        return RedirectResponse("/perfil?msg=Error:+estudiante+no+encontrado&ok=0", status_code=303)
    
    # Validar que el email no esté duplicado (excepto el mismo usuario)
    email_existe = any(
        u["email"].lower() == email.lower() and uid != usuario_id 
        for uid, u in cu.USUARIOS_MOCK.items()
    )
    if email_existe:
        return RedirectResponse(
            f"/perfil?estudiante_id={usuario_id}&msg=Error:+el+email+ya+esta+en+uso+por+otro+estudiante&ok=0", 
            status_code=303
        )
    
    # ✅ Actualizar en el mock de usuarios (en memoria)
    cu.USUARIOS_MOCK[usuario_id]["nombre"] = nombre
    cu.USUARIOS_MOCK[usuario_id]["email"] = email
    cu.USUARIOS_MOCK[usuario_id]["carrera"] = carrera
    
    print(f"[admin] Estudiante {usuario_id} actualizado: {nombre}, {email}, {carrera}")
    
    return RedirectResponse(
        f"/perfil?estudiante_id={usuario_id}&msg=Estudiante+actualizado+correctamente&ok=1", 
        status_code=303
    )

@app.post("/admin/eliminar_estudiante", include_in_schema=False)
def admin_eliminar_estudiante(request: Request, usuario_id: int = Form(...),
                              db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    # No permitir eliminar al propio administrador
    if usuario_id == usuario["usuario_id"]:
        return RedirectResponse("/perfil?msg=Error:+no+puedes+eliminarte+a+ti+mismo&ok=0", status_code=303)
    
    # Verificar que el estudiante exista en el mock
    if usuario_id not in cu.USUARIOS_MOCK:
        return RedirectResponse("/perfil?msg=Error:+estudiante+no+encontrado&ok=0", status_code=303)
    
    # Obtener nombre antes de eliminar (para el mensaje)
    nombre_estudiante = cu.USUARIOS_MOCK[usuario_id]["nombre"]
    
    # 1. Eliminar primero sus inscripciones en la BD (integridad referencial)
    db.execute(text("DELETE FROM UsuarioMaterias WHERE usuario_id = :u"), {"u": usuario_id})
    db.commit()
    
    # 2. Eliminar del mock de usuarios
    del cu.USUARIOS_MOCK[usuario_id]
    
    return RedirectResponse(
        f"/perfil?msg=Estudiante+{nombre_estudiante}+(ID+{usuario_id})+eliminado+correctamente+junto+con+sus+inscripciones&ok=1", 
        status_code=303
    )


@app.post("/admin/actualizar_inscripcion", include_in_schema=False)
def admin_actualizar_inscripcion(request: Request, usuario_id: int = Form(...),
                                 materia_id: int = Form(...), dia: str = Form(...),
                                 hora: str = Form(...), salon: str = Form(...),
                                 periodo: str = Form(...), db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    # Actualizar día, hora, salón en la tabla Materias
    db.execute(text("UPDATE Materias SET dia=:d, hora=:h, salon=:s WHERE materia_id=:m"),
               {"d": dia, "h": hora, "s": salon, "m": materia_id})
    
    # Actualizar periodo en UsuarioMaterias
    db.execute(text("UPDATE UsuarioMaterias SET periodo=:p WHERE usuario_id=:u AND materia_id=:m"),
               {"p": periodo, "u": usuario_id, "m": materia_id})
    db.commit()
    
    return RedirectResponse(f"/perfil?estudiante_id={usuario_id}&msg=Inscripcion+actualizada+correctamente&ok=1", status_code=303)


@app.post("/admin/habilitar_periodo", include_in_schema=False)
def admin_habilitar_periodo(request: Request, periodo: str = Form(...),
                            db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    if periodo not in PERIODOS_HABILITADOS:
        PERIODOS_HABILITADOS.append(periodo)
    
    return RedirectResponse("/admin?msg=Periodo+habilitado&ok=1", status_code=303)

@app.post("/admin/inhabilitar_periodo", include_in_schema=False)
def admin_inhabilitar_periodo(request: Request, periodo: str = Form(...),
                              db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    if periodo in PERIODOS_HABILITADOS and periodo != PERIODO_ACTIVO:
        PERIODOS_HABILITADOS.remove(periodo)
    
    return RedirectResponse("/admin?msg=Periodo+inhabilitado&ok=1", status_code=303)

@app.post("/admin/eliminar_inscripcion", include_in_schema=False)
def admin_eliminar_inscripcion(request: Request, usuario_id: int = Form(...),
                               materia_id: int = Form(...),
                               db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    # materia_id aquí es el grupo_id
    db.execute(text("DELETE FROM UsuarioMaterias WHERE usuario_id = :u AND materia_id = :m"),
               {"u": usuario_id, "m": materia_id})
    db.commit()
    
    return RedirectResponse(f"/perfil?estudiante_id={usuario_id}&msg=Inscripcion+eliminada+correctamente&ok=1", status_code=303)

@app.post("/admin/cambiar_carrera_estudiante", include_in_schema=False)
def admin_cambiar_carrera(request: Request, usuario_id: int = Form(...),
                          nueva_carrera: str = Form(...),
                          db: Session = Depends(database.get_db)):
    r = _o_login(request)
    if not isinstance(r, int): return r
    usuario = cu.obtener_usuario(r)
    if usuario.get("rol") != "admin":
        return RedirectResponse("/tablero", status_code=303)
    
    # Actualizar en el mock de usuarios
    if usuario_id in cu.USUARIOS_MOCK:
        cu.USUARIOS_MOCK[usuario_id]["carrera"] = nueva_carrera
    
    return RedirectResponse(f"/admin?msg=Carrera+actualizada&ok=1", status_code=303)