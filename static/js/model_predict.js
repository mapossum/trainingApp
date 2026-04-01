// Model Predict module — runs deep learning model inference on current area
const ModelPredict = (() => {
    let _map = null;
    let _available = false;
    let _models = [];
    let _selectedModel = null;
    let _loading = false;

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

    async function run() {
        if (!_available || _loading) return;

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
                return;
            }

            if (data.features && data.features.length > 0) {
                for (const feature of data.features) {
                    // Map class value to app class if available
                    const cls = Classes.getByValue(feature.properties.class_value);
                    if (cls) {
                        feature.properties.class_name = cls.name;
                    }
                    feature.properties.id = Math.random().toString(36).substring(2, 10);
                    Annotations.addFeature(feature);
                }
                App.toast(`Added ${data.features.length} polygons from model`, 'success');
            } else {
                App.toast('Model found no features in this area', 'info');
            }
        } catch (err) {
            console.error('Model prediction failed:', err);
            App.toast('Model prediction failed: ' + err.message, 'error');
        } finally {
            _loading = false;
            btn.classList.remove('active');
            _showLoading(false);
        }
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

    return { init, run, isAvailable };
})();
