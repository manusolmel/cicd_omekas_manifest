# Proyecto: Pipeline CI/CD para Omeka S basado en manifests en Libnamic

## Resumen

Este proyecto define un sistema reproducible para construir **imágenes de contenedor** de **Omeka S** (aplicación web en **PHP**) mediante **CI/CD en GitLab**, usando un enfoque declarativo basado en **manifests versionados**.

La idea central es separar:

1. Una **imagen base** de Omeka S (core + runtime PHP-FPM/Nginx + dependencias de sistema).
2. Imágenes **por proyecto** (cliente/instancia), que se construyen a partir de la imagen base y añaden **módulos** y **temas** específicos, declarados en un *manifest*.

El resultado final de cada build es siempre una **imagen publicada en el GitLab Container Registry**, lista para desplegarse tanto en **Kubernetes** como en **Docker Compose** (daemonizado con systemd).

---

## Motivación

En proyectos PHP tradicionales, las actualizaciones suelen hacerse entrando a servidores y:

- descomprimiendo ZIPs,
- tocando dependencias del sistema,
- resolviendo incompatibilidades de versiones (PHP, extensiones, librerías),
- aplicando cambios manuales con riesgo en producción.

Este enfoque genera deuda operativa y problemas repetibles:

- entornos no reproducibles,
- cambios no trazables,
- despliegues no deterministas,
- upgrades frágiles.

Con un flujo CI/CD orientado a contenedores:

- Todo queda **versionado** (base + módulos/temas + configuración).
- Los cambios se aplican con **commit + push**.
- Staging/producción se actualizan **cambiando únicamente la tag de la imagen**.
- Se reduce drásticamente el trabajo manual y el riesgo en producción.

---

## Objetivos

### Objetivo principal

Implementar una pipeline estándar que, dado un **manifest**, construya y publique una **imagen de contenedor** de Omeka S con:

- una imagen base seleccionada (core + runtime),
- módulos/temas añadidos según declaración.

### Objetivos secundarios

- Definir una especificación clara del **manifest**.
- Soportar varias formas de referenciar módulos/temas.
- Incorporar fases típicas de CI: dependencias, build, tests, packaging.
- Preparar el terreno para despliegue continuo en Kubernetes o Docker Compose.

---

## Contexto: Omeka S

**Omeka S** es una plataforma de publicación y gestión de colecciones para instituciones culturales (GLAM). Está desarrollada en **PHP** y utiliza un ecosistema de **módulos** y **temas** para extender funcionalidad y personalizar el frontend.

En este proyecto se asume:

- runtime con **PHP-FPM** y un servidor HTTP (p. ej. Nginx),
- instalación de Omeka S como base,
- módulos/temas como artefactos añadibles desde diferentes orígenes.

---

## Arquitectura propuesta

### 1) Imagen base (`omeka-s-base`)

Contiene:

- versión de **Omeka S core**,
- versión de **PHP** (y extensiones necesarias),
- **Nginx / PHP-FPM** y dependencias del sistema,
- configuración por defecto y entrypoint.

**Motivo:** poder actualizar runtime (seguridad, SO, PHP, nginx, libs) incluso si Omeka S no publica una versión nueva.

Ejemplo de tags:

- `omeka-s-base:4.1.1-php8.2-bookworm-2026.02`
- `omeka-s-base:4.0.4-php8.1-bookworm-2026.02`

> Nota: el esquema exacto de tagging puede ajustarse, pero debe ser *determinista* y con información suficiente.
No es que “venga del documento”. Es simplemente la forma mínima de materializar la tubería: entrada → validación → descarga → build. Podrías meter todo en u
---

### 2) Imagen por proyecto

Partiendo de `omeka-s-base:<tag>`, se añaden:

- módulos (plugins),
- temas,
- código o assets específicos (si aplica),
- configuración o wiring requerido.

Produce:

- `omeka-s-proj-<nombre>:<tag>` en el registry.

---

## Organización de repositorios

Se contemplan dos modalidades para proyectos:

### A) Proyectos con repositorio individual

Contienen:

- `manifest.yml` (o `manifest.yaml`)
- código propio del proyecto (módulos/temas internos, branding, assets, scripts)

Ejemplo:

```
omeka-proj-museo-x/
  manifest.yml
  themes/
    museo-x-theme/
  modules/
    custom-module/
  .gitlab-ci.yml
  README.md
```

### B) Proyectos simples en repositorio compartido

Para proyectos que no tengan código propio:

- un repo central `omeka-projects-manifests` con carpetas por proyecto
- cada carpeta incluye solo `manifest.yml`

Ejemplo:

```
omeka-projects-manifests/
  projects/
    archivo-municipal/
      manifest.yml
    coleccion-2026/
      manifest.yml
```

En ambos casos, la pipeline debe:

1. localizar el manifest (ruta fija o variable),
2. construir la imagen resultante,
3. publicar en registry.

---

## Especificación del manifest

El manifest es la **fuente de verdad** declarativa de:

- base seleccionada,
- módulos/temas a incorporar,
- (opcional) parámetros de build o validaciones.

### Campos mínimos propuestos

