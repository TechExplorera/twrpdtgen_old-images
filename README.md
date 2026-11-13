# twrpdtgen (versión adaptada para imágenes viejas / TWRP)

Genera un árbol de device tree base para TWRP a partir de un `recovery.img` o `boot.img` del firmware stock.

Base: twrpdtgen 3.0.0 original (Apache-2.0, Sebastiano Barezzi / SebaUbuntu). Esta versión cambia:
- Sin AIK: el desempaquetado se hace en Python (`twrpdtgen/utils/unpack.py`).
- Sin Omni: los nombres de producto y lunch combos usan `twrp_<codename>`.
- Validación del modelo con `--expect-model`.
- Respaldo para firmwares viejos que no traen todas las propiedades que exige `sebaubuntu_libs`.

Ver `CAMBIOS.md` para el detalle de cada cambio.

## Requisitos

- Python 3.8 o superior
- `cpio` en el sistema
- `lz4`, `zstd` o `xz` si el ramdisk viene comprimido con ese formato
- Paquetes de Python: `jinja2`, `gitpython`, `sebaubuntu-libs`

En Debian/Ubuntu:

```bash
sudo apt install cpio lz4 zstd xz-utils
python3 -m venv ~/venv-twrp
source ~/venv-twrp/bin/activate
pip install jinja2 gitpython sebaubuntu-libs
```

Activa el entorno (`source ~/venv-twrp/bin/activate`) cada vez que ejecutes el generador.

## Uso

Desde la carpeta que contiene `twrpdtgen/`:

```bash
python3 -m twrpdtgen recovery.img -o output --expect-model SM-A127F --arch arm
```

Argumentos:

| Argumento | Descripción |
|---|---|
| `image` | recovery.img o boot.img |
| `-o`, `--output` | carpeta de salida (por defecto `./output`) |
| `--expect-model MODELO` | falla si la imagen no es de ese modelo o codename |
| `--arch` | `arm`, `arm64`, `x86` o `x86_64`. Solo se usa si el `build.prop` no trae `cpu.abi` |
| `--build-prop ARCHIVO` | `build.prop` adicional (repetible) |
| `--git` | crea un repositorio git con el árbol generado |
| `-d`, `--debug` | muestra mensajes de depuración |

Ejemplo de salida:

```
output/samsung/<codename>/
```

## Qué se genera

- `BoardConfig.mk`, `device.mk`, `AndroidProducts.mk`, `Android.mk`, `Android.bp`
- `twrp_<codename>.mk` y `vendorsetup.sh` (lunch combos `twrp_<codename>-user|userdebug|eng`)
- `recovery/root/` con los scripts de init extraídos
- `recovery.fstab` a partir del fstab del ramdisk
- `prebuilt/` con kernel, dt, dtb y dtbo cuando existen en la imagen
- `extract-files.sh` y `setup-makefiles.sh`

## Validaciones

- **header**: solo acepta boot v0, v1 y v2. Si el campo `header_version` no vale 0-2, se asume v0 y se avisa, porque en v0 ese offset es `unused` y algunos firmwares guardan ahí otro dato.
- **modelo**: con `--expect-model`, compara contra `ro.product.model` y `ro.product.device`.
- **respaldo de propiedades**: si el `build.prop` está incompleto, se completan las propiedades que exige la librería y se muestra un aviso. Las variantes por partición (`ro.product.system.device`, `ro.product.vendor.model`, etc.) se copian desde la propiedad base, y `cpu.abilist` se toma de `cpu.abi` o de `--arch`. Solo hay dos valores de relleno: `ro.product.board` (de `ro.board.platform`, o `unknown`) y `ro.build.version.security_patch=1970-01-01`. Si falta `ro.product.device`, el generador falla, porque no hay de dónde copiar el codename.

## Limitaciones

- No soporta boot v3/v4 ni `vendor_boot`.
- `origsize` en `BoardConfig.mk` es el tamaño del archivo de imagen, no el de la partición real.
- Algunos valores fijos de la plantilla original siguen ahí (`PLATFORM_VERSION`, `BOARD_SUPER_PARTITION_SIZE`, `VENDOR_SECURITY_PATCH`) y están marcados como `TODO`.
- El árbol no compila solo. Faltan el kernel fuente o el prebuilt correcto, los blobs de vendor y los módulos propios de TWRP.
- Depende de `sebaubuntu_libs` para `BuildProp`, `Fstab` y `DeviceInfo`.

## Revisión antes de compilar

```bash
cd output/samsung/<codename>
grep -n "TODO\|placeholder\|unknown\|1970" *.mk
cat recovery/root/etc/recovery.fstab
```

Compara `BOARD_KERNEL_CMDLINE`, `BOARD_KERNEL_BASE`, `BOARD_KERNEL_PAGESIZE` y `TARGET_BOARD_PLATFORM` con el firmware de tu equipo.

## Pruebas

Probado de punta a punta con una imagen boot v0 sintética (kernel, ramdisk gzip, `system/build.prop` y `etc/recovery.fstab`). Con un `recovery.img` real de un Galaxy A25 5G (SM-A256E, header v2) el generador produjo el árbol. No se ha probado con un `recovery.img` del Galaxy A12s.

## Licencia

Apache-2.0, igual que el original. Se conserva el aviso de copyright en los archivos modificados.

## Créditos

Original project: twrpdtgen
Original author: Sebastiano Barezzi (SebaUbuntu)
Original repository: https://github.com/twrpdtgen/twrpdtgen
Original license: Apache License 2.0.
Adaptation and modifications: This repository.

This repository is based on the original twrpdtgen 3.0.0 by Sebastiano Barezzi (SebaUbuntu). All original copyright notices are preserved in the modified files.

Additional modifications and features were developed for generating TWRP device trees without OmniROM dependencies, supporting AIK-free image extraction, and improving compatibility with older firmware images.
