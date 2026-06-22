"""
KMZ to CSV Converter (Deep Nesting Fix)
=======================================
Handles Points, LineStrings, Polygons, and MultiGeometry.
Extracts everything deeply nested in Folders or Documents.

Install dependency:
    pip install lxml

Usage:
    python kmz_to_csv.py <input.kmz> [--output-dir <directory>]
"""

import argparse
import csv
import os
import re
import zipfile
from pathlib import Path
import math

try:
    from lxml import etree
except ImportError:
    raise ImportError("Please install lxml:  pip install lxml")


KML_URIS = [
    "http://www.opengis.net/kml/2.2",
    "http://earth.google.com/kml/2.1",
    "http://earth.google.com/kml/2.0",
]


def detect_kml_uri(root) -> str:
    for el in root.iter():
        for uri in KML_URIS:
            if uri in el.tag:
                return uri
    return KML_URIS[0]


def local(el) -> str:
    """Return local tag name of an element."""
    return etree.QName(el.tag).localname

def strip_html(text: str) -> str:
    if not text:
        return ""
    # Ganti tag HTML dengan spasi agar data antar kolom/baris tabel tidak menempel
    text = re.sub(r"<[^>]+>", " ", text)
    # Rapikan spasi yang berlebihan
    return " ".join(text.split())

def get_text(elem, local_tag, kml_uri) -> str:
    el = elem.find(f"{{{kml_uri}}}{local_tag}")
    if el is None:
        for child in elem:
            if local(child) == local_tag:
                el = child
                break
                
    if el is not None:
        # KUNCI UTAMA: Gunakan itertext() untuk mengambil semua teks, 
        # termasuk yang terperangkap di dalam tag HTML <table>, <tr>, <td>
        raw_text = "".join(el.itertext())
        return strip_html(raw_text)
        
    return ""

def get_raw_text(elem, local_tag, kml_uri) -> str:
    """Mengambil teks mentah beserta tag HTML-nya tanpa dipotong."""
    el = elem.find(f"{{{kml_uri}}}{local_tag}")
    if el is None:
        for child in elem:
            if local(child) == local_tag:
                el = child
                break
    return el.text if el is not None and el.text else ""

def parse_description_table(html_text: str) -> dict:
    """Membedah tabel HTML di dalam description menjadi kolom CSV."""
    if not html_text:
        return {}
    data = {}
    try:
        # Gunakan etree.HTML untuk membaca struktur tabel
        doc = etree.HTML(html_text)
        if doc is None:
            return {}
            
        # Cari semua elemen baris tabel (<tr>)
        for tr in doc.xpath('//tr'):
            # Ambil sel tabel (<td> atau <th>)
            cells = tr.xpath('./td | ./th')
            if len(cells) >= 2:
                # Kolom kiri jadi kunci, kolom kanan jadi nilai
                key = "".join(cells[0].itertext()).strip()
                val = "".join(cells[1].itertext()).strip()
                
                # Bersihkan nilai kosong bawaan GIS
                if val in ("<Null>", "&lt;Null&gt;", "Null", "null"):
                    val = ""
                    
                # Abaikan baris aneh yang berisi script JavaScript bawaan ArcGIS
                if key and not key.startswith("function") and not key.startswith("document."):
                    data[key] = val
    except Exception:
        pass
    return data


# ---------------------------------------------------------------------------
# Coordinate / geometry helpers
# ---------------------------------------------------------------------------

def parse_coord_string(coords_text: str):
    if not coords_text:
        return []
    points = []
    for token in coords_text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                alt = float(parts[2]) if len(parts) > 2 else 0.0
                points.append((lon, lat, alt))
            except ValueError:
                continue
    return points


def coords_to_wkt_linestring(points) -> str:
    inner = ", ".join(f"{p[0]} {p[1]}" for p in points)
    return f"LINESTRING ({inner})"


def coords_to_wkt_point(lon, lat) -> str:
    return f"POINT ({lon} {lat})"


def coords_to_wkt_polygon(points) -> str:
    inner = ", ".join(f"{p[0]} {p[1]}" for p in points)
    return f"POLYGON (({inner}))"