```yaml
apiVersion: "libnamic.omk/v1"
kind: "OmekaSProject"

project:
  name: "archivo-municipal"
  description: "Instancia Omeka S para Archivo Municipal"
  image:
    name: "registry.gitlab.com/<grupo>/<repo>/omeka-archivo-municipal"

base:
  image: "registry.gitlab.com/<grupo>/omeka-s-base"
  tag: "4.1.1-php8.2-bookworm-2026.02"

extensions:
  modules:
    - name: "Mapping"
      source:
        type: "catalog"
        version: "1.2.3"

    - name: "CustomModuleX"
      source:
        type: "git"
        repo: "https://gitlab.com/<grupo>/omeka-modules/custom-module-x.git"
        ref: "v0.4.1" # tag o commit

    - name: "MediaTools"
      source:
        type: "release_zip"
        repo: "https://gitlab.com/<grupo>/omeka-modules/media-tools"
        version: "2.0.0"
        asset: "media-tools-2.0.0.zip"

  themes:
    - name: "Default"
      source:
        type: "catalog"
        version: "2.0.1"

    - name: "MuseoTheme"
      source:
        type: "git"
        repo: "https://gitlab.com/<grupo>/omeka-themes/museo-theme.git"
        ref: "b6c1f92"  # commit

build:
  # opcional: configuraciones de build
  enable_tests: true
  target_tags:
    - "staging"
    - "prod"
```

### Tipos de `source` soportados

1) **git (repo clonable)**

- `repo`: URL clonable
- `ref`: commit o tag
- Ventaja: reproducible y trazable.

2) **release_zip (zip en releases)**

- `repo`: URL del repositorio
- `version`: versión
- `asset`: nombre del ZIP
- Ventaja: consumo “tipo paquete”, fácil para usuarios no técnicos.

3) **catalog (nombre + versión)**

- Se busca en el **catálogo oficial de módulos/temas de Omeka S**.
- Debe resolverse a una descarga determinista (URL + checksum si es posible).

4) **omeka-s-cli (opcional)**

Libnamic mantiene una herramienta en PHP que facilita la descarga de módulos del repositorio oficial:

- `omeka-s-cli`: https://github.com/libnamic/omeka-s-cli

Puede usarse para resolver el tipo `catalog` si simplifica el pipeline, pero no es obligatorio.

---

## Pipeline CI/CD

La pipeline debe ser **estándar y repetible**.

### Fases sugeridas

1) **lint / validate**

- Validación de schema del manifest (campos requeridos).
- Comprobación de que la base existe en el registry.
- Resolución de módulos/temas (sin descargarlos aún si se quiere).

2) **fetch**

- Descarga/clonado de módulos y temas según manifest.
- Guardado en una estructura predecible:
  - `build-context/modules/<name>/...`
  - `build-context/themes/<name>/...`

3) **build**

- Construcción de la imagen del proyecto:
  - `FROM <base_image>:<base_tag>`
  - Copia de módulos/temas al lugar correspondiente.
  - Ajustes de permisos y ownership.
  - Labels OCI (recomendado): commit, pipeline, manifest digest, etc.

4) **test**

- Smoke tests: PHP lint, comprobación de extensiones, arranque básico del runtime.
- Opcional: tests más específicos (si existe suite).

5) **publish**

- Push al GitLab Container Registry.
- Publicación de tags según convención (p. ej. commit SHA, semver, staging/prod).

---

## Resultados esperados

Al finalizar, cada proyecto debe producir:

- Una imagen disponible en GitLab Container Registry:
  - `registry.gitlab.com/.../<imagen>:<tag>`
- Trazabilidad: debe ser posible saber exactamente:
  - qué base se usó,
  - qué módulos/temas (y sus versiones/refs),
  - qué commit y pipeline construyó la imagen.

---

## Convenciones de tagging (propuesta)

Para imágenes de proyecto:

- Tag por commit:
  - `:<shortsha>`
- Tag “release” (si se versiona):
  - `:v1.2.0`
- Tag de entorno (si se usa promoción):
  - `:staging`
  - `:prod`

> Importante: si se usan tags de entorno, deben estar controlados (solo ramas protegidas / releases) para evitar “pisar” prod accidentalmente.

---

## Despliegue (objetivo posterior)

Una vez que la imagen existe, el despliegue se simplifica:

### Kubernetes

- Deployment apuntando a `image: ...:<tag>`
- Cambio de versión = cambio de tag y rollout.

### Docker Compose (daemonizado)

- `docker compose pull && docker compose up -d`
- Servicio gestionado con systemd para asegurar arranque/restart en boot.

---

## Entregables

1) Repositorio (personal) con:

- parser/validador de manifest,
- lógica de resolución y descarga (git/zip/catalog),
- Dockerfile de proyecto (o generación automática),
- `.gitlab-ci.yml` funcional,
- documentación de uso.

2) Ejemplos de manifests:

- uno con módulos desde git por tag,
- uno con zip de releases,
- uno con catálogo oficial.

3) Pipeline que termine en push al registry con tags claros.

---

## Criterios de aceptación

Se considera completado cuando:

- Se puede ejecutar una pipeline en GitLab que:
  1) lea un manifest,
  2) resuelva módulos/temas,
  3) construya una imagen basada en una base concreta,
  4) ejecute tests básicos,
  5) publique en GitLab Container Registry.

- La imagen final contiene:
  - Omeka S core (en base),
  - módulos y temas declarados,
  - trazabilidad (labels o fichero de metadatos embebido).

- La ejecución es reproducible:
  - reconstruir con el mismo manifest produce el mismo resultado funcional.

---

## Mejoras opcionales

- Cache de builds (BuildKit cache-from/cache-to en registry).
- Verificación de integridad:
  - checksums para ZIP,
  - digest pinning para imágenes base.
- Generación automática de SBOM (Software Bill of Materials).
- “Promoción” controlada:
  - pipeline que promueve `:<shortsha>` → `:staging` → `:prod` con approvals.
- Soporte para “proyectos sin repo propio”:
  - pipeline que itera manifests de un repo compartido y genera imágenes por carpeta.
