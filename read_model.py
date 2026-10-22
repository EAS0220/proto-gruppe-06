from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import rhino3dm


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "_Data" / "Stockerau Rhino Export from RFEM.3dm"
CSV_PATH = ROOT / "data" / "staebe.csv"
TARGET_LAYER = "MemberAxes"


def point_xyz(point) -> tuple[float, float, float]:
    return (float(point.X), float(point.Y), float(point.Z))


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def main() -> int:
    if not MODEL_PATH.is_file():
        print(f"FEHLER: Rhino-Datei nicht gefunden: {MODEL_PATH}", file=sys.stderr)
        return 2

    model = rhino3dm.File3dm.Read(str(MODEL_PATH))
    if model is None:
        print(f"FEHLER: Rhino-Datei konnte nicht gelesen werden: {MODEL_PATH}", file=sys.stderr)
        return 2

    if model.Settings.ModelUnitSystem != rhino3dm.UnitSystem.Meters:
        print(
            "FEHLER: Das Modell ist nicht in Metern gespeichert "
            f"({model.Settings.ModelUnitSystem}); Koordinaten werden nicht ungeprüft "
            "als Meter ausgegeben.",
            file=sys.stderr,
        )
        return 2

    layers = list(model.Layers)
    layer_by_id = {str(layer.Id): layer for layer in layers}
    target_layers = [layer for layer in layers if layer.Name == TARGET_LAYER]

    if len(target_layers) != 1:
        print(
            f"FEHLER: Erwartet wurde genau ein Layer namens {TARGET_LAYER!r}, "
            f"gefunden: {len(target_layers)}.",
            file=sys.stderr,
        )
        return 2

    target_id = str(target_layers[0].Id)

    def is_under_target(layer_index: int) -> bool:
        layer = layers[layer_index]
        seen: set[str] = set()

        while True:
            layer_id = str(layer.Id)
            if layer_id == target_id:
                return True
            if layer_id in seen:
                return False
            seen.add(layer_id)

            parent_id = str(layer.ParentLayerId)
            parent = layer_by_id.get(parent_id)
            if parent is None:
                return False
            layer = parent

    def profile_path(layer_index: int) -> str:
        parts: list[str] = []
        layer = layers[layer_index]
        seen: set[str] = set()

        while str(layer.Id) != target_id:
            layer_id = str(layer.Id)
            if layer_id in seen:
                break
            seen.add(layer_id)
            parts.append(layer.Name)

            parent = layer_by_id.get(str(layer.ParentLayerId))
            if parent is None:
                break
            layer = parent

        return "/".join(reversed(parts)) or "(MemberAxes)"

    entries: list[dict[str, object]] = []
    unsuitable: list[str] = []

    for object_index, obj in enumerate(model.Objects):
        layer_index = obj.Attributes.LayerIndex
        if not (0 <= layer_index < len(layers)) or not is_under_target(layer_index):
            continue

        geometry = obj.Geometry
        if not isinstance(geometry, rhino3dm.LineCurve):
            unsuitable.append(
                f"Objekt {object_index}, Layer {profile_path(layer_index)!r}: "
                f"{type(geometry).__name__}"
            )
            continue

        start = point_xyz(geometry.PointAtStart)
        end = point_xyz(geometry.PointAtEnd)
        length = float(geometry.Line.Length)
        endpoint_distance = distance(start, end)

        if length <= 0 or abs(length - endpoint_distance) > 1e-8:
            unsuitable.append(
                f"Objekt {object_index}, Layer {profile_path(layer_index)!r}: "
                f"keine gültige gerade Linie (Kurvenlänge {length}, "
                f"Endpunktabstand {endpoint_distance})"
            )
            continue

        entries.append(
            {
                "profile_layer": profile_path(layer_index),
                "start_x_m": start[0],
                "start_y_m": start[1],
                "start_z_m": start[2],
                "end_x_m": end[0],
                "end_y_m": end[1],
                "end_z_m": end[2],
                "length_m": length,
            }
        )

    if unsuitable:
        print(
            f"FEHLER: {len(unsuitable)} ungeeignete Geometrie(n) unter "
            f"{TARGET_LAYER} gefunden:",
            file=sys.stderr,
        )
        for issue in unsuitable:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "nummer",
        "profile_layer",
        "start_x_m",
        "start_y_m",
        "start_z_m",
        "end_x_m",
        "end_y_m",
        "end_z_m",
        "length_m",
    ]

    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for number, entry in enumerate(entries, start=1):
            writer.writerow({"nummer": number, **entry})

    counts = Counter(str(entry["profile_layer"]) for entry in entries)
    print(f"Erfasste Stäbe: {len(entries)}")
    print("Aufschlüsselung nach Profil-Unterlayer:")
    for profile, count in sorted(counts.items()):
        print(f"  {profile}: {count}")
    print(f"CSV geschrieben: {CSV_PATH}")
    print(f"Geprüfte Geometrien: {len(entries)} LineCurve; ungeeignet: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
