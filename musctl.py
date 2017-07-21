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

    def __deinit(self):
        # no special deinitialising required
        pass

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
        subparsers = self.parser.add_subparsers(title="commands", dest="command", metavar="[command]")
        subparsers.required = True

        subp_dedup = subparsers.add_parser("deduplicate-playlists",
                aliases=["deduplicate", "playlist-dedup", "dedup"],
                help="deduplicate playlists",
                description="Remove duplicate track in all playlist files (so that each playlist may only contain a given track once).")
        subp_dedup.set_defaults(func=self.deduplicate_playlists)

        subp_all = subparsers.add_parser("all",
                help="run all mainentance commands",
                description="Run all common maintenance commands.")
        subp_all.set_defaults(func=self.cmd_all)

        self.args = self.parser.parse_args()
        if self.args.verbose == 0:
            self.logger.setLevel(logging.INFO)
        elif self.args.verbose >= 1:
            self.logger.setLevel(logging.DEBUG)
        if self.args.quiet >= 1:
            self.logger.setLevel(logging.NOTSET)

        self.args.func()

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

    def run(self):
        """Run from CLI: parse arguments, execute command, deinitialise."""
        self.__init_logging()
        self.__parse_args()
        self.__deinit()
    ## }}}

    def exit(self, msg, ret):
        """Exit with explanation."""
        self.logger.error(msg)
        self.logger.info("deinitialising...")
        self.__deinit()
        sys.exit(ret)

    def get_shell(self, args):
        """Run a shell command and return the exit code."""
        return subprocess.run(args).returncode

    def deduplicate_playlists(self):
        self.logger.info("deduplicating all playlists")
        playlist_was_edited = False
        for playlist in os.listdir(self.media_loc["playlists"]):
            # get file contents
            with open(os.path.join(self.media_loc["playlists"], playlist), "r") as f:
                playlist_orig = f.read().splitlines()

            # get deduplicated contents
            seen = set()
            playlist_dedup = [l for l in playlist_orig if not (l in seen or seen.add(l))]

            # compare
            if playlist_dedup != playlist_orig:
                playlist_was_edited = True
                with open(os.path.join(self.media_loc["playlists"], playlist), "w") as f:
                    for line in playlist_dedup:
                        f.write("{}\n".format(line))
                self.logger.info("playlist dedup: edited {}".format(playlist))
        if not playlist_was_edited:
            self.logger.info("no edits made")

    def cmd_all(self):
        self.deduplicate_playlists()

if __name__ == "__main__":
    musctl = MusCtl()
    musctl.run()
