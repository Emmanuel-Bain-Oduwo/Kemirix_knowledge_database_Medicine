"""Streaming RRF parsing for the stored RxNorm release.

RRF files are headerless pipe-delimited UTF-8 with the official column
layouts. Members are located by basename anywhere inside the ZIP (releases
nest them under versioned directories). Rows stream line-by-line; nothing
is buffered unboundedly.
"""

import zipfile

from ..exceptions import SourceContractError

RRF_COLUMNS = {
    "RXNCONSO": (
        "RXCUI",
        "LAT",
        "TS",
        "LUI",
        "STT",
        "SUI",
        "ISPREF",
        "RXAUI",
        "SAUI",
        "SCUI",
        "SDUI",
        "SAB",
        "TTY",
        "CODE",
        "STR",
        "SRL",
        "SUPPRESS",
        "CVF",
    ),
    "RXNREL": (
        "RXCUI1",
        "RXAUI1",
        "STYPE1",
        "REL",
        "RXCUI2",
        "RXAUI2",
        "STYPE2",
        "RELA",
        "RUI",
        "SRUI",
        "SAB",
        "SL",
        "RG",
        "DIR",
        "SUPPRESS",
        "CVF",
    ),
    "RXNSAT": (
        "RXCUI",
        "LUI",
        "SUI",
        "RXAUI",
        "STYPE",
        "CODE",
        "ATUI",
        "SATUI",
        "SAB",
        "ATN",
        "ATV",
        "SUPPRESS",
        "CVF",
    ),
    "RXNSTY": ("RXCUI", "TUI", "STN", "STY", "ATUI", "CVF"),
    "RXNDOC": ("KEY", "VALUE", "TYPE", "EXPL"),
}


def locate_member(zip_path, basename):
    """Find one RRF member by basename, case-insensitively."""
    if not basename.upper().endswith(".RRF"):
        basename = basename + ".RRF"
    target = basename.upper()
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if name.upper().rsplit("/", 1)[-1] == target:
                return name
    raise SourceContractError(f"{basename} not found in the RxNorm release")


def iter_rrf(zip_path, basename, *, sab=None, suppress="N"):
    """Stream parsed rows of one RRF member as dicts.

    Filters: sab keeps only rows whose SAB column matches (for example
    RXNORM normalized content); suppress keeps only rows with the given
    SUPPRESS value (None disables the filter).
    """
    columns = RRF_COLUMNS.get(basename.upper())
    if columns is None:
        raise SourceContractError(f"unsupported RRF member: {basename}")
    member = locate_member(zip_path, basename)
    width = len(columns)
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member) as handle:
            for raw in handle:
                line = raw.decode("utf-8").rstrip("\r\n")
                if not line:
                    continue
                fields = line.split("|")
                if len(fields) != width:
                    raise SourceContractError(
                        f"{basename}: expected {width} columns, got {len(fields)}"
                    )
                row = dict(zip(columns, fields))
                if sab is not None and row.get("SAB") != sab:
                    continue
                if suppress is not None and row.get("SUPPRESS") != suppress:
                    continue
                yield row
