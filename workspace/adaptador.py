"""
Punto de entrada del agente · capstone AIENG01.

    python adaptador.py "Pedido A-1042, la chaqueta me quedó pequeña, ¿la cambio por M?"

Corre el agente con guardrails, deja la traza en resultados/ y registra el costo
de cada pregunta en usage_log.jsonl, que es lo que alimenta la medición del lab 8.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from agente import guardar_traza, run_agent

RAIZ = Path(__file__).parent
USAGE_LOG = RAIZ / "usage_log.jsonl"


def registrar_uso(pregunta: str, res) -> None:
    linea = {
        "momento": datetime.now().isoformat(timespec="seconds"),
        "pregunta": pregunta,
        "modelo": res.modelo,
        "tokens_entrada": res.tokens_entrada,
        "tokens_salida": res.tokens_salida,
        "costo_usd": round(res.costo_usd, 6),
        "herramientas": res.herramientas,
        "subagentes": res.subagentes,
        "bloqueado_por": res.bloqueado_por,
        "segundos": res.segundos,
    }
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def main() -> int:
    pregunta = " ".join(sys.argv[1:]).strip()
    if not pregunta:
        print('Uso: python adaptador.py "tu pregunta"')
        return 1

    res = run_agent(pregunta, con_guardrails=True, verboso=True)

    print("\n" + "─" * 60)
    print(res.respuesta)
    print("─" * 60)
    if res.bloqueado_por:
        print(f"guardrail: {res.bloqueado_por}")
    print(f"herramientas : {', '.join(h.split('__')[-1] for h in res.herramientas) or '(ninguna)'}")
    print(f"subagentes   : {', '.join(res.subagentes) or '(ninguno)'}")
    print(f"modelo       : {res.modelo or '(el del entorno)'}")
    print(f"tokens       : {res.tokens_entrada} entrada / {res.tokens_salida} salida")
    print(f"costo        : ${res.costo_usd:.6f} · {res.segundos}s")
    if res.error:
        print(f"error        : {res.error}")

    registrar_uso(pregunta, res)
    print(f"traza        : {guardar_traza(pregunta, res)}")
    print(f"uso          : {USAGE_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
