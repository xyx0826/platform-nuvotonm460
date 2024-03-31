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

# This file is overriding the stdlib module "platform"
# pyright: reportShadowedImports=false

from typing import Any, Dict, List, Optional, Union

from platformio.platform.base import PlatformBase
from platformio.platform.board import PlatformBoardConfig


class Nuvotonm460Platform(PlatformBase):
    """The Nuvoton M460 series platform."""

    def configure_default_packages(
        self,
        options: Dict[str, Any],
        targets: List[str]
    ) -> None:
        """Requests packages based on current environment and targets to run.

        Args:
            options (Dict[str, Any]): Project configuration in current environment.
            https://docs.platformio.org/en/latest/projectconf/index.html
            targets (List[str]): List of targets to run.
            https://docs.platformio.org/en/latest/projectconf/sections/env/options/build/targets.html

        Returns:
            _type_: _description_
        """
        board_id = options.get("board")
        assert board_id and isinstance(board_id, str), \
            "The project configuration file must specify a valid board for the current environment."

        board_config: Dict[str, Any] = self.board_config(board_id)
        build_mcu = options.get(
            "board_build.mcu",
            board_config.get("build.mcu", "")
        )

        frameworks: List[str] = options.get("framework", [])
        if "cmsis" in frameworks:
            # Need MCU to determine which CMSIS device package to require
            assert build_mcu and isinstance(build_mcu, str), \
                "Either the project configuration file or board defintion " \
                f"of \"{board_id}\" must specify a valid MCU."

            device_package = "framework-cmsis-" + build_mcu[0:3] + "0"
            if device_package in self.packages:
                self.packages[device_package]["optional"] = False
            else:
                print(f"[!] Missing CMSIS device package \"{device_package}\" "
                      f"required for device \"{build_mcu}\"")

        super().configure_default_packages(options, targets)

    def get_boards(
        self,
        id_: Optional[str] = None
    ) -> Union[PlatformBoardConfig, Dict[str, PlatformBoardConfig]]:
        """Returns the board with the given ID.
        If ID us unspecified, return a dict of all boards.

        Args:
            id_ (Optional[str], optional): Board ID. Defaults to None.

        Returns:
            Union[Dict[str, Any], Dict[str, Dict[str, Any]]]: Given board or all boards.
        """
        board_or_boards: Union[PlatformBoardConfig, Dict[str, PlatformBoardConfig]] \
            = super().get_boards(id_)

        if board_or_boards and id_:
            # We have the given board
            self._add_default_debug_tools(board_or_boards)
            return board_or_boards
        elif board_or_boards:
            # Board ID unspecified, we have a dict of all boards
            for board in board_or_boards.values():
                self._add_default_debug_tools(board)
        else:
            print(f"[!] Unknown board \"{id_}\"")

        return board_or_boards

    def _add_default_debug_tools(self, board: PlatformBoardConfig) -> None:
        """Updates the given board to include availability of all board debug tools.
        If a board upload protocol is not defined as a debug tool, adds a default OpenOCD definition
        for it.

        Args:
            board (PlatformBoardConfig): The board to update.
        """
        board_debug = board.manifest.get("debug", {})
        board_upload_protocols = board.manifest.get("upload", {}) \
            .get("protocols", [])
        if "tools" not in board_debug:
            board_debug["tools"] = {}

        # Nu-Link
        for probe in ("nulink",):
            if probe not in board_upload_protocols or probe in board_debug["tools"]:
                continue

            # Defined as upload protocol but not debug tool
            print(f"[+] Creating OpenOCD definition for upload protocol \"{probe}\"")
            server_args = ["-s", "$PACKAGE_DIR/openocd/scripts"]
            openocd_board: Optional[str] = board_debug.get("openocd_board")

            if openocd_board:
                server_args.extend(["-f", f"board/{openocd_board}.cfg"])
            else:
                transport = "hla_swd" if probe == "nulink" else "swd"
                server_args.extend([
                    "-f", f"interface/{probe}.cfg",
                    "-c", f"transport select {transport}",
                    "-f", "target/numicroM4.cfg"
                ])
                server_args.extend(board_debug.get("openocd_extra_args", []))

            board_debug["tools"][probe] = {
                "server": {
                    "package": "tool-openocd-nuvoton",
                    "executable": "bin/openocd",
                    "arguments": server_args
                }
            }

            board_debug["tools"][probe]["onboard"] = \
                probe in board_debug.get("onboard_tools", [])
            board_debug["tools"][probe]["default"] = \
                probe in board_debug.get("default_tools", [])

        board.manifest["debug"] = board_debug

    def configure_debug_session(self, debug_config):
        if debug_config.speed:
            server_executable = (debug_config.server or {}).get("executable", "").lower()
            if "openocd" in server_executable:
                debug_config.server["arguments"].extend(
                    ["-c", "adapter speed %s" % debug_config.speed]
                )
