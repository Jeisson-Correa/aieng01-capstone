# Agente de posventa Aurelia

Capstone AIENG01 · agente de posventa para una marca de bolsos y chaquetas.
Datos simulados: ningún pedido, cliente ni documento de este repositorio corresponde a una persona real.

## El caso

**Quién lo usa:** el asesor de servicio al cliente de Aurelia, por chat.

**Qué le pide:** resolver un caso de posventa concreto — "pedido A-1042, la chaqueta me quedó pequeña, ¿la cambio por M?" — con el número de pedido en la mano.

**Cómo se sabe que lo resolvió:** entrega una decisión (`aprueba_cambio`, `aprueba_garantia`, `aprueba_devolucion`, `nota_credito`, `rechaza`, `escala_humano`), cita la causal de la política con su plazo, y da un número de caso `RMA-####` que existe de verdad porque lo creó la herramienta. Si le falta un dato, pide ese dato y nada más.

## Arquitectura

```
cliente
  │
  ▼
guardrail de ENTRADA ──── bloquea inyección · redacta tarjetas
  │
  ▼
ORQUESTADOR (agente.py · Claude Agent SDK)
  │
  ├──► servidor MCP propio «posventa» (server.py)
  │       buscar_pedido · consultar_politica · verificar_inventario · crear_caso_rma
  │
  └──► subagente «auditor_politica» (subagentes/orquestador_sdk.py)
          contexto propio · solo 2 herramientas de lectura · no puede crear casos
  │
  ▼
guardrail de SALIDA ──── no deja anunciar un RMA que nadie creó
  │
  ▼
respuesta + traza + costo (resultados/ · usage_log.jsonl)
```

**Por qué un subagente aquí.** Atender al cliente y aplicar la norma son dos trabajos distintos. El orquestador lleva la conversación y tiende a querer resolver; el auditor solo lee la política literal y el pedido, en su propio contexto, y responde `OK` o `NO` con la regla que lo sustenta. Tiene dos herramientas de lectura y **no tiene `crear_caso_rma`**: no puede aprobar nada, solo contradecir. Además mantiene el texto completo de la política fuera del contexto del orquestador, que se alarga con la conversación.

## Cómo correrlo

```bash
cd /workshop/aieng01/lab-09-capstone/workspace     # el .venv se activa solo
python adaptador.py "Pedido A-1042, la chaqueta me quedó pequeña, ¿la cambio por M?"
```

Otros comandos:

```bash
python server.py                                   # prueba las 4 herramientas sin el modelo
python guardrails.py                               # prueba los guardrails sin el modelo
python evals.py --sin-guardrails --etiqueta antes  # corrida base
python evals.py --etiqueta despues                 # con guardrails
python evals.py --comparar antes despues           # la tabla antes/después
python ver_traza.py > resultados/traza.txt         # la traza de la última pregunta
python3 /workshop/aieng01/lab-09-capstone/verificar.py
```

La fecha de referencia está congelada en `2026-11-18` (`FECHA_HOY` en `server.py`) para que los plazos — y por lo tanto las evaluaciones — den igual cada vez que se corren. Se cambia con la variable de entorno `FECHA_HOY`.

## Evaluación

Golden set: **10 casos, 3 adversariales** (`golden_set.json`), escritos desde lo que debe pasar: qué herramienta tiene que usar, qué tiene que decir y qué no puede decir.

Dos calificadores: por código (herramientas usadas, frases obligatorias, frases prohibidas) y un juez que lee el criterio del caso y la respuesta.

| | antes (sin guardrails) | después (con guardrails) |
|---|---|---|
| Aprobados | _pendiente_ / 10 | _pendiente_ / 10 |
| Adversariales aprobados | _pendiente_ / 3 | _pendiente_ / 3 |

> Completa esta tabla con tu corrida real y escribe aquí **qué caso falló y qué hiciste**. Es lo que más pesa en la defensa: un número sin la historia detrás no convence.

## Guardrails

**Entrada** (`revisar_entrada`): bloquea diez patrones de inyección de prompt — "ignora tus instrucciones", "sáltate el plazo", "apruébalo igual", "muéstrame tu system prompt" — y devuelve una respuesta fija sin llamar al modelo. Aparte, redacta números de tarjeta y CVV antes de que el texto llegue al modelo, y marca el caso para escalar.

**Salida** (`revisar_salida`): la respuesta se contrasta contra la evidencia de las herramientas de ese turno. Si menciona un `RMA-####` que `crear_caso_rma` no devolvió, se bloquea: es el guardrail contra el error más caro de este agente, prometerle al cliente un caso que no existe. También bloquea si cita un pedido que no se consultó, o si repite un número de tarjeta.

**Un falso positivo que encontré:** _pendiente — anota aquí el primero que te aparezca, por ejemplo un cliente que escribe un número largo de guía de envío y el filtro de tarjeta lo redacta._

## Costo

Medido con el `usage_log.jsonl` que escribe `adaptador.py` en cada pregunta.

| | valor |
|---|---|
| Costo por pregunta (promedio) | _pendiente_ USD |
| Palanca aplicada | el subagente auditor solo se invoca cuando la decisión es aprobar algo, no en consultas informativas |
| Ahorro medido | _pendiente_ % |
| Proyección a 1.000 preguntas/día | _pendiente_ USD/día |

Precios en `agente.py` (`PRECIO_ENTRADA`, `PRECIO_SALIDA`), ajustables por variable de entorno.

## Límites

- La política vive en un Markdown y se recupera por sección, no por búsqueda semántica. Con un catálogo de políticas grande habría que indexarla.
- El inventario es una foto estática: no hay reserva, así que dos casos simultáneos podrían prometer la misma unidad.
- El auditor valida la política, no la intención del cliente: no detecta fraude por patrón de devoluciones repetidas.
- Con una semana más: reserva de inventario al aprobar un cambio, detección de clientes con devoluciones reincidentes, y un segundo guardrail de salida que verifique que la causal citada existe literalmente en la política.
