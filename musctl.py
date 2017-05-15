#!/usr/bin/env python
#
# Manage and maintain a music library.
#

import sys
import os
import argparse
import subprocess
import logging

class MusCtl:
    def __init__(self):
        self.media_loc = {
            "music":     os.path.join(os.environ["HOME"], "media", "music"),
            "playlists": os.path.join(os.environ["HOME"], "media", "music-etc", "playlists"),
            "lyrics":    os.path.join(os.environ["HOME"], "media", "music-etc", "lyrics"),
        }

    ## CLI-related {{{
    def __init_logging(self):
        self.logger = logging.getLogger(os.path.basename(sys.argv[0]))
        lh = logging.StreamHandler()
        lh.setFormatter(logging.Formatter("%(name)s: %(levelname)s: %(message)s"))
        self.logger.addHandler(lh)

    def __parse_args(self):
        self.parser = argparse.ArgumentParser(description="Manage and maintain a music library.")
        self.parser.add_argument("-v", "--verbose", help="be verbose", action="count", default=0)
        self.parser.add_argument("-q", "--quiet", help="be quiet (overrides -v)", action="count", default=0)
        self.parser.add_argument("command", help="command to run")
        self.parser.add_argument("arguments", nargs="*", help="arguments for command")

        self.args = self.parser.parse_args()
        if self.args.verbose == 0:
            self.logger.setLevel(logging.INFO)
        elif self.args.verbose >= 1:
            self.logger.setLevel(logging.DEBUG)
        if self.args.quiet >= 1:
            self.logger.setLevel(logging.NOTSET)

        # dictionary of command -> function
        # command aliases are easily specified by adding to the key tuple
        self.cmds = {
            ("deduplicate-playlists", "deduplicate", "playlist-dedup", "dedup"):
                self.deduplicate_playlists,
            ("help", "h"):
                lambda: self.__show_cmd_help(self.args.arguments),
        }

    def __show_cmd_help(self, args):
        """Show specific command help, or list available commands."""
        if not args:
            print("Available commands: {}".format(", ".join([c[0] for c in self.cmds])))
        else:
            aliases = [c for c in self.cmds.keys() if args[0] in c]
            if not aliases:
                self.exit("unknown command '{}'".format(args[0]), 5)
            aliases = aliases[0]
            print("Command: {}".format(aliases[0]))
            print("Aliases: {}".format(", ".join(aliases[1:])))

    def __parse_cmd(self):
        """Parse commandline command and run a command if found."""
        for cmd_options, cmd_exec in self.cmds.items():
            if self.args.command in cmd_options:
                cmd_exec()
                break
        else:
            self.exit("unknown command '{}'".format(self.args.command), 3)

    def run(self):
        """Run from CLI: parse arguments, execute command."""
        self.__init_logging()
        self.__parse_args()
        self.__parse_cmd()
    ## }}}

    def exit(self, msg, ret):
        """Exit with explanation."""
        self.logger.error(msg)
        sys.exit(ret)

    def get_shell(self, args):
        """Run a shell command and return the exit code."""
        return subprocess.run(args).returncode

    def deduplicate_playlists(self):
        self.logger.info("deduplicating all playlists")
        for playlist in os.listdir(self.media_loc["playlists"]):
            # get file contents
            with open(os.path.join(self.media_loc["playlists"], playlist), "r") as f:
                playlist_orig = f.read().splitlines()

            # get deduplicated contents
            seen = set()
            playlist_dedup = [l for l in playlist_orig if not (l in seen or seen.add(l))]

            # compare
            if playlist_dedup != playlist_orig:
                with open(os.path.join(self.media_loc["playlists"], playlist), "w") as f:
                    for line in playlist_dedup:
                        f.write("{}\n".format(line))
                self.logger.info("playlist dedup: edited {}".format(playlist))

if __name__ == "__main__":
    musctl = MusCtl()
    musctl.run()
