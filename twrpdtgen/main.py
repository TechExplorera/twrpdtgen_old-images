#
# Copyright (C) 2022 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

from argparse import ArgumentParser
from pathlib import Path
from sebaubuntu_libs.liblogging import setup_logging
from twrpdtgen import __version__ as version, current_path
from twrpdtgen.device_tree import DeviceTree

def main():
	print(f"TWRP device tree generator\n"
	      f"Version {version}\n")

	parser = ArgumentParser(prog='python3 -m twrpdtgen')

	# Main DeviceTree arguments
	parser.add_argument("image", type=Path,
						help="path to an image (recovery image or boot image if the device is A/B)")
	parser.add_argument("-o", "--output", type=Path, default=current_path / "output",
						help="custom output folder")

	# Optional DeviceTree arguments
	parser.add_argument("--git", action='store_true',
						help="create a git repo after the generation")
	parser.add_argument("--expect-model", default=None,
						help="fail if the image is not from this model (e.g. SM-A127F)")
	parser.add_argument("--arch", default=None, choices=["arm", "arm64", "x86", "x86_64"],
						help="architecture, used only when build.prop has no cpu.abi")
	parser.add_argument("--build-prop", action='append', default=[], type=Path,
						help="extra build.prop file to read (repeatable)")

	# Logging
	parser.add_argument("-d", "--debug", action='store_true',
						help="enable debugging features")

	args = parser.parse_args()

	setup_logging(args.debug)

	device_tree = DeviceTree(image=args.image,
							 expect_model=args.expect_model,
							 extra_build_props=args.build_prop,
							 arch_hint=args.arch)
	folder = device_tree.dump_to_folder(args.output, git=args.git)
	device_tree.cleanup()

	print(f"\nDone! You can find the device tree in {folder}")
