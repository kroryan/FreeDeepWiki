# Setup local con Ollama

Esta instalación mantiene intactos los archivos funcionales de upstream. La
personalización vive en `deepwiki.sh` y en overrides de Docker Compose, de modo
que un `git pull` o merge futuro pueda incorporar cambios sin sobrescribir la
configuración local.

## Requisitos

- Docker con Docker Compose v2
- Ollama
- Bash y `curl`

En Linux nativo el script usa automáticamente red host, porque Ollama suele
escuchar solo en `127.0.0.1`. En Docker Desktop, WSL, macOS y Windows usa red
bridge y `host.docker.internal`. Puede forzarse con `--network host` o
`--network bridge`.

## Primer uso

```bash
./deepwiki.sh setup
./deepwiki.sh up --no-build
```

La interfaz queda en <http://localhost:3000> y la API en
<http://localhost:8001>. El proveedor predeterminado es Ollama, con
`gpt-oss:120b-cloud` para generación y `nomic-embed-text` para embeddings.
El modelo `gpt-oss:120b-cloud` necesita conexión a Internet e inicio de sesión
en Ollama. Para un equipo totalmente offline, seleccione un modelo descargado
localmente con `--ollama-model`.

## Uso diario

```bash
./deepwiki.sh status
./deepwiki.sh health
./deepwiki.sh models
./deepwiki.sh test
./deepwiki.sh logs -f
./deepwiki.sh down
```

Para seleccionar otro modelo y recrear el servicio:

```bash
./deepwiki.sh up --no-build --ollama-model qwen3.5:4b
```

Para otro servidor Ollama:

```bash
./deepwiki.sh up --ollama-endpoint http://192.168.1.20:11434
```

Las opciones persistentes pueden guardarse copiando
`deepwiki.env.example` a `deepwiki.env`. Este último y el runtime `.deepwiki/`
están ignorados por Git.

El contenedor tiene `restart: "no"`: solo arranca al ejecutar `up`, nunca por
reiniciar el equipo o el daemon de Docker. `down` no detiene Ollama.
