// Model Predict module — runs deep learning model inference on current area
const ModelPredict = (() => {
    let _map = null;
    let _available = false;
    let _models = [];
    let _selectedModel = null;
    let _loading = false;
    let _previewLayer = null;
    let _previewFeatures = [];
    let _actionBar = null;

    async function init(map) {
        _map = map;

        try {
            const resp = await fetch('/api/models');
            const data = await resp.json();
            _models = data.models || [];
            _available = _models.length > 0;
            if (_models.length === 1) {
                _selectedModel = _models[0].name;
            }
        } catch {
            _available = false;
        }

        const btn = document.getElementById('btn-model-predict');
        if (!_available) {
            btn.title = 'No prediction models found in models/ directory';
            btn.style.opacity = '0.5';
            btn.style.pointerEvents = 'none';
        } else {
            btn.title = `Run model prediction on current area (M) — ${_models.map(m => m.name).join(', ')}`;
        }
        btn.addEventListener('click', run);

        // Build model selector if multiple models
        if (_models.length > 1) {
            _buildModelSelector();
        }

        _createActionBar();
    }

    function _buildModelSelector() {
        const toolbar = document.getElementById('tool-buttons');
        const select = document.createElement('select');
        select.id = 'model-selector';
        select.title = 'Select prediction model';
        for (const m of _models) {
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = m.name;
            select.appendChild(opt);
        }
        select.value = _models[0].name;
        _selectedModel = _models[0].name;
        select.addEventListener('change', () => {
            _selectedModel = select.value;
        });
        // Insert after the predict button
        const btn = document.getElementById('btn-model-predict');
        btn.parentNode.insertBefore(select, btn.nextSibling);
    }

    function _createActionBar() {
        _actionBar = document.createElement('div');
        _actionBar.id = 'predict-action-bar';
        _actionBar.style.display = 'none';
        _actionBar.innerHTML = `
            <div class="predict-action-label">Model Preview: <span id="predict-count">0</span> polygons</div>
            <button id="predict-accept" class="predict-action-btn predict-accept-btn" title="Accept and add to annotations (Enter)">Accept</button>
            <button id="predict-discard" class="predict-action-btn predict-discard-btn" title="Discard prediction">Discard</button>
        `;
        document.getElementById('map-container').appendChild(_actionBar);

        document.getElementById('predict-accept').addEventListener('click', (e) => {
            e.stopPropagation();
            _accept();
        });
        document.getElementById('predict-discard').addEventListener('click', (e) => {
            e.stopPropagation();
            _discard();
        });
    }

    function _showActionBar(show) {
        if (_actionBar) {
            _actionBar.style.display = show ? 'flex' : 'none';
        }
    }

    function _accept() {
        if (!_previewLayer || _previewFeatures.length === 0) return;
        Annotations.pushUndo();
        for (const feature of _previewFeatures) {
            Annotations.addFeature(feature);
        }
        App.toast(`Added ${_previewFeatures.length} polygons`, 'success');
        _clearPreview();
    }

    function _discard() {
        _clearPreview();
        App.toast('Prediction discarded', 'info');
    }

    function _clearPreview() {
        if (_previewLayer) {
            _map.removeLayer(_previewLayer);
            _previewLayer = null;
        }
        _previewFeatures = [];
        _showActionBar(false);
        const btn = document.getElementById('btn-model-predict');
        if (btn) btn.classList.remove('active');
    }

    async function run() {
        if (!_available || _loading) return;

        // Discard any existing preview first
        if (_previewLayer) _discard();

        const areaId = MapModule.getCurrentAreaId();
        if (!areaId) {
            App.toast('No area loaded', 'error');
            return;
        }

        if (!_selectedModel) {
            App.toast('Select a model first', 'info');
            return;
        }

        _loading = true;
        const btn = document.getElementById('btn-model-predict');
        btn.classList.add('active');
        _showLoading(true);

        try {
            const resp = await fetch('/api/model-predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    area_id: areaId,
                    model_name: _selectedModel,
                }),
            });
            const data = await resp.json();

            if (data.error) {
                App.toast(data.error, 'error');
                btn.classList.remove('active');
                return;
            }

            if (data.features && data.features.length > 0) {
                _previewFeatures = data.features.map(feature => {
                    const cls = Classes.getByValue(feature.properties.class_value);
                    if (cls) feature.properties.class_name = cls.name;
                    feature.properties.id = Math.random().toString(36).substring(2, 10);
                    return feature;
                });

                // Show as preview layer with dashed style
                _previewLayer = L.geoJSON(_previewFeatures, {
                    style: feature => {
                        const cls = Classes.getByValue(feature.properties.class_value);
                        const color = cls ? cls.color : '#f39c12';
                        return {
                            color: color,
                            weight: 2,
                            dashArray: '6 4',
                            fillColor: color,
                            fillOpacity: 0.15,
                            opacity: 0.8,
                        };
                    },
                }).addTo(_map);

                document.getElementById('predict-count').textContent = _previewFeatures.length;
                _showActionBar(true);
                App.toast(`${_previewFeatures.length} polygons ready — accept or discard`, 'info');
            } else {
                App.toast('Model found no features in this area', 'info');
                btn.classList.remove('active');
            }
        } catch (err) {
            console.error('Model prediction failed:', err);
            App.toast('Model prediction failed: ' + err.message, 'error');
            btn.classList.remove('active');
        } finally {
            _loading = false;
            _showLoading(false);
        }
    }

    function clearPreviewOnAreaChange() {
        if (_previewLayer) _clearPreview();
    }

    function _showLoading(show) {
        let overlay = document.querySelector('.loading-overlay');
        if (show && !overlay) {
            overlay = document.createElement('div');
            overlay.className = 'loading-overlay';
            overlay.innerHTML = '<div class="spinner"></div><div style="color:white;margin-top:12px;">Running model inference...</div>';
            document.getElementById('map-container').appendChild(overlay);
        } else if (!show && overlay) {
            overlay.remove();
        }
    }

    function isAvailable() { return _available; }

    return { init, run, isAvailable, clearPreviewOnAreaChange };
})();
