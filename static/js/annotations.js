// Annotations module — GeoJSON layer management and auto-save
const Annotations = (() => {
    let _map = null;
    let _layer = null;
    let _currentAreaId = null;
    let _saveTimeout = null;
    let _onChangeCallback = null;

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
            fillOpacity: 0.3,
        };
    }

    function _onEachFeature(feature, layer) {
        layer.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            _showPopup(feature, layer, e.latlng);
        });
    }

    function _showPopup(feature, layer, latlng) {
        const classes = Classes.getAll();
        const currentValue = feature.properties.class_value;
        let options = classes.map(c =>
            `<option value="${c.value}" ${c.value === currentValue ? 'selected' : ''}>${c.name}</option>`
        ).join('');

        const html = `
            <div style="min-width:120px">
                <select id="popup-class" style="width:100%;margin-bottom:6px;padding:2px">
                    ${options}
                </select>
                <button id="popup-delete" style="width:100%;padding:3px;background:#e74c3c;color:white;border:none;cursor:pointer;border-radius:3px">Delete</button>
            </div>
        `;

        const popup = L.popup().setLatLng(latlng).setContent(html).openOn(_map);

        // Defer event binding until popup is in DOM
        setTimeout(() => {
            const sel = document.getElementById('popup-class');
            const del = document.getElementById('popup-delete');
            if (sel) {
                sel.addEventListener('change', () => {
                    const newValue = parseInt(sel.value);
                    const cls = Classes.getByValue(newValue);
                    feature.properties.class_value = newValue;
                    feature.properties.class_name = cls ? cls.name : '';
                    layer.setStyle(_featureStyle(feature));
                    _map.closePopup();
                    _scheduleSave();
                });
            }
            if (del) {
                del.addEventListener('click', () => {
                    _layer.removeLayer(layer);
                    _map.closePopup();
                    _scheduleSave();
                });
            }
        }, 50);
    }

    async function loadForArea(areaId) {
        _currentAreaId = areaId;
        _layer.clearLayers();

        const resp = await fetch(`/api/annotations/${areaId}`);
        const fc = await resp.json();

        if (fc.features && fc.features.length > 0) {
            _layer.addData(fc);
        }
    }

    function addFeature(geojsonFeature) {
        _layer.addData(geojsonFeature);
        _scheduleSave();
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

    function refreshStyles() {
        _layer.eachLayer(layer => {
            if (layer.feature) {
                layer.setStyle(_featureStyle(layer.feature));
            }
        });
    }

    return { init, loadForArea, addFeature, getLayer, getFeatureCollection, triggerSave, onChange, refreshStyles };
})();
