// SAM2 module — click-to-segment interaction
const SAM = (() => {
    let _map = null;
    let _active = false;
    let _available = false;
    let _points = [];
    let _markers = [];
    let _previewLayer = null;
    let _loading = false;
    let _actionBar = null;

    async function init(map) {
        _map = map;

        // Check if SAM2 is available
        try {
            const resp = await fetch('/api/sam2/status');
            const data = await resp.json();
            _available = data.available;
        } catch {
            _available = false;
        }

        const btn = document.getElementById('btn-sam');
        if (!_available) {
            btn.title = 'SAM2 not available (no model loaded)';
            btn.style.opacity = '0.5';
        }
        btn.addEventListener('click', toggle);

        // Create the SAM2 action bar (hidden until a prediction is made)
        _createActionBar();
    }

    function _createActionBar() {
        _actionBar = document.createElement('div');
        _actionBar.id = 'sam-action-bar';
        _actionBar.style.display = 'none';
        _actionBar.innerHTML = `
            <div class="sam-action-label">SAM2 Preview</div>
            <button id="sam-accept" class="sam-action-btn sam-accept-btn" title="Accept polygon (Enter)">Accept</button>
            <button id="sam-undo" class="sam-action-btn sam-undo-btn" title="Undo last point (Z)">Undo Point</button>
            <button id="sam-clear" class="sam-action-btn sam-clear-btn" title="Clear all (Escape)">Clear</button>
        `;
        document.getElementById('map-container').appendChild(_actionBar);

        document.getElementById('sam-accept').addEventListener('click', (e) => {
            e.stopPropagation();
            _accept();
        });
        document.getElementById('sam-undo').addEventListener('click', (e) => {
            e.stopPropagation();
            undoLastPoint();
        });
        document.getElementById('sam-clear').addEventListener('click', (e) => {
            e.stopPropagation();
            _clearAll();
        });
    }

    function _showActionBar(show) {
        if (_actionBar) {
            _actionBar.style.display = show ? 'flex' : 'none';
        }
    }

    function toggle() {
        if (!_available) {
            App.toast('SAM2 not available. Place a checkpoint in sam2_weights/', 'error');
            return;
        }
        if (_active) {
            deactivate();
        } else {
            activate();
        }
    }

    function activate() {
        Drawing.deactivateAll();
        _active = true;
        _points = [];
        _clearMarkers();
        _clearPreview();

        Annotations.setInteractive(false);
        document.getElementById('btn-sam').classList.add('sam-active');
        _map.getContainer().style.cursor = 'crosshair';

        App.toast('SAM2 active: Left-click to add point, right-click for background. Click Accept or press Enter to keep.', 'info');

        _map.on('click', _onLeftClick);
        _map.on('contextmenu', _onRightClick);
    }

    function deactivate() {
        _active = false;
        _points = [];
        _clearMarkers();
        _clearPreview();
        _showActionBar(false);

        Annotations.setInteractive(true);
        document.getElementById('btn-sam').classList.remove('sam-active');
        _map.getContainer().style.cursor = '';

        _map.off('click', _onLeftClick);
        _map.off('contextmenu', _onRightClick);
    }

    function _onLeftClick(e) {
        if (!_active || _loading) return;
        _addPoint(e.latlng, 1);  // foreground
        _predict();
    }

    function _onRightClick(e) {
        if (!_active || _loading) return;
        L.DomEvent.preventDefault(e);
        _addPoint(e.latlng, 0);  // background
        _predict();
    }

    function _addPoint(latlng, label) {
        _points.push({ lng: latlng.lng, lat: latlng.lat, label: label });

        const color = label === 1 ? '#2ecc71' : '#e74c3c';
        const marker = L.circleMarker(latlng, {
            radius: 6,
            color: color,
            fillColor: color,
            fillOpacity: 0.8,
            weight: 2,
        }).addTo(_map);
        _markers.push(marker);
    }

    async function _predict() {
        const areaId = MapModule.getCurrentAreaId();
        if (!areaId || _points.length === 0) return;

        _loading = true;
        _showLoading(true);

        try {
            const resp = await fetch('/api/sam2/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ area_id: areaId, points: _points }),
            });
            const data = await resp.json();

            _clearPreview();

            if (data.polygon) {
                const cls = Classes.getActive();
                _previewLayer = L.geoJSON(data.polygon, {
                    style: {
                        color: '#8e44ad',
                        weight: 3,
                        dashArray: '6 4',
                        fillColor: '#8e44ad',
                        fillOpacity: 0.25,
                        className: 'sam-preview',
                    },
                }).addTo(_map);

                // Show action bar
                _showActionBar(true);
            } else if (data.error) {
                App.toast(data.error, 'info');
            }
        } catch (err) {
            console.error('SAM2 prediction failed:', err);
            App.toast('SAM2 prediction failed', 'error');
        } finally {
            _loading = false;
            _showLoading(false);
        }
    }

    function _accept() {
        if (!_previewLayer) return;

        if (Classes.isEraseActive()) {
            // Erase mode: use SAM prediction to clip existing annotations
            _previewLayer.eachLayer(layer => {
                const geojson = layer.toGeoJSON(15);
                Annotations.eraseWithPolygon(geojson.geometry);
            });
            App.toast('Erased with SAM polygon', 'success');
        } else {
            const cls = Classes.getActive();
            _previewLayer.eachLayer(layer => {
                const geojson = layer.toGeoJSON(15);
                const feature = {
                    type: "Feature",
                    geometry: geojson.geometry,
                    properties: {
                        class_name: cls.name,
                        class_value: cls.value,
                        source: "sam2",
                        id: Math.random().toString(36).substring(2, 10),
                    },
                };
                Annotations.addFeature(feature);
            });
            App.toast('Polygon accepted', 'success');
        }
        _clearPreview();
        _clearMarkers();
        _points = [];
        _showActionBar(false);
    }

    function acceptCurrent() {
        _accept();
    }

    function _clearAll() {
        _clearPreview();
        _clearMarkers();
        _points = [];
        _showActionBar(false);
    }

    function undoLastPoint() {
        if (_points.length === 0) return;
        _points.pop();
        const marker = _markers.pop();
        if (marker) _map.removeLayer(marker);
        if (_points.length > 0) {
            _predict();
        } else {
            _clearPreview();
            _showActionBar(false);
        }
    }

    function _clearMarkers() {
        _markers.forEach(m => _map.removeLayer(m));
        _markers = [];
    }

    function _clearPreview() {
        if (_previewLayer) {
            _map.removeLayer(_previewLayer);
            _previewLayer = null;
        }
    }

    function _showLoading(show) {
        let overlay = document.querySelector('.loading-overlay');
        if (show && !overlay) {
            overlay = document.createElement('div');
            overlay.className = 'loading-overlay';
            overlay.innerHTML = '<div class="spinner"></div>';
            document.getElementById('map-container').appendChild(overlay);
        } else if (!show && overlay) {
            overlay.remove();
        }
    }

    function isActive() { return _active; }

    return { init, toggle, activate, deactivate, acceptCurrent, undoLastPoint, isActive };
})();