def get_geometry(pm) -> dict:
    base = {
        "geometry_type":     "",
        "longitude":         "",
        "latitude":          "",
        "altitude":          "",
        "start_longitude":   "",
        "start_latitude":    "",
        "end_longitude":     "",
        "end_latitude":      "",
        "centroid_longitude":"",
        "centroid_latitude": "",
        "num_vertices":      "",
        "wkt":               "",
        "panjang_rute_km":      ""
    }

    geom_types_found = []
    all_line_pts = []
    all_poly_pts = []
    all_point_pts = []
    parts = []

    for el in pm.iter():
        tag = local(el)
        if tag == "LineString":
            geom_types_found.append("LineString")
            for sub in el.iter():
                if local(sub) == "coordinates":
                    pts = parse_coord_string(sub.text or "")
                    if pts:
                        parts.append(coords_to_wkt_linestring(pts))
                        all_line_pts.extend(pts)
                    break 
        elif tag == "Polygon":
            geom_types_found.append("Polygon")
            for sub in el.iter():
                if local(sub) == "coordinates":
                    pts = parse_coord_string(sub.text or "")
                    if pts:
                        parts.append(coords_to_wkt_polygon(pts))
                        all_poly_pts.extend(pts)
                    break 
        elif tag == "Point":
            geom_types_found.append("Point")
            for sub in el.iter():
                if local(sub) == "coordinates":
                    pts = parse_coord_string(sub.text or "")
                    if pts:
                        parts.append(coords_to_wkt_point(pts[0][0], pts[0][1]))
                        all_point_pts.extend(pts)
                    break

    if not parts:
        return base

    is_multi = any(local(el) == "MultiGeometry" for el in pm.iter())

    if is_multi or len(parts) > 1:
        primary_type = "MultiGeometry"
    elif "Polygon" in geom_types_found:
        primary_type = "Polygon"
    elif "LineString" in geom_types_found:
        primary_type = "LineString"
    elif "Point" in geom_types_found:
        primary_type = "Point"
    else:
        primary_type = "Unknown"

    result = {**base, "geometry_type": primary_type, "wkt": " | ".join(parts)}

    if all_line_pts:
        result["num_vertices"] = len(all_line_pts)
        result["start_longitude"] = all_line_pts[0][0]
        result["start_latitude"] = all_line_pts[0][1]
        result["end_longitude"] = all_line_pts[-1][0]
        result["end_latitude"] = all_line_pts[-1][1]
        panjang = calculate_linestring_length(all_line_pts)
        result["panjang_rute_km"] = round(panjang, 4) # Dibulatkan 4 angka di belakang koma
    elif all_poly_pts:
        result["num_vertices"] = len(all_poly_pts)
        cx = sum(p[0] for p in all_poly_pts) / len(all_poly_pts)
        cy = sum(p[1] for p in all_poly_pts) / len(all_poly_pts)
        result["centroid_longitude"] = round(cx, 8)
        result["centroid_latitude"] = round(cy, 8)
    elif all_point_pts:
        result["longitude"] = all_point_pts[0][0]
        result["latitude"] = all_point_pts[0][1]
        result["altitude"] = all_point_pts[0][2]

    return result

def calculate_haversine_distance(lon1, lat1, lon2, lat2):
    """
    Menghitung jarak antara dua titik koordinat geografis dalam Kilometer
    menggunakan rumus Haversine.
    """
    R = 6371.0 # Radius rata-rata bumi dalam kilometer

    # Konversi derajat ke radian
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Rumus Haversine
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance_km = R * c
    return distance_km

def calculate_linestring_length(points):
    """
    Menghitung total panjang jalur (LINESTRING) dalam kilometer.
    Parameter 'points' adalah list of tuples: [(lon1, lat1), (lon2, lat2), ...]
    """
    total_length = 0.0
    if len(points) < 2:
        return total_length

    # Iterasi dari titik pertama sampai titik sebelum terakhir
    for i in range(len(points) - 1):
        lon1, lat1 = points[i][0], points[i][1]
        lon2, lat2 = points[i+1][0], points[i+1][1]
        
        # Jumlahkan jarak antar titik yang bersebelahan
        total_length += calculate_haversine_distance(lon1, lat1, lon2, lat2)
        
    return total_length


# ---------------------------------------------------------------------------
# ExtendedData
# ---------------------------------------------------------------------------

def parse_extended_data(pm) -> dict:
    data = {}
    for el in pm.iter():
        if local(el) == "ExtendedData":
            for item in el:
                item_local = local(item)
                if item_local == "Data":
                    name = item.get("name", "")
                    for child in item:
                        if local(child) == "value":
                            data[name] = strip_html(child.text or "")
                elif item_local == "SchemaData":
                    for simple in item:
                        if local(simple) == "SimpleData":
                            data[simple.get("name", "")] = strip_html(simple.text or "")
    return data


# ---------------------------------------------------------------------------
# Placemark / Folder Deep Walking
# ---------------------------------------------------------------------------

