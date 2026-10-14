from pydantic import BaseModel, Field
from typing import List

class MateriaResponse(BaseModel):
    materia_id: int
    nombre: str
    class Config:
        from_attributes = True

class AsociarMateria(BaseModel):
    materia_id: int = Field(..., gt=0, description="ID de materia positivo")

class MateriaUsuarioResponse(BaseModel):
    usuario_id: int
    materias: List[MateriaResponse]