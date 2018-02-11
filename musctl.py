#!/usr/bin/env python
#
# Manage and maintain a music library.
#

import raehutils
import sys, os, argparse, logging

class MusCtl(raehutils.RaehBaseClass):
    ERR_RSYNC = 1
    ERR_FILESYSTEM = 2
    ERR_FFMPEG = 3

    def __init__(self):
        self.media_loc = {
            "music":     os.path.join(os.environ["HOME"], "media", "music"),
            "music-portable": os.path.join(os.environ["HOME"], "media", "music-etc", "music-portable"),
            "playlists": os.path.join(os.environ["HOME"], "media", "music-etc", "playlists"),
            "lyrics":    os.path.join(os.environ["HOME"], "media", "music-etc", "lyrics"),
        }
        self.convert_exts = ["flac"]
        self.excluded_dirs = ["etc"]

    ## CLI-related {{{
    def _parse_args(self):
        self.parser = argparse.ArgumentParser(description="Manage and maintain a music library.")
        self.parser.add_argument("-v", "--verbose", help="be verbose", action="count", default=0)
        self.parser.add_argument("-q", "--quiet", help="be quiet (overrides -v)", action="count", default=0)
        subparsers = self.parser.add_subparsers(title="commands", dest="command", metavar="[command]")
        subparsers.required = True

        subp_dedup_pl = subparsers.add_parser("deduplicate-playlists",
                aliases=["deduplicate", "playlist-dedup", "dedup"],
                help="deduplicate playlists",
                description="Remove duplicate track in all playlist files (so that each playlist may only contain a given track once).")
        subp_dedup_pl.set_defaults(func=self.cmd_deduplicate_playlists)

        subp_check_pl = subparsers.add_parser("check-playlists",
                aliases=["playlist-check"],
                help="check all playlist tracks exist",
                description="Check for and report any tracks referenced in a playlist that cannot be found.")
        subp_check_pl.set_defaults(func=self.cmd_check_playlists)

        subp_gen_port = subparsers.add_parser("generate-portable",
                aliases=["gen-portable", "gen-port", "portable", "port"],
                help="generate a portable version of the library",
                description="Generate a portable version of the music library, with certain formats re-encoded to a consistent format and most scans and extras left out. Intended to be used to generate a library usable for portable music players with higher space constraints.")
        subp_gen_port.set_defaults(func=self.cmd_generate_portable)

        subp_maintenance = subparsers.add_parser("maintenance",
                help="run mainentance commands",
                aliases=["maint"],
                description="Run all maintenance commands.")
        subp_maintenance.set_defaults(func=self.cmd_maintenance)

        self.args = self.parser.parse_args()

        self.args.verbose += 1 # force some verbosity
        self._parse_verbosity()
    ## }}}

    def main(self):
        """Main entrypoint after program initialisation."""
        self.args.func()

    def fail_if_error(self, function_ret, msg, ret):
        """Fail if function_ret is non-zero."""
        if function_ret != 0:
            self.fail(msg, ret)

    def cmd_maintenance(self):
        self.cmd_deduplicate_playlists()
        self.cmd_check_playlists()

    def cmd_deduplicate_playlists(self):
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

    def cmd_check_playlists(self):
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

    def __get_playlists(self):
        playlists = {}
        for pl in os.listdir(self.media_loc["playlists"]):
            with open(os.path.join(self.media_loc["playlists"], pl), "r") as f:
                playlists[pl] = f.read().splitlines()
        return playlists

    def cmd_generate_portable(self):
        """Generate a portable version of the music library.

        Certain files are left out, and certain formats are re-encoded.

        The process is complicated slightly by the fact that we don't want to
        perform re-encoding in-place, because it'd mess up the main library,
        waste lots of disk space (and potentially time, if the portable library
        is kept on a separate filesystem) and just not be useful.
        """
        self.logger.info("generating portable library...")

        self.logger.info("finding files to copy...")
        tracks_needing_converting = []
        regular_files = []
        for root, dirs, files in os.walk(self.media_loc["music"], topdown=True):
            # edit dirs in place to remove any excluded ones (must be top-down)
            dirs[:] = [d for d in dirs if d not in self.excluded_dirs]
            for filename in files:
                filepath = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1][1:]

                # add file to either regular list or convert list
                # we remove the non-library part, so we're left with filenames
                # used in playlists e.g. `sort/track.ogg`
                if ext in self.convert_exts:
                    tracks_needing_converting.append(self.__path_without_music_lib(filepath))
                else:
                    regular_files.append(self.__path_without_music_lib(filepath))

        # sort lists, just because (means we go from track 01 -> 10 etc.)
        tracks_needing_converting.sort()
        regular_files.sort()

        self.logger.info("copying files & tracks not requiring conversion...")
        cmd_rsync_regular = ["rsync", "-aR"]
        if self.args.verbose == 2:
            cmd_rsync_regular.append("--info=progress2")
        elif self.args.verbose >= 3:
            cmd_rsync_regular.append("-P")
        cmd_rsync_regular += regular_files + [self.media_loc["music-portable"]]
        self.fail_if_error(
                self.run_shell_cmd(
                    cmd_rsync_regular,
                    cwd=self.media_loc["music"],
                    min_verb_lvl=2),
                "rsync command copying regular files failed", MusCtl.ERR_RSYNC)

        self.logger.info("converting tracks and placing into portable library...")
        total_convert_tracks = len(tracks_needing_converting)
        for track_num in range(total_convert_tracks):
            track = tracks_needing_converting[track_num]
            infile = os.path.join(self.media_loc["music"], track)
            outdir = os.path.dirname(os.path.join(self.media_loc["music-portable"], track))

            self.logger.info("converting track ({}/{}): {}".format(
                track_num+1, total_convert_tracks, track))

            # ensure the track's directory exists
            self.fail_if_error(
                    self.run_shell_cmd(["mkdir", "-p", outdir]),
                    "couldn't create directory structure for a track to be converted",
                    MusCtl.ERR_FILESYSTEM)

            # convert and move (without converting in place)
            self.fail_if_error(
                    self.__ffmpeg_convert(infile, outdir),
                    "an ffmpeg command failed", MusCtl.ERR_FFMPEG)

        self.logger.info("portable library generated")

    def __path_without_music_lib(self, path):
        """Remove media_loc["music"] from the start of a path."""
        return path.replace("{}/".format(self.media_loc["music"]), "")

    def __ffmpeg_convert(self, infile, outdir):
        """Convert a track and place the output in the given directory.

          * infile is guaranteed to have an extension
          * outdir is guaranteed to be a valid existing directory

        Things we do in the conversion:

          * null video (i.e. remove embedded album art)
          * convert to OGG, quality 5

        If the outfile exists, we fail.

        @param infile an absolute path to a track
        @param outdir absolute path of directory to place the output file in
        @return the return code of the FFmpeg command
        """
        outfile = os.path.join(outdir, os.path.splitext(os.path.basename(infile))[0]+".ogg")
        if os.path.exists(outfile):
            self.fail("ffmpeg outfile already exists: {}".format(outfile), MusCtl.ERR_FILESYSTEM)
            #self.logger.error("ffmpeg outfile already exists: {}".format(outfile)) # TODO
            pass
        cmd_ffmpeg_conv_cp = ["ffmpeg", "-n", "-i", infile, "-vn", "-q:a", "5", outfile]

        rc = self.run_shell_cmd(cmd_ffmpeg_conv_cp)
        #rc = 0 # TODO
        return rc

    def run_shell_cmd(self, cmd, cwd=None, min_verb_lvl=3):
        """Run a shell command, only showing output if sufficiently verbose.

        Assumes that command's output is "optional" in the first place, and
        doesn't require any input.

        @param cmd command to run as an array, where each element is an argument
        @param cwd if present, directory to use as CWD
        @param min_verb_lvl verbosity level required to show output
        @return the command's exit code
        """
        rc = 0
        if self.args.quiet == 0 and self.args.verbose >= min_verb_lvl:
            rc = raehutils.drop_to_shell(cmd, cwd=cwd)
        else:
            rc = raehutils.get_shell(cmd, cwd=cwd)[0]
        return rc

if __name__ == "__main__":
    musctl = MusCtl()
    musctl.run()
