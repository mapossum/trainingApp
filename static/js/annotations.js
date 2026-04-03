// Annotations module — GeoJSON layer management, auto-save, undo, erase
const Annotations = (() => {
    let _map = null;
    let _layer = null;
    let _currentAreaId = null;
    let _saveTimeout = null;
    let _onChangeCallback = null;
    let _undoStack = [];
    const UNDO_MAX = 5;
    let _fillOpacity = 0.3;

    function init(map) {
        _map = map;
        _layer = L.geoJSON(null, {
            style: _featureStyle,
            onEachFeature: _onEachFeature,
        }).addTo(_map);
    }

    function _featureStyle(feature) {
        const cls = Classes.getByValue(feature.properties.class_value);
        const color = cls ? cls.color : '#ffffff';
        return {
            color: color,
            weight: 2,
            opacity: 0.9,
            fillColor: color,
            fillOpacity: _fillOpacity,
        };
    }

    function _onEachFeature(feature, layer) {
        // Ensure every feature has a unique id
        if (!feature.properties.id) {
            feature.properties.id = Math.random().toString(36).substring(2, 10);
        }
        // Bind tooltip if note exists
        if (feature.properties.note) {
            layer.bindTooltip(feature.properties.note, { sticky: true, className: 'note-tooltip' });
        }
        layer.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            if (typeof Select !== 'undefined' && Select.isActive()) {
                Select.toggleFeature(layer);
                return;
            }
            _showPopup(feature, layer, e.latlng);
        });
    }

    function _showPopup(feature, layer, latlng) {
        const classes = Classes.getAll();
        const currentValue = feature.properties.class_value;
        let options = classes.map(c =>
            `<option value="${c.value}" ${c.value === currentValue ? 'selected' : ''}>${c.name}</option>`
        ).join('');

        const currentNote = feature.properties.note || '';

        const html = `
            <div style="min-width:160px">
                <select id="popup-class" style="width:100%;margin-bottom:6px;padding:2px">
                    ${options}
                </select>
                <textarea id="popup-note" placeholder="Note..." style="width:100%;height:56px;margin-bottom:6px;padding:3px;background:#222;color:#eee;border:1px solid #444;border-radius:3px;resize:vertical;font-size:12px;font-family:inherit">${currentNote}</textarea>
                <button id="popup-delete" style="width:100%;padding:3px;background:#e74c3c;color:white;border:none;cursor:pointer;border-radius:3px">Delete</button>
            </div>
        `;

        L.popup().setLatLng(latlng).setContent(html).openOn(_map);

        // Defer event binding until popup is in DOM
        setTimeout(() => {
            const sel = document.getElementById('popup-class');
            const noteEl = document.getElementById('popup-note');
            const del = document.getElementById('popup-delete');
            if (sel) {
                sel.addEventListener('change', () => {
                    pushUndo();
                    const newValue = parseInt(sel.value);
                    const cls = Classes.getByValue(newValue);
                    feature.properties.class_value = newValue;
                    feature.properties.class_name = cls ? cls.name : '';
                    layer.setStyle(_featureStyle(feature));
                    _map.closePopup();
                    _scheduleSave();
                });
            }
            if (noteEl) {
                noteEl.addEventListener('blur', () => {
                    const newNote = noteEl.value.trim();
                    const oldNote = feature.properties.note || '';
                    if (newNote !== oldNote) {
                        feature.properties.note = newNote || undefined;
                        layer.unbindTooltip();
                        if (newNote) {
                            layer.bindTooltip(newNote, { sticky: true, className: 'note-tooltip' });
                        }
                        _scheduleSave();
                        if (typeof Notes !== 'undefined') Notes.refreshAnnotations();
                    }
                });
            }
            if (del) {
                del.addEventListener('click', () => {
                    pushUndo();
                    _layer.removeLayer(layer);
                    _map.closePopup();
                    _scheduleSave();
                });
            }
        }, 50);
    }

    function openPopupForId(id) {
        _layer.eachLayer(layer => {
            if (layer.feature && layer.feature.properties.id === id) {
                const bounds = layer.getBounds ? layer.getBounds() : null;
                const latlng = bounds ? bounds.getCenter() : layer.getLatLng();
                _showPopup(layer.feature, layer, latlng);
            }
        });
    }

    async function loadForArea(areaId) {
        _currentAreaId = areaId;
        _layer.clearLayers();
        _undoStack = [];
        _updateUndoButton();

        const resp = await fetch(`/api/annotations/${areaId}`);
        const fc = await resp.json();

        if (fc.features && fc.features.length > 0) {
            _layer.addData(fc);
        }
    }

    function addFeature(geojsonFeature) {
        pushUndo();
        _layer.addData(geojsonFeature);
        _scheduleSave();
    }

    function removeLayer(layer) {
        _layer.removeLayer(layer);
    }

    function getLayer() {
        return _layer;
    }

    function getFeatureCollection() {
        const features = [];
        _layer.eachLayer(layer => {
            const geojson = layer.toGeoJSON(15);
            // Preserve custom properties
            if (layer.feature && layer.feature.properties) {
                geojson.properties = { ...layer.feature.properties };
            }
            features.push(geojson);
        });
        return {
            type: "FeatureCollection",
            properties: { area_id: _currentAreaId },
            features: features,
        };
    }

    function _scheduleSave() {
        if (_saveTimeout) clearTimeout(_saveTimeout);
        _saveTimeout = setTimeout(_save, 1000);
        if (_onChangeCallback) _onChangeCallback();
    }

    async function _save() {
        if (!_currentAreaId) return;
        const fc = getFeatureCollection();
        try {
            await fetch(`/api/annotations/${_currentAreaId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fc),
            });
        } catch (err) {
            console.error('Save failed:', err);
            App.toast('Save failed', 'error');
        }
    }

    function triggerSave() {
        _scheduleSave();
    }

    function onChange(callback) {
        _onChangeCallback = callback;
    }

    function setFillOpacity(opacity) {
        _fillOpacity = opacity;
        _layer.eachLayer(layer => {
            if (layer.feature) {
                layer.setStyle({ fillOpacity: opacity });
            }
        });
    }

    function getFillOpacity() {
        return _fillOpacity;
    }

    function setInteractive(interactive) {
        _layer.eachLayer(layer => {
            if (interactive) {
                layer.getElement && layer.getElement() && (layer.getElement().style.pointerEvents = '');
            } else {
                layer.getElement && layer.getElement() && (layer.getElement().style.pointerEvents = 'none');
            }
        });
    }

    function refreshStyles() {
        _layer.eachLayer(layer => {
            if (layer.feature) {
                layer.setStyle(_featureStyle(layer.feature));
            }
        });
    }

    async function dissolveOverlapping() {
        if (!_currentAreaId) return;

        pushUndo();
        // Save current state first
        await _save();

        try {
            const resp = await fetch(`/api/annotations/${_currentAreaId}/dissolve`, {
                method: 'POST',
            });
            const fc = await resp.json();

            // Reload the layer with dissolved features
            _layer.clearLayers();
            if (fc.features && fc.features.length > 0) {
                _layer.addData(fc);
            }
            if (_onChangeCallback) _onChangeCallback();

            App.toast(`Dissolved to ${fc.features.length} polygons`, 'success');
        } catch (err) {
            console.error('Dissolve failed:', err);
            App.toast('Dissolve failed', 'error');
        }
    }

    // --- Erase ---

    async function eraseWithPolygon(geometry) {
        if (!_currentAreaId) return;

        pushUndo();
        await _save();

        try {
            const resp = await fetch(`/api/annotations/${_currentAreaId}/erase`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ geometry: geometry }),
            });
            const fc = await resp.json();

            _layer.clearLayers();
            if (fc.features && fc.features.length > 0) {
                _layer.addData(fc);
            }
            if (_onChangeCallback) _onChangeCallback();

            App.toast('Erased', 'success');
        } catch (err) {
            console.error('Erase failed:', err);
            App.toast('Erase failed', 'error');
        }
    }

    // --- Undo ---

    function pushUndo() {
        const snapshot = getFeatureCollection();
        _undoStack.push(JSON.parse(JSON.stringify(snapshot)));
        if (_undoStack.length > UNDO_MAX) {
            _undoStack.shift();
        }
        _updateUndoButton();
    }

    function undo() {
        if (_undoStack.length === 0) return;

        const snapshot = _undoStack.pop();
        _layer.clearLayers();
        if (snapshot.features && snapshot.features.length > 0) {
            _layer.addData(snapshot);
        }
        _scheduleSave();
        _updateUndoButton();
        App.toast('Undone', 'info');
    }

    function _updateUndoButton() {
        const btn = document.getElementById('btn-undo');
        if (!btn) return;
        const count = _undoStack.length;
        btn.textContent = count > 0 ? `Undo (${count})` : 'Undo';
        btn.style.opacity = count > 0 ? '1' : '0.5';
    }

    function getUndoCount() {
        return _undoStack.length;
    }

    return {
        init, loadForArea, addFeature, removeLayer, getLayer, getFeatureCollection,
        triggerSave, onChange, refreshStyles, setFillOpacity, getFillOpacity,
        setInteractive, dissolveOverlapping, eraseWithPolygon, pushUndo, undo, getUndoCount,
        openPopupForId,
    };
})();
