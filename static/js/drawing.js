// Drawing module — Leaflet-Geoman polygon drawing, editing, deleting, freehand
const Drawing = (() => {
    let _map = null;
    let _active = false;
    let _freehandActive = false;
    let _editActive = false;
    let _deleteActive = false;

    // Freehand state
    let _freehandDrawing = false;
    let _freehandPoints = [];
    let _freehandPolyline = null;

    function init(map) {
        _map = map;

        // Remove default Geoman toolbar (we use our own buttons)
        _map.pm.removeControls();

        // When a polygon is created via Geoman
        _map.on('pm:create', (e) => {
            // Remove the Geoman layer (we add it to our annotation layer instead)
            _map.removeLayer(e.layer);

            const cls = Classes.getActive();
            const geojson = e.layer.toGeoJSON(15);

            // Erase mode: use drawn polygon to clip existing annotations
            if (Classes.isEraseActive()) {
                Annotations.eraseWithPolygon(geojson.geometry);
                return;
            }

            const feature = {
                type: "Feature",
                geometry: geojson.geometry,
                properties: {
                    class_name: cls.name,
                    class_value: cls.value,
                    source: "manual",
                    id: _randomId(),
                },
            };
            Annotations.addFeature(feature);
        });

        // When editing is done on the annotation layer
        _map.on('pm:edit', () => {
            Annotations.triggerSave();
        });

        // Wire up toolbar buttons
        document.getElementById('btn-draw').addEventListener('click', toggleDraw);
        document.getElementById('btn-freehand').addEventListener('click', toggleFreehand);
        document.getElementById('btn-edit').addEventListener('click', toggleEdit);
        document.getElementById('btn-delete').addEventListener('click', toggleDelete);
    }

    // --- Standard polygon draw ---

    function toggleDraw() {
        if (typeof SAM !== 'undefined') SAM.deactivate();
        if (typeof Select !== 'undefined') Select.deactivate();
        _deactivateFreehand();
        _deactivateEdit();
        _deactivateDelete();

        if (_active) {
            _deactivateDraw();
        } else {
            _activateDraw();
        }
    }

    function _activateDraw() {
        const cls = Classes.getActive();
        _map.pm.enableDraw('Polygon', {
            snappable: false,
            templineStyle: { color: cls.color, weight: 2 },
            hintlineStyle: { color: cls.color, weight: 2, dashArray: '5,5' },
            pathOptions: {
                color: cls.color,
                fillColor: cls.color,
                fillOpacity: 0.3,
            },
        });
        _active = true;
        document.getElementById('btn-draw').classList.add('active');
    }

    function _deactivateDraw() {
        _map.pm.disableDraw();
        _active = false;
        document.getElementById('btn-draw').classList.remove('active');
    }

    // --- Freehand polygon draw ---
    // Click to start tracing, move mouse to place vertices, click again to finish.

    function toggleFreehand() {
        if (typeof SAM !== 'undefined') SAM.deactivate();
        if (typeof Select !== 'undefined') Select.deactivate();
        _deactivateDraw();
        _deactivateEdit();
        _deactivateDelete();

        if (_freehandActive) {
            _deactivateFreehand();
        } else {
            _activateFreehand();
        }
    }

    function _activateFreehand() {
        _freehandActive = true;
        _freehandDrawing = false;
        _freehandPoints = [];
        document.getElementById('btn-freehand').classList.add('active');
        _map.getContainer().style.cursor = 'crosshair';
        _map.on('click', _freehandClick);
    }

    function _deactivateFreehand() {
        _freehandActive = false;
        _freehandDrawing = false;
        _freehandPoints = [];
        _removeFreehandPolyline();
        document.getElementById('btn-freehand').classList.remove('active');
        _map.getContainer().style.cursor = '';
        _map.off('click', _freehandClick);
        _map.off('mousemove', _freehandMouseMove);
        _map.dragging.enable();
    }

    function _freehandClick(e) {
        if (!_freehandActive) return;

        if (!_freehandDrawing) {
            // First click — start tracing
            _freehandDrawing = true;
            _freehandPoints = [e.latlng];
            _map.dragging.disable();

            const cls = Classes.getActive();
            _freehandPolyline = L.polyline(_freehandPoints, {
                color: cls.color,
                weight: 2,
                dashArray: '4 4',
            }).addTo(_map);

            _map.on('mousemove', _freehandMouseMove);
        } else {
            // Second click — finish and create polygon
            _freehandFinish();
        }
    }

    function _freehandMouseMove(e) {
        if (!_freehandDrawing) return;
        _freehandPoints.push(e.latlng);
        _freehandPolyline.setLatLngs(_freehandPoints);
    }

    function _freehandFinish() {
        _map.off('mousemove', _freehandMouseMove);
        _map.dragging.enable();
        _freehandDrawing = false;

        if (_freehandPoints.length < 3) {
            _freehandPoints = [];
            _removeFreehandPolyline();
            return;
        }

        // Close the polygon
        _freehandPoints.push(_freehandPoints[0]);

        // Simplify: reduce point count to avoid huge GeoJSON
        const simplified = _simplifyPoints(_freehandPoints, 0.4);

        if (simplified.length < 4) {
            _freehandPoints = [];
            _removeFreehandPolyline();
            return;
        }

        const cls = Classes.getActive();
        const coords = simplified.map(p => [p.lng, p.lat]);
        const geometry = {
            type: "Polygon",
            coordinates: [coords],
        };

        // Erase mode: use drawn polygon to clip existing annotations
        if (Classes.isEraseActive()) {
            Annotations.eraseWithPolygon(geometry);
            _freehandPoints = [];
            _removeFreehandPolyline();
            return;
        }

        const feature = {
            type: "Feature",
            geometry: geometry,
            properties: {
                class_name: cls.name,
                class_value: cls.value,
                source: "freehand",
                id: _randomId(),
            },
        };

        Annotations.addFeature(feature);
        _freehandPoints = [];
        _removeFreehandPolyline();
    }

    function _removeFreehandPolyline() {
        if (_freehandPolyline) {
            _map.removeLayer(_freehandPolyline);
            _freehandPolyline = null;
        }
    }

    // Douglas-Peucker simplification in screen pixels
    function _simplifyPoints(points, tolerancePx) {
        if (points.length <= 2) return points;
        // Convert to pixel coords for distance calc
        const pixPts = points.map(p => _map.latLngToContainerPoint(p));
        const keep = new Array(points.length).fill(false);
        keep[0] = true;
        keep[points.length - 1] = true;
        _dpRecurse(pixPts, keep, 0, points.length - 1, tolerancePx);
        return points.filter((_, i) => keep[i]);
    }

    function _dpRecurse(pts, keep, start, end, tol) {
        if (end - start < 2) return;
        let maxDist = 0;
        let maxIdx = start;
        const a = pts[start];
        const b = pts[end];
        for (let i = start + 1; i < end; i++) {
            const d = _pointToLineDist(pts[i], a, b);
            if (d > maxDist) {
                maxDist = d;
                maxIdx = i;
            }
        }
        if (maxDist > tol) {
            keep[maxIdx] = true;
            _dpRecurse(pts, keep, start, maxIdx, tol);
            _dpRecurse(pts, keep, maxIdx, end, tol);
        }
    }

    function _pointToLineDist(p, a, b) {
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const lenSq = dx * dx + dy * dy;
        if (lenSq === 0) return Math.sqrt((p.x - a.x) ** 2 + (p.y - a.y) ** 2);
        const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lenSq));
        const px = a.x + t * dx;
        const py = a.y + t * dy;
        return Math.sqrt((p.x - px) ** 2 + (p.y - py) ** 2);
    }

    // --- Edit mode ---

    function toggleEdit() {
        _deactivateDraw();
        _deactivateFreehand();
        _deactivateDelete();
        if (typeof SAM !== 'undefined') SAM.deactivate();
        if (typeof Select !== 'undefined') Select.deactivate();

        if (_editActive) {
            _deactivateEdit();
        } else {
            _activateEdit();
        }
    }

    function _activateEdit() {
        Annotations.pushUndo();
        Annotations.getLayer().eachLayer(layer => {
            layer.pm.enable({ allowSelfIntersection: false });
        });

        Annotations.getLayer().eachLayer(layer => {
            layer.on('pm:edit', () => {
                Annotations.triggerSave();
            });
        });

        _editActive = true;
        document.getElementById('btn-edit').classList.add('active');
    }

    function _deactivateEdit() {
        Annotations.getLayer().eachLayer(layer => {
            layer.pm.disable();
        });
        _editActive = false;
        document.getElementById('btn-edit').classList.remove('active');
    }

    // --- Delete mode ---

    function toggleDelete() {
        _deactivateDraw();
        _deactivateFreehand();
        _deactivateEdit();
        if (typeof SAM !== 'undefined') SAM.deactivate();
        if (typeof Select !== 'undefined') Select.deactivate();

        if (_deleteActive) {
            _deactivateDelete();
        } else {
            _activateDelete();
        }
    }

    function _activateDelete() {
        _map.pm.enableGlobalRemovalMode();
        _deleteActive = true;
        document.getElementById('btn-delete').classList.add('active');

        _map.on('pm:remove', (e) => {
            Annotations.pushUndo();
            Annotations.triggerSave();
        });
    }

    function _deactivateDelete() {
        _map.pm.disableGlobalRemovalMode();
        _deleteActive = false;
        document.getElementById('btn-delete').classList.remove('active');
    }

    // --- Common ---

    function deactivateAll() {
        _deactivateDraw();
        _deactivateFreehand();
        _deactivateEdit();
        _deactivateDelete();
    }

    function isActive() {
        return _active || _freehandActive || _editActive || _deleteActive;
    }

    function _randomId() {
        return Math.random().toString(36).substring(2, 10);
    }

    function isEditActive() { return _editActive; }

    return { init, toggleDraw, toggleFreehand, toggleEdit, toggleDelete, deactivateAll, isActive, isEditActive };
})();
