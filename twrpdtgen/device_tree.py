#
# Copyright (C) 2022 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

from datetime import datetime
from git import Repo
from os import chmod
from pathlib import Path
from twrpdtgen.utils.unpack import unpack_image
import tempfile
from sebaubuntu_libs.libandroid.device_info import DeviceArch, DeviceInfo
from sebaubuntu_libs.libandroid.fstab import Fstab
from sebaubuntu_libs.libandroid.props import BuildProp
from sebaubuntu_libs.liblogging import LOGD
from shutil import copyfile, rmtree
from stat import S_IRWXU, S_IRGRP, S_IROTH
from twrpdtgen import __version__ as version
from twrpdtgen.templates import render_template
from typing import List

BUILDPROP_LOCATIONS = [Path() / "default.prop",
                       Path() / "prop.default",]
BUILDPROP_LOCATIONS += [Path() / dir / "build.prop"
                        for dir in ["system", "vendor"]]
BUILDPROP_LOCATIONS += [Path() / dir / "etc" / "build.prop"
                        for dir in ["system", "vendor"]]

FSTAB_LOCATIONS = [Path() / "etc" / "recovery.fstab"]
FSTAB_LOCATIONS += [Path() / dir / "etc" / "recovery.fstab"
                    for dir in ["system", "vendor"]]

INIT_RC_LOCATIONS = [Path()]
INIT_RC_LOCATIONS += [Path() / dir / "etc" / "init"
                      for dir in ["system", "vendor"]]

ARCH_HINT_TO_ABI = {
	"arm": "armeabi-v7a",
	"arm64": "arm64-v8a",
	"x86": "x86",
	"x86_64": "x86_64",
}

