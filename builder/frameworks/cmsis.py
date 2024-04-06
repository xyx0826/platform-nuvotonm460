# Copyright 2014-present PlatformIO <contact@platformio.org>
# Copyright 2024-present xyx0826 <xyx0826@hotmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
CMSIS

The ARM Cortex Microcontroller Software Interface Standard (CMSIS) is a
vendor-independent hardware abstraction layer for the Cortex-M processor
series and specifies debugger interfaces. The CMSIS enables consistent and
simple software interfaces to the processor for interface peripherals,
real-time operating systems, and middleware. It simplifies software
re-use, reducing the learning curve for new microcontroller developers
and cutting the time-to-market for devices.

http://www.arm.com/products/processors/cortex-m/cortex-microcontroller-software-interface-standard.php
"""

import os
import re
import string

from platformio.platform.base import PlatformBase
from platformio.platform.board import PlatformBoardConfig
from SCons.Script import DefaultEnvironment

env = DefaultEnvironment()
platform: PlatformBase = env.PioPlatform()
board: PlatformBoardConfig = env.BoardConfig()
product_line: str = board.get("build.product_line", "")
product_line = product_line.lower()
assert product_line, (
    "Invalid or unspecified product line. "
    "Please specify a valid product line in board definition."
)

env.SConscript("_bare.py")

CMSIS_DIR = platform.get_package_dir("framework-cmsis")
CMSIS_DEVICE_DIR = platform.get_package_dir("framework-cmsis-" + product_line)
SOURCES_PATH = os.path.join(CMSIS_DEVICE_DIR, "Source")
assert all(os.path.isdir(d) for d in (CMSIS_DIR, CMSIS_DEVICE_DIR, SOURCES_PATH))


def generate_default_linker_script(template_path: str, script_path: str) -> None:
    """Generates a default linker script with board RAM and flash size using the
    given template to the given output path.

    Args:
        template_path (str): Path to linker script template.
        script_path (str): Path to default linker script output.
    """
    ram = board.get("upload.maximum_ram_size", 0)
    flash = board.get("upload.maximum_size", 0)
    if ram == 0 or flash == 0:
        print(
            "Warning: either RAM or flash size is zero in upload config of "
            "board definition. "
            "This may cause the default linker script to not work. "
            "Either provide RAM and flash size in board definition or use a "
            "custom linker script for the board."
        )

    script = ""
    with open(template_path) as template_file:
        # Replace parentheses around placeholders with braces
        template = re.sub(r"\$\((.+)\)", r"${\1}", template_file.read())
        data = string.Template(template)
        # In KB
        script = data.substitute(
            CMramSize=str(int(ram / 1024)), CMflashSize=str(int(flash / 1024))
        )

    with open(script_path, "w") as script_file:
        script_file.write(script)


def get_linker_script_path() -> str:
    """Gets path to linker script to use.
    Returns board defined linker script if specified, or a default linker script
    for the current product line.
    Generates the default linker script if one is needed but does not exist.

    Returns:
        str: Path to linker script.
    """
    script_path = ""

    board_linker_script = board.get("build.ldscript", "")
    if board_linker_script:
        print(f'Using board defined linker script "{board_linker_script}"')
        script_path = board_linker_script
    else:
        # Use default linker script in build directory
        default_script_name = product_line + "_DEFAULT.ld"
        default_script_path = \
            os.path.join(env.subst("$BUILD_DIR"), "FrameworkCMSIS", default_script_name)
        if not os.path.isfile(default_script_path):
            template_name = product_line + ".ld"
            env.Replace(LDSCRIPT_PATH=product_line + ".ld")  # Path hint
            print(f"Generating default linker script from platform template "
                  f"\"{template_name}\"")
            template_path = env.GetActualLDScript()
            generate_default_linker_script(template_path, default_script_path)

        script_path = default_script_path

    return script_path


def get_startup_file_path(cmsis_sources_path: str) -> str:
    """Gets path to startup file for the current product line.
    The file should be found in the CMSIS package for the current product line.

    Args:
        cmsis_sources_path (str): Path to CMSIS source directory.

    Returns:
        str: Path to startup file, or empty if one does not exist.
    """
    path_upper = os.path.join(cmsis_sources_path, "GCC", f"startup_{product_line}.S")
    path_lower = os.path.join(cmsis_sources_path, "GCC", f"startup_{product_line}.s")
    path = ""

    if os.path.isfile(path_lower):
        path = path_lower
    elif not os.path.isfile(path_upper):
        print("Warning: could not find startup file "
              f"\"startup_{product_line}(.S|.s)\" in source directory of CMSIS package. "
              "Ignore this warning if the startup file is part of your project instead.")
        
    if path:
        print(f"Using startup file for \"{product_line}\" at \"{path}\"")

    return path


env.Replace(LDSCRIPT_PATH=get_linker_script_path())
startup_file_path = get_startup_file_path(SOURCES_PATH)

# Update build environment

# The final firmware is linked against standard library with two specifications:
# nano.specs - link against a reduced-size variant of libc
# nosys.specs - link against stubbed standard syscalls

env.Append(
    CPPPATH=[
        os.path.join(CMSIS_DIR, "CMSIS", "Include"),
        os.path.join(CMSIS_DEVICE_DIR, "Include"),
        os.path.join(CMSIS_DEVICE_DIR, "Source", "GCC"),
        os.path.join(CMSIS_DEVICE_DIR, "StdDriver", "inc"),
    ],
    LINKFLAGS=["--specs=nano.specs", "--specs=nosys.specs"],
)

# Compile CMSIS sources

env.BuildSources(
    variant_dir=os.path.join("$BUILD_DIR", "FrameworkCMSIS"),
    src_dir=CMSIS_DEVICE_DIR,
    src_filter=[
        f"-<*>",
        f"+<Source/system_{product_line}.c>",
        f"+<Source/GCC/{os.path.basename(startup_file_path)}>",
        f"+<StdDriver/src/*.c>",
    ],
)
