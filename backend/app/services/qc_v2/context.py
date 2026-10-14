"""Contexto de dispositivo y región. El dispositivo cambia verbos y datos, nunca la lógica."""

from __future__ import annotations

import re
from dataclasses import dataclass

_GRANDES = {"AAF", "STV", "TVOS", "COSHIP", "COSHIP9085", "9085", "ROKU", "ADT", "FTV", "FIRETV", "KEPLER"}
_MEDIANAS = {"WEB", "WIN", "WINDOWS", "XBOX"}
_CHICAS = {"ADR", "ANDROID", "IOS"}

_PAGOS_MX = "PayPal, MDP Móvil, MDP Fijo, Pincode, TDC"
_PAGOS_OTRAS = "MDP Móvil, MDP Fijo"


@dataclass(frozen=True)
class DeviceContext:
    dispositivo: str
    grupo_pantalla: str
    modo_interaccion: str
    region: str
    metodos_pago: str

    def as_text(self) -> str:
        return (
            f"DISPOSITIVO: {self.dispositivo} ({self.grupo_pantalla}, {self.modo_interaccion})\n"
            f"REGIÓN: {self.region}\n"
            f"MÉTODOS DE PAGO: {self.metodos_pago}"
        )


def _token(platform: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (platform or "").upper())


def device_context(platform: str | None, region: str | None = None) -> DeviceContext:
    raw = (platform or "").strip() or "No especificado"
    token = _token(raw)
    if token in _GRANDES or token.startswith("COSHIP"):
        grupo, modo = "Pantalla grande", "control remoto"
    elif token in _MEDIANAS:
        grupo, modo = "Pantalla mediana", "cursor / teclado"
    elif token in _CHICAS:
        grupo, modo = "Pantalla chica", "táctil"
    else:
        grupo, modo = "No especificado", "según el dispositivo"
    region_text = (region or "").strip() or "México y otras operaciones según la historia"
    if token in {"WIN", "WINDOWS", "XBOX"}:
        pagos = "No transacciona"
    elif token == "ROKU":
        pagos = f"México: RokuPay, PayPal · Otras: RokuPay"
    elif token in {"IOS", "TVOS"}:
        pagos = "México: iTunes, PayPal · Otras: no transacciona"
    else:
        pagos = f"México: {_PAGOS_MX} · Otras: {_PAGOS_OTRAS}"
    return DeviceContext(raw, grupo, modo, region_text, pagos)