class DeviceTree:
	"""
	A class representing a device tree

	It initialize a basic device tree structure
	and save the location of some important files
	"""
	def __init__(self, image: Path, expect_model: str = None, extra_build_props=None, arch_hint: str = None):
		"""Initialize the device tree class."""
		self.image = image

		self.current_year = str(datetime.now().year)

		# Check if the image exists
		if not self.image.is_file():
			raise FileNotFoundError("Specified file doesn't exist")

		# Extract the image
		self._workdir = Path(tempfile.mkdtemp(prefix="twrpdtgen-"))
		self.image_info = unpack_image(image, self._workdir)

		LOGD("Getting device infos...")
		self.build_prop = BuildProp()
		for build_prop in [self.image_info.ramdisk / location for location in BUILDPROP_LOCATIONS]:
			if not build_prop.is_file():
				continue

			self.build_prop.import_props(build_prop)

		for extra in (extra_build_props or []):
			if Path(extra).is_file():
				self.build_prop.import_props(Path(extra))

		self._inject_product_fallbacks(arch_hint)

		self.device_info = DeviceInfo(self.build_prop)

		self._validate_image(expect_model)

		# Generate fstab
		self.fstab = None
		for fstab in [self.image_info.ramdisk / location for location in FSTAB_LOCATIONS]:
			if not fstab.is_file():
				continue

			LOGD(f"Generating fstab using {fstab} as reference...")
			self.fstab = Fstab(fstab)
			break

		if self.fstab is None:
			raise AssertionError("fstab not found")

		# Search for init rc files
		self.init_rcs: List[Path] = []
		for init_rc_path in [self.image_info.ramdisk / location for location in INIT_RC_LOCATIONS]:
			if not init_rc_path.is_dir():
				continue

			self.init_rcs += [init_rc for init_rc in init_rc_path.iterdir()
			                  if init_rc.name.endswith(".rc") and init_rc.name != "init.rc"]

	def _inject_product_fallbacks(self, arch_hint: str = None):
		"""Firmwares viejos solo traen ro.product.* sin prefijo de partición, y sebaubuntu_libs
		exige variantes como ro.product.system.device o ro.system.product.cpu.abilist.
		Se copian desde la propiedad base cuando falta, y el ABI se toma de --arch si no hay."""
		prefixes = ["", "system.", "vendor.", "product.", "odm.", "system_ext.", "bootimage."]
		bases = ["device", "manufacturer", "brand", "model", "name"]
		fallback_lines = []

		for base in bases:
			value = self.build_prop.get_prop(f"ro.product.{base}")
			if not value:
				continue
			for prefix in prefixes:
				key = f"ro.product.{prefix}{base}"
				if not self.build_prop.get_prop(key):
					fallback_lines.append(f"{key}={value}")

		abilist_props = [f"ro.{p}product.cpu.abilist" for p in ["", "system.", "vendor.", "odm."]]
		abilist_props += ["ro.product.cpu.abilist"]
		if not any(self.build_prop.get_prop(k) for k in abilist_props):
			abi = self.build_prop.get_prop("ro.product.cpu.abi") or ARCH_HINT_TO_ABI.get(arch_hint or "")
			if not abi:
				raise AssertionError(
					"build.prop no trae cpu.abilist ni cpu.abi. Pasa --arch arm, arm64, x86 o x86_64.")
			fallback_lines += [f"{k}={abi}" for k in abilist_props]

		# Propiedades obligatorias de sebaubuntu_libs que los firmwares viejos no traen.
		# Se derivan de otras o se rellenan con un valor marcado (se avisa al usuario).
		def have(key):
			return self.build_prop.get_prop(key) or any(l.startswith(key + "=") for l in fallback_lines)

		if not have("ro.product.board"):
			plat = self.build_prop.get_prop("ro.board.platform") or "unknown"
			fallback_lines.append(f"ro.product.board={plat}")
			print(f"[!] ro.product.board ausente: se usa '{plat}' (revisa BOARD/bootloader)")

		if not have("ro.build.description") and not self.build_prop.get_prop("ro.build.fingerprint"):
			rel = self.build_prop.get_prop("ro.build.version.release") or "unknown"
			bid = self.build_prop.get_prop("ro.build.id") or "unknown"
			inc = self.build_prop.get_prop("ro.build.version.incremental") or "unknown"
			dev = self.build_prop.get_prop("ro.product.device") or "unknown"
			fallback_lines.append(f"ro.build.description={dev}-user {rel} {bid} {inc} release-keys")

		if not have("ro.product.first_api_level"):
			sdk = self.build_prop.get_prop("ro.build.version.sdk") or "1"
			fallback_lines.append(f"ro.product.first_api_level={sdk}")

		if not have("ro.build.version.security_patch"):
			fallback_lines.append("ro.build.version.security_patch=1970-01-01")
			print("[!] ro.build.version.security_patch ausente: se usa 1970-01-01 (placeholder)")

		if not fallback_lines:
			return

		fallback = self.image_info.ramdisk.parent / "fallback.prop"
		fallback.write_text("\n".join(fallback_lines) + "\n")
		print(f"[i] build.prop incompleto: se añadieron {len(fallback_lines)} propiedades de respaldo")
		self.build_prop.import_props(fallback)

	def _validate_image(self, expect_model: str = None):
		"""Reject boot headers this generator can't handle and images from the wrong model."""
		header_version = str(self.image_info.header_version)
		if header_version not in ("0", "1", "2"):
			raise AssertionError(
				f"header_version={header_version} not supported (only v0-v2). "
				"boot v3/v4 and vendor_boot need extra work.")

		model = self.device_info.model or ""
		codename = self.device_info.codename or ""
		print(f"[i] header v{header_version} | model: {model} | device: {codename} | "
			  f"platform: {self.device_info.platform}")
		if expect_model and expect_model.lower() not in (model.lower(), codename.lower()):
			raise AssertionError(
				f"Image looks like '{model}' ({codename}), not '{expect_model}'. "
				"Use the image from the correct firmware.")

	def dump_to_folder(self, output_path: Path, git: bool = False) -> Path:
		device_tree_folder = output_path / self.device_info.manufacturer / self.device_info.codename
		prebuilt_path = device_tree_folder / "prebuilt"
		recovery_root_path = device_tree_folder / "recovery" / "root"

		LOGD("Creating device tree folders...")
		if device_tree_folder.is_dir():
			rmtree(device_tree_folder, ignore_errors=True)
		device_tree_folder.mkdir(parents=True)
		prebuilt_path.mkdir(parents=True)
		recovery_root_path.mkdir(parents=True)

		LOGD("Writing makefiles/blueprints")
		self._render_template(device_tree_folder, "Android.bp", comment_prefix="//")
		self._render_template(device_tree_folder, "Android.mk")
		self._render_template(device_tree_folder, "AndroidProducts.mk")
		self._render_template(device_tree_folder, "BoardConfig.mk")
		self._render_template(device_tree_folder, "device.mk")
		self._render_template(device_tree_folder, "extract-files.sh")
		self._render_template(device_tree_folder, "twrp_device.mk", out_file=f"twrp_{self.device_info.codename}.mk")
		self._render_template(device_tree_folder, "README.md")
		self._render_template(device_tree_folder, "setup-makefiles.sh")
		self._render_template(device_tree_folder, "vendorsetup.sh")

		# Set permissions
		chmod(device_tree_folder / "extract-files.sh", S_IRWXU | S_IRGRP | S_IROTH)
		chmod(device_tree_folder / "setup-makefiles.sh", S_IRWXU | S_IRGRP | S_IROTH)

		LOGD("Copying kernel...")
		if self.image_info.kernel is not None:
			copyfile(self.image_info.kernel, prebuilt_path / "kernel")
		if self.image_info.dt is not None:
			copyfile(self.image_info.dt, prebuilt_path / "dt.img")
		if self.image_info.dtb is not None:
			copyfile(self.image_info.dtb, prebuilt_path / "dtb.img")
		if self.image_info.dtbo is not None:
			copyfile(self.image_info.dtbo, prebuilt_path / "dtbo.img")

		LOGD("Copying fstab...")
		(device_tree_folder / "recovery.fstab").write_text(self.fstab.format(twrp=True))

		LOGD("Copying init scripts...")
		for init_rc in self.init_rcs:
			copyfile(init_rc, recovery_root_path / init_rc.name, follow_symlinks=True)

		if not git:
			return device_tree_folder

		# Create a git repo
		LOGD("Creating git repo...")

		git_repo = Repo.init(device_tree_folder)
		git_config_reader = git_repo.config_reader()
		git_config_writer = git_repo.config_writer()

		try:
			git_global_email, git_global_name = git_config_reader.get_value('user', 'email'), git_config_reader.get_value('user', 'name')
		except Exception:
			git_global_email, git_global_name = None, None

		if git_global_email is None or git_global_name is None:
			# No se usa la identidad del autor original: si no hay configuración global de git,
			# el commit queda con un autor genérico y neutro.
			git_config_writer.set_value('user', 'email', 'twrpdtgen@localhost')
			git_config_writer.set_value('user', 'name', 'twrpdtgen')

		git_repo.index.add(["*"])
		commit_message = self._render_template(None, "commit_message", to_file=False)
		git_repo.index.commit(commit_message)

		return device_tree_folder

	def _render_template(self, *args, comment_prefix: str = "#", **kwargs):
		return render_template(*args,
		                       comment_prefix=comment_prefix,
		                       current_year=self.current_year,
		                       device_info=self.device_info,
		                       fstab=self.fstab,
		                       image_info=self.image_info,
		                       version=version,
		                       **kwargs)

	def cleanup(self):
		# Cleanup
		rmtree(self._workdir, ignore_errors=True)
