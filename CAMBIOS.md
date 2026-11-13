# twrpdtgen 3.0.0 adaptado para TWRP (sin Omni)

Base: twrpdtgen 3.0.0 original (Apache-2.0, Sebastiano Barezzi / SebaUbuntu).

Cambios:
- El makefile de producto ahora se llama `twrp_<codename>.mk` (antes `omni_<codename>.mk`).
- Se quitó `inherit-product vendor/omni/config/common.mk`.
- `PRODUCT_NAME` y los lunch combos usan `twrp_<codename>-user|userdebug|eng`.
- Archivos modificados: `device_tree.py`, `main.py`, `utils/unpack.py` (nuevo),
  `templates/twrp_device.mk.jinja2` (renombrado de `omni_device.mk.jinja2`),
  `templates/AndroidProducts.mk.jinja2`, `templates/vendorsetup.sh.jinja2`.
- Las secciones de abajo describen los cambios posteriores (validación, sin AIK, respaldos).

Sin cambios: AIK, sebaubuntu_libs, extracción del ramdisk, BoardConfig.mk, fstab y plantillas restantes.

Uso (igual que el original):
    pip3 install jinja2 gitpython sebaubuntu-libs
    python3 -m twrpdtgen recovery.img -o output
Nota: el original necesita AIK y el paquete sebaubuntu_libs. Revisa las dependencias en su versión actual.

## Cambios añadidos (validación)
- `--expect-model MODELO`: falla si la imagen no es de ese modelo o codename.
- `--build-prop ARCHIVO` (repetible): importa un build.prop adicional.
- Validación de `header_version`: solo acepta v0-v2 y falla con mensaje claro en v3/v4 y vendor_boot.
- Mensaje informativo con modelo, codename, SoC y versión del header.
- No se añadió `--set`: depende de la API interna de BuildProp de sebaubuntu_libs, que no pude revisar.

## Sin AIK
- Nuevo `twrpdtgen/utils/unpack.py`: desempaqueta boot/recovery v0-v2 y devuelve un
  `ImageInfo` con los mismos atributos que usan las plantillas (`header_version`,
  `base_address`, `ramdisk_offset`, `tags_offset`, `pagesize`, `cmdline`, `kernel`,
  `dtb`, `dtbo`, `ramdisk`, `sigtype`, `ramdisk_compression`, `origsize`).
- Soporta ramdisk gzip, lz4, zstd, xz y lzma. Requiere `cpio` en el sistema.
- `device_tree.py` ya no importa `sebaubuntu_libs.libaik`. Usa un directorio temporal
  que se borra en `cleanup()`, que `main.py` llama al final.
- Limitaciones: `origsize` es el tamaño del archivo de imagen, no el tamaño de la
  partición. Sin soporte de boot v3/v4 ni vendor_boot. `dt` (Android DT separado)
  no se extrae.
- Sigue usando `sebaubuntu_libs` para `BuildProp`, `Fstab` y `DeviceInfo`.
- Probado con una imagen boot v0 sintética (kernel, ramdisk gzip y build.prop). No
  probado con una imagen real del A12s.

## Corrección de header v0 con campo no-versión
- En v0, el offset 40 es `unused`. Algunos firmwares (p. ej. Samsung) guardan ahí otro dato.
  Si el valor no es 0-2, el unpacker asume v0, avisa y sigue. Probado con un header
  leído de un recovery.img real (page 2048, kernel 0x8000, ramdisk 0x01000000).

## Respaldo de ABI (firmwares viejos)
- sebaubuntu_libs exige ro.system.product.cpu.abilist. Si el build.prop no la trae,
  se usa ro.product.cpu.abi o --arch (arm, arm64, x86, x86_64) y se añade como propiedad.
- Si no hay ni abi ni --arch, el generador falla con un mensaje claro.

## Propiedades de respaldo (firmwares viejos)
- sebaubuntu_libs exige algunas propiedades que los firmwares antiguos no traen. Se añaden
  como respaldo: variantes por partición de ro.product.* (copiadas de la base), cpu.abilist
  (de cpu.abi o --arch), ro.product.board (de ro.board.platform), ro.build.description
  (de release/id/incremental), ro.product.first_api_level (de sdk) y
  ro.build.version.security_patch (placeholder 1970-01-01, con aviso).
- Un build.prop ausente o incompleto ya no detiene el generador sin explicación.
- Probado de punta a punta con una imagen boot v0 sintética. No probado con tu recovery.img.

## Identidad de commits (--git)
- Se quitó el autor fijo del proyecto original. Sin configuración global de git,
  el commit usa `twrpdtgen <twrpdtgen@localhost>`.
