"""
Traza legible de la última pregunta · capstone AIENG01.

    python ver_traza.py
    python ver_traza.py > resultados/traza.txt
"""

from __future__ import annotations

import json
from pathlib import Path

TRAZA = Path(__file__).parent / "resultados" / "traza_ultima.json"


def main() -> int:
    if not TRAZA.exists():
        print("No hay traza todavía. Corre primero: python adaptador.py \"tu pregunta\"")
        return 1

    t = json.loads(TRAZA.read_text(encoding="utf-8"))

    print("=" * 64)
    print("TRAZA · agente de posventa Aurelia")
    print("=" * 64)
    print(f"\nPREGUNTA\n  {t['pregunta']}\n")
    print("PASOS")
    for i, paso in enumerate(t.get("pasos", []), 1):
        tipo = paso.get("tipo")
        if tipo == "guardrail_entrada":
            estado = "pasa" if paso["permitir"] else "BLOQUEA"
            print(f"  {i}. guardrail de entrada · {estado} · {paso['motivo']}")
        elif tipo == "herramienta":
            entrada = json.dumps(paso.get("entrada", {}), ensure_ascii=False)
            corto = paso["nombre"].split("__")[-1]
            print(f"  {i}. herramienta · {corto} · {entrada[:150]}")
        elif tipo == "guardrail_salida":
            estado = "pasa" if paso["permitir"] else "BLOQUEA"
            print(f"  {i}. guardrail de salida · {estado} · {paso['motivo']}")
        elif tipo == "respuesta":
            print(f"  {i}. respuesta generada ({len(paso.get('texto', ''))} caracteres)")

    print(f"\nSUBAGENTES\n  {', '.join(t.get('subagentes') or []) or '(ninguno en este turno)'}")
    if t.get("bloqueado_por"):
        print(f"\nBLOQUEADO POR\n  {t['bloqueado_por']}")
    print(f"\nRESPUESTA FINAL\n  " + (t.get("respuesta") or "").replace("\n", "\n  "))
    print(
        f"\nCOSTO\n  {t['tokens_entrada']} tokens entrada · {t['tokens_salida']} salida "
        f"· ${t['costo_usd']:.6f} · {t['segundos']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
