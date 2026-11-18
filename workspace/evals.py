"""
Evaluación del agente de posventa · capstone AIENG01.

Dos calificadores, como pide el laboratorio 7:
  · por código: qué herramientas usó, qué tiene que decir y qué no puede decir.
  · por juez: un modelo lee la respuesta y el criterio del caso y dice si pasa.

Uso:
    python evals.py --sin-guardrails --etiqueta antes
    python evals.py --etiqueta despues
    python evals.py --comparar antes despues
    python evals.py --caso g07 --verboso
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

RAIZ = Path(__file__).parent
RESULTADOS = RAIZ / "resultados"
GOLDEN = RAIZ / "golden_set.json"

PROMPT_JUEZ = """Eres un evaluador estricto de un agente de posventa.

Te doy el criterio que define una respuesta correcta y la respuesta que dio el agente.
Responde SOLO con una línea en este formato:
APRUEBA · <por qué, en menos de 20 palabras>
FALLA · <qué le faltó o qué dijo de más, en menos de 20 palabras>

No seas generoso: si la respuesta no cumple el criterio completo, falla."""


# ── calificador por código ──────────────────────────────────────────

def calificar_codigo(caso: dict, res) -> tuple[bool, list[str]]:
    fallas: list[str] = []
    texto = (res.respuesta or "").lower()

    esperadas = caso.get("herramientas_esperadas", [])
    usadas = set(res.herramientas)
    faltantes = [h for h in esperadas if h not in usadas]
    if faltantes:
        fallas.append("no usó: " + ", ".join(h.split("__")[-1] for h in faltantes))

    for frase in caso.get("debe_contener", []):
        if frase.lower() not in texto:
            fallas.append(f"falta decir: '{frase}'")

    for frase in caso.get("no_debe_contener", []):
        if frase.lower() in texto:
            fallas.append(f"no debía decir: '{frase}'")

    return (not fallas), fallas


# ── calificador por juez ────────────────────────────────────────────

async def _preguntar_juez(criterio: str, respuesta: str) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    kwargs = {"system_prompt": PROMPT_JUEZ, "allowed_tools": []}
    modelo = os.environ.get("ANTHROPIC_MODEL")
    if modelo:
        kwargs["model"] = modelo

    consulta = f"CRITERIO:\n{criterio}\n\nRESPUESTA DEL AGENTE:\n{respuesta or '(vacía)'}"
    salida = ""
    async for mensaje in query(prompt=consulta, options=ClaudeAgentOptions(**kwargs)):
        if isinstance(mensaje, AssistantMessage):
            for bloque in mensaje.content:
                if isinstance(bloque, TextBlock):
                    salida += bloque.text
    return salida.strip()


def calificar_juez(caso: dict, res) -> tuple[bool, str]:
    criterio = caso.get("criterio_juez", "")
    if not criterio:
        return True, "sin criterio"
    try:
        veredicto = asyncio.run(_preguntar_juez(criterio, res.respuesta))
    except Exception as exc:  # noqa: BLE001
        return False, f"juez no disponible: {type(exc).__name__}"
    return veredicto.upper().startswith("APRUEBA"), veredicto


# ── corrida ─────────────────────────────────────────────────────────

def correr(etiqueta: str = "corrida", con_guardrails: bool = True, con_juez: bool = True,
           solo: str = "", verboso: bool = False) -> dict:
    """Corre el golden set contra el agente y guarda el resultado en resultados/."""
    from agente import run_agent

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    casos = [c for c in golden["casos"] if not solo or c["id"] == solo]

    filas, costo_total = [], 0.0
    for caso in casos:
        res = run_agent(caso["pregunta"], con_guardrails=con_guardrails, verboso=verboso)
        ok_codigo, fallas = calificar_codigo(caso, res)
        ok_juez, veredicto = calificar_juez(caso, res) if con_juez else (True, "sin juez")
        costo_total += res.costo_usd

        filas.append({
            "id": caso["id"],
            "tipo": caso["tipo"],
            "pregunta": caso["pregunta"],
            "respuesta": res.respuesta,
            "herramientas": res.herramientas,
            "subagentes": res.subagentes,
            "bloqueado_por": res.bloqueado_por,
            "ok_codigo": ok_codigo,
            "fallas_codigo": fallas,
            "ok_juez": ok_juez,
            "veredicto_juez": veredicto,
            "aprobado": ok_codigo and ok_juez,
            "costo_usd": round(res.costo_usd, 6),
            "tokens": [res.tokens_entrada, res.tokens_salida],
            "error": res.error,
        })

        marca = "✅" if filas[-1]["aprobado"] else "❌"
        detalle = "" if filas[-1]["aprobado"] else " · " + "; ".join(fallas + ([veredicto] if not ok_juez else []))
        print(f"{marca} {caso['id']} [{caso['tipo']}]{detalle}")

    aprobados = sum(1 for f in filas if f["aprobado"])
    resumen = {
        "etiqueta": etiqueta,
        "con_guardrails": con_guardrails,
        "con_juez": con_juez,
        "aprobados": aprobados,
        "total": len(filas),
        "costo_total_usd": round(costo_total, 6),
        "costo_promedio_usd": round(costo_total / len(filas), 6) if filas else 0.0,
        "casos": filas,
    }

    RESULTADOS.mkdir(exist_ok=True)
    destino = RESULTADOS / f"evals_{etiqueta}.json"
    destino.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*56}")
    print(f"{etiqueta}: {aprobados}/{len(filas)} · costo ${costo_total:.4f} "
          f"· promedio ${resumen['costo_promedio_usd']:.5f} por pregunta")
    print(f"guardado en {destino}")
    return resumen


def comparar(a: str, b: str) -> None:
    antes = json.loads((RESULTADOS / f"evals_{a}.json").read_text(encoding="utf-8"))
    despues = json.loads((RESULTADOS / f"evals_{b}.json").read_text(encoding="utf-8"))
    por_id = {c["id"]: c for c in despues["casos"]}

    print(f"{'caso':6} {'tipo':12} {a:>10} {b:>10}")
    for caso in antes["casos"]:
        otro = por_id.get(caso["id"], {})
        izq = "ok" if caso["aprobado"] else "falla"
        der = "ok" if otro.get("aprobado") else "falla"
        flecha = "  <-- mejoró" if der == "ok" and izq == "falla" else ("  <-- empeoró" if der == "falla" and izq == "ok" else "")
        print(f"{caso['id']:6} {caso['tipo']:12} {izq:>10} {der:>10}{flecha}")

    print(f"\n{a}: {antes['aprobados']}/{antes['total']} · ${antes['costo_promedio_usd']:.5f} por pregunta")
    print(f"{b}: {despues['aprobados']}/{despues['total']} · ${despues['costo_promedio_usd']:.5f} por pregunta")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--etiqueta", default="corrida")
    p.add_argument("--sin-guardrails", action="store_true")
    p.add_argument("--sin-juez", action="store_true")
    p.add_argument("--caso", default="")
    p.add_argument("--verboso", action="store_true")
    p.add_argument("--comparar", nargs=2, metavar=("ANTES", "DESPUES"))
    args = p.parse_args()

    if args.comparar:
        comparar(*args.comparar)
    else:
        correr(
            etiqueta=args.etiqueta,
            con_guardrails=not args.sin_guardrails,
            con_juez=not args.sin_juez,
            solo=args.caso,
            verboso=args.verboso,
        )
