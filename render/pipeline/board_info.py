"""Read the native KiCad board and export render-only component metadata.

Run with KiCad's system Python (the interpreter that provides pcbnew):

    /usr/bin/python3 render/pipeline/board_info.py kit-bt-amp-22v.kicad_pcb render/work/components.json

This script never saves or modifies the board. Dimensions and coordinates are mm.
"""
import json
import sys

import pcbnew

src, output = sys.argv[1:3]
board = pcbnew.LoadBoard(src)
rows = []
for footprint in board.GetFootprints():
    pads = []
    for pad in footprint.Pads():
        pads.append({
            "x": pcbnew.ToMM(pad.GetPosition().x),
            "y": pcbnew.ToMM(pad.GetPosition().y),
            "drill_x": pcbnew.ToMM(pad.GetDrillSize().x),
            "drill_y": pcbnew.ToMM(pad.GetDrillSize().y),
        })
    rows.append({
        "ref": footprint.GetReference(),
        "value": footprint.GetValue(),
        "fpid": footprint.GetFPIDAsString(),
        "x": pcbnew.ToMM(footprint.GetPosition().x),
        "y": pcbnew.ToMM(footprint.GetPosition().y),
        "rotation": footprint.GetOrientationDegrees(),
        "layer": footprint.GetLayerName(),
        "models": [model.m_Filename for model in footprint.Models()],
        "dnp": bool(footprint.IsDNP()) if hasattr(footprint, "IsDNP") else False,
        "pads": pads,
    })

edges = board.GetBoardEdgesBoundingBox()
data = {
    "board_thickness": pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()),
    "edges": [pcbnew.ToMM(edges.GetX()), pcbnew.ToMM(edges.GetY()),
              pcbnew.ToMM(edges.GetWidth()), pcbnew.ToMM(edges.GetHeight())],
    "footprints": rows,
}
with open(output, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
print(f"Read {len(rows)} footprints from {src}; wrote {output}; no board changes made")
