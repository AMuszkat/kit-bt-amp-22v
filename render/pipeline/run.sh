#!/usr/bin/env bash
# Reproducible, fully headless render of the native KiCad board.
#   render/pipeline/run.sh [--draft] [--reuse-glb]
# Needs kicad-cli, /usr/bin/python3 with pcbnew, Blender, and CQ_PYTHON with
# numpy + Pillow (only for JSON and image composition; CadQuery is not needed).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
proj="$(cd "$here/../.." && pwd)"
name=kit-bt-amp-22v
py="${CQ_PYTHON:-$HOME/miniforge3/bin/python}"
work="$proj/render/work"
out="$proj/render/output"
mkdir -p "$work" "$out"
draft=0
reuse=0
for arg in "$@"; do
  case "$arg" in
    --draft) draft=1 ;;
    --reuse-glb) reuse=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ "$reuse" = 0 ]; then
  kicad-cli pcb export glb -f -o "$work/board.glb" --subst-models --no-dnp \
    --include-tracks --include-pads --include-zones --include-silkscreen \
    --include-soldermask "$proj/$name.kicad_pcb" >"$work/glb-export.log" 2>&1
fi
[ -s "$work/board.glb" ] || { echo "GLB export failed; see $work/glb-export.log" >&2; exit 1; }
/usr/bin/python3 "$here/board_info.py" "$proj/$name.kicad_pcb" \
  "$work/components.json" >"$work/board-info.log" 2>&1

"$py" - "$work" "$draft" <<'PY'
import json, sys
work, draft = sys.argv[1], sys.argv[2] == "1"
job = {"glb": f"{work}/board.glb", "components": f"{work}/components.json",
       "beauty": f"{work}/beauty.png", "matte": f"{work}/matte.png"}
if draft:
    job.update(px=1.5e6, samples=48, adaptive=0.03)
else:
    job.update(px=12e6, samples=256, adaptive=0.008)
json.dump(job, open(f"{work}/job.json", "w"), indent=2)
PY
blender -b --factory-startup --python "$here/scene.py" -- "$work/job.json" \
  >"$work/blender.log" 2>&1
[ -s "$work/beauty.png" ] && [ -s "$work/matte.png" ] || {
  echo "Blender render failed; see $work/blender.log" >&2; exit 1; }
grep -E "^(DEVICE|HIDDEN|UNMODELLED_LEFT|BEAUTY|MATTE|EXTENT)" "$work/blender.log" || true

if [ "$draft" = 1 ]; then
  "$py" "$here/compose.py" "$work/beauty.png" "$work/matte.png" \
    "$work/draft_2400x1800.png" --jpg "$work/draft_2400x1800.jpg"
  echo "draft: $work/draft_2400x1800.jpg"
else
  "$py" "$here/compose.py" "$work/beauty.png" "$work/matte.png" \
    "$out/${name}_2400x1800.png" --jpg "$out/${name}_2400x1800.jpg"
  echo "render: $out/${name}_2400x1800.png"
  echo "render: $out/${name}_2400x1800.jpg"
fi
