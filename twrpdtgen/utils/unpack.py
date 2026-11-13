#
# Unpacker de boot/recovery image sin AIK.
# Soporta encabezados boot v0, v1 y v2. Devuelve un objeto con los mismos
# atributos que usan las plantillas (image_info.*).
#
# SPDX-License-Identifier: Apache-2.0
#

import shutil
import struct
import subprocess
from pathlib import Path
from typing import Optional

MAGIC = b"ANDROID!"
SUPPORTED_HEADERS = (0, 1, 2)
DECOMPRESSORS = [
	(b"\x1f\x8b", "gzip", ["gzip", "-dc"]),
	(b"\x02\x21\x4c\x18", "lz4", ["lz4", "-dc"]),
	(b"\x28\xb5\x2f\xfd", "zstd", ["zstd", "-dc"]),
	(b"\xfd7zXZ\x00", "xz", ["xz", "-dc"]),
	(b"\x5d\x00\x00", "lzma", ["xz", "-dc", "--format=lzma"]),
]


class ImageInfo:
	"""Campos que usan las plantillas. Todos los tamaños/direcciones son strings hex o None."""
	def __init__(self):
		self.header_version: str = "0"
		self.base_address: Optional[str] = None
		self.ramdisk_offset: Optional[str] = None
		self.tags_offset: Optional[str] = None
		self.pagesize: Optional[str] = None
		self.cmdline: Optional[str] = None
		self.origsize: int = 0
		self.sigtype: Optional[str] = None
		self.ramdisk_compression: Optional[str] = None
		self.kernel: Optional[Path] = None
		self.dt: Optional[Path] = None
		self.dtb: Optional[Path] = None
		self.dtbo: Optional[Path] = None
		self.ramdisk: Optional[Path] = None


def _align(value: int, page: int) -> int:
	return (value + page - 1) // page * page


def _parse_header(data: bytes) -> dict:
	if data[:8] != MAGIC:
		raise ValueError("No es una imagen Android boot/recovery (falta ANDROID!)")

	(kernel_size, kernel_addr, ramdisk_size, ramdisk_addr,
	 second_size, _second_addr, tags_addr, page_size,
	 header_version, _os_version) = struct.unpack_from("<10I", data, 8)

	# En v0 el offset 40 es 'unused' y algunos firmwares (p. ej. Samsung) meten ahí otro dato
	# (os_version). Si el valor no es 0-2, se trata como v0 y se avisa.
	if header_version not in SUPPORTED_HEADERS:
		print(f"[!] El campo header_version vale {header_version} (no es 0-2). "
			  "Se asume boot v0 y ese campo se ignora.")
		header_version = 0
	if page_size == 0:
		raise ValueError("page_size = 0: encabezado inválido")

	h = {
		"kernel_size": kernel_size, "kernel_addr": kernel_addr,
		"ramdisk_size": ramdisk_size, "ramdisk_addr": ramdisk_addr,
		"second_size": second_size, "tags_addr": tags_addr,
		"page_size": page_size, "header_version": header_version,
		"cmdline": data[64:576].split(b"\0")[0].decode(errors="ignore"),
		"recovery_dtbo_size": 0, "recovery_dtbo_offset": 0,
		"dtb_size": 0,
	}
	if header_version >= 1:
		h["recovery_dtbo_size"], = struct.unpack_from("<I", data, 1632)
		h["recovery_dtbo_offset"], = struct.unpack_from("<Q", data, 1636)
	if header_version >= 2:
		h["dtb_size"], = struct.unpack_from("<I", data, 1648)
	return h


def _section(data: bytes, offset: int, size: int) -> bytes:
	chunk = data[offset:offset + size]
	if size and len(chunk) != size:
		raise ValueError("La imagen está truncada")
	return chunk


def _detect_compression(blob: bytes):
	for magic, name, cmd in DECOMPRESSORS:
		if blob.startswith(magic):
			return name, cmd
	return None, None


def unpack_image(image: Path, workdir: Path) -> ImageInfo:
	"""Extrae kernel, ramdisk y secciones opcionales de la imagen dentro de workdir."""
	data = image.read_bytes()
	h = _parse_header(data)
	page = h["page_size"]
	info = ImageInfo()

	info.header_version = str(h["header_version"])
	info.pagesize = str(page)
	info.cmdline = h["cmdline"] or None
	info.origsize = image.stat().st_size

	# AVB: el footer AVBf va en los últimos 64 bytes de la imagen
	if len(data) >= 64 and data[-64:-60] == b"AVBf":
		info.sigtype = "AVBv2"

	# Base: convención de AOSP, kernel_addr = base + 0x8000
	base = (h["kernel_addr"] - 0x8000) & 0xffffffff
	info.base_address = f"0x{base:08x}"
	info.ramdisk_offset = f"0x{(h['ramdisk_addr'] - base) & 0xffffffff:08x}"
	info.tags_offset = f"0x{(h['tags_addr'] - base) & 0xffffffff:08x}"

	workdir.mkdir(parents=True, exist_ok=True)

	# Secciones, en orden: kernel, ramdisk, second, recovery_dtbo (v1), dtb (v2)
	off = page
	kernel = _section(data, off, h["kernel_size"])
	off += _align(h["kernel_size"], page)
	ramdisk_blob = _section(data, off, h["ramdisk_size"])
	off += _align(h["ramdisk_size"], page)
	off += _align(h["second_size"], page)

	kernel_path = workdir / "kernel"
	kernel_path.write_bytes(kernel)
	info.kernel = kernel_path

	if h["header_version"] >= 1 and h["recovery_dtbo_size"]:
		dtbo_path = workdir / "recovery_dtbo.img"
		dtbo_path.write_bytes(_section(data, h["recovery_dtbo_offset"], h["recovery_dtbo_size"]))
		info.dtbo = dtbo_path
		off += _align(h["recovery_dtbo_size"], page)

	if h["header_version"] >= 2 and h["dtb_size"]:
		dtb_path = workdir / "dtb.img"
		dtb_path.write_bytes(_section(data, off, h["dtb_size"]))
		info.dtb = dtb_path

	# Ramdisk: descomprimir y extraer con cpio
	name, cmd = _detect_compression(ramdisk_blob)
	info.ramdisk_compression = name
	raw = ramdisk_blob
	if cmd:
		if shutil.which(cmd[0]) is None:
			raise RuntimeError(f"Falta '{cmd[0]}' en el sistema")
		raw = subprocess.run(cmd, input=ramdisk_blob, capture_output=True, check=True).stdout

	ramdisk_dir = workdir / "ramdisk"
	ramdisk_dir.mkdir(parents=True, exist_ok=True)
	subprocess.run(["cpio", "-idm", "--no-absolute-filenames"],
	               input=raw, cwd=ramdisk_dir, capture_output=True, check=True)
	info.ramdisk = ramdisk_dir

	return info
