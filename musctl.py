#!/usr/bin/env python
#
# Manage and maintain a music library.
#

import raehutils
import sys, os, argparse, logging

import configparser

import hashlib

class MusCtl(raehutils.RaehBaseClass):
    DEF_CONFIG_FILE = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expandvars("$HOME/.config"), "musctl.ini")

    DEF_CONVERT_EXTS = ["flac"]
    DEF_EXCLUDE_DIRS = ["etc"]

    HASHER = hashlib.sha256
    HASHER_CHUNK_SIZE = 4096
    HASH_FIELD = "OriginalHash"

    ERR_RSYNC = 1
    ERR_FILESYSTEM = 2
    ERR_FFMPEG = 3
    ERR_CONFIG = 7

    def __init__(self):
        pass

    ## CLI-related {{{
    def _parse_args(self):
        self.parser = argparse.ArgumentParser(description="Manage and maintain a music library.")
        self.parser.add_argument("-v", "--verbose", help="be verbose", action="count", default=0)
        self.parser.add_argument("-q", "--quiet", help="be quiet (overrides -v)", action="count", default=0)
        self.parser.add_argument("-c", "--config",  help="specify configuration file", metavar="FILE", default=MusCtl.DEF_CONFIG_FILE)
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
        self._read_config()

    def _read_config(self):
        config_file = self.args.config
        self.config = configparser.ConfigParser()
        self.config.read(config_file)

        try:
            convert_exts_str = self.config["General"]["convert_exts"]
            self.convert_exts = convert_exts_str.split(",")
        except (AttributeError, KeyError):
            self.convert_exts = MusCtl.DEF_CONVERT_EXTS
        try:
            exclude_dirs_str = self.config["General"]["exclude_dirs"]
            self.exclude_dirs = exclude_dirs_str.split(",")
        except (AttributeError, KeyError):
            self.exclude_dirs = MusCtl.DEF_EXCLUDE_DIRS

        self.media_loc = {
            "music":          self._get_general_opt("media_music"),
            "music-portable": self._get_general_opt("media_music_portable"),
            "playlists":      self._get_general_opt("media_playlists"),
        }

    def _get_general_opt(self, opt_name):
        try:
            return os.path.expanduser(self.config["General"][opt_name])
        except (AttributeError, KeyError):
            return None

    def _require_locs(self, locs):
        for loc in locs:
            if loc == None:
                self.fail("missing a required location", MusCtl.ERR_CONFIG)
                return False
        return True
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
        self._require_locs([
            self.media_loc["playlists"]
        ])

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
        self._require_locs([
            self.media_loc["playlists"],
            self.media_loc["music"]
        ])

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
        self._require_locs([
            self.media_loc["music"],
            self.media_loc["music-portable"]
        ])

        self.logger.info("generating portable library...")

        self.logger.info("finding files to copy...")
        tracks_needing_converting = []
        regular_files = []
        for root, dirs, files in os.walk(self.media_loc["music"], topdown=True):
            # edit dirs in place to remove any excluded ones (must be top-down)
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
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

        if len(regular_files) == 0:
            self.logger.info("(no simple-copy files, moving on)")
        else:
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

    def __ffmpeg_convert(self, intrack, outdir):
        """Convert a track and place the output in the given directory.

        intrack is assumed to have an extension, and outdir is assumed to be a
        valid existing directory that we can write to.

        Things we do in the conversion:

          * null video (i.e. remove embedded album art)
          * convert to OGG, quality 5
          * add a Vorbis comment indicating the original's hash

        If a file with the planned converted track filename already exists, we
        look at its stored hash:

          * if the outtrack's stored hash is different to the intrack's hash,
            fail
          * if the outtrack's stored hash is the same as the intrack's hash,
            return successfully
          * (if we fail to retrieve the outtrack's stored hash, we fail)

        If the outtrack doesn't yet exist, we convert.

        @param intrack an absolute path to a track
        @param outdir absolute path of directory to place the outtrack in
        @return 0 or the return code of the FFmpeg command
        """
        # outtrack filename = outdir+basename (filename only) of intrack
        outtrack = os.path.join(outdir, os.path.splitext(os.path.basename(intrack))[0]+".ogg")

        intrack_hash = self.__get_file_hash(intrack)
        if os.path.exists(outtrack):
            outtrack_stored_hash = self.__get_track_stored_hash(outtrack)
            if outtrack_stored_hash == intrack_hash:
                self.logger.info("(skipping conversion due to matching hashes)")
                return 0
            else:
                self.fail("outtrack's stored hash does not match intrack: {}".format(outtrack), MusCtl.ERR_FILESYSTEM)

        hash_metadata_segment = "{}={}".format(MusCtl.HASH_FIELD, intrack_hash)
        cmd_ffmpeg_conv = ["ffmpeg", "-n", "-i", intrack, "-vn", "-q:a", "5", "-metadata", hash_metadata_segment, outtrack]
        return self.run_shell_cmd(cmd_ffmpeg_conv)

    def __get_file_hash(self, filename):
        """Return the hash of the file referenced by the string passed.

        The hashing method is decided internally.

        @return the file's hash
        """

        hasher = MusCtl.HASHER()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(MusCtl.HASHER_CHUNK_SIZE), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def __get_track_stored_hash(self, track):
        """Return the stored hash of a (converted) track.

        @return the track's stored hash
        """
        cmd_ffprobe_hash = ["ffprobe", track, "-show_entries", "stream_tags={}".format(MusCtl.HASH_FIELD), "-of", "csv=p=0"]
        rc, stdout, _ = raehutils.get_shell(cmd_ffprobe_hash)
        if rc != 0:
            self.fail("error while retrieving stored hash: {}".format(track), MusCtl.ERR_FFMPEG)
        retrieved_hash = stdout.strip()
        if retrieved_hash == "":
            self.fail("converted track has no stored hash: {}".format(track), MusCtl.ERR_FILESYSTEM)
        return retrieved_hash

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
