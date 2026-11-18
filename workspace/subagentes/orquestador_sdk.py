"""
Subagente `auditor_politica` · capstone AIENG01.

Por qué existe: el orquestador atiende al cliente (tono, contexto de la conversación,
varias vueltas). Aplicar la norma es otro trabajo: leer la política literal y contrastarla
con el pedido, sin que lo arrastre la conversación ni las ganas de quedar bien.

El auditor corre en su propio contexto, con un prompt distinto y SOLO dos herramientas
de lectura. No puede crear casos: no tiene crear_caso_rma. Ese es el punto.

Se invoca de dos formas, las dos válidas para la defensa:
  1. El orquestador delega con la herramienta Agent (AGENTES, registrado en agente.py).
  2. Llamada directa con correr_auditor(), que es lo que usan las evals y verificar.py.

Palanca de costo: el auditor solo se llama cuando la decisión es aprobar algo.
En consultas informativas no se invoca, y eso se nota en el costo por pregunta.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

PROMPT_AUDITOR = """Eres el auditor de política de posventa de Aurelia.

No hablas con el cliente. Recibes una decisión propuesta y la contrastas con los datos.

Procedimiento, sin saltarte pasos:
1. Trae el pedido con buscar_pedido.
2. Trae la política del motivo con consultar_politica.
3. Compara: plazo en días desde la entrega, estado del pedido, condiciones,
   si el ítem venía en promoción final, y si la categoría admite ese motivo.

Respondes en una sola línea, y solo en uno de estos dos formatos:
OK · <la regla que la sustenta, con su plazo>
NO · <qué no cuadra y por qué, citando la política>

No propones alternativas, no saludas, no inventas números de caso.
Si te falta un dato para decidir, respondes: NO · falta <el dato>."""

HERRAMIENTAS_AUDITOR = [
    "mcp__posventa__buscar_pedido",
    "mcp__posventa__consultar_politica",
]

DESCRIPCION_AUDITOR = (
    "Úsalo SIEMPRE antes de aprobar un cambio, una garantía, una devolución o una nota "
    "crédito: contrasta tu decisión propuesta contra el pedido y la política vigente. "
    "No lo uses para preguntas informativas que no terminan en una aprobación."
)


def definicion_agente():
    """AgentDefinition del auditor, o None si el SDK no está disponible."""
    try:
        from claude_agent_sdk import AgentDefinition
    except Exception:
        return None

    return AgentDefinition(
        description=DESCRIPCION_AUDITOR,
        prompt=PROMPT_AUDITOR,
        tools=HERRAMIENTAS_AUDITOR,
        model="inherit",
    )


AGENTES = {}
_definicion = definicion_agente()
if _definicion is not None:
    AGENTES["auditor_politica"] = _definicion


@dataclass
class Veredicto:
    ok: bool
    detalle: str
    tokens_entrada: int = 0
    tokens_salida: int = 0


def _opciones_auditor():
    from claude_agent_sdk import ClaudeAgentOptions

    kwargs = {
        "system_prompt": PROMPT_AUDITOR,
        "allowed_tools": HERRAMIENTAS_AUDITOR,
        "max_turns": 6,
    }
    modelo = os.environ.get("ANTHROPIC_MODEL")
    if modelo:
        kwargs["model"] = modelo

    from server import servidor

    if servidor is not None:
        kwargs["mcp_servers"] = {"posventa": servidor}

    try:
        return ClaudeAgentOptions(**kwargs)
    except TypeError:
        kwargs.pop("max_turns", None)
        return ClaudeAgentOptions(**kwargs)


async def _auditar(consulta: str) -> Veredicto:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

    texto, t_in, t_out = "", 0, 0
    async for mensaje in query(prompt=consulta, options=_opciones_auditor()):
        if isinstance(mensaje, AssistantMessage):
            for bloque in mensaje.content:
                if isinstance(bloque, TextBlock):
                    texto += bloque.text
        elif isinstance(mensaje, ResultMessage):
            uso = getattr(mensaje, "usage", None) or {}
            t_in += uso.get("input_tokens", 0)
            t_out += uso.get("output_tokens", 0)

    limpio = texto.strip()
    return Veredicto(ok=limpio.upper().startswith("OK"), detalle=limpio, tokens_entrada=t_in, tokens_salida=t_out)


def correr_auditor(numero_pedido: str, sku: str, motivo: str, decision_propuesta: str) -> Veredicto:
    """Contrasta una decisión propuesta contra el pedido y la política. Síncrono."""
    consulta = (
        f"Pedido {numero_pedido}, SKU {sku}, motivo {motivo}. "
        f"Decisión propuesta: {decision_propuesta}. ¿La sustenta la política?"
    )
    try:
        return asyncio.run(_auditar(consulta))
    except Exception as exc:  # el auditor nunca tumba al orquestador
        return Veredicto(ok=False, detalle=f"NO · el auditor no pudo verificar: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    print(correr_auditor("A-1042", "CH-001", "cambio_talla", "aprueba_cambio"))
