#!/usr/bin/env python3
"""Build georeferenced display previews and a pair-aware interactive dashboard."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.features import geometry_mask
from rasterio.transform import Affine, array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

SCHEMA = "sarguardian-web-dashboard/1.0"
WEB_CRS = "EPSG:4326"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"Required dashboard input missing: {path.name}")
        return {}
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return result


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def parse_wkt(value: str) -> list[list[float]]:
    match = re.fullmatch(r"\s*POLYGON\s*\(\(\s*(.*?)\s*\)\)\s*", value, flags=re.I)
    if not match:
        raise ValueError("Dashboard requires an already-validated single-ring WKT POLYGON")
    ring = []
    for token in match.group(1).split(","):
        xy = token.strip().split()
        if len(xy) != 2:
            raise ValueError("Malformed AOI WKT coordinate")
        x, y = float(xy[0]), float(xy[1])
        if not math.isfinite(x) or not math.isfinite(y) or not (-180 <= x <= 180 and -90 <= y <= 90):
            raise ValueError("AOI coordinate outside WGS84 limits")
        ring.append([x, y])
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("AOI WKT ring must be closed")
    return ring


def reproject_band(path: Path, band: int, aoi_geometry: dict[str, Any]) -> tuple[np.ndarray, tuple[float, float, float, float], dict[str, Any]]:
    with rasterio.open(path) as src:
        if src.crs is None or band < 1 or band > src.count:
            raise ValueError(f"Missing CRS or invalid band in {path.name}")
        source = src.read(band).astype("float32", copy=False)
        if src.nodata is not None:
            source = source.copy()
            source[source == src.nodata] = np.nan
        source[~np.isfinite(source)] = np.nan
        source_valid = int(np.isfinite(source).sum())
        transform, width, height = calculate_default_transform(
            src.crs, WEB_CRS, src.width, src.height, *src.bounds
        )
        if width < 1 or height < 1:
            raise ValueError(f"Invalid preview raster dimensions for {path.name}")
        # Keep presentation previews compact. Native GeoTIFF is never resampled or replaced.
        shrink = min(1.0, 1024.0 / width, 1024.0 / height)
        out_width = max(1, int(round(width * shrink)))
        out_height = max(1, int(round(height * shrink)))
        transform = transform @ Affine.scale(width / out_width, height / out_height)
        width, height = out_width, out_height
        if width * height > 1_100_000:
            raise ValueError(f"Preview raster exceeds the display-pixel cap for {path.name}")
        out = np.full((height, width), np.nan, dtype="float32")
        reproject(
            source=source, destination=out,
            src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
            dst_transform=transform, dst_crs=WEB_CRS, dst_nodata=np.nan,
            resampling=Resampling.nearest, init_dest_nodata=True,
        )
        # Clip the display preview to the exact AOI polygon; never expose the
        # rectangular raster window outside the requested polygon as data.
        inside_aoi = geometry_mask([aoi_geometry], out_shape=(height, width), transform=transform, invert=True, all_touched=False)
        out[~inside_aoi] = np.nan
        west, south, east, north = array_bounds(height, width, transform)
        if not all(math.isfinite(v) for v in (west, south, east, north)) or west >= east or south >= north:
            raise ValueError(f"Invalid WGS84 bounds for {path.name}")
        description = (src.descriptions[band - 1] if src.descriptions else None) or f"Band {band}"
        unit = (src.units[band - 1] if src.units else None) or ""
        if not unit:
            found = re.search(r"\(([^()]*)\)\s*$", description)
            unit = found.group(1).strip() if found else ("dimensionless" if "coherence" in description.lower() else "source units not declared")
        return out, (float(west), float(south), float(east), float(north)), {
            "description": description.strip(), "units": unit, "source_crs": src.crs.to_string(),
            "source_transform": [float(v) for v in src.transform[:6]],
            "source_width": src.width, "source_height": src.height, "source_valid_pixels": source_valid,
            "data_type": src.dtypes[band - 1], "source_nodata": float(src.nodata) if src.nodata is not None and math.isfinite(float(src.nodata)) else None,
            "preview_crs": WEB_CRS, "preview_transform": [float(v) for v in transform[:6]],
            "preview_width": width, "preview_height": height,
        }


def write_rgba(values: np.ndarray, lo: float, hi: float, kind: str, path: Path) -> tuple[int, float | None, float | None]:
    valid = np.isfinite(values)
    count = int(valid.sum())
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if count:
        normalized = np.clip((np.where(valid, values, lo) - lo) / (hi - lo), 0.0, 1.0)
        palette = "viridis" if kind == "coherence" else "RdBu_r"
        rgba[..., :3] = (colormaps[palette](normalized)[..., :3] * 255).astype(np.uint8)
        rgba[..., 3] = np.where(valid, 220, 0).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", optimize=True)
    return count, (float(np.nanmin(values)) if count else None), (float(np.nanmax(values)) if count else None)


def write_viewer(path: Path) -> None:
    page = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SARGuardian · Interactive Science Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@6.16.0/dist/maplibre-gl.css">
<style>
:root{color-scheme:dark;--bg:#07121c;--panel:#0e1e2a;--edge:#254050;--ink:#edf7fb;--muted:#a5bec8;--aqua:#66e2d3;--amber:#f7c76b}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#123444,#07121c 55%);color:var(--ink);font:14px/1.45 system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:22px}header{display:flex;gap:18px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;border-bottom:1px solid var(--edge);padding-bottom:16px}h1{font-size:clamp(25px,3vw,38px);line-height:1.05;letter-spacing:-.035em;margin:7px 0}.kicker{color:var(--aqua);font-size:10px;font-weight:800;letter-spacing:.17em;text-transform:uppercase}.muted{color:var(--muted)}button,select,input{font:inherit;color:inherit;background:#102a39;border:1px solid #396071;border-radius:7px;padding:8px}button{cursor:pointer}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--aqua);outline-offset:2px}.warn{margin:14px 0;padding:12px 14px;border:1px solid #8e6b35;background:#322816;color:#ffe7b6;border-radius:10px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}.card,.panel{background:linear-gradient(145deg,#112b39,#0c1a25);border:1px solid var(--edge);border-radius:12px;padding:13px;min-width:0}.label{color:var(--muted);font-size:10px;letter-spacing:.08em;text-transform:uppercase}.big{font-size:26px;font-weight:750;margin-top:3px;overflow-wrap:anywhere}.layout{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(290px,.8fr);gap:12px}.maphead{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.mapbox{position:relative;height:min(65vh,640px);min-height:340px;border:1px solid var(--edge);border-radius:10px;overflow:hidden;background:#0a1720}.mapbox #map{position:absolute;inset:0}#mapFallback{position:absolute;inset:0;overflow:auto;z-index:3;background:#0a1720}#mapFallbackPreview{display:flex;justify-content:center;align-items:center;min-height:160px;max-height:calc(100% - 90px);margin-top:12px}#mapFallbackPreview img{display:block;max-width:100%;max-height:100%;object-fit:contain;border:1px solid var(--edge);background:#07121c}#mapFallbackCoordinates{font-size:11px;line-height:1.5;overflow-wrap:anywhere}.controls{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.timeline{margin-top:12px;display:grid;grid-template-columns:auto minmax(100px,1fr) auto;gap:9px;align-items:center}.timeline input{width:100%;padding:0;accent-color:var(--aqua)}.timeline small{font-variant-numeric:tabular-nums;color:var(--muted)}.metriclist{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.metricitem{padding:10px;background:#091721;border:1px solid var(--edge);border-radius:8px;min-width:0}.metricitem strong{display:block;margin-top:4px;overflow-wrap:anywhere}.chart{width:100%;height:170px;display:block}.chart text{fill:var(--muted);font-size:10px}.product-list{display:grid;gap:6px;max-height:250px;overflow:auto}.product-row{width:100%;display:flex;justify-content:space-between;align-items:center;text-align:left;gap:9px;background:#091721}.product-row[aria-current=true]{border-color:var(--aqua);background:#153746}.product-row span{display:block}.product-row small{display:block;color:var(--muted)}details{margin-top:10px;border-top:1px solid var(--edge);padding-top:10px}summary{cursor:pointer}.foot{margin-top:15px;font-size:11px;color:var(--muted)}.legend{font-size:11px;color:var(--muted);margin:7px 0}.legendbar{height:8px;border-radius:4px;background:linear-gradient(90deg,#053061,#f7f7f7,#67001f);margin-top:5px}.hidden{display:none!important}.compare-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.compare-mapbox{height:300px;min-height:250px;border:1px solid var(--edge);border-radius:10px;overflow:hidden}.compare-mapbox>div{height:100%;width:100%}.compare-controls{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}.compare-controls label{display:grid;gap:5px;flex:1;min-width:160px}.compare-map-title{font-size:12px;overflow-wrap:anywhere;margin:8px 0}.scenario-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.scenario-grid label{display:grid;gap:5px}.scenario-result{padding:10px;border:1px solid var(--edge);border-radius:8px;margin-top:10px}.scenario-result strong{color:var(--aqua)}@media(max-width:850px){main{padding:12px}.layout{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.mapbox{height:48vh;min-height:300px}.compare-grid{grid-template-columns:1fr}.compare-mapbox{height:280px}.scenario-grid{grid-template-columns:1fr}}@media(max-width:450px){.cards{grid-template-columns:1fr 1fr}.big{font-size:21px}.timeline{grid-template-columns:1fr}.timeline input{grid-row:2}}
</style></head><body><main>
<header><div><div class="kicker">SARGuardian · Earth in sight</div><h1>Interactive Science Dashboard</h1><p class="muted">AOI-clipped NISAR observations · pair-aware map playback · reproducible evidence</p></div><div class="controls"><button id="presentation">Presentation mode</button><a href="../index.html" style="color:var(--aqua);padding:9px">Processing report ↗</a></div></header>
<div class="warn"><strong>Scientific interpretation:</strong> a processing PASS confirms structural/provenance checks, not independent geophysical accuracy. Pairwise LOS measurements are not automatically cumulative or 3-D motion. Playback switches actual observations; it does not interpolate or forecast.</div>
<div class="cards" id="summaryCards"></div>
<div id="targetNotice" class="warn hidden" role="status"></div>
<div class="layout"><section class="panel"><div class="maphead"><div><div class="kicker">Geospatial workspace</div><strong id="mapTitle">Loading map layers…</strong></div><div class="controls"><label>Band <select id="bandSelect" aria-label="Select raster band"></select></label><label>Opacity <input id="opacity" type="range" min="0" max="100" value="80" aria-label="Raster opacity"></label><label>Speed <select id="speed"><option value="2500">0.5×</option><option value="1500" selected>1×</option><option value="750">2×</option></select></label></div></div><div class="mapbox"><div id="map"></div><div id="mapFallback" class="hidden" style="padding:16px"><strong>Interactive map unavailable.</strong><p>The basemap could not load, but the saved raster preview and all processing evidence remain available below. Static preview is not pan/zoom or a substitute for a georeferenced map.</p><div id="mapFallbackPreview"></div><p id="mapFallbackCoordinates" class="muted"></p></div></div><div id="legend" class="legend"></div><div class="timeline"><div class="controls"><button id="previous" aria-label="Previous observation">◀</button><button id="play">Play</button><button id="next" aria-label="Next observation">▶</button></div><input id="timeline" type="range" min="0" max="0" value="0" step="1" aria-label="Observation pair timeline"><small id="dateLabel">—</small></div><p class="muted" id="timelineNote">Each point is a real acquisition pair. No synthetic intermediate observations are created.</p>
<details id="pairCompare"><summary>Side-by-side observed pair comparison</summary><p class="muted" style="font-size:11px">Compares two actual pairwise raster previews only when both source products have the same product family, track/look and exact source grid. This is not optical before/after imagery, not a computed difference, and not a cumulative trajectory.</p><div class="compare-controls"><label>Observed pair A<select id="compareA"></select></label><label>Observed pair B<select id="compareB"></select></label><label>Shared raster band<select id="compareBand"></select></label></div><p class="muted" id="compareStatus" role="status">Select two compatible observations to compare.</p><div class="compare-grid"><div><h3 id="compareTitleA" class="compare-map-title">Pair A</h3><div class="compare-mapbox"><div id="compareMapA"></div></div><p id="compareLegendA" class="legend"></p></div><div><h3 id="compareTitleB" class="compare-map-title">Pair B</h3><div class="compare-mapbox"><div id="compareMapB"></div></div><p id="compareLegendB" class="legend"></p></div></div></details>
<details id="scenarioSandbox"><summary>Hypothetical motion sensitivity sandbox (not a forecast)</summary><p class="muted" style="font-size:11px">Enter a hypothetical constant rate and duration to draw a scenario curve. It is generated by the calculator, not NISAR observations, not a landslide/glacier-collapse prediction, and must never be read as an alert. Any displayed noise floor comes only from a measured pair-local floor in this run.</p><div class="scenario-grid"><label>Hypothetical rate (mm/day)<input id="scenarioRate" type="number" min="-500" max="500" step="0.1" placeholder="Enter rate"></label><label>Duration (days)<input id="scenarioDays" type="number" min="1" max="90" step="1" placeholder="Enter duration"></label><div style="display:flex;align-items:end"><button id="simulateScenario" type="button">Simulate scenario</button></div></div><svg id="scenarioChart" class="chart" role="img" aria-label="Explicitly hypothetical cumulative displacement scenario" viewBox="0 0 560 180"></svg><div id="scenarioResult" class="scenario-result muted" role="status">No scenario generated.</div></details>
</section>
<aside class="panel"><div class="kicker">Selected observation</div><h2 id="productTitle">—</h2><p class="muted" id="productDescription">—</p><div class="metriclist" id="productMetrics"></div><label>Jump to pair <select id="productSelect"></select></label><div class="kicker" style="margin-top:18px">Quality / support by product</div><svg id="supportChart" class="chart" role="img" aria-label="Bar chart of valid pixels by product"></svg><p class="muted" style="font-size:11px">Bars show per-product valid-pixel counts; they are not a movement trend.</p><div class="kicker" style="margin-top:12px">Observed pair measurements · selected track</div><label>Metric <select id="measurementMetric" aria-label="Select one measurement metric and its units"></select></label><label>Measurement track <select id="measurementTrack" aria-label="Choose one track for the selected metric"></select></label><svg id="measurementChart" class="chart" role="img" aria-label="Per-product pairwise science metrics shown as separate bars, not a time series"></svg><p class="muted" style="font-size:11px">Each bar belongs to a real acquisition pair. Metric choices keep measurement families and units separate. Target-local values remain pair-specific; detection floors are noise bounds, not observed motion. White whiskers show the stored target-floor confidence interval when available; bars are not connected into a cumulative trend.</p><div class="kicker" style="margin-top:18px">Common-reference cumulative LOS diagnostic</div><p class="muted" style="font-size:11px">This graph appears only when the retained GUNW rasters share one projected grid, at least 200 common-valid AOI pixels remain outside a 2 km target buffer, the temporal network has redundancy, and leave-one-out velocity signs agree. The zero is an AOI-derived median, not an independently surveyed stable-ground reference; fit-only error bars omit systematic datum uncertainty.</p><label>Network/component <select id="cumulativeNetwork" aria-label="Select eligible common-reference network"></select></label><div id="cumulativeStatus" class="muted" role="status">Checking common-reference eligibility…</div><svg id="cumulativeChart" class="chart" role="img" aria-label="Cumulative line of actual connected GUNW acquisition epochs with fit-only uncertainty where available"></svg><p class="muted" style="font-size:11px">Only actual inversion epochs are plotted; no intermediate observations are created. This is a research diagnostic, not a hazard alert or forecast.</p><div class="kicker" style="margin-top:18px">Scientific pipeline coverage</div><div id="scienceStages" class="metriclist"></div><p class="muted" style="font-size:11px">A withheld stage is shown explicitly rather than filled with invented numbers. See its reason and the network redundancy before interpreting any movement.</p><div class="kicker" style="margin-top:12px">Observation list</div><div class="product-list" id="productList"></div><details><summary>Provenance and limitations</summary><div id="provenance" class="muted" style="font-size:11px;overflow-wrap:anywhere"></div></details></aside></div>
<footer class="foot">Map data attribution: © OpenStreetMap contributors. Raster preview is reprojected from the validated clipped GeoTIFF; native raster and per-product records remain the scientific source assets. This is a research viewer, not a hazard-alert service.</footer>
</main><script src="./dashboard-data.js"></script><script type="module">
// A failed CDN import must not abort the rest of the dashboard's science panels.
let maplibregl = null;
try {
  maplibregl = await import('https://unpkg.com/maplibre-gl@6.16.0/dist/maplibre-gl.mjs');
} catch (error) {
  console.warn('SARGuardian map library unavailable; keeping report, metrics and product details available.', error);
}
(function(){const $=id=>document.getElementById(id);const manifest=window.SARGUARDIAN_DASHBOARD;let M=null,selected=0,playing=false,timer=null,activeLayer=null;const esc=s=>String(s==null?'—':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));if(!manifest){$('mapTitle').textContent='Manifest is missing';$('mapFallback').classList.remove('hidden');return}const obs=manifest.observations||[],layers=manifest.layers||[],aoi=manifest.aoi&&manifest.aoi.geometry,n=obs.length;
$('timeline').max=String(Math.max(0,n-1));$('timeline').disabled=n<2;$('productSelect').innerHTML=obs.map((p,i)=>'<option value="'+i+'">'+esc(p.secondary_date)+' · '+esc(p.id)+'</option>').join('');
const site=(manifest.site_context||{}),place=site.place||{},target=site.measurement_target||{};const cards=[['Products',n],['GUNW',obs.filter(p=>p.product_type==='GUNW').length],['GOFF',obs.filter(p=>p.product_type==='GOFF').length],['Target local measurements',obs.filter(p=>{const m=p.metrics||{};return m.target_measurement_status==='MEASURED'&&(m.target_local_los_median_mm!=null||m.target_local_range_median_mm!=null);}).length],['Measured local floors',obs.filter(p=>{const m=p.metrics||{};return m.target_local_floor_status==='MEASURED'&&m.target_local_floor_mm_day!=null;}).length],['Selected place',place.name||'Not selected']];$('summaryCards').innerHTML=cards.map(x=>'<div class="card"><div class="label">'+esc(x[0])+'</div><div class="big">'+esc(x[1])+'</div></div>').join('');const targetNotice=$('targetNotice');if(target.status!=='IN_AOI_TARGET_CAPTURED'){targetNotice.classList.remove('hidden');targetNotice.textContent='No explicit in-AOI measurement target was supplied for this run. Target-local measurements and detection floors are not reported (not zero). To request them, rerun the workflow with target_latitude and target_longitude set to an explicit WGS84 point inside this AOI. This dashboard cannot reconstruct missing target measurements after processing.';}
function addFallback(){ $('mapFallback').classList.remove('hidden'); }
 function renderFallbackPreview(layer){const holder=$('mapFallbackPreview'),note=$('mapFallbackCoordinates');if(!holder||!note)return;holder.replaceChildren();if(!layer){note.textContent='No raster preview is available for the selected observation.';return;}const source=(window.SARGUARDIAN_LAYER_DATA||{})[layer.id]||layer.preview_asset;if(!source){note.textContent='No static raster preview is attached to this layer.';return;}const img=document.createElement('img');img.src=String(source);img.alt='Static raster preview: '+String(layer.description||layer.id);img.onerror=function(){holder.replaceChildren();const message=document.createElement('p');message.textContent='The local raster preview could not be loaded. Download the georeferenced assets from this bundle to inspect it in a GIS.';holder.appendChild(message);};holder.appendChild(img);const corners=Array.isArray(layer.corners)?layer.corners.map(c=>Number(c[0]).toFixed(5)+', '+Number(c[1]).toFixed(5)).join(' · '):'not reported';note.textContent='Static preview only — '+String(layer.description||layer.id)+' ('+String(layer.units||'units')+'). Preview corners in longitude, latitude order: '+corners+'. This fallback does not provide a basemap or interactive geographic positioning.';}
if(maplibregl && typeof maplibregl.Map==='function'){try{M=new maplibregl.Map({container:'map',style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm'}]},center:[0,0],zoom:2});M.addControl(new maplibregl.NavigationControl(),'top-right');M.on('load',function(){if(aoi){M.addSource('aoi',{type:'geojson',data:manifest.aoi});M.addLayer({id:'aoi-fill',type:'fill',source:'aoi',paint:{'fill-color':'#66e2d3','fill-opacity':0.09}});M.addLayer({id:'aoi-outline',type:'line',source:'aoi',paint:{'line-color':'#66e2d3','line-width':2,'line-dasharray':[2,1]}});const coords=aoi.coordinates[0]||[];if(coords.length){let west=Infinity,south=Infinity,east=-Infinity,north=-Infinity;coords.forEach(c=>{west=Math.min(west,c[0]);south=Math.min(south,c[1]);east=Math.max(east,c[0]);north=Math.max(north,c[1]);});M.fitBounds([[west,south],[east,north]],{padding:55,maxZoom:14});}}if(place&&Number.isFinite(Number(place.longitude))&&Number.isFinite(Number(place.latitude))){M.addSource('selected-site',{type:'geojson',data:{type:'Feature',properties:{name:place.name||'Selected place'},geometry:{type:'Point',coordinates:[Number(place.longitude),Number(place.latitude)]}}});M.addLayer({id:'selected-site-marker',type:'circle',source:'selected-site',paint:{'circle-radius':8,'circle-color':'#f7c76b','circle-stroke-color':'#ffffff','circle-stroke-width':2}});}if(target.status==='IN_AOI_TARGET_CAPTURED'&&Number.isFinite(Number(target.longitude))&&Number.isFinite(Number(target.latitude))){M.addSource('selected-target',{type:'geojson',data:{type:'Feature',properties:{name:'Measurement target'},geometry:{type:'Point',coordinates:[Number(target.longitude),Number(target.latitude)]}}});M.addLayer({id:'selected-target-marker',type:'circle',source:'selected-target',paint:{'circle-radius':4,'circle-color':'#ff806e','circle-stroke-color':'#ffffff','circle-stroke-width':1.5}});}layers.forEach(function(l){const source='src-'+l.id;M.addSource(source,{type:'image',url:(window.SARGUARDIAN_LAYER_DATA||{})[l.id]||l.preview_asset,coordinates:l.corners});M.addLayer({id:'raster-'+l.id,type:'raster',source:source,layout:{visibility:'none'},paint:{'raster-opacity':Number($('opacity').value)/100,'raster-resampling':'nearest'}});});if(n)renderProduct();});}catch(e){addFallback();}}else addFallback();
function current(){return obs[selected]||null;}function obsLayers(p){return layers.filter(l=>l.observation_id===p.id);}function hideLayers(){if(!M)return;layers.forEach(l=>{const id='raster-'+l.id;if(M.getLayer(id))M.setLayoutProperty(id,'visibility','none');});activeLayer=null;}
function renderLegend(l){if(!l){$('legend').textContent='No renderable raster overlay for this product.';return;}const d=l.display_scale||{};const ramp=l.kind==='coherence'?'linear-gradient(90deg,#440154,#21918c,#fde725)':'linear-gradient(90deg,#053061,#f7f7f7,#67001f)';$('legend').innerHTML='<strong>'+esc(l.description)+'</strong> · '+esc(l.units)+' · preview-valid pixels '+esc(l.valid_pixels)+'<br>Scale '+esc(d.min)+' to '+esc(d.max)+' '+esc(l.units)+' ('+esc(d.method)+')<div class="legendbar" style="background:'+ramp+'"></div>';}
function renderProduct(){const p=current();if(!p)return;const pl=obsLayers(p);$('timeline').value=String(selected);$('productSelect').value=String(selected);$('dateLabel').textContent=(p.reference_date||'—')+' → '+(p.secondary_date||'—');$('mapTitle').textContent=p.id+' · '+p.product_type+' · '+(p.track||'track unavailable');$('productTitle').textContent=p.id+' · '+p.product_type;$('productDescription').textContent=(p.reference_date||'—')+' reference → '+(p.secondary_date||'—')+' secondary · '+(p.maturity||'maturity not reported')+' · '+(p.look_direction||'view geometry in metadata');
const priorBand=$('bandSelect').value;$('bandSelect').innerHTML=pl.map(l=>'<option value="'+esc(l.id)+'">Band '+esc(l.band)+': '+esc(l.description)+'</option>').join('');if(pl.some(l=>l.id===priorBand))$('bandSelect').value=priorBand;$('bandSelect').disabled=!pl.length;const layer=pl.find(l=>l.id===$('bandSelect').value)||pl[0]||null;hideLayers();if(layer&&M&&M.getLayer('raster-'+layer.id)){M.setLayoutProperty('raster-'+layer.id,'visibility','visible');M.setPaintProperty('raster-'+layer.id,'raster-opacity',Number($('opacity').value)/100);activeLayer=layer.id;}renderLegend(layer);if(!M)renderFallbackPreview(layer);
const m=p.metrics||{};const siteTarget=manifest.site_context&&manifest.site_context.measurement_target;const items=[['Reference date',p.reference_date],['Secondary date',p.secondary_date],['Track / look',p.track||'Not reported'],['Maturity',p.maturity],['Valid pixels',p.valid_pixels],['Reader median',m.reader_median==null?'Not reported':String(m.reader_median)+' '+(m.reader_median_units||'(source units)')],['Target local LOS/range',m.target_local_los_median_mm!=null?m.target_local_los_median_mm+' mm':m.target_local_range_median_mm!=null?m.target_local_range_median_mm+' mm':'Not measured'],['Target local along-track',m.target_local_azimuth_median_mm==null?'Not measured':m.target_local_azimuth_median_mm+' mm'],['Target local floor',m.target_local_floor_mm_day==null?'Not measured':m.target_local_floor_mm_day+' mm/day'],['Target floor CI',m.target_local_floor_ci_lo_mm_day==null||m.target_local_floor_ci_hi_mm_day==null?'Not reported':m.target_local_floor_ci_lo_mm_day+'–'+m.target_local_floor_ci_hi_mm_day+' mm/day'],['Mean coherence',m.mean_coherence==null?'Not reported':m.mean_coherence],['CRID',p.crid]];$('productMetrics').innerHTML=items.map(x=>'<div class="metricitem"><div class="label">'+esc(x[0])+'</div><strong>'+esc(x[1])+'</strong></div>').join('');$('provenance').innerHTML='<p>Run: '+esc(manifest.run.github_run_id)+'</p><p>AOI SHA-256: '+esc(manifest.run.aoi_wkt_sha256)+'</p><p>Science commit: '+esc(manifest.run.science_commit)+'</p><p>Orchestration commit: '+esc(manifest.run.orchestration_commit)+'</p><p>Source hash: '+esc(p.source_sha256)+'</p><p>'+esc(p.validation_scope||'Structural/provenance only; independent geophysical validation not performed.')+'</p><p>'+(p.warnings||[]).map(esc).join('<br>')+'</p>';document.querySelectorAll('.product-row').forEach(row=>row.setAttribute('aria-current',row.dataset.idx===String(selected)?'true':'false'));}
function renderSciencePipeline(){const root=$('scienceStages'),r=manifest.science_pipeline||{};const modules=Array.isArray(r.modules)?r.modules:[];const networks=Array.isArray(r.networks)?r.networks:[];if(!modules.length){root.innerHTML='<div class="metricitem"><div class="label">Science pipeline</div><strong>Not reported</strong><small>Older result bundles may not contain stage-level eligibility.</small></div>';return;}root.innerHTML=modules.map(m=>'<div class="metricitem"><div class="label">'+esc(m.name)+'</div><strong>'+esc(m.status)+'</strong><small style="display:block;margin-top:4px">'+esc(m.reason||m.interpretation||m.limitation||m.produces||'See the structured pipeline report.')+'</small></div>').join('');if(networks.length){root.insertAdjacentHTML('beforeend','<div class="metricitem"><div class="label">Temporal network diagnostics</div><strong>'+networks.length+' network component(s)</strong><small style="display:block;margin-top:4px">'+networks.map(n=>esc(n.geometry)+': '+esc(n.n_pairs)+' pairs, '+esc(n.n_epochs)+' epochs, redundancy '+esc(n.redundancy)+' ('+esc(n.topology_status)+')').join('<br>')+'</small></div>');}const overall=document.createElement('div');overall.className='metricitem';overall.innerHTML='<div class="label">Stage assessment</div><strong>'+esc(r.overall_status||r.network_assessment_status||'PARTIAL')+'</strong><small style="display:block;margin-top:4px">'+esc((r.warnings||[]).join(' '))+'</small>';root.prepend(overall);}function renderList(){$('productList').innerHTML=obs.map((p,i)=>'<button class="product-row" data-idx="'+i+'" aria-current="'+(i===selected?'true':'false')+'"><span><strong>'+esc(p.id)+' · '+esc(p.product_type)+'</strong><small>'+esc(p.reference_date)+' → '+esc(p.secondary_date)+' · '+esc(p.track||'track N/A')+'</small></span><span>'+esc(p.valid_pixels)+' px</span></button>').join('');document.querySelectorAll('.product-row').forEach(b=>b.addEventListener('click',()=>select(Number(b.dataset.idx))));}
function renderChart(){const svg=$('supportChart'),w=480,h=170;svg.setAttribute('viewBox','0 0 '+w+' '+h);svg.replaceChildren();const max=Math.max(1,...obs.map(p=>Number(p.valid_pixels)||0)),pad=25,bw=Math.max(4,(w-pad*2)/Math.max(1,obs.length)*.62),step=(w-pad*2)/Math.max(1,obs.length);obs.forEach((p,i)=>{const value=Math.max(0,Number(p.valid_pixels)||0),bar=Math.max(1,value/max*105),x=pad+i*step+(step-bw)/2;const r=document.createElementNS('http://www.w3.org/2000/svg','rect');r.setAttribute('x',x);r.setAttribute('y',125-bar);r.setAttribute('width',bw);r.setAttribute('height',bar);r.setAttribute('rx',2);r.setAttribute('fill',p.product_type==='GUNW'?'#66e2d3':'#f7c76b');const t=document.createElementNS('http://www.w3.org/2000/svg','title');t.textContent=p.id+': '+value+' valid pixels';r.append(t);svg.append(r);if(obs.length<=16){const tx=document.createElementNS('http://www.w3.org/2000/svg','text');tx.setAttribute('x',x+bw/2);tx.setAttribute('y',143);tx.setAttribute('text-anchor','middle');tx.textContent=p.id.replace('GUNW-','').replace('GOFF-','');svg.append(tx);}});const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',pad);t.setAttribute('y',12);t.textContent='Valid pixels in each product (not unique across pairs)';svg.append(t);}
function metricValue(p,key){const m=p.metrics||{};let value=null;if(key==='gunw_los_median'&&p.product_type==='GUNW'&&m.reader_median_units==='mm')value=m.reader_median;else if(key==='goff_range_median'&&p.product_type==='GOFF')value=m.goff_range_median_mm;else if(key==='goff_azimuth_median'&&p.product_type==='GOFF')value=m.goff_azimuth_median_mm;else if(key==='goff_detection_floor'&&p.product_type==='GOFF')value=m.goff_detect_floor_mm_day;else if(key==='gunw_target_los'&&p.product_type==='GUNW'&&m.target_measurement_status==='MEASURED')value=m.target_local_los_median_mm;else if(key==='goff_target_range'&&p.product_type==='GOFF'&&m.target_measurement_status==='MEASURED')value=m.target_local_range_median_mm;else if(key==='goff_target_azimuth'&&p.product_type==='GOFF'&&m.target_measurement_status==='MEASURED')value=m.target_local_azimuth_median_mm;else if(key==='target_local_floor'&&m.target_local_floor_status==='MEASURED')value=m.target_local_floor_mm_day;return value!==null&&value!==undefined&&Number.isFinite(Number(value))?Number(value):null}
function metricUncertainty(p,key){if(key!=='target_local_floor')return null;const m=p.metrics||{},lo=m.target_local_floor_ci_lo_mm_day,hi=m.target_local_floor_ci_hi_mm_day;if(lo===null||lo===undefined||hi===null||hi===undefined||!Number.isFinite(Number(lo))||!Number.isFinite(Number(hi))||Number(hi)<Number(lo))return null;return [Number(lo),Number(hi)];}
function metricSpecs(){return [
{id:'gunw_los_median',label:'GUNW LOS displacement median (mm)',units:'mm',note:'Pairwise LOS displacement; not cumulative or 3-D motion.'},
{id:'goff_range_median',label:'GOFF range-offset median (mm)',units:'mm',note:'Pairwise slant-range offset statistic; not interchangeable with GUNW phase displacement.'},
{id:'goff_azimuth_median',label:'GOFF along-track offset median (mm)',units:'mm',note:'Along-track offset component; does not by itself provide full ground-motion direction.'},
{id:'goff_detection_floor',label:'GOFF detection floor (mm/day)',units:'mm/day',note:'Reader-reported detectability bound/noise floor, not observed displacement or a velocity measurement.'},
{id:'gunw_target_los',label:'Target-local GUNW LOS median (mm)',units:'mm',note:'Target-window value in this GUNW pair’s own reference frame; not a shared-datum displacement series.'},
{id:'goff_target_range',label:'Target-local GOFF range median (mm)',units:'mm',note:'Target-window range offset in this GOFF pair’s own reference frame; do not equate to GUNW phase displacement.'},
{id:'goff_target_azimuth',label:'Target-local GOFF along-track median (mm)',units:'mm',note:'Target-window along-track offset; not a complete 3-D movement vector.'},
{id:'target_local_floor',label:'Target-local detection floor (mm/day)',units:'mm/day',note:'Pair-specific local noise/detectability bound, not observed motion or a forecast.'}
]}
function renderMeasurementChart(){const metricSelect=$('measurementMetric'),trackSelect=$('measurementTrack'),svg=$('measurementChart');const specs=metricSpecs().filter(s=>obs.some(p=>metricValue(p,s.id)!==null));const priorMetric=metricSelect.value;metricSelect.innerHTML=specs.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.label)+'</option>').join('');metricSelect.disabled=!specs.length;if(specs.some(s=>s.id===priorMetric))metricSelect.value=priorMetric;svg.replaceChildren();if(!specs.length){svg.setAttribute('viewBox','0 0 420 70');svg.style.height='70px';const tx=document.createElementNS('http://www.w3.org/2000/svg','text');tx.setAttribute('x','10');tx.setAttribute('y','35');tx.textContent='No unit-labelled compatible metrics are available for this run.';svg.append(tx);trackSelect.innerHTML='';trackSelect.disabled=true;return;}const spec=specs.find(s=>s.id===metricSelect.value)||specs[0];const values=obs.map(p=>({p,value:metricValue(p,spec.id)})).filter(x=>x.value!==null);const tracks=[...new Set(values.map(x=>x.p.track||'track unavailable'))].sort();const priorTrack=trackSelect.value;trackSelect.innerHTML=tracks.map(t=>'<option value="'+esc(t)+'">'+esc(t)+'</option>').join('');if(tracks.includes(priorTrack))trackSelect.value=priorTrack;trackSelect.disabled=!tracks.length;const track=trackSelect.value||tracks[0],rows=values.filter(x=>(x.p.track||'track unavailable')===track);const rangeValues=rows.flatMap(x=>{const band=metricUncertainty(x.p,spec.id);return [x.value,...(band||[])];});const maxAbs=Math.max(1,...rangeValues.map(v=>Math.abs(v)));const positiveOnly=rows.every(x=>x.value>=0);const h=Math.max(100,rows.length*30+48),w=560,left=150,plot=370,zero=positiveOnly?left:left+plot/2;svg.setAttribute('viewBox','0 0 '+w+' '+h);svg.style.height=h+'px';const makeText=(x,y,t,anchor='start')=>{const tx=document.createElementNS('http://www.w3.org/2000/svg','text');tx.setAttribute('x',x);tx.setAttribute('y',y);tx.setAttribute('text-anchor',anchor);tx.textContent=t;svg.append(tx);};const axis=document.createElementNS('http://www.w3.org/2000/svg','line');axis.setAttribute('x1',zero);axis.setAttribute('x2',zero);axis.setAttribute('y1',20);axis.setAttribute('y2',h-24);axis.setAttribute('stroke','#72909d');axis.setAttribute('stroke-dasharray','3 3');svg.append(axis);makeText(left,12,spec.label+' · '+track);makeText(left,h-5,positiveOnly?'0':(-maxAbs).toFixed(1),'start');makeText(zero,h-5,'0','middle');makeText(left+plot,h-5,maxAbs.toFixed(1),'end');rows.forEach((x,i)=>{const p=x.p,value=x.value,y=25+i*30,width=Math.abs(value)/maxAbs*(positiveOnly?plot-5:plot/2-4),barX=value<0?zero-width:zero;makeText(left-8,y+13,p.id+' · '+String(p.secondary_date||'').slice(5),'end');const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('x',barX);rect.setAttribute('y',y);rect.setAttribute('width',Math.max(1,width));rect.setAttribute('height',18);rect.setAttribute('rx',3);rect.setAttribute('fill',spec.id==='goff_detection_floor'?'#f7c76b':(value<0?'#66b9e8':'#f4a879'));const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=p.id+': '+value+' '+spec.units+' · '+p.reference_date+' → '+p.secondary_date;rect.append(title);svg.append(rect);const uncertainty=metricUncertainty(p,spec.id);if(uncertainty){const scale=positiveOnly?plot-5:plot/2-4;const mapX=v=>zero+(v/maxAbs)*scale;const xLo=mapX(uncertainty[0]),xHi=mapX(uncertainty[1]),midY=y+9;const whisker=document.createElementNS('http://www.w3.org/2000/svg','line');whisker.setAttribute('x1',xLo);whisker.setAttribute('x2',xHi);whisker.setAttribute('y1',midY);whisker.setAttribute('y2',midY);whisker.setAttribute('stroke','#ffffff');whisker.setAttribute('stroke-width','2');svg.append(whisker);[xLo,xHi].forEach(xp=>{const cap=document.createElementNS('http://www.w3.org/2000/svg','line');cap.setAttribute('x1',xp);cap.setAttribute('x2',xp);cap.setAttribute('y1',y+4);cap.setAttribute('y2',y+14);cap.setAttribute('stroke','#ffffff');cap.setAttribute('stroke-width','1.5');svg.append(cap);});}});const note=document.createElementNS('http://www.w3.org/2000/svg','text');note.setAttribute('x',left);note.setAttribute('y',h-24);note.textContent=spec.note;svg.append(note);}
// Comparison viewers are deliberately pairwise: same family, same track/look,
// same source grid and matching band semantics are required. No raster
// subtraction, cumulative trend, or cross-datum motion is synthesized here.
let compareMapAInstance=null,compareMapBInstance=null,compareMapALoaded=false,compareMapBLoaded=false;
let comparisonSyncing=false,compareOverlayA=null,compareOverlayB=null;
function compareLayerFor(p,band){return layers.find(l=>l.observation_id===p.id&&Number(l.band)===Number(band))||null;}
function nearlyEqual(a,b){return Number.isFinite(Number(a))&&Number.isFinite(Number(b))&&Math.abs(Number(a)-Number(b))<=1e-8;}
function sameNumbers(a,b){return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>nearlyEqual(v,b[i]));}
function sameSourceGrid(a,b){return Boolean(a&&b&&a.source_crs&&a.source_crs===b.source_crs&&Number(a.source_width)===Number(b.source_width)&&Number(a.source_height)===Number(b.source_height)&&sameNumbers(a.source_transform,b.source_transform)&&sameNumbers(a.corners&&a.corners.flat(),b.corners&&b.corners.flat()));}
function compatiblePair(a,b){
 if(!a||!b||a.id===b.id||a.product_type!==b.product_type)return false;
 const at=String(a.track||''),bt=String(b.track||'');
 const al=String(a.look_direction||''),bl=String(b.look_direction||'');
 if(!at||!bt||at.startsWith('geometry-unclassified:')||bt.startsWith('geometry-unclassified:')||at!==bt||!al||!bl||al!==bl)return false;
 const aa=compareLayerFor(a,1),bb=compareLayerFor(b,1);
 return Boolean(aa&&bb&&aa.description===bb.description&&aa.units===bb.units&&sameSourceGrid(aa,bb));
}
function compareOptions(select,items,currentValue){select.innerHTML=items.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.secondary_date)+' · '+esc(p.id)+'</option>').join('');if(items.some(p=>p.id===currentValue))select.value=currentValue;}
function addComparisonBaseLayers(map,loadedFlag){
 if(!map||!map.isStyleLoaded())return;
 if(aoi&&!map.getSource('compare-aoi')){map.addSource('compare-aoi',{type:'geojson',data:manifest.aoi});map.addLayer({id:'compare-aoi-fill',type:'fill',source:'compare-aoi',paint:{'fill-color':'#66e2d3','fill-opacity':0.04}});map.addLayer({id:'compare-aoi-outline',type:'line',source:'compare-aoi',paint:{'line-color':'#66e2d3','line-width':2,'line-dasharray':[2,1]}});}
 if(place&&Number.isFinite(Number(place.longitude))&&Number.isFinite(Number(place.latitude))&&!map.getSource('compare-site')){map.addSource('compare-site',{type:'geojson',data:{type:'Feature',properties:{name:place.name||'Selected site'},geometry:{type:'Point',coordinates:[Number(place.longitude),Number(place.latitude)]}}});map.addLayer({id:'compare-site-marker',type:'circle',source:'compare-site',paint:{'circle-radius':6,'circle-color':'#f7c76b','circle-stroke-color':'#fff','circle-stroke-width':1.5}});}if(target.status==='IN_AOI_TARGET_CAPTURED'&&Number.isFinite(Number(target.longitude))&&Number.isFinite(Number(target.latitude))&&!map.getSource('compare-target')){map.addSource('compare-target',{type:'geojson',data:{type:'Feature',properties:{name:'Measurement target'},geometry:{type:'Point',coordinates:[Number(target.longitude),Number(target.latitude)]}}});map.addLayer({id:'compare-target-marker',type:'circle',source:'compare-target',paint:{'circle-radius':3.5,'circle-color':'#ff806e','circle-stroke-color':'#fff','circle-stroke-width':1.2}});}
}
function createComparisonMap(container,side){
 const map=new maplibregl.Map({container,style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm'}]},center:[0,0],zoom:2});
 map.addControl(new maplibregl.NavigationControl(),'top-right');
 map.on('load',function(){addComparisonBaseLayers(map);if(aoi){const coords=aoi.coordinates[0]||[];if(coords.length){let west=Infinity,south=Infinity,east=-Infinity,north=-Infinity;coords.forEach(c=>{west=Math.min(west,c[0]);south=Math.min(south,c[1]);east=Math.max(east,c[0]);north=Math.max(north,c[1]);});map.fitBounds([[west,south],[east,north]],{padding:24,maxZoom:14});}}if(side==='A')compareMapALoaded=true;else compareMapBLoaded=true;renderPairComparison();});
 map.on('move',function(){if(comparisonSyncing)return;const other=side==='A'?compareMapBInstance:compareMapAInstance;if(!other||!other.loaded())return;comparisonSyncing=true;other.jumpTo({center:map.getCenter(),zoom:map.getZoom(),bearing:map.getBearing(),pitch:map.getPitch()});comparisonSyncing=false;});
 return map;
}
function setCompareOverlay(map,side,p,band){
 if(!map||!map.isStyleLoaded())return;
 const sourceId='compare-raster-'+side,layerId='compare-raster-layer-'+side;
 if(map.getLayer(layerId))map.removeLayer(layerId);if(map.getSource(sourceId))map.removeSource(sourceId);
 const layer=compareLayerFor(p,band);if(!layer)return;
 const url=(window.SARGUARDIAN_LAYER_DATA||{})[layer.id]||layer.preview_asset;
 map.addSource(sourceId,{type:'image',url,coordinates:layer.corners});
 map.addLayer({id:layerId,type:'raster',source:sourceId,paint:{'raster-opacity':0.88,'raster-resampling':'nearest'}});
}
function renderPairComparison(){
 const selectA=$('compareA'),selectB=$('compareB'),selectBand=$('compareBand');
 if(!selectA||!selectB||!selectBand)return;
 const observationA=obs.find(p=>p.id===selectA.value)||null;
 const priorB=selectB.value;
 const compatible=obs.filter(p=>compatiblePair(observationA,p));
 compareOptions(selectB,compatible,priorB);
 const observationB=obs.find(p=>p.id===selectB.value)||null;
 const compatibleNow=compatiblePair(observationA,observationB);
 const status=$('compareStatus');
 selectB.disabled=!compatible.length;
 if(!compatibleNow){
  status.textContent='Comparison withheld: no second observation with matching product family, known track/look geometry and exact source grid. No difference or movement claim is generated.';
  $('compareTitleA').textContent=observationA?'Pair A · '+observationA.id:'Pair A';
  $('compareTitleB').textContent='No compatible Pair B';
  $('compareLegendA').textContent='No valid pair comparison selected.';
  $('compareLegendB').textContent='A compatible source grid is required.';
  return;
 }
 const layerA=compareLayerFor(observationA,1),layerB=compareLayerFor(observationB,1);
 const commonBands=layers.filter(l=>l.observation_id===observationA.id).filter(l=>{
  const other=compareLayerFor(observationB,l.band);
  return other&&l.description===other.description&&l.units===other.units&&sameSourceGrid(l,other);
 });
 const previousBand=selectBand.value;
 selectBand.innerHTML=commonBands.map(l=>'<option value="'+esc(l.band)+'">Band '+esc(l.band)+': '+esc(l.description)+' ('+esc(l.units)+')</option>').join('');
 if(commonBands.some(l=>String(l.band)===previousBand))selectBand.value=previousBand;
 selectBand.disabled=!commonBands.length;
 const band=Number(selectBand.value||1),chosenA=compareLayerFor(observationA,band),chosenB=compareLayerFor(observationB,band);
 if(!chosenA||!chosenB||!sameSourceGrid(chosenA,chosenB)||chosenA.description!==chosenB.description||chosenA.units!==chosenB.units){
  status.textContent='Selected bands do not satisfy the common-grid and common-band contract. Comparison withheld.';
  return;
 }
 $('compareTitleA').textContent=(observationA.reference_date||'—')+' → '+(observationA.secondary_date||'—')+' · '+observationA.id;
 $('compareTitleB').textContent=(observationB.reference_date||'—')+' → '+(observationB.secondary_date||'—')+' · '+observationB.id;
 const warning='Separate pairwise raster · '+chosenA.description+' · '+chosenA.units+' · display scaling is for visualization only.';
 $('compareLegendA').textContent=warning;
 $('compareLegendB').textContent=warning;
 status.textContent='Compatible pairwise view only: same family ('+observationA.product_type+'), track '+observationA.track+', look '+observationA.look_direction+', source CRS/grid and band meaning match. The two values are not subtracted and may still use different per-pair references.';
 if(!compareMapAInstance&&maplibregl&&typeof maplibregl.Map==='function')compareMapAInstance=createComparisonMap('compareMapA','A');
 if(!compareMapBInstance&&maplibregl&&typeof maplibregl.Map==='function')compareMapBInstance=createComparisonMap('compareMapB','B');
 if(compareMapALoaded&&compareMapAInstance)setCompareOverlay(compareMapAInstance,'A',observationA,band);
 if(compareMapBLoaded&&compareMapBInstance)setCompareOverlay(compareMapBInstance,'B',observationB,band);
 if(compareMapAInstance)compareMapAInstance.resize();if(compareMapBInstance)compareMapBInstance.resize();
}
function renderHypotheticalScenario(){
 const svg=$('scenarioChart'),result=$('scenarioResult');if(!svg||!result)return;
 const rate=Number($('scenarioRate').value),days=Number($('scenarioDays').value);
 svg.replaceChildren();
 if($('scenarioRate').value.trim()===''||$('scenarioDays').value.trim()===''||!Number.isFinite(rate)||!Number.isFinite(days)||days<1||days>90||!Number.isInteger(days)||Math.abs(rate)>500){
  result.textContent='Enter a finite hypothetical rate between −500 and +500 mm/day and a duration of 1–90 whole days. No scenario is shown until both inputs are valid.';
  svg.setAttribute('viewBox','0 0 560 80');svg.style.height='80px';return;
 }
 const cumulative=rate*days,maxAbs=Math.max(1,Math.abs(cumulative));
 svg.setAttribute('viewBox','0 0 560 180');svg.style.height='180px';
 const line=(x1,y1,x2,y2,stroke,width,dash)=>{const e=document.createElementNS('http://www.w3.org/2000/svg','line');for(const [k,v] of Object.entries({x1,y1,x2,y2,stroke,'stroke-width':width,'stroke-dasharray':dash||''}))e.setAttribute(k,v);svg.append(e);};
 const textSvg=(x,y,value,anchor='start')=>{const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',x);t.setAttribute('y',y);t.setAttribute('text-anchor',anchor);t.textContent=value;svg.append(t);};
 const zero=88,endY=zero-(cumulative/maxAbs)*55;
 line(38,zero,522,zero,'#72909d',1,'4 3');line(38,28,38,148,'#72909d',1,'');
 line(38,zero,522,endY,'#66e2d3',3,'');
 const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');dot.setAttribute('cx','522');dot.setAttribute('cy',String(endY));dot.setAttribute('r','4');dot.setAttribute('fill','#66e2d3');svg.append(dot);
 textSvg(38,17,'HYPOTHETICAL RATE × DURATION · NOT OBSERVED');textSvg(38,164,'0 days');textSvg(522,164,String(days)+' days','end');
 textSvg(48,zero-7,'0 mm');textSvg(514,endY+(cumulative>=0?-8:16),cumulative.toFixed(1)+' mm','end');
 const pair=current(),metrics=pair&&pair.metrics||{},floor=(metrics.target_local_floor_status==='MEASURED'?Number(metrics.target_local_floor_mm_day):NaN);
 let message='Hypothetical only — not observed NISAR data, not a hazard alert, and not a forecast. Scenario displacement after '+days+' days: '+cumulative.toFixed(2)+' mm at '+rate.toFixed(2)+' mm/day.';
 if(Number.isFinite(floor)&&floor>0){
  const ratio=Math.abs(rate)/floor;
  message+=' Selected observed pair '+pair.id+' has a measured pair-local floor of '+floor.toFixed(2)+' mm/day; absolute scenario rate is '+ratio.toFixed(2)+'× that floor. This ratio is a simple sensitivity comparison, not a formal detection probability, inverse-velocity test or prediction.';
 } else {
  message+=' No measured target-local floor is available for the selected observed pair; no detection-threshold comparison is shown.';
 }
 result.textContent=message;
}
function initComparisonControls(){
 const a=$('compareA'),b=$('compareB'),band=$('compareBand'),details=$('pairCompare');
 compareOptions(a,obs,obs[0]&&obs[0].id);
 if(obs.length>1){const first=obs.find(p=>obs.some(q=>compatiblePair(p,q)));if(first)a.value=first.id;}
 renderPairComparison();
 a.addEventListener('change',renderPairComparison);b.addEventListener('change',renderPairComparison);band.addEventListener('change',renderPairComparison);
 details.addEventListener('toggle',()=>{if(details.open){renderPairComparison();if(compareMapAInstance)compareMapAInstance.resize();if(compareMapBInstance)compareMapBInstance.resize();}});
 $('simulateScenario').addEventListener('click',renderHypotheticalScenario);
}
function renderCommonReferenceChart(){
 const report=manifest.common_reference_timeseries||{},selectBox=$('cumulativeNetwork'),status=$('cumulativeStatus'),svg=$('cumulativeChart');
 if(!selectBox||!status||!svg)return;
 const components=(report.components||[]).filter(c=>c.status==='DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED'&&Array.isArray(c.series)&&c.series.length>=3);
 const oldValue=selectBox.value;
 selectBox.innerHTML=components.map((c,i)=>'<option value="'+i+'">'+esc(c.network)+' · component '+esc(c.component)+'</option>').join('');
 selectBox.disabled=!components.length;
 svg.replaceChildren();
 if(!components.length){
  const reason=report.reason||'No common-reference cumulative series met the minimum pixel, grid, redundancy and jackknife-stability gates.';
  status.textContent='Series withheld · '+String(report.status||'NOT_REPORTED')+' · '+reason;
  svg.setAttribute('viewBox','0 0 560 85');svg.style.height='85px';
  const textNode=document.createElementNS('http://www.w3.org/2000/svg','text');textNode.setAttribute('x','10');textNode.setAttribute('y','34');textNode.textContent='No publishable cumulative diagnostic series for this run.';svg.append(textNode);
  return;
 }
 if(oldValue!==''&&Number.isInteger(Number(oldValue))&&Number(oldValue)>=0&&Number(oldValue)<components.length)selectBox.value=oldValue;
 const component=components[Number(selectBox.value)||0],rows=component.series.filter(p=>p.cumulative_los_mm!==null&&p.cumulative_los_mm!==undefined&&Number.isFinite(Number(p.cumulative_los_mm)));
 if(rows.length<3){
  status.textContent='Series withheld: insufficient finite acquisition-epoch values.';
  return;
 }
 status.textContent='DIAGNOSTIC ONLY · '+component.network+' · '+rows.length+' actual epochs · '+component.pairs_count+' pairs · redundancy '+component.redundancy+' · common-reference pixels '+((report.networks||[]).find(n=>n.network===component.network)||{}).common_pixels_outside_target_buffer+'. The common datum is AOI-derived and reference stability is not independently validated.';
 const epochs=rows.map(p=>Date.parse(p.epoch+'T00:00:00Z')),values=rows.map(p=>Number(p.cumulative_los_mm));
 const uncertainty=rows.map(p=>({lo:p.graph_fit_ci95_low_mm,hi:p.graph_fit_ci95_high_mm})).filter(v=>v.lo!==null&&v.hi!==null&&Number.isFinite(Number(v.lo))&&Number.isFinite(Number(v.hi)));
 const yVals=[...values,...uncertainty.flatMap(v=>[Number(v.lo),Number(v.hi)])],minY=Math.min(0,...yVals),maxY=Math.max(0,...yVals),spanY=Math.max(1,maxY-minY);
 const minX=Math.min(...epochs),maxX=Math.max(...epochs),spanX=Math.max(1,maxX-minX);
 const W=600,H=230,left=66,right=18,top=30,bottom=45,plotW=W-left-right,plotH=H-top-bottom;
 const xMap=x=>left+(x-minX)/spanX*plotW;
 const yMap=y=>top+(maxY-y)/spanY*plotH;
 svg.setAttribute('viewBox','0 0 '+W+' '+H);svg.style.height='230px';
 const addLine=(x1,y1,x2,y2,stroke,width,dash)=>{const e=document.createElementNS('http://www.w3.org/2000/svg','line');[['x1',x1],['y1',y1],['x2',x2],['y2',y2],['stroke',stroke],['stroke-width',width],['stroke-dasharray',dash||'']].forEach(([k,v])=>e.setAttribute(k,v));svg.append(e);};
 const addText=(x,y,txt,anchor='middle')=>{const e=document.createElementNS('http://www.w3.org/2000/svg','text');e.setAttribute('x',x);e.setAttribute('y',y);e.setAttribute('text-anchor',anchor);e.textContent=txt;svg.append(e);};
 for(let i=0;i<=4;i++){const value=minY+spanY*i/4,y=yMap(value);addLine(left,y,W-right,y,'#29414f',1,'3 4');addText(left-8,y+3,value.toFixed(1),'end');}
 addLine(left,top,left,H-bottom,'#72909d',1,'');addLine(left,H-bottom,W-right,H-bottom,'#72909d',1,'');
 addText(left,14,'Cumulative LOS · mm (relative to first connected epoch)','start');
 const pathNode=document.createElementNS('http://www.w3.org/2000/svg','path');pathNode.setAttribute('d',rows.map((p,i)=>(i?'L':'M')+xMap(epochs[i]).toFixed(2)+' '+yMap(values[i]).toFixed(2)).join(' '));pathNode.setAttribute('fill','none');pathNode.setAttribute('stroke','#66e2d3');pathNode.setAttribute('stroke-width','2.5');svg.append(pathNode);
 rows.forEach((p,i)=>{const x=xMap(epochs[i]),y=yMap(values[i]),lo=p.graph_fit_ci95_low_mm,hi=p.graph_fit_ci95_high_mm;
  if(lo!==null&&hi!==null&&Number.isFinite(Number(lo))&&Number.isFinite(Number(hi))){const y1=yMap(Number(hi)),y2=yMap(Number(lo));addLine(x,y1,x,y2,'#ffffff',1.4,'');addLine(x-4,y1,x+4,y1,'#ffffff',1.4,'');addLine(x-4,y2,x+4,y2,'#ffffff',1.4,'');}
  const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');dot.setAttribute('cx',x);dot.setAttribute('cy',y);dot.setAttribute('r',4);dot.setAttribute('fill','#66e2d3');dot.setAttribute('stroke','#07121c');dot.setAttribute('stroke-width',1);const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=p.epoch+': '+values[i].toFixed(2)+' mm cumulative LOS';dot.append(title);svg.append(dot);
 });
 addText(left,H-17,rows[0].epoch,'start');addText(W-right,H-17,rows[rows.length-1].epoch,'end');
 addText(W-right,14,'White bars: fit-only 95% interval','end');
}
function select(i){if(!n)return;selected=(i+n)%n;renderProduct();}function stop(){playing=false;if(timer)clearInterval(timer);timer=null;$('play').textContent='Play';}function play(){if(!n)return;if(playing){stop();return;}playing=true;$('play').textContent='Pause';timer=setInterval(()=>select((selected+1)%n),Number($('speed').value||1500));}
$('timeline').addEventListener('input',e=>{stop();select(Number(e.target.value));});$('productSelect').addEventListener('change',e=>{stop();select(Number(e.target.value));});$('previous').addEventListener('click',()=>{stop();select(selected-1);});$('next').addEventListener('click',()=>{stop();select(selected+1);});$('play').addEventListener('click',play);$('speed').addEventListener('change',()=>{if(playing){stop();play();}});$('measurementTrack').addEventListener('change',renderMeasurementChart);$('measurementMetric').addEventListener('change',renderMeasurementChart);$('cumulativeNetwork').addEventListener('change',renderCommonReferenceChart);$('bandSelect').addEventListener('change',renderProduct);$('opacity').addEventListener('input',()=>{if(M&&activeLayer&&M.getLayer('raster-'+activeLayer))M.setPaintProperty('raster-'+activeLayer,'raster-opacity',Number($('opacity').value)/100);});$('presentation').addEventListener('click',async()=>{try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen();}catch(e){$('presentation').textContent='Fullscreen unavailable';}});window.addEventListener('beforeunload',()=>{stop();if(compareMapAInstance)compareMapAInstance.remove();if(compareMapBInstance)compareMapBInstance.remove();});renderList();renderChart();renderMeasurementChart();renderCommonReferenceChart();renderSciencePipeline();initComparisonControls();if(n)renderProduct();else $('mapTitle').textContent='No observations available';})();
</script></body></html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def metric_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def prepare_web_dashboard(root: Path) -> dict[str, Any]:
    root = root.resolve()
    summary_path = root / "aoi-run-summary.json"
    report_path = root / "aoi-processing-report.json"
    summary = read_json(summary_path)
    report = read_json(report_path, required=False)
    products = report.get("products")
    if not isinstance(products, list):
        products = [read_json(p) for p in sorted((root / "product-data").glob("*/product-record.json"))]
    if len(products) != int(summary.get("products_expected", len(products))):
        raise ValueError("Dashboard product count does not match processing summary")
    ring = parse_wkt(str(summary.get("aoi_wkt") or ""))
    geometry = {"type": "Polygon", "coordinates": [ring]}
    feature = {"type": "Feature", "properties": {"name": summary.get("aoi_name", "custom"), "aoi_wkt_sha256": summary.get("aoi_wkt_sha256")}, "geometry": geometry}
    bbox = [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)]

    pending = []
    groups: dict[tuple[str, str, str], list[np.ndarray]] = {}
    ordered = sorted(products, key=lambda p: (str(p.get("secondary_date") or "9999"), str(p.get("reference_date") or "9999"), str(p.get("id") or "")))
    for product in ordered:
        pid = str(product.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", pid):
            raise ValueError("Invalid product ID in processing report")
        exports = product.get("exports") or []
        if not exports:
            exports = [{"relative_path": next((p.relative_to(root).as_posix() for p in (root / "product-data" / pid).glob("*.tif")), "")}]
        band1_source_counts: list[int] = []
        for export_index, export in enumerate(exports):
            relative = str(export.get("relative_path") or "")
            if not relative:
                continue
            raster_path = safe_path(root, relative)
            if not raster_path.is_file() or raster_path.suffix.lower() not in {".tif", ".tiff"}:
                raise ValueError(f"Validated GeoTIFF not found: {pid}/{relative}")
            original_hash = sha256(raster_path)
            with rasterio.open(raster_path) as ds:
                band_count = ds.count
            for band in range(1, band_count + 1):
                values, bounds, meta = reproject_band(raster_path, band, geometry)
                overlaps = bounds[0] <= bbox[2] and bounds[2] >= bbox[0] and bounds[1] <= bbox[3] and bounds[3] >= bbox[1]
                if not overlaps:
                    raise ValueError(f"Preview does not intersect AOI: {pid}/{raster_path.name}")
                valid = values[np.isfinite(values)]
                if band == 1:
                    band1_source_counts.append(meta["source_valid_pixels"])
                if not valid.size:
                    continue
                track_value = (product.get("stats") or {}).get("track") or product.get("track")
                track = str(track_value) if track_value else "geometry-unclassified:" + pid
                kind = "coherence" if "coherence" in meta["description"].lower() else "continuous"
                group_key = (str(product.get("product_type") or "UNKNOWN"), track, meta["description"])
                groups.setdefault(group_key, []).append(valid.astype("float32", copy=False))
                layer_id = f"{pid}-e{export_index+1}-band-{band}"
                pending.append({
                    "id": layer_id, "observation_id": pid, "product_type": product.get("product_type"),
                    "export_name": raster_path.name, "band": band, "description": meta["description"], "units": meta["units"],
                    "kind": kind, "source_sha256": original_hash, "source_asset": relative,
                    "source_crs": meta["source_crs"], "source_transform": meta["source_transform"],
                    "source_width": meta["source_width"], "source_height": meta["source_height"],
                    "source_valid_pixels": meta["source_valid_pixels"], "data_type": meta["data_type"],
                    "preview_crs": WEB_CRS, "preview_transform": meta["preview_transform"],
                    "preview_width": meta["preview_width"], "preview_height": meta["preview_height"],
                    "bounds_wgs84": list(bounds),
                    "corners": [[bounds[0], bounds[3]], [bounds[2], bounds[3]], [bounds[2], bounds[1]], [bounds[0], bounds[1]]],
                    "valid_pixels": int(valid.size), "value_min": float(np.min(valid)), "value_max": float(np.max(valid)),
                    "values": values, "group_key": group_key,
                })
            if sha256(raster_path) != original_hash:
                raise RuntimeError(f"Source GeoTIFF unexpectedly changed: {raster_path.name}")
        if band1_source_counts and product.get("valid_pixels") is not None:
            try:
                expected_valid = int(product["valid_pixels"])
            except (TypeError, ValueError):
                expected_valid = -1
            if expected_valid >= 0 and max(band1_source_counts) != expected_valid:
                raise ValueError(f"Product valid-pixel summary mismatch for {pid}: record={expected_valid}, max_export={max(band1_source_counts)}")

    webroot = root / "web-dashboard"
    public_layers = []
    for layer in pending:
        values = layer.pop("values")
        group_key = layer.pop("group_key")
        if layer["kind"] == "coherence":
            lo, hi, method = 0.0, 1.0, "fixed_coherence_0_to_1"
        else:
            joined = np.concatenate(groups[group_key])
            limit = float(np.percentile(np.abs(joined[np.isfinite(joined)]), 98))
            if not math.isfinite(limit) or limit <= 0:
                limit = max(float(np.max(np.abs(joined[np.isfinite(joined)]))), 1.0)
            lo, hi, method = -limit, limit, "track_group_symmetric_98th_percentile"
        rel = f"layers/{layer['id']}.png"
        image_path = webroot / rel
        count, min_value, max_value = write_rgba(values, lo, hi, layer["kind"], image_path)
        if count != layer["valid_pixels"] or image_path.stat().st_size <= 0:
            raise ValueError(f"Preview integrity check failed: {layer['id']}")
        layer.update({"preview_asset": rel, "preview_sha256": sha256(image_path), "preview_bytes": image_path.stat().st_size,
                      "display_scale": {"min": lo, "max": hi, "method": method, "clipping_percentile": 98 if layer["kind"] != "coherence" else None},
                      "value_min": min_value, "value_max": max_value})
        public_layers.append(layer)

    observations = []
    for product in ordered:
        stats = product.get("stats") or {}
        floor = product.get("local_floor") if isinstance(product.get("local_floor"), dict) else {}
        floor_metrics = floor.get("metrics") if isinstance(floor.get("metrics"), dict) else {}
        target = product.get("target_measurement") if isinstance(product.get("target_measurement"), dict) else {}
        target_metrics = target.get("measurements") if isinstance(target.get("measurements"), dict) else {}
        target_status = str(target.get("status") or "NOT_REPORTED")
        floor_status = str(floor.get("status") or "NOT_REPORTED")
        product_layers = [layer for layer in public_layers if layer["observation_id"] == product.get("id")]
        band1 = next((layer for layer in product_layers if layer["band"] == 1), None)
        metric_name = str(product.get("metric_name") or "")
        metric_units = "source units not declared"
        if product.get("product_type") == "GUNW" and band1 and "los displacement" in band1["description"].lower() and "median" in metric_name.lower():
            metric_units = "mm"
        elif product.get("product_type") == "GOFF" and metric_name.lower() in {"range_median_mm", "median_range_mm", "azimuth_median_mm"}:
            metric_units = "mm"
        elif "mm_day" in metric_name.lower() or "floor" in metric_name.lower() or "velocity" in metric_name.lower():
            metric_units = "mm/day"
        observations.append({
            "id": product.get("id"), "product_type": product.get("product_type"), "granule_name": product.get("granule_name"),
            "reference_date": product.get("reference_date"), "secondary_date": product.get("secondary_date"),
            "track": stats.get("track") or product.get("track"),
            "look_direction": product.get("look_direction") or stats.get("look_direction"),
            "maturity": product.get("maturity"), "crid": product.get("crid") or stats.get("crid"),
            "status": product.get("status"), "valid_pixels": product.get("valid_pixels"),
            "grid_pixels_inside_aoi": product.get("grid_pixels_inside_aoi"), "source_sha256": product.get("source_sha256"),
            "warnings": product.get("warnings") or [], "validation_scope": product.get("validation_scope") or "structural_and_provenance_not_independent_geophysical_validation",
            "native_assets": [item.get("relative_path") for item in product.get("exports", []) if item.get("relative_path")],
            "quicklook": product.get("quicklook"), "layers": [layer["id"] for layer in product_layers],
            "metrics": {
                "reader_median": product.get("metric_value"),
                "reader_median_name": product.get("metric_name"),
                "reader_median_units": metric_units if product.get("metric_value") is not None else None,
                "goff_range_median_mm": metric_number(stats.get("range_median_mm")),
                "goff_azimuth_median_mm": metric_number(stats.get("azimuth_median_mm")),
                "goff_detect_floor_mm_day": metric_number(stats.get("detect_floor_mm_day")),
                "goff_range_velocity_mm_day": metric_number(stats.get("range_velocity_mm_day")),
                "mean_coherence": metric_number(stats.get("mean_coherence")),
                "mean_correlation": metric_number(stats.get("mean_correlation")),
                "target_measurement_status": target_status,
                "target_local_los_median_mm": metric_number(target_metrics.get("target_local_los_median_mm")) if target_status == "MEASURED" else None,
                "target_local_range_median_mm": metric_number(target_metrics.get("target_local_range_median_mm")) if target_status == "MEASURED" else None,
                "target_local_azimuth_median_mm": metric_number(target_metrics.get("target_local_azimuth_median_mm")) if target_status == "MEASURED" else None,
                "target_mean_coherence": metric_number(target_metrics.get("mean_coherence")) if target_status == "MEASURED" else None,
                "target_mean_correlation": metric_number(target_metrics.get("mean_correlation")) if target_status == "MEASURED" else None,
                "target_local_floor_status": floor_status,
                "target_local_floor_mm_day": metric_number(floor_metrics.get("local_floor_mm_day")) if floor_status == "MEASURED" else None,
                "target_local_floor_ci_lo_mm_day": metric_number(floor_metrics.get("local_floor_ci_lo_mm_day")) if floor_status == "MEASURED" else None,
                "target_local_floor_ci_hi_mm_day": metric_number(floor_metrics.get("local_floor_ci_hi_mm_day")) if floor_status == "MEASURED" else None,
            },
        })
    limitations = [
        "Structural/provenance PASS is not independent geophysical validation.",
        "Pairwise LOS displacement is not automatically cumulative, vertical, or 3-D ground motion.",
        "Playback shows actual acquisition pairs and does not interpolate missing observations or forecast movement.",
    ]
    diagnostics = summary.get("science_diagnostics") or {}
    stack = diagnostics.get("pixel_stack") or {}
    if stack:
        limitations.append(f"Pixel-stack status: {stack.get('status')}; inspect saved logs and diagnostics before interpreting a trend.")
    candidate = diagnostics.get("candidate_checks") or {}
    if str(candidate.get("status", "")).startswith("SKIPPED"):
        limitations.append("Candidate screening was skipped for this arbitrary WKT AOI because the current candidate checker does not support it.")
    manifest = {
        "schema_version": SCHEMA, "run": {
            "github_run_id": summary.get("run_id"), "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "aoi_wkt_sha256": summary.get("aoi_wkt_sha256"), "science_commit": summary.get("science_commit"),
            "orchestration_commit": summary.get("orchestration_sha"), "workflow_commit": summary.get("dispatcher_workflow_sha"),
        },
        "validation": {"processing_status": summary.get("status", "UNKNOWN"), "visual_assets_status": "PASS" if public_layers else "NO_RENDERABLE_LAYERS",
                       "independent_geophysical_validation": "NOT_PERFORMED", "products_expected": summary.get("products_expected"),
                       "products_validated": summary.get("products_validated")},
        "aoi": feature, "aoi_bbox": bbox,
        "time_window": {"start_date": summary.get("date_start"), "end_date": summary.get("date_end"),
                        "date_basis": summary.get("date_basis"), "date_filter_mode": summary.get("date_filter_mode")},
        "observations": observations, "layers": public_layers, "science_limitations": limitations,
        "science_pipeline": summary.get("science_pipeline") or {},
        "site_context": summary.get("site_context") or {},
        "common_reference_timeseries": summary.get("common_reference_timeseries") or {},
        "display_policy": "Actual pair selection only. The common-reference graph is explicitly diagnostic when shown; no extrapolation or hazard inference is added by the visualization layer.",
    }
    webroot.mkdir(parents=True, exist_ok=True)
    (webroot / "aoi.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, indent=2) + "\n", encoding="utf-8")
    selected_place = (summary.get("site_context") or {}).get("place") or {}
    site_features = []
    try:
        site_lat, site_lon = float(selected_place.get("latitude")), float(selected_place.get("longitude"))
        if (math.isfinite(site_lat) and math.isfinite(site_lon)
                and -90 <= site_lat <= 90 and -180 <= site_lon <= 180):
            site_features.append({
                "type": "Feature",
                "properties": {
                    "name": str(selected_place.get("name") or "Selected place")[:200],
                    "inside_aoi": selected_place.get("inside_aoi"),
                    "role": "map-selected-place-context_not_hazard_evidence",
                },
                "geometry": {"type": "Point", "coordinates": [site_lon, site_lat]},
            })
    except (TypeError, ValueError, OverflowError):
        pass
    target_context = (summary.get("site_context") or {}).get("measurement_target") or {}
    if target_context.get("status") == "IN_AOI_TARGET_CAPTURED":
        try:
            target_lat = float(target_context.get("latitude"))
            target_lon = float(target_context.get("longitude"))
            if (math.isfinite(target_lat) and math.isfinite(target_lon)
                    and -90 <= target_lat <= 90 and -180 <= target_lon <= 180):
                site_features.append({
                    "type": "Feature",
                    "properties": {
                        "name": "Measurement target",
                        "inside_aoi": True,
                        "role": "in_aoi_pair_local_measurement_target_not_stable_reference",
                    },
                    "geometry": {"type": "Point", "coordinates": [target_lon, target_lat]},
                })
        except (TypeError, ValueError, OverflowError):
            pass
    (webroot / "site.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "features": site_features,
        "note": "Place context and measurement target are separate; neither marker is hazard evidence or a stable-ground reference.",
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (webroot / "timeline.json").write_text(json.dumps({"schema_version": SCHEMA, "observations": [
        {key: obs.get(key) for key in ("id", "product_type", "reference_date", "secondary_date", "track", "look_direction", "maturity", "valid_pixels", "layers")} for obs in observations
    ], "policy": "pair-aware; no synthetic intermediate observations"}, indent=2) + "\n", encoding="utf-8")
    (webroot / "metrics.json").write_text(json.dumps({"schema_version": SCHEMA, "products": [
        {"id": obs["id"], "product_type": obs["product_type"], "track": obs["track"], "secondary_date": obs["secondary_date"],
         "valid_pixels": obs["valid_pixels"], "metrics": obs["metrics"]} for obs in observations
    ], "limitations": limitations}, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (webroot / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    image_data = {}
    for layer in public_layers:
        image = safe_path(webroot, layer["preview_asset"])
        image_data[layer["id"]] = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")
    manifest_blob = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    manifest_blob = manifest_blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    (webroot / "dashboard-data.js").write_text(
        "window.SARGUARDIAN_DASHBOARD=" + manifest_blob + ";\nwindow.SARGUARDIAN_LAYER_DATA=" +
        json.dumps(image_data, separators=(",", ":"), allow_nan=False) + ";\n", encoding="utf-8"
    )

    stac_root = webroot / "stac"
    stac_items = stac_root / "items"
    stac_items.mkdir(parents=True, exist_ok=True)
    item_links = []
    for obs in observations:
        product = next(p for p in products if p.get("id") == obs["id"])
        date = str(obs.get("secondary_date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError(f"Invalid secondary date for STAC item {obs['id']}")
        assets = {}
        exports = product.get("exports") or []
        if exports and exports[0].get("relative_path"):
            assets["native_raster"] = {"href": "../../../" + str(exports[0]["relative_path"]), "type": "image/tiff; application=geotiff", "roles": ["data"]}
        for idx, layer in enumerate(l for l in public_layers if l["observation_id"] == obs["id"]):
            assets["preview_band_" + str(layer["band"]) + "_" + str(idx + 1)] = {"href": "../../" + layer["preview_asset"], "type": "image/png", "roles": ["overview"]}
        if obs.get("quicklook"):
            assets["quicklook"] = {"href": "../../../" + str(obs["quicklook"]), "type": "image/png", "roles": ["overview"]}
        item = {
            "stac_version": "1.1.0", "type": "Feature", "id": str(obs["id"]), "geometry": geometry, "bbox": bbox,
            "properties": {"datetime": date + "T00:00:00Z", "start_datetime": str(obs.get("reference_date")) + "T00:00:00Z",
                           "end_datetime": date + "T00:00:00Z", "platform": "NISAR", "instruments": ["L-SAR"],
                           "sarguardian:product_type": obs.get("product_type"), "sarguardian:track": obs.get("track"),
                           "sarguardian:crid": obs.get("crid"), "sarguardian:maturity": obs.get("maturity"),
                           "sarguardian:source_sha256": obs.get("source_sha256"), "sarguardian:validation_scope": obs.get("validation_scope")},
            "links": [{"rel": "self", "href": str(obs["id"]) + ".json"}, {"rel": "parent", "href": "../collection.json"}, {"rel": "root", "href": "../catalog.json"}],
            "assets": assets,
        }
        (stac_items / (str(obs["id"]) + ".json")).write_text(json.dumps(item, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        item_links.append({"rel": "item", "href": "items/" + str(obs["id"]) + ".json", "type": "application/geo+json"})
    dates = [str(o.get("secondary_date")) for o in observations if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(o.get("secondary_date") or ""))]
    date_start = str(summary.get("date_start") or (min(dates) if dates else "2026-01-01"))
    date_end = str(summary.get("date_end") or (max(dates) if dates else "2026-12-31"))
    collection = {"stac_version": "1.1.0", "type": "Collection", "id": "sarguardian-" + str(summary.get("run_id", "run")),
                  "description": "AOI-clipped NISAR acquisition-pair exports; pairwise values are not automatically a common-reference time series.",
                  "license": "other",
                  "sarguardian:license_note": "Official NASA/NISAR data-use guidance is linked below for source context only. Verify the exact source product metadata and any non-NASA/third-party terms before redistribution; this package does not relicense source data or grant rights to third-party content.",
                  "providers": [
                      {"name": "NASA / ISRO NISAR mission", "roles": ["producer"], "url": "https://nisar-docs.asf.alaska.edu/"},
                      {"name": "Alaska Satellite Facility DAAC", "roles": ["host"], "url": "https://asf.alaska.edu/"},
                  ],
                  "extent": {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [[date_start + "T00:00:00Z", date_end + "T23:59:59Z"]]}},
                  "links": [
                      {"rel": "self", "href": "collection.json"},
                      {"rel": "root", "href": "catalog.json"},
                      {"rel": "items", "href": "items/"},
                      {"rel": "license", "href": "https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy", "type": "text/html", "title": "NASA Earthdata data-use and citation guidance"},
                      {"rel": "license", "href": "https://nisar-docs.asf.alaska.edu/data-use-citation-guidance/", "type": "text/html", "title": "NISAR data-use and citation guidance"},
                  ] + item_links}
    (stac_root / "collection.json").write_text(json.dumps(collection, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    catalog = {"stac_version": "1.1.0", "type": "Catalog", "id": "sarguardian-" + str(summary.get("run_id", "run")),
               "description": "SARGuardian AOI-scoped NISAR products and derived previews.",
               "links": [{"rel": "self", "href": "catalog.json"}, {"rel": "child", "href": "collection.json", "type": "application/json"}]}
    (stac_root / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    write_viewer(webroot / "index.html")
    report_html = root / "index.html"
    if report_html.is_file():
        content = report_html.read_text(encoding="utf-8")
        if "web-dashboard/index.html" not in content:
            link = '<p class="interactive-dashboard-link"><a href="web-dashboard/index.html">Open interactive geospatial map &amp; observation timeline ↗</a></p>'
            content = re.sub(r"(<main(?:\s[^>]*)?>)", lambda m: m.group(1) + link, content, count=1, flags=re.I)
            report_html.write_text(content, encoding="utf-8")

    receipt = {"schema_version": SCHEMA, "status": "PASS" if public_layers else "PARTIAL", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "manifest": "web-dashboard/manifest.json", "viewer": "web-dashboard/index.html",
               "viewer_data": "web-dashboard/dashboard-data.js", "aoi_geojson": "web-dashboard/aoi.geojson",
               "timeline": "web-dashboard/timeline.json", "metrics": "web-dashboard/metrics.json",
               "stac_catalog": "web-dashboard/stac/catalog.json", "observations": len(observations),
               "layers": len(public_layers), "source_geotiffs_unchanged": True}
    (root / "web-dashboard-build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-root", required=True, type=Path)
    result = prepare_web_dashboard(parser.parse_args().dashboard_root)
    print("WEB_DASHBOARD_STATUS=" + result["status"])
    print("WEB_DASHBOARD_OBSERVATIONS=" + str(result["observations"]))
    print("WEB_DASHBOARD_LAYERS=" + str(result["layers"]))
    print("WEB_DASHBOARD_VIEWER=" + result["viewer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
