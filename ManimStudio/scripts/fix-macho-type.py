#!/usr/bin/env python3
"""
fix-macho-type.py — flip MH_BUNDLE → MH_DYLIB on every .framework binary.

Apple's archive validator rejects `.framework` bundles whose executable
has Mach-O filetype `MH_BUNDLE` (0x8 = .so file format, dlopen-only).
It demands `MH_DYLIB` (0x6 = dynamic library) — the actual load
commands and content can stay otherwise unchanged.

The diff is exactly one 4-byte field in the Mach-O header at offset 12:

    struct mach_header_64 {
        uint32_t magic;                   // bytes 0-3   (0xcffaedfe LE for 64)
        cpu_type_t cputype;               // bytes 4-7
        cpu_subtype_t cpusubtype;         // bytes 8-11
        uint32_t filetype;                // bytes 12-15  ← we flip 0x8 → 0x6
        ...
    };

After the flip, install_name_tool -id may add LC_ID_DYLIB if missing.
Some MH_BUNDLE binaries already have LC_ID_DYLIB (Cython produces them
that way); for those that don't, we patch one in via a separate pass.

Usage:
    python3 fix-macho-type.py <path-to-.app>

It walks every */<X>.framework/<X> binary, mutates in place, and prints
a summary. Idempotent — already-MH_DYLIB binaries are skipped.
"""
import os
import struct
import subprocess
import sys
from pathlib import Path


# Mach-O magic numbers (little-endian on Apple silicon)
MH_MAGIC_64 = b'\xcf\xfa\xed\xfe'   # 0xfeedfacf LE
MH_MAGIC_32 = b'\xce\xfa\xed\xfe'   # 0xfeedface LE
FAT_MAGIC   = b'\xca\xfe\xba\xbe'   # multi-arch (rare for .so)
FAT_MAGIC_LE = b'\xbe\xba\xfe\xca'  # multi-arch little-endian (modern fat)

# Mach-O filetypes
MH_OBJECT  = 0x1
MH_EXECUTE = 0x2
MH_DYLIB   = 0x6
MH_BUNDLE  = 0x8


def patch_one(path: Path) -> str:
    """Flip MH_BUNDLE → MH_DYLIB in a single Mach-O file. Returns one of:
       'patched', 'already_dylib', 'not_macho', 'unsupported_arch', 'fat_macho'."""
    if not path.is_file() or path.is_symlink():
        return 'not_macho'
    try:
        with open(path, 'r+b') as f:
            magic = f.read(4)
            if magic == FAT_MAGIC or magic == FAT_MAGIC_LE:
                # FAT (multi-arch) Mach-O. Each slice has its own header
                # we'd need to patch separately. Rare for iOS .so but
                # handle gracefully: punt to lipo + per-slice patch.
                return 'fat_macho'
            if magic not in (MH_MAGIC_64, MH_MAGIC_32):
                return 'not_macho'
            f.seek(12)
            filetype_bytes = f.read(4)
            filetype = struct.unpack('<I', filetype_bytes)[0]
            if filetype == MH_DYLIB:
                return 'already_dylib'
            if filetype != MH_BUNDLE:
                return 'unsupported_filetype_%d' % filetype
            f.seek(12)
            f.write(struct.pack('<I', MH_DYLIB))
        return 'patched'
    except OSError as e:
        return f'error: {e}'


def patch_fat(path: Path) -> str:
    """For a fat Mach-O, extract each slice with lipo, patch, recombine."""
    try:
        # List archs
        r = subprocess.run(['lipo', '-archs', str(path)],
                           capture_output=True, text=True, check=True)
        archs = r.stdout.strip().split()
        slices = []
        try:
            for a in archs:
                slice_path = path.parent / f"{path.name}.{a}"
                subprocess.run(['lipo', str(path), '-thin', a, '-output', str(slice_path)],
                               check=True, capture_output=True)
                patch_one(slice_path)
                slices.append((a, slice_path))
            # Recombine
            cmd = ['lipo', '-create']
            for _, sp in slices:
                cmd += ['-arch', _, str(sp)]
            cmd += ['-output', str(path)]
            subprocess.run(cmd, check=True, capture_output=True)
        finally:
            for _, sp in slices:
                try: sp.unlink()
                except OSError: pass
        return 'patched_fat'
    except subprocess.CalledProcessError as e:
        return f'fat_error: {e}'


# Mach-O load command IDs we care about
LC_SEGMENT     = 0x1
LC_SEGMENT_64  = 0x19
LC_ID_DYLIB    = 0xd


def add_id_dylib_if_missing(path: Path, install_name: str) -> bool:
    """Insert an LC_ID_DYLIB load command into a Mach-O file in place.

    Cython-generated Python C extensions ship as MH_BUNDLE without an
    LC_ID_DYLIB. After we flip the filetype to MH_DYLIB, dyld refuses to
    load them with `MH_DYLIB is missing LC_ID_DYLIB`. `install_name_tool
    -id` cannot help — it only modifies an existing LC_ID_DYLIB, never
    inserts one. So we patch the binary directly by writing a new
    dylib_command struct into the unused padding between the end of the
    existing load commands and the first section's file offset.

    Returns True if the binary now has LC_ID_DYLIB (already had one, or
    we successfully added it). Returns False if there isn't enough
    padding to insert one (very rare for Cython-generated extensions).
    """
    name_b = install_name.encode('utf-8') + b'\x00'
    # Total command size = 24 (fixed dylib_command header) + name + pad to 8.
    fixed = 24
    pad_len = (-(fixed + len(name_b))) % 8
    name_padded = name_b + b'\x00' * pad_len
    new_cmdsize = fixed + len(name_padded)
    new_cmd = struct.pack(
        '<IIIIII',
        LC_ID_DYLIB,    # cmd
        new_cmdsize,    # cmdsize
        24,             # name offset within this load command
        2,              # timestamp
        0x00010000,     # current_version 1.0.0
        0x00010000,     # compatibility_version 1.0.0
    ) + name_padded

    try:
        with open(path, 'r+b') as f:
            magic = f.read(4)
            if magic not in (MH_MAGIC_64, MH_MAGIC_32):
                return False
            is_64 = (magic == MH_MAGIC_64)
            header_size = 32 if is_64 else 28
            seg_cmd_id = LC_SEGMENT_64 if is_64 else LC_SEGMENT
            section_size = 80 if is_64 else 68

            # Re-read header to pull ncmds/sizeofcmds.
            f.seek(0)
            if is_64:
                (_m, _ct, _cs, _ft, ncmds,
                 sizeofcmds, _flg, _res) = struct.unpack('<IIIIIIII', f.read(32))
            else:
                (_m, _ct, _cs, _ft, ncmds,
                 sizeofcmds, _flg) = struct.unpack('<IIIIIII', f.read(28))

            # Walk load commands. Detect existing LC_ID_DYLIB and find the
            # lowest section file offset (= upper bound on how far we can
            # grow the load-commands region without shifting data).
            lowest_section_offset = None
            f.seek(header_size)
            for _ in range(ncmds):
                cmd_pos = f.tell()
                cmd, cmdsize = struct.unpack('<II', f.read(8))
                if cmd == LC_ID_DYLIB:
                    return True  # idempotent: already present
                if cmd == seg_cmd_id:
                    f.read(16)  # segname
                    if is_64:
                        # vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, flags
                        _va, _vs, _fo, _fs = struct.unpack('<QQQQ', f.read(32))
                        _mp, _ip, nsects, _fl = struct.unpack('<IIII', f.read(16))
                    else:
                        _va, _vs, _fo, _fs = struct.unpack('<IIII', f.read(16))
                        _mp, _ip, nsects, _fl = struct.unpack('<IIII', f.read(16))
                    for _ in range(nsects):
                        sec = f.read(section_size)
                        # In section_64, offset is at bytes 48..51.
                        # In section, offset is at bytes 40..43.
                        off_pos = 48 if is_64 else 40
                        offset = struct.unpack('<I', sec[off_pos:off_pos + 4])[0]
                        if offset > 0 and (
                            lowest_section_offset is None
                            or offset < lowest_section_offset
                        ):
                            lowest_section_offset = offset
                f.seek(cmd_pos + cmdsize)

            end_of_lc = header_size + sizeofcmds
            if lowest_section_offset is None:
                # No sections — fail safe. Shouldn't happen for real .so files.
                return False
            available = lowest_section_offset - end_of_lc
            if available < new_cmdsize:
                return False

            # Splice the new load command into the padding.
            f.seek(end_of_lc)
            f.write(new_cmd)

            # Bump ncmds / sizeofcmds in the header. Both fields are at
            # the same byte offsets (16 and 20) in 32- and 64-bit headers.
            f.seek(16)
            f.write(struct.pack('<II', ncmds + 1, sizeofcmds + new_cmdsize))
        return True
    except OSError:
        return False


