# MIL

1000 km en un año: del 23 de noviembre de 2026 al 23 de noviembre de 2027, con 6 semanas de margen incluidas. Plan periodizado basado en evidencia, zonas de FC y ritmos personalizados, y un panel que se alimenta solo desde un Garmin Forerunner 255.

Mil kilómetros, un año, cada día suma.

## Empezar en 5 minutos

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[garmin,dev]"
pytest -q                      # 35 pruebas, deben pasar
mil plan                        # genera plan/plan.json, plan.csv y mil-km.ics
mil garmin-login                # UNA vez: email, contraseña y código MFA. Solo se guardan tokens
mil sync --dias 60              # primera descarga: últimos 60 días
mil replan                      # (opcional) ajusta el plan a tu nivel real
mil build && python -m http.server -d docs 8000   # panel en http://localhost:8000
```

Importa `plan/mil-km.ics` en Google Calendar o Apple Calendar para ver cada sesión en tu agenda.

Antes de `mil plan`, edita `config.yaml`: si sabes tu 5K reciente, tu FC máxima o cuánto corres hoy por semana (`km_semana_actual`, por defecto 12), el plan queda calibrado desde el primer día. Lo que Garmin conozca tiene prioridad sobre lo que pongas, salvo `forzar: true`.

## El plan

**Los 1000 km se completan el domingo 10 de octubre de 2027**, y quedan 6 semanas de margen (11 de octubre a 23 de noviembre) para lesión, enfermedad, viajes o simplemente una mala racha. El margen se configura con `margen_semanas` en `config.yaml` (0 lo desactiva).

El coste del margen es honesto: 46 semanas de plan en lugar de 52, o sea unos 21,7 km por semana de media en vez de 19,2. Con los valores por defecto (12 km/semana al inicio): pico de unos 31 km semanales y tirada larga máxima de unos 10 km. Suma exactamente 1000,0 km.

| Fase | Semanas | Objetivo | Calidad semanal |
|---|---|---|---|
| A Base aeróbica | 1 a 12 | Tendones, hábito, economía de carrera | Todo fácil; rectas desde la semana 3; cuestas cortas semanas 9 a 11 |
| B Umbral | 13 a 24 | Subir el ritmo que aguantas | Intervalos de umbral de 3x4' a 2x12' |
| C Potencia aeróbica | 25 a 36 | Subir el VO2max | Intervalos 4 a 6 x 3 a 5' alternados con umbral |
| D Específica y consolidación | 37 a 46 | Consolidar y llegar fresco al kilómetro 1000 | Umbral continuo e intervalos; la semana 46 es de descarga |
| R Margen | 47 a 53 | Reserva | Corre suave si quieres (no cuenta) o recupera km con `mil replan` |

Estructura de cada bloque de 4 semanas: tres de carga (90%, 95% y 100% del pico del bloque) y una de descarga (75%). Las semanas 12, 24 y 36 son de test (30 minutos, 5 km y 30 minutos) para recalibrar zonas y ritmos. Tres carreras por semana hasta la semana 12, cuatro después. Dos sesiones de fuerza de 25 minutos cada semana.

**Cómo se usa el margen.** Si vas al día, el 10 de octubre terminas el plan y el panel muestra el reto completado. Si pierdes semanas, `mil replan` reparte lo que falta en el plan restante conservando el margen; solo cuando quedan menos de dos semanas de plan, empieza a consumir el margen, y te lo dice.

## Ciencia: qué se aplica y con qué solidez

- **Tope de 110% por carrera.** Ninguna carrera supera el 110% de la más larga de los 30 días anteriores (o +0,5 km cuando el 10% es menos que eso). Es la regla con más respaldo reciente: en una cohorte de unos 5200 corredores seguidos 18 meses con Garmin, lo que predijo las lesiones fue el salto de distancia en una sola sesión, no el ACWR ni el cambio semanal (Frandsen et al., *Br J Sports Med* 2025;59(17):1203-1210). Por eso el plan controla la carrera larga y no se apoya en la "regla del 10% semanal".
- **Distribución 80/20.** Al menos el 80% del tiempo en Z1 y Z2, y como mucho el 20% en umbral o más (el plan limita el trabajo duro al 18% del tiempo semanal). Se apoya en el análisis de la distribución de intensidad en deportistas de resistencia (Seiler y Kjerland, 2006) y en la comparación con otras distribuciones (Stöggl y Sperlich, 2014). Evidencia sólida en corredores entrenados; en recreativos es extrapolación razonable.
- **Zonas de FC.** Si se conoce el umbral de lactato (LTHR) se usan zonas por % del umbral (estilo Friel); si no, reserva cardíaca (Karvonen); sin datos, una estimación provisional (Tanaka) marcada como tal. La FC es una guía: el test de la conversación manda en los rodajes.
- **Ritmos.** Modelo VDOT de Daniels y Gilbert: del tiempo de un 5K se derivan los ritmos de fácil, umbral, intervalos y repeticiones. Los ritmos son una consecuencia del esfuerzo, no un objetivo en los rodajes.
- **Fuerza 2 veces por semana.** Los programas de ejercicio y fuerza se asocian a menos lesiones por sobreuso (Lauersen et al., *Br J Sports Med* 2014) y mejor economía de carrera (Blagrove et al., *Sports Med* 2018). Progresión: base, carga, potencia.
- **Descarga cada 4 semanas.** Práctica estándar de periodización; la evidencia directa en corredores recreativos es débil, pero cuesta poco y deja margen al cuerpo.
- **Avisos de recuperación (FC en reposo, VFC, sueño).** Son heurísticas prudentes, no diagnóstico. Mira tendencias, no un día aislado.

## Garmin Forerunner 255: de dónde salen los datos

El FR255 no tiene API abierta para particulares. La vía que funciona hoy es la librería no oficial [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) (versión 0.3.x), que inicia sesión como la app móvil y guarda tokens en `~/.garminconnect/garmin_tokens.json`.

Limitaciones que conviene conocer:

1. **Garmin cambió su autenticación en 2026** y la librería antigua `garth` quedó obsoleta; hace falta `garminconnect>=0.3.20`.
2. **Cloudflare bloquea muchas IP de centros de datos**, así que la sincronización NO corre en GitHub Actions: corre en tu ordenador con `scripts/sync_and_push.sh`, que sube los datos al repo. Actions solo construye y publica el panel.
3. **No repitas intentos de login fallidos**: Garmin puede bloquear la cuenta horas (error 429). Tras `mil garmin-login` ya no se usa la contraseña, solo los tokens.
4. **Los tokens equivalen a tu sesión.** Nunca los subas al repo (`.gitignore` ya los excluye).
5. Es una librería no oficial: si Garmin cambia algo puede romperse. `mil sync --probe` guarda las respuestas crudas (sin GPS) en `data/_probe/` para ajustar el extractor en minutos.

Qué se descarga: carreras (distancia, duración, FC, tiempo en zonas, efecto de entrenamiento, desnivel), y por día FC en reposo, VFC, sueño y Body Battery; además VO2max, FC en el umbral, FC máxima y predicción de 5K para calibrar zonas y ritmos. El FR255 tiene Estado de VFC y detección del umbral de lactato, pero no Training Readiness, así que no se pide.

Programar la sincronización:

- **macOS:** `scripts/install_schedule_macos.sh` (cada 6 horas).
- **Linux:** `crontab -e` y añade `0 */6 * * * /ruta/al/repo/scripts/sync_and_push.sh`
- **Windows:** Programador de tareas, acción `bash scripts/sync_and_push.sh` desde Git Bash o WSL, cada 6 horas.

Si prefieres no depender de ese ordenador, el plan B es sincronizar Garmin con Strava (integración oficial) y leer Strava; no está implementado aquí.

## Panel

`mil build` crea `docs/` con un panel estático: km acumulados frente al plan, km por semana, reparto de intensidad 80/20, próximos 7 días con ritmos y zonas, avisos, y proyección a fin de año. `mil demo` genera uno con datos sintéticos en `docs-demo/` para ver cómo queda.

Para publicarlo: activa GitHub Pages con la fuente "GitHub Actions" (Settings, Pages). El workflow `.github/workflows/site.yml` ejecuta los tests, construye el panel cada día y al hacer push. Aviso: Pages desde un repositorio privado requiere un plan de pago de GitHub; en un repositorio gratuito tendría que ser público.

## Privacidad

- El panel público **nunca incluye GPS ni nombres de actividad**; las coordenadas se descartan al sincronizar.
- Sueño, VFC y FC en reposo están en `data/wellness.json`, que está en `.gitignore`, y el panel público no los muestra (`publicar_bienestar: false`). `mil build --privado` los incluye para verlos solo en local.
- Aun así, ritmos y FC media son datos personales: valora un repositorio privado.

## Comandos

| Comando | Qué hace |
|---|---|
| `mil plan` | Genera el plan completo (CSV, JSON, iCalendar) |
| `mil zonas` | Muestra zonas de FC y ritmos actuales |
| `mil garmin-login` | Primer inicio de sesión (una vez) |
| `mil sync --dias N` | Descarga carreras y métricas de Garmin |
| `mil test --tipo 5k --tiempo 24:10` | Registra un test de 5 km y recalcula el VDOT |
| `mil test --tipo 30min --fc 168` | Registra la FC media de los últimos 20 min del test de 30 min (tu LTHR) |
| `mil replan` | Redistribuye los km que faltan en las semanas que quedan, con tu nivel real |
| `mil resumen` | Estado en una línea más avisos |
| `mil build` | Construye el panel en `docs/` |
| `mil demo` | Panel de ejemplo con datos sintéticos |

## Cuándo hacer `mil replan`

Después de cada test (semanas 12, 24, 36 y 48), si el panel dice que vas 6 km o más por detrás, tras una lesión o un parón de más de una semana, o si cambias la FC máxima o el umbral. Conserva lo ya planificado y recalcula desde el lunes siguiente para que la suma final siga siendo 1000 km, protegiendo el margen mientras puede. Si el objetivo ya no es alcanzable con una progresión prudente, te lo avisa en lugar de inflar las semanas.

## Si te lesionas o enfermas

Nada de recuperar kilómetros de golpe: es justo lo que sube el riesgo. Para unos días, retoma el plan donde toca. Para más de una semana, `mil replan`. Con dolor que cambia tu forma de correr, para y consulta a un fisioterapeuta o médico del deporte. Este plan no sustituye a un profesional sanitario.

## Estructura

```
config.yaml             parámetros del reto
src/mil/     planner, zonas, Garmin, análisis, replan, CLI
site/index.html         panel (HTML + JS sin dependencias)
plan/                   plan.json, plan.csv, mil-km.ics
data/                   actividades, perfil y resumen (JSON)
scripts/                sincronización y programación
tests/                  35 pruebas
```
