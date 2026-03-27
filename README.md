# 🏠 Bot del Hogar — Telegram

Bot de Telegram modular para administración del hogar en pareja. Gastos, balance, despensa, inventario, servicios, tareas, recordatorios y más — todo desde el grupo privado de Telegram.

---

## Módulos incluidos

| Módulo | Comandos |
|--------|----------|
| 💰 Gastos | `/gasto`, `/gastos_hoy`, `/gastos_semana`, `/gastos_mes` |
| ⚖️ Balance | `/balance`, `/compensar`, `/deudas` |
| 🛒 Compras | `/agregar`, `/lista`, `/urgentes`, `/comprado`, `/quitar` |
| 📦 Inventario | `/stock`, `/usar`, `/inventario`, `/bajo_minimo`, `/minimo` |
| 🔌 Servicios | `/servicio`, `/servicios`, `/pagado`, `/proximos_pagos` |
| 💼 Presupuesto | `/presupuesto`, `/presupuesto_ver` |
| ✅ Tareas | `/tarea`, `/pendientes`, `/hecha` |
| ⏰ Recordatorios | `/recordar`, `/recordatorios`, `/cancelar_recordatorio` |
| 📊 Reportes | `/resumen_semana`, `/resumen_mes` |
| 📤 Exportación | `/exportar_gastos`, `/exportar_lista`, `/exportar_inventario` |
| ⚙️ Config | `/config`, `/moneda`, `/mi_id`, `/id_grupo` |

---

## Requisitos

