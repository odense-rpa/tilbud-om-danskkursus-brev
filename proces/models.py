from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date


class Borger(BaseModel):
    cpr:str
    navn:str
    adresse:str
    postnr: int
    by: str
    statsborgerskab: str
    indrejsedato: date

    @field_validator("cpr")
    @classmethod
    def validate_cpr(cls, v: str) -> str:
        if not v:
            raise ValueError("CPR må ikke være tomt")
        v = v.strip()
        if "-" not in v:
            if len(v) != 10:
                raise ValueError("CPR skal være 10 cifre uden bindestreg eller 11 tegn med bindestreg")
            v = v[:6] + "-" + v[6:]
        return v 