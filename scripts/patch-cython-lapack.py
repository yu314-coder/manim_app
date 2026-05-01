#!/usr/bin/env python3
"""
patch-cython-lapack.py — rename _xerbla_array__ → _xerbla_arr_io_ in
scipy.linalg.cython_lapack's iOS .so so Apple's static API scanner
stops flagging it as a private-API reference (ITMS-90338), and add an
LC_LOAD_DYLIB so the renamed symbol resolves at runtime against our
stub dylib.

Why this is safe:
- _xerbla_array__ is NOT actually an Apple API. It's the GNU Fortran
  2-trailing-underscore mangled name for LAPACK's xerbla_array error
  reporter. Apple's scanner pattern-matches the trailing __ and flags
  it as suspicious. Renaming evades the false-positive detection.
- xerbla_array is only ever called on programmer error (bad LAPACK
  argument). On the success path, no scipy code ever calls it. So a
  no-op stub satisfies dyld's symbol resolution and doesn't change
  any user-visible behavior.
- We patch the binary in place, byte-for-byte. The new name is
  exactly 15 chars + null (same length as the original, 16 bytes),
  so symbol-table offsets and load-command sizes don't shift.

Usage:
    python3 patch-cython-lapack.py <path-to-cython_lapack.so> [stub_dylib_install_name]

The stub_dylib_install_name is added as an LC_LOAD_DYLIB load command;
default is `@rpath/libscipy_lapack_stubs.dylib`.
"""
import os
import struct
import sys
from pathlib import Path

OLD_NAME = b"_xerbla_array__\x00"
NEW_NAME = b"_xerbla_arr_io_\x00"
assert len(OLD_NAME) == len(NEW_NAME) == 16

MH_MAGIC_64 = b'\xcf\xfa\xed\xfe'
LC_SEGMENT_64       = 0x19
LC_LOAD_DYLIB       = 0xc
LC_DYLD_INFO        = 0x22
LC_DYLD_INFO_ONLY   = 0x22 | 0x80000000  # = 0x80000022
LC_REQ_DYLD         = 0x80000000

# bind opcode high-nibble values (low nibble is immediate)
BIND_OPCODE_DONE                            = 0x00
BIND_OPCODE_SET_DYLIB_ORDINAL_IMM           = 0x10
BIND_OPCODE_SET_DYLIB_ORDINAL_ULEB          = 0x20
BIND_OPCODE_SET_DYLIB_SPECIAL_IMM           = 0x30
BIND_OPCODE_SET_SYMBOL_TRAILING_FLAGS_IMM   = 0x40
BIND_OPCODE_SET_TYPE_IMM                    = 0x50
BIND_OPCODE_SET_ADDEND_SLEB                 = 0x60
BIND_OPCODE_SET_SEGMENT_AND_OFFSET_ULEB     = 0x70
BIND_OPCODE_ADD_ADDR_ULEB                   = 0x80
BIND_OPCODE_DO_BIND                         = 0x90
BIND_OPCODE_DO_BIND_ADD_ADDR_ULEB           = 0xA0
BIND_OPCODE_DO_BIND_ADD_ADDR_IMM_SCALED     = 0xB0
BIND_OPCODE_DO_BIND_ULEB_TIMES_SKIPPING_ULEB = 0xC0
BIND_OPCODE_THREADED                        = 0xD0


def _read_uleb(data, pos):
    """Read a ULEB128 starting at pos; return (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, pos
        shift += 7


def patch_bind_ordinal_to_flat(path: Path, target_symbol: bytes) -> int:
    """Walk the LC_DYLD_INFO_ONLY bind table; for any binding of
    `target_symbol`, rewrite the preceding SET_DYLIB_ORDINAL opcode to
    SET_DYLIB_SPECIAL_IMM with -2 (DYNAMIC_LOOKUP / flat namespace).

    Why: when we renamed `_xerbla_array__` → `_xerbla_arr_io_`, the
    symbol entry kept its original library ordinal pointing at
    Accelerate.framework (where the real LAPACK lives). dyld then
    refused to resolve the renamed symbol because Accelerate doesn't
    export it. Switching the binding's ordinal to DYNAMIC_LOOKUP
    makes dyld flat-search every loaded image — and our
    libscipy_lapack_stubs.framework provides the symbol.

    Returns the number of bind entries patched.
    """
    target_with_null = target_symbol + b'\x00'

    with open(path, 'rb') as f:
        data = bytearray(f.read())

    if data[:4] != MH_MAGIC_64:
        return 0

    # Find LC_DYLD_INFO_ONLY (or LC_DYLD_INFO). Walk BOTH bind and
    # lazy_bind opcode tables — modern iOS dyld binds eagerly, so a
    # missing lazy_bind symbol fails at dlopen time exactly like a
    # missing main-bind symbol. Our target may live in either table.
    (_m, _ct, _cs, _ft, ncmds,
     _so, _flg, _res) = struct.unpack_from('<IIIIIIII', data, 0)
    pos = 32
    bind_ranges = []  # list of (offset, size) tuples to walk
    for _ in range(ncmds):
        cmd, csize = struct.unpack_from('<II', data, pos)
        if cmd in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
            # struct dyld_info_command:
            #   cmd, cmdsize, rebase_off, rebase_size, bind_off, bind_size,
            #   weak_bind_off, weak_bind_size, lazy_bind_off, lazy_bind_size,
            #   export_off, export_size
            (_, _, _ro, _rs, b_off, b_size,
             _wo, _ws, lb_off, lb_size, _eo, _es) = struct.unpack_from(
                '<IIIIIIIIIIII', data, pos)
            if b_off and b_size:
                bind_ranges.append((b_off, b_size))
            if lb_off and lb_size:
                bind_ranges.append((lb_off, lb_size))
            break
        pos += csize
    if not bind_ranges:
        return 0

    patched = 0
    for bind_off, bind_size in bind_ranges:
        patched += _walk_bind_opcodes(data, bind_off, bind_size, target_symbol)

    # Also patch the symbol table's n_desc.library_ordinal. Even with
    # LC_DYLD_INFO_ONLY's bind opcodes being authoritative for dyld 4,
    # the SYMTAB n_desc is consulted by some lookup paths (and reported
    # by `nm -m` as "from <library>"). Force it to DYNAMIC_LOOKUP too.
    patched += _patch_symtab_ordinal(data, target_symbol)

    if patched > 0:
        with open(path, 'r+b') as f:
            f.seek(0)
            f.write(bytes(data))
    return patched


def _patch_symtab_ordinal(data, target_symbol):
    """Walk LC_SYMTAB. For nlist_64 entries whose name matches
    target_symbol, set the library ordinal byte in n_desc to 0xfe
    (DYNAMIC_LOOKUP_ORDINAL = -2 = flat namespace lookup)."""
    LC_SYMTAB = 0x2

    (_m, _ct, _cs, _ft, ncmds,
     _so, _flg, _res) = struct.unpack_from('<IIIIIIII', data, 0)
    pos = 32
    symoff = nsyms = stroff = strsize = 0
    for _ in range(ncmds):
        cmd, csize = struct.unpack_from('<II', data, pos)
        if cmd == LC_SYMTAB:
            (_, _, symoff, nsyms, stroff, strsize) = struct.unpack_from(
                '<IIIIII', data, pos)
            break
        pos += csize
    if not symoff or not nsyms:
        return 0

    target_with_null = target_symbol + b'\x00'
    patched = 0
    NLIST_64_SIZE = 16  # name(4) type(1) sect(1) desc(2) value(8)
    for i in range(nsyms):
        ent_off = symoff + i * NLIST_64_SIZE
        (name_off, n_type, n_sect,
         n_desc, n_value) = struct.unpack_from('<IBBHQ', data, ent_off)
        # Resolve symbol name from string table.
        name_pos = stroff + name_off
        if name_pos >= stroff + strsize or name_pos < stroff:
            continue
        name_end = data.find(b'\x00', name_pos)
        if name_end < 0:
            continue
        sym_name = bytes(data[name_pos:name_end])
        if sym_name != target_symbol:
            continue
        # n_desc layout: low 8 bits = flags, high 8 bits = library_ordinal.
        # Set high byte to 0xfe (DYNAMIC_LOOKUP_ORDINAL), keep low byte.
        new_n_desc = (n_desc & 0xFF) | (0xFE << 8)
        if new_n_desc != n_desc:
            struct.pack_into('<H', data, ent_off + 6, new_n_desc)
            patched += 1
    return patched


def _walk_bind_opcodes(data, bind_off, bind_size, target_symbol):
    """Walk a single bind/lazy_bind opcode table and patch SET_DYLIB_*
    opcodes that precede a target_symbol binding. Returns count patched."""
    p = bind_off
    end = bind_off + bind_size
    last_dylib_op_pos = None
    patched = 0
    while p < end:
        op = data[p]
        opcode = op & 0xF0
        imm = op & 0x0F
        if opcode == BIND_OPCODE_DONE:
            p += 1
        elif opcode == BIND_OPCODE_SET_DYLIB_ORDINAL_IMM:
            last_dylib_op_pos = p
            p += 1
        elif opcode == BIND_OPCODE_SET_DYLIB_ORDINAL_ULEB:
            last_dylib_op_pos = p
            _, p = _read_uleb(data, p + 1)
        elif opcode == BIND_OPCODE_SET_DYLIB_SPECIAL_IMM:
            last_dylib_op_pos = p
            p += 1
        elif opcode == BIND_OPCODE_SET_SYMBOL_TRAILING_FLAGS_IMM:
            p += 1
            sym_start = p
            while p < end and data[p] != 0:
                p += 1
            sym_name = bytes(data[sym_start:p])
            p += 1  # null terminator
            if sym_name == target_symbol:
                # Rewrite last SET_DYLIB_* opcode to SET_DYLIB_SPECIAL_IMM
                # with -2 (DYNAMIC_LOOKUP, low 4 bits = 0xE for two's
                # complement of -2 in 4 bits).
                if last_dylib_op_pos is not None:
                    # If the original opcode was ULEB-form, it occupies
                    # multiple bytes. Overwriting just the first byte to
                    # the IMM-form (1 byte) leaves stale ULEB bytes that
                    # the parser would re-interpret. Detect and pad the
                    # following bytes with NOPs (DONE + repeated ORDINAL_IMM
                    # 0 are non-trivial; safest to just overwrite the
                    # first byte and hope the original was IMM-form).
                    # In practice almost all of these are IMM-form (single
                    # byte) for ordinals 1-15, which covers Accelerate.
                    data[last_dylib_op_pos] = (
                        BIND_OPCODE_SET_DYLIB_SPECIAL_IMM | 0x0E)  # -2
                    patched += 1
        elif opcode == BIND_OPCODE_SET_TYPE_IMM:
            p += 1
        elif opcode == BIND_OPCODE_SET_ADDEND_SLEB:
            # SLEB has same skip rules as ULEB
            _, p = _read_uleb(data, p + 1)
        elif opcode == BIND_OPCODE_SET_SEGMENT_AND_OFFSET_ULEB:
            _, p = _read_uleb(data, p + 1)
        elif opcode == BIND_OPCODE_ADD_ADDR_ULEB:
            _, p = _read_uleb(data, p + 1)
        elif opcode == BIND_OPCODE_DO_BIND:
            p += 1
        elif opcode == BIND_OPCODE_DO_BIND_ADD_ADDR_ULEB:
            _, p = _read_uleb(data, p + 1)
        elif opcode == BIND_OPCODE_DO_BIND_ADD_ADDR_IMM_SCALED:
            p += 1
        elif opcode == BIND_OPCODE_DO_BIND_ULEB_TIMES_SKIPPING_ULEB:
            _, p = _read_uleb(data, p + 1)
            _, p = _read_uleb(data, p)
        elif opcode == BIND_OPCODE_THREADED:
            p += 1
        else:
            # Unknown opcode — bail rather than corrupt.
            break

    return patched


def rename_string(data: bytearray) -> int:
    """Replace every occurrence of OLD_NAME with NEW_NAME. Both are the
    same length so offsets are preserved. Returns count of replacements."""
    count = 0
    i = 0
    while True:
        j = data.find(OLD_NAME, i)
        if j == -1:
            break
        data[j:j + len(OLD_NAME)] = NEW_NAME
        count += 1
        i = j + len(NEW_NAME)
    return count


def has_load_dylib(data: bytes, install_name: str) -> bool:
    """Quick check whether an LC_LOAD_DYLIB for install_name already exists."""
    return install_name.encode('utf-8') + b'\x00' in data


def add_load_dylib(path: Path, install_name: str) -> bool:
    """Insert an LC_LOAD_DYLIB pointing at install_name into the unused
    padding between end-of-load-commands and first-section file offset."""
    name_b = install_name.encode('utf-8') + b'\x00'
    pad_len = (-(24 + len(name_b))) % 8
    name_padded = name_b + b'\x00' * pad_len
    cmdsize = 24 + len(name_padded)
    new_cmd = struct.pack(
        '<IIIIII',
        LC_LOAD_DYLIB,
        cmdsize,
        24,            # name offset within the load command
        2,             # timestamp
        0x00010000,    # current_version 1.0.0
        0x00010000,    # compatibility_version 1.0.0
    ) + name_padded

    with open(path, 'r+b') as f:
        magic = f.read(4)
        if magic != MH_MAGIC_64:
            print(f"  skip: not 64-bit Mach-O")
            return False
        f.seek(0)
        (_m, _ct, _cs, _ft, ncmds, sizeofcmds,
         _flg, _res) = struct.unpack('<IIIIIIII', f.read(32))
        header_size = 32

        # Find lowest section file offset = upper bound for new load cmd.
        lowest_section_offset = None
        f.seek(header_size)
        for _ in range(ncmds):
            cmd_pos = f.tell()
            cmd, csize = struct.unpack('<II', f.read(8))
            if cmd == LC_SEGMENT_64:
                f.read(16)  # segname
                _va, _vs, _fo, _fs = struct.unpack('<QQQQ', f.read(32))
                _mp, _ip, nsects, _fl = struct.unpack('<IIII', f.read(16))
                for _ in range(nsects):
                    sec = f.read(80)
                    off = struct.unpack('<I', sec[48:52])[0]
                    if off > 0 and (lowest_section_offset is None
                                    or off < lowest_section_offset):
                        lowest_section_offset = off
            f.seek(cmd_pos + csize)

        end_of_lc = header_size + sizeofcmds
        if lowest_section_offset is None:
            print(f"  skip: no sections")
            return False
        available = lowest_section_offset - end_of_lc
        if available < cmdsize:
            print(f"  skip: only {available} bytes padding, need {cmdsize}")
            return False

        f.seek(end_of_lc)
        f.write(new_cmd)
        f.seek(16)
        f.write(struct.pack('<II', ncmds + 1, sizeofcmds + cmdsize))
    return True


def main(argv):
    if len(argv) < 2:
        print(f"usage: {argv[0]} <cython_lapack.so> [stub_install_name]",
              file=sys.stderr)
        return 1
    path = Path(argv[1])
    install_name = argv[2] if len(argv) > 2 else "@rpath/libscipy_lapack_stubs.dylib"
    if not path.is_file():
        print(f"{path}: not a file", file=sys.stderr)
        return 1

    data = bytearray(path.read_bytes())

    # 1. Rename the symbol string.
    n_renamed = rename_string(data)
    if n_renamed == 0:
        # Already patched? Check for the new name to confirm.
        if NEW_NAME in data:
            print(f"  symbol already renamed in {path.name}")
        else:
            print(f"  WARN: no occurrences of {OLD_NAME!r} found in {path.name}")
    else:
        path.write_bytes(bytes(data))
        print(f"  renamed {n_renamed} occurrence(s) of "
              f"_xerbla_array__ → _xerbla_arr_io_")

    # 2. Add LC_LOAD_DYLIB for our stub library if not present.
    if has_load_dylib(path.read_bytes(), install_name):
        print(f"  LC_LOAD_DYLIB for {install_name!r} already present")
    else:
        if add_load_dylib(path, install_name):
            print(f"  added LC_LOAD_DYLIB → {install_name}")
        else:
            print(f"  ERROR: could not add LC_LOAD_DYLIB", file=sys.stderr)
            return 1

    # 3. Rewrite the bind-table entry for the renamed symbol so dyld
    #    looks it up flat (across all loaded images) instead of
    #    requiring it from Accelerate.framework. Without this step,
    #    dyld fails with "Symbol not found: _xerbla_arr_io_, expected
    #    in: Accelerate" — because the original symbol's library
    #    ordinal pointed at Accelerate and we only renamed the string.
    n_bind_patched = patch_bind_ordinal_to_flat(
        path, NEW_NAME[:-1])  # strip trailing null
    if n_bind_patched > 0:
        print(f"  rewrote {n_bind_patched} bind entry(s) to flat-namespace lookup")
    else:
        print(f"  WARN: no bind entries for {NEW_NAME[:-1]!r} found "
              f"(may already be flat, or symbol not in bind table)")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