def find_framework_binaries(app_dir: Path):
    """Yield every <X>.framework/<X> binary under <app>/Frameworks/."""
    fw_dir = app_dir / 'Frameworks'
    if not fw_dir.is_dir():
        return
    for fw in fw_dir.iterdir():
        if not fw.is_dir() or not fw.name.endswith('.framework'):
            continue
        plist = fw / 'Info.plist'
        exe_name = fw.name[:-len('.framework')]
        if plist.is_file():
            try:
                r = subprocess.run(
                    ['/usr/libexec/PlistBuddy', '-c',
                     'Print :CFBundleExecutable', str(plist)],
                    capture_output=True, text=True, check=True)
                exe_name = r.stdout.strip() or exe_name
            except subprocess.CalledProcessError:
                pass
        bin_path = fw / exe_name
        if bin_path.is_file() and not bin_path.is_symlink():
            yield fw, bin_path


def main(argv):
    if len(argv) != 2:
        print(f"usage: {argv[0]} <path-to-.app>", file=sys.stderr)
        return 1
    app = Path(argv[1]).resolve()
    if not app.is_dir():
        print(f"not a directory: {app}", file=sys.stderr)
        return 1

    counts = {}
    id_added = 0
    id_already = 0
    id_failed = 0
    id_failures = []
    for fw, binpath in find_framework_binaries(app):
        result = patch_one(binpath)
        if result == 'fat_macho':
            result = patch_fat(binpath)
        # Always attempt LC_ID_DYLIB insertion — including on `already_dylib`
        # binaries. A previous wrap-script run may have flipped the filetype
        # via patch_one() but failed to add LC_ID_DYLIB (the old codepath
        # used install_name_tool, which can only modify an existing
        # LC_ID_DYLIB, not add one). Without LC_ID_DYLIB, dyld refuses the
        # binary at load time. add_id_dylib_if_missing() is idempotent.
        if result.startswith('patched') or result == 'already_dylib':
            install_name = f"@rpath/{fw.name}/{binpath.name}"
            # Distinguish "already had LC_ID_DYLIB" from "we added one" so
            # the build log makes the diff visible.
            had_before = _has_id_dylib(binpath)
            ok = add_id_dylib_if_missing(binpath, install_name)
            if ok and had_before:
                id_already += 1
            elif ok:
                id_added += 1
            else:
                id_failed += 1
                if len(id_failures) < 5:
                    id_failures.append(str(binpath.relative_to(app)))
        counts[result] = counts.get(result, 0) + 1

    print("fix-macho-type summary:")
    for k in sorted(counts):
        print(f"  {counts[k]:5d}  {k}")
    print(f"  LC_ID_DYLIB: {id_added} added, {id_already} already present, "
          f"{id_failed} failed")
    if id_failures:
        print("  failures (first 5):")
        for p in id_failures:
            print(f"    {p}")
    return 0


def _has_id_dylib(path: Path) -> bool:
    """Quick scan: does this Mach-O already have an LC_ID_DYLIB?"""
    try:
        with open(path, 'rb') as f:
            magic = f.read(4)
            if magic not in (MH_MAGIC_64, MH_MAGIC_32):
                return True  # not our problem
            is_64 = (magic == MH_MAGIC_64)
            f.seek(0)
            if is_64:
                hdr = struct.unpack('<IIIIIIII', f.read(32))
            else:
                hdr = struct.unpack('<IIIIIII', f.read(28))
            ncmds = hdr[4]
            f.seek(32 if is_64 else 28)
            for _ in range(ncmds):
                pos = f.tell()
                cmd, cmdsize = struct.unpack('<II', f.read(8))
                if cmd == LC_ID_DYLIB:
                    return True
                f.seek(pos + cmdsize)
        return False
    except OSError:
        return True


if __name__ == '__main__':
    sys.exit(main(sys.argv))
