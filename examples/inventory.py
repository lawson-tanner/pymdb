#!/usr/bin/env python3
"""Inventory an Avid media folder's database as CSV.

One row per live mob: name, project, essence, volume, bin and file path --
the columns you want when media has gone offline and you need to work out
what was where.

    python3 examples/inventory.py msmMMOB.mdb > inventory.csv
"""
import csv
import sys

import mdb


COLUMNS = ["object_id", "mob_id", "name", "project", "usage", "track_kind",
           "edit_rate", "essence", "length", "volume", "bin", "path",
           "source_mob"]


def rows(f):
    for mob in f.spine_mobs:
        descriptor = mob.descriptor
        sources = mob.sources()
        yield {
            "object_id": "0x%x" % mob.object_id,
            "mob_id": mob.mob_id.hex() if mob.mob_id else "",
            "name": mob.name or "",
            "project": mob.attribute("_PJ") or "",
            "usage": mob.usage_code_name,
            "track_kind": ", ".join(sorted(
                {t.track_kind_name for t in (mob.tracks or [])})),
            "edit_rate": str(mob.edit_rate) if mob.edit_rate else "",
            "essence": descriptor.summary() if descriptor else "",
            "length": getattr(descriptor, "length", "") or "",
            "volume": "; ".join(mob.volumes()),
            "bin": "; ".join(mob.bins()),
            "path": "; ".join(mob.paths()),
            "source_mob": sources[0].name if sources else "",
        }


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with mdb.open(argv[1]) as f:
        writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows(f))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