def extract_placemark(pm, folder_path, kml_uri) -> dict:
    row = {
        "folder_path": folder_path,
        "name":        get_text(pm, "name", kml_uri),
        "visibility":  get_text(pm, "visibility", kml_uri),
        "styleUrl":    get_text(pm, "styleUrl", kml_uri),
    }
    
    # Ambil geometri dan data bawaan KML
    row.update(get_geometry(pm))
    row.update(parse_extended_data(pm))
    
    # ==========================================
    # PARSING DESCRIPTION TABLE (FITUR BARU)
    # ==========================================
    raw_desc = get_raw_text(pm, "description", kml_uri)
    if raw_desc:
        table_data = parse_description_table(raw_desc)
        if table_data:
            # Jika tabel ditemukan, gabungkan kuncinya menjadi kolom CSV
            row.update(table_data)
        else:
            # Jika isinya cuma teks biasa (bukan tabel), masukkan ke kolom 'description'
            row["description"] = strip_html(raw_desc)
            
    return row


def walk_node(node, current_path, buckets, kml_uri):
    """
    Recursively walk through any KML node.
    Treats both <Folder> and <Document> as containers.
    """
    for child in node:
        tag = local(child)
        
        if tag == "Placemark":
            # Jika Placemark ada di root tanpa folder, kasih nama 'root'
            path = current_path if current_path else "root"
            row = extract_placemark(child, path, kml_uri)
            buckets.setdefault(path, []).append(row)
            
        elif tag in ("Folder", "Document"):
            name_el = child.find(f"{{{kml_uri}}}name")
            if name_el is not None and name_el.text:
                node_name = name_el.text.strip()
            else:
                node_name = f"unnamed_{tag}"
                
            new_path = f"{current_path}/{node_name}" if current_path else node_name
            walk_node(child, new_path, buckets, kml_uri)


def parse_kml(kml_bytes: bytes) -> dict:
    parser = etree.XMLParser(recover=True, resolve_entities=False)
    root = etree.fromstring(kml_bytes, parser)

    kml_uri = detect_kml_uri(root)
    print(f"  Detected KML namespace: {kml_uri}")

    buckets = {}
    
    # Mulai penelusuran dari akar <kml>
    walk_node(root, "", buckets, kml_uri)

    return buckets


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    # Ganti path '/' dengan '--' agar menjadi satu nama file yang unik tapi terbaca
    safe = name.replace("/", "--")
    safe = re.sub(r'[\\:*?"<>|]', "_", safe)
    return safe.strip() or "unnamed"


def write_csvs(buckets: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for folder_path, rows in buckets.items():
        if not rows:
            continue
        all_keys = list(dict.fromkeys(k for row in rows for k in row))
        filename = sanitize_filename(folder_path) + ".csv"
        filepath = output_dir / filename
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in all_keys})
                
        written.append((folder_path, filename, len(rows)))
        print(f"  ✓ {filename}  ({len(rows)} feature(s))")
        
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def convert_kmz(kmz_path: str, output_dir: str = None):
    kmz_path = Path(kmz_path)
    if not kmz_path.exists():
        raise FileNotFoundError(f"KMZ file not found: {kmz_path}")

    if output_dir is None:
        output_dir = kmz_path.parent / kmz_path.stem
    output_dir = Path(output_dir)

    print(f"\nReading KMZ: {kmz_path}")

    with zipfile.ZipFile(kmz_path, "r") as zf:
        kml_files = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        if not kml_files:
            raise ValueError("No .kml file found inside the KMZ archive.")
        main_kml = next(
            (f for f in kml_files if os.path.basename(f).lower() == "doc.kml"),
            kml_files[0]
        )
        print(f"Using KML file: {main_kml}")
        kml_bytes = zf.read(main_kml)

    buckets = parse_kml(kml_bytes)

    if not buckets:
        print("No features found in the KML file.")
        return

    # Summary by geometry type
    type_counts = {}
    for rows in buckets.values():
        for row in rows:
            gt = row.get("geometry_type", "unknown")
            type_counts[gt] = type_counts.get(gt, 0) + 1
            
    print(f"\nGeometry summary: {type_counts}")
    print(f"Found {len(buckets)} layer(s)/folder(s). Writing CSVs to: {output_dir}\n")

    written = write_csvs(buckets, output_dir)
    total = sum(r[2] for r in written)
    print(f"\nDone! {len(written)} CSV file(s), {total} total feature(s).")
    return written


def main():
    parser = argparse.ArgumentParser(
        description="Convert a KMZ file to CSV files (extracts all deep folders)."
    )
    parser.add_argument("kmz_file", help="Path to the input .kmz file")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Output directory (default: <kmz_name>/ next to the KMZ)")
    args = parser.parse_args()
    convert_kmz(args.kmz_file, args.output_dir)


if __name__ == "__main__":
    main()