- Python 3.11+
- Token de bot obtenido desde [@BotFather](https://t.me/BotFather) en Telegram
- El bot debe ser **administrador** del grupo privado donde lo uses

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <tu-repo>
cd hogar_bot

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux / Mac
# venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu BOT_TOKEN
```

---

## Configuración del `.env`

```env
BOT_TOKEN=123456789:ABCDefghIJKLmnopQRSTuvwxyz
DATABASE_URL=sqlite+aiosqlite:///./hogar.db
SCHEDULER_DB_URL=sqlite:///./jobs.sqlite
TIMEZONE=America/Mexico_City
```

Para producción con PostgreSQL:
```env
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/hogar_db
```

---

## Cómo crear el bot en Telegram

1. Habla con [@BotFather](https://t.me/BotFather)
2. Envía `/newbot`
3. Elige un nombre y un username (debe terminar en `bot`)
4. Copia el token y pégalo en `.env` como `BOT_TOKEN`
5. En BotFather: `/setprivacy` → Selecciona tu bot → `Disable` (para que pueda leer mensajes de grupo)

---

## Ejecutar

```bash
python main.py
```

La base de datos se crea automáticamente en el primer arranque.

---

## Cómo usar en Telegram

1. Agrega el bot a tu grupo privado de pareja
2. Hazlo administrador del grupo
3. Ambos ejecutan `/start` para registrarse
4. Empieza con `/menu` para ver todos los comandos

---

## Comandos de referencia rápida

### Gastos
```
/gasto 380 despensa leche huevos pan
/gastos_hoy
/gastos_semana
/gastos_mes
```

### Balance
```
/balance
/compensar 200 te pago lo del super
/deudas
```

### Lista de compras
```
/agregar leche 2 litros alta
/agregar papel
/lista
/urgentes
/comprado leche
/quitar papel
```

### Inventario
```
/stock arroz 2 kg
/stock papel 4 rollos
/usar papel 1
/inventario
/bajo_minimo
/minimo papel 2
```

### Servicios y pagos fijos
```
/servicio internet 600 5 ambos
/servicio luz 900 12 ambos
/servicios
/pagado internet 620
/proximos_pagos
```

### Presupuesto mensual
```
/presupuesto despensa 4000
/presupuesto comida_fuera 1500
/presupuesto_ver
```

### Tareas
```
/tarea limpiar baño sábado por la mañana
/pendientes
/hecha limpiar baño
/hecha #5
```

### Recordatorios
```
/recordar sacar basura mañana 8pm
/recordar pagar internet lunes 9am
/recordar revisar refri domingo 7pm semanal
/recordatorios
/cancelar_recordatorio 3
```

### Reportes y exportación
```
/resumen_semana
/resumen_mes
/exportar_gastos
/exportar_lista
/exportar_inventario
```

### Utilidades
```
/mi_id
/id_grupo
/config
/moneda USD
```

---

## Flujo guiado por botones

Además de los comandos rápidos, el bot soporta flujos interactivos:

- **Nuevo gasto guiado**: botón inline que pide monto → categoría → nota → confirmación
- **Editar/Borrar gasto**: botones que aparecen debajo de cada gasto registrado (con confirmación antes de borrar)
- **Marcar comprado/urgente/quitar**: botones inline debajo de cada producto agregado
- **Marcar tarea hecha/cancelar**: botones inline debajo de cada tarea creada

---

## Recordatorios persistentes

Los recordatorios sobreviven reinicios del bot porque:

1. Se guardan en la base de datos (`reminders` table)
2. Al arrancar, `main.py` llama a `rehidrate_reminders()` que los recarga al scheduler
3. El scheduler usa `SQLAlchemyJobStore` con su propia base de datos (`jobs.sqlite`)

Frecuencias soportadas: `una vez`, `diario`, `semanal`, `mensual`

---

## Resúmenes automáticos

El bot envía un resumen semanal automáticamente cada domingo a las 20:00 (hora configurada en `TIMEZONE`).

Incluye: total gastado, top categorías, balance, urgentes en lista, próximos servicios y tareas pendientes.

---

## Migraciones (Alembic — producción)

Para PostgreSQL en producción:

```bash
pip install alembic
alembic init -t async migrations

# Editar migrations/env.py para importar tus modelos y apuntar al DATABASE_URL
# Luego:
alembic revision --autogenerate -m "Init"
alembic upgrade head
```

Para desarrollo local con SQLite, las tablas se crean automáticamente al arrancar.

---

## Pruebas

```bash
pytest tests/ -v
```

Los tests usan SQLite en memoria y no necesitan conexión a Telegram. Cubren:

- Balance 50/50 con un solo pagador
- Balance cuando ambos pagan igual (sin deuda)
- Balance sin gastos
- Reducción de deuda al registrar compensación
- Error con menos de 2 miembros
- Creación y borrado de gasto con auditoría
- Actualización de gasto
- Permisos de grupo (gasto de otro grupo lanza error)
- Deduplicación de productos en lista
- Marcar comprado y verificar que sale de pendientes
- Detección de stock bajo mínimo
- Que `usar` no deja cantidad negativa

---

## Arquitectura

```
hogar_bot/
├── main.py                     # Punto de entrada
├── bot/
│   ├── config.py               # Variables de entorno (pydantic-settings)
│   ├── database.py             # Engine, sesiones, init_db, FK pragma
│   ├── models/
│   │   └── domain.py           # Todos los modelos ORM (15 tablas)
│   ├── services/               # Lógica de negocio pura
│   │   ├── expense_service.py
│   │   ├── balance_service.py  # Con settlements y simplificación de deudas
│   │   ├── shopping_service.py
│   │   ├── inventory_service.py
│   │   ├── service_manager.py
│   │   ├── task_service.py
│   │   ├── reminder_service.py
│   │   ├── budget_service.py
│   │   ├── report_service.py
│   │   └── export_service.py
│   ├── handlers/               # Routers de Telegram (aiogram)
│   │   ├── registration.py     # get_or_create en una sola transacción
│   │   ├── start.py            # /start, /help, /menu, /mi_id, /id_grupo
│   │   ├── expenses.py         # FSM completo + comando rápido + callbacks
│   │   ├── balance.py
│   │   ├── shopping.py
│   │   ├── inventory.py
│   │   ├── services_handler.py
│   │   ├── tasks.py
│   │   ├── reminders.py
│   │   ├── reports_and_export.py
│   │   └── config_handler.py
│   └── scheduler/
│       └── core.py             # APScheduler + rehidratación + resúmenes automáticos
└── tests/
    └── test_services.py        # 11 tests reales contra servicios
```

---

## Modelos de base de datos

| Tabla | Descripción |
|-------|-------------|
| `users` | Usuarios registrados (BigInteger telegram_user_id) |
| `groups` | Grupos de Telegram (BigInteger telegram_chat_id) |
| `group_members` | Membresías con UniqueConstraint y CheckConstraint de rol |
| `expenses` | Gastos con CheckConstraint de monto y split_type |
| `settlements` | Compensaciones de balance |
| `shopping_items` | Lista de compras con estados y prioridades |
| `inventory_items` | Inventario con UniqueConstraint por grupo+producto |
| `services` | Pagos fijos recurrentes |
| `service_payments` | Historial de pagos de servicios |
| `budgets` | Presupuestos mensuales por categoría |
| `reminders` | Recordatorios persistentes |
| `tasks` | Tareas domésticas |
| `meal_plan` | Planeación de comidas (estructura lista) |
| `wishlist_items` | Lista de deseos del hogar |
| `audit_logs` | Auditoría de CREATE/UPDATE/DELETE |

---

## Seguridad

- Los IDs de Telegram se guardan como `BigInteger` (correcto para IDs de grupos negativos y grandes)
- FK activadas en SQLite con `PRAGMA foreign_keys=ON`
- Toda acción destructiva pide confirmación con botón inline
- Toda edición importante deja registro en `audit_logs`
- Las acciones validan que el gasto/tarea pertenezca al grupo correcto antes de ejecutar
