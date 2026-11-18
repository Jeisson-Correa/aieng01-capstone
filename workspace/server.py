"""
Servidor MCP `posventa` · capstone AIENG01 (Aurelia, bolsos y chaquetas).

Cuatro herramientas sobre datos simulados en datos/:
  buscar_pedido · consultar_politica · verificar_inventario · crear_caso_rma

Cada herramienta devuelve siempre un dict con la clave "exito".
Si exito es False, trae "error" (qué pasó) y "sugerencia" (qué debe hacer el agente).
Nunca lanza excepciones hacia el agente: un fallo es un dato, no una caída.

La fecha de referencia se congela con la variable de entorno FECHA_HOY
(por defecto 2026-11-18) para que las evaluaciones sean reproducibles.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

DATOS = Path(__file__).parent / "datos"
FECHA_HOY = date.fromisoformat(os.environ.get("FECHA_HOY", "2026-11-18"))

DECISIONES_VALIDAS = {
    "aprueba_cambio",
    "aprueba_garantia",
    "aprueba_devolucion",
    "nota_credito",
    "rechaza",
    "escala_humano",
}

# Qué sección de la política responde a cada motivo.
SECCIONES = {
    "cambio_talla": "Cambios por Talla",
    "defecto": "Garantía por Defecto de Fábrica",
    "garantia": "Garantía por Defecto de Fábrica",
    "devolucion": "Devoluciones con Reembolso",
    "promocion_final": "Promoción Final",
    "no_entregado": "Pedidos aún no entregados",
    "escalamiento": "Casos que escalan a un humano",
}


# ────────────────────────── acceso a datos ──────────────────────────

def _leer_json(nombre: str) -> dict:
    return json.loads((DATOS / nombre).read_text(encoding="utf-8"))


def _escribir_json(nombre: str, contenido: dict) -> None:
    (DATOS / nombre).write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _dias_desde(fecha_iso: str | None) -> int | None:
    if not fecha_iso:
        return None
    return (FECHA_HOY - date.fromisoformat(fecha_iso)).days


# ────────────────────────── herramientas ──────────────────────────

def buscar_pedido(numero_pedido: str | None = None, documento: str | None = None) -> dict:
    """Busca un pedido por su número (A-####) o todos los de un documento de cliente."""
    if not numero_pedido and not documento:
        return {
            "exito": False,
            "error": "Faltan datos: se necesita numero_pedido o documento.",
            "sugerencia": "Pídele al cliente el número de pedido, que empieza por A-.",
        }

    pedidos = _leer_json("pedidos.json")["pedidos"]

    if numero_pedido:
        clave = numero_pedido.strip().upper()
        encontrados = [p for p in pedidos if p["numero_pedido"].upper() == clave]
        if not encontrados:
            return {
                "exito": False,
                "error": f"No existe el pedido {clave}.",
                "sugerencia": "Confirma el número con el cliente. No inventes un pedido ni asumas otro.",
            }
        pedido = dict(encontrados[0])
        pedido["dias_desde_entrega"] = _dias_desde(pedido.get("fecha_entrega"))
        return {"exito": True, "pedido": pedido}

    doc = documento.strip()
    encontrados = [p for p in pedidos if p["documento_cliente"] == doc]
    if not encontrados:
        return {
            "exito": False,
            "error": f"No hay pedidos para el documento {doc}.",
            "sugerencia": "Verifica el documento o pide el número de pedido.",
        }
    resumen = []
    for p in encontrados:
        fila = dict(p)
        fila["dias_desde_entrega"] = _dias_desde(p.get("fecha_entrega"))
        resumen.append(fila)
    return {
        "exito": True,
        "pedidos": resumen,
        "nota": "Hay más de un pedido. Confirma con el cliente cuál antes de decidir."
        if len(resumen) > 1
        else "",
    }


def consultar_politica(categoria: str, motivo: str) -> dict:
    """Devuelve el fragmento vigente de la política para una categoría y un motivo."""
    seccion = SECCIONES.get((motivo or "").strip().lower())
    if not seccion:
        return {
            "exito": False,
            "error": f"Motivo no reconocido: {motivo}.",
            "sugerencia": "Usa uno de: " + ", ".join(sorted(SECCIONES)),
        }

    texto = (DATOS / "politica.md").read_text(encoding="utf-8")
    bloques = texto.split("\n## ")
    fragmento = ""
    for bloque in bloques:
        if bloque.startswith(seccion):
            fragmento = "## " + bloque.strip()
            break

    if not fragmento:
        return {
            "exito": False,
            "error": f"No se encontró la sección '{seccion}' en la política.",
            "sugerencia": "Escala a un humano antes de decidir sin política.",
        }

    aviso = ""
    if seccion == "Cambios por Talla" and (categoria or "").strip().lower() == "bolso":
        aviso = "Ojo: los bolsos no tienen talla, así que el cambio por talla no aplica."

    return {
        "exito": True,
        "seccion": seccion,
        "categoria": categoria,
        "fragmento": fragmento,
        "aviso": aviso,
    }


def verificar_inventario(sku: str, talla: str, color: str) -> dict:
    """Unidades disponibles de un SKU en una talla y color, con alternativas si no hay."""
    catalogo = _leer_json("catalogo.json")["skus"]
    item = next((s for s in catalogo if s["sku"].upper() == (sku or "").strip().upper()), None)
    if not item:
        return {
            "exito": False,
            "error": f"El SKU {sku} no está en el catálogo.",
            "sugerencia": "Toma el SKU del pedido con buscar_pedido, no del texto del cliente.",
        }

    color_k = (color or "").strip().lower()
    talla_k = (talla or "").strip().upper() if item["categoria"] == "chaqueta" else "unica"
    disponible = item["stock"].get(color_k, {}).get(talla_k, 0)

    alternativas = [
        {"color": c, "talla": t, "unidades": n}
        for c, tallas in item["stock"].items()
        for t, n in tallas.items()
        if n > 0 and not (c == color_k and t == talla_k)
    ]

    return {
        "exito": True,
        "sku": item["sku"],
        "nombre": item["nombre"],
        "categoria": item["categoria"],
        "talla": talla_k,
        "color": color_k,
        "disponible": disponible,
        "alternativas": alternativas[:5],
        "nota": "Sin stock en la combinación pedida: según la política procede nota crédito."
        if disponible == 0
        else "",
    }


def crear_caso_rma(numero_pedido: str, sku: str, motivo: str, decision: str) -> dict:
    """Registra el caso de posventa y devuelve su número. Es la única acción con efecto."""
    if decision not in DECISIONES_VALIDAS:
        return {
            "exito": False,
            "error": f"Decisión inválida: {decision}.",
            "sugerencia": "Usa una de: " + ", ".join(sorted(DECISIONES_VALIDAS)),
        }

    pedido = buscar_pedido(numero_pedido=numero_pedido)
    if not pedido["exito"]:
        return {
            "exito": False,
            "error": pedido["error"],
            "sugerencia": "No se puede abrir un caso sobre un pedido que no existe.",
        }

    skus_del_pedido = {i["sku"].upper() for i in pedido["pedido"]["items"]}
    if (sku or "").strip().upper() not in skus_del_pedido:
        return {
            "exito": False,
            "error": f"El SKU {sku} no está en el pedido {numero_pedido}.",
            "sugerencia": "Confirma con el cliente cuál de los ítems del pedido es.",
        }

    archivo = _leer_json("casos_rma.json")
    caso_id = f"RMA-{1000 + len(archivo['casos']) + 1}"
    caso = {
        "caso_id": caso_id,
        "numero_pedido": pedido["pedido"]["numero_pedido"],
        "sku": sku.strip().upper(),
        "motivo": motivo,
        "decision": decision,
        "creado": FECHA_HOY.isoformat(),
        "estado": "abierto",
    }
    archivo["casos"].append(caso)
    _escribir_json("casos_rma.json", archivo)

    return {"exito": True, "caso_id": caso_id, "caso": caso}


# ────────────────────────── metadatos MCP ──────────────────────────
# Cada descripción dice CUÁNDO usarla, QUÉ devuelve y QUÉ hacer si falla.

HERRAMIENTAS = [
    {
        "nombre": "buscar_pedido",
        "fn": buscar_pedido,
        "descripcion": (
            "Úsala SIEMPRE primero, antes de prometer nada: trae el pedido del cliente. "
            "Entra numero_pedido (formato A-1042) o documento del cliente. "
            "Devuelve fecha de entrega, estado, dias_desde_entrega e items con sku, talla, "
            "color, precio y en_promocion_final. "
            "Si falla, el pedido no existe: pide el número correcto, nunca lo inventes ni uses otro pedido."
        ),
        "parametros": {"numero_pedido": "str opcional", "documento": "str opcional"},
    },
    {
        "nombre": "consultar_politica",
        "fn": consultar_politica,
        "descripcion": (
            "Úsala antes de decidir, para citar la regla vigente en vez de recordarla. "
            "Entra categoria (chaqueta o bolso) y motivo "
            "(cambio_talla, defecto, devolucion, promocion_final, no_entregado, escalamiento). "
            "Devuelve el fragmento literal de la política con su plazo y condiciones. "
            "Si falla, no decidas por tu cuenta: escala el caso a un humano."
        ),
        "parametros": {"categoria": "str", "motivo": "str"},
    },
    {
        "nombre": "verificar_inventario",
        "fn": verificar_inventario,
        "descripcion": (
            "Úsala solo cuando la decisión sea un cambio, para saber si hay con qué cambiar. "
            "Entra sku, talla y color tomados del pedido. "
            "Devuelve disponible (unidades) y alternativas con stock. "
            "Si disponible es 0, según la política procede nota crédito. "
            "Si falla, el SKU no existe: tómalo de buscar_pedido, no del texto del cliente."
        ),
        "parametros": {"sku": "str", "talla": "str", "color": "str"},
    },
    {
        "nombre": "crear_caso_rma",
        "fn": crear_caso_rma,
        "descripcion": (
            "Úsala SOLO al final, cuando ya tienes pedido, política y (si aplica) inventario. "
            "Es la única herramienta con efecto: registra el caso. "
            "Entra numero_pedido, sku, motivo y decision "
            "(aprueba_cambio, aprueba_garantia, aprueba_devolucion, nota_credito, rechaza, escala_humano). "
            "Devuelve caso_id con formato RMA-####, que es el único número que puedes darle al cliente. "
            "Si falla, no anuncies ningún número de caso: explica qué falta."
        ),
        "parametros": {
            "numero_pedido": "str",
            "sku": "str",
            "motivo": "str",
            "decision": "str",
        },
    },
]


# ───────────────── servidor MCP en proceso (Claude Agent SDK) ─────────────────
# Se expone como `servidor` para que agente.py lo registre en SERVIDORES.
# Si el SDK no está instalado, el módulo igual importa y las funciones se pueden probar.

servidor = None
try:  # pragma: no cover - depende del entorno del workspace
    from claude_agent_sdk import create_sdk_mcp_server, tool

    def _respuesta(payload: dict) -> dict:
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}

    @tool("buscar_pedido", HERRAMIENTAS[0]["descripcion"], {"numero_pedido": str, "documento": str})
    async def _t_buscar_pedido(args):
        return _respuesta(buscar_pedido(args.get("numero_pedido"), args.get("documento")))

    @tool("consultar_politica", HERRAMIENTAS[1]["descripcion"], {"categoria": str, "motivo": str})
    async def _t_consultar_politica(args):
        return _respuesta(consultar_politica(args.get("categoria", ""), args.get("motivo", "")))

    @tool("verificar_inventario", HERRAMIENTAS[2]["descripcion"], {"sku": str, "talla": str, "color": str})
    async def _t_verificar_inventario(args):
        return _respuesta(
            verificar_inventario(args.get("sku", ""), args.get("talla", ""), args.get("color", ""))
        )

    @tool(
        "crear_caso_rma",
        HERRAMIENTAS[3]["descripcion"],
        {"numero_pedido": str, "sku": str, "motivo": str, "decision": str},
    )
    async def _t_crear_caso_rma(args):
        return _respuesta(
            crear_caso_rma(
                args.get("numero_pedido", ""),
                args.get("sku", ""),
                args.get("motivo", ""),
                args.get("decision", ""),
            )
        )

    servidor = create_sdk_mcp_server(
        name="posventa",
        version="1.0.0",
        tools=[_t_buscar_pedido, _t_consultar_politica, _t_verificar_inventario, _t_crear_caso_rma],
    )
except Exception:  # el modulo debe importar aunque el SDK cambie de firma
    pass


if __name__ == "__main__":
    print("Herramientas:", [h["nombre"] for h in HERRAMIENTAS])
    print("Servidor MCP cargado:", servidor is not None)
    print(json.dumps(buscar_pedido(numero_pedido="A-1042"), ensure_ascii=False, indent=2))
    print(json.dumps(verificar_inventario("CH-001", "M", "azul"), ensure_ascii=False, indent=2))
