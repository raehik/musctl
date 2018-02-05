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

        subp_dedup_pl = subparsers.add_parser("deduplicate-playlists",
                aliases=["deduplicate", "playlist-dedup", "dedup"],
                help="deduplicate playlists",
                description="Remove duplicate track in all playlist files (so that each playlist may only contain a given track once).")
        subp_dedup_pl.set_defaults(func=self.deduplicate_playlists)

        subp_check_pl = subparsers.add_parser("check-playlists",
                aliases=["playlist-check"],
                help="check all playlist tracks exist",
                description="Check for and report any tracks referenced in a playlist that cannot be found.")
        subp_check_pl.set_defaults(func=self.check_playlists)

        subp_maintenance = subparsers.add_parser("maintenance",
                help="run mainentance commands",
                aliases=["maint"],
                description="Run all maintenance commands.")
        subp_maintenance.set_defaults(func=self.cmd_maintenance)

        self.args = self.parser.parse_args()
        if self.args.verbose == 0:
            self.logger.setLevel(logging.INFO)
        elif self.args.verbose >= 1:
            self.logger.setLevel(logging.DEBUG)
        if self.args.quiet >= 1:
            self.logger.setLevel(logging.NOTSET)

        self.args.func()

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

    def __get_playlists(self):
        playlists = {}
        for pl in os.listdir(self.media_loc["playlists"]):
            with open(os.path.join(self.media_loc["playlists"], pl), "r") as f:
                playlists[pl] = f.read().splitlines()
        return playlists

    def deduplicate_playlists(self):
        self.logger.info("deduplicating all playlists...")
        playlist_was_edited = False
        for playlist, tracks in self.__get_playlists().items():
            # get deduplicated contents
            seen = set()
            tracks_dedup = [l for l in tracks if not (l in seen or seen.add(l))]

            # compare
            if tracks_dedup != tracks:
                playlist_was_edited = True
                with open(os.path.join(self.media_loc["playlists"], playlist), "w") as f:
                    for line in tracks_dedup:
                        f.write("{}\n".format(line))
                self.logger.info("playlist dedup: edited {}".format(playlist))

        if playlist_was_edited:
            self.logger.warning("one or more playlists were edited to remove duplicate tracks")
        else:
            self.logger.info("no edits made")

    def check_playlists(self):
        self.logger.info("checking for non-existing playlist tracks...")
        nonexist_track_was_found = False
        for playlist, tracks in self.__get_playlists().items():
            for line in tracks:
                if line.startswith("#"):
                    # ignore comment lines
                    continue
                track = os.path.join(self.media_loc["music"], line)
                ret = os.path.exists(track)
                if ret == False:
                    nonexist_track_was_found = True
                    self.logger.info("playlist '{}' contained non-existing track '{}'".format(playlist, track))

        if nonexist_track_was_found:
            self.logger.warning("one or many playlists contained non-existing tracks")
        else:
            self.logger.info("all playlists contain only valid filepaths")

    def cmd_maintenance(self):
        self.deduplicate_playlists()
        self.check_playlists()

if __name__ == "__main__":
    musctl = MusCtl()
    musctl.run()
