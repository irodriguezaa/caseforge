# CaseForge Web v0.1

Esqueleto técnico del Sprint 1 para comprobar el flujo `Browser → Frontend → Backend → PostgreSQL`.

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) con Docker Compose v2.
- Git para clonar el repositorio.

## Configuración

1. Clone el repositorio y entre al directorio del proyecto.
2. Cree su archivo local de configuración a partir del ejemplo:

   ```bash
   cp .env.example .env
   ```

3. Cambie `POSTGRES_PASSWORD` y `DATABASE_PASSWORD` por el mismo valor seguro para su entorno local. El archivo `.env` no se versiona.

   Las variables son obligatorias: Docker Compose se detendrá con un mensaje claro si falta alguna.

## Ejecutar el proyecto

Desde la raíz del repositorio:

```bash
docker compose up --build
```

Docker iniciará PostgreSQL, FastAPI y Next.js. La primera construcción puede tardar unos minutos porque descarga las dependencias.

PostgreSQL solo es accesible para los servicios de la red Docker. El frontend y la API se publican únicamente en `localhost` para desarrollo local.

URLs disponibles:

- Frontend: http://localhost:3000
- Backend (FastAPI): http://localhost:8000
- Documentación interactiva de la API: http://localhost:8000/docs

## Comprobar el estado

En el navegador abra la página del frontend y pulse **Comprobar conexión**. El frontend consulta sus rutas internas, que a su vez consultan el backend dentro de la red Docker.

También puede consultar directamente:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

Las respuestas exitosas son JSON con `status: "ok"`. El segundo endpoint devuelve HTTP 503 y un mensaje claro si PostgreSQL no está disponible.

## Detener el proyecto

Para detener los contenedores:

```bash
docker compose down
```

Para detenerlos y eliminar también los datos locales de PostgreSQL:

```bash
docker compose down -v
```

## Tests del backend

Con Python 3.12, desde `backend/` instale las dependencias de desarrollo y ejecute:

```bash
pip install -r requirements-dev.txt
pytest
```

Los tests incluidos verifican `GET /health` y la respuesta de error de `GET /health/db`.
