// Select module — click polygons to select, then bulk delete or change class
const Select = (() => {
    let _map = null;
    let _active = false;
    let _selectedLayers = new Set();
    let _actionBar = null;

    function init(map) {
        _map = map;
        document.getElementById('btn-select').addEventListener('click', toggle);
        _createActionBar();

        // Clicking the map (not a feature) clears selection
        _map.on('click', () => {
            if (_active && _selectedLayers.size > 0) {
                clearSelection();
            }
        });
    }

    function _createActionBar() {
        _actionBar = document.createElement('div');
        _actionBar.id = 'select-action-bar';
        _actionBar.style.display = 'none';
        _actionBar.innerHTML = `
            <div class="select-action-label">Selected: <span id="select-count">0</span></div>
            <select id="select-class-dropdown" title="Change class of selected">
            </select>
            <button id="select-apply-class" class="select-action-btn select-apply-btn" title="Apply class">Apply</button>
            <button id="select-delete" class="select-action-btn select-delete-btn" title="Delete selected">Delete</button>
            <button id="select-clear" class="select-action-btn select-clear-btn" title="Clear selection">Clear</button>
        `;
        document.getElementById('map-container').appendChild(_actionBar);

        document.getElementById('select-apply-class').addEventListener('click', (e) => {
            e.stopPropagation();
            const val = parseInt(document.getElementById('select-class-dropdown').value);
            if (!isNaN(val)) changeClassSelected(val);
        });
        document.getElementById('select-delete').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSelected();
        });
        document.getElementById('select-clear').addEventListener('click', (e) => {
            e.stopPropagation();
            clearSelection();
        });
    }

    function _populateClassDropdown() {
        const dropdown = document.getElementById('select-class-dropdown');
        if (!dropdown) return;
        const classes = Classes.getAll();
        dropdown.innerHTML = classes.map(c =>
            `<option value="${c.value}">${c.name}</option>`
        ).join('');
    }

    function toggle() {
        if (_active) {
            deactivate();
        } else {
            activate();
        }
    }

    function activate() {
        Drawing.deactivateAll();
        if (typeof SAM !== 'undefined') SAM.deactivate();
        _active = true;
        document.getElementById('btn-select').classList.add('active');
        _map.getContainer().style.cursor = 'pointer';
        _populateClassDropdown();
        App.toast('Select mode: click polygons to select them', 'info');
    }

    function deactivate() {
        clearSelection();
        _active = false;
        document.getElementById('btn-select').classList.remove('active');
        _map.getContainer().style.cursor = '';
        _showActionBar(false);
    }

    function toggleFeature(layer) {
        if (_selectedLayers.has(layer)) {
            _unselectLayer(layer);
        } else {
            _selectLayer(layer);
        }
        _updateActionBar();
    }

    function _selectLayer(layer) {
        _selectedLayers.add(layer);
        layer.setStyle({
            weight: 4,
            dashArray: '6 3',
            fillOpacity: 0.5,
            color: '#ffffff',
        });
        layer.bringToFront();
    }

    function _unselectLayer(layer) {
        _selectedLayers.delete(layer);
        if (layer.feature) {
            const cls = Classes.getByValue(layer.feature.properties.class_value);
            const color = cls ? cls.color : '#ffffff';
            layer.setStyle({
                color: color,
                weight: 2,
                opacity: 0.9,
                fillColor: color,
                fillOpacity: Annotations.getFillOpacity(),
                dashArray: null,
            });
        }
    }

    function clearSelection() {
        for (const layer of _selectedLayers) {
            _unselectLayer(layer);
        }
        _selectedLayers.clear();
        _updateActionBar();
    }

    function deleteSelected() {
        if (_selectedLayers.size === 0) return;
        Annotations.pushUndo();
        for (const layer of _selectedLayers) {
            Annotations.removeLayer(layer);
        }
        const count = _selectedLayers.size;
        _selectedLayers.clear();
        Annotations.triggerSave();
        _updateActionBar();
        App.toast(`Deleted ${count} polygons`, 'success');
    }

    function changeClassSelected(newValue) {
        if (_selectedLayers.size === 0) return;
        Annotations.pushUndo();
        const cls = Classes.getByValue(newValue);
        if (!cls) return;
        for (const layer of _selectedLayers) {
            if (layer.feature) {
                layer.feature.properties.class_value = newValue;
                layer.feature.properties.class_name = cls.name;
            }
            layer.setStyle({
                weight: 4,
                dashArray: '6 3',
                fillOpacity: 0.5,
                color: '#ffffff',
                fillColor: cls.color,
            });
        }
        Annotations.triggerSave();
        App.toast(`Changed ${_selectedLayers.size} polygons to ${cls.name}`, 'success');
    }

    function _updateActionBar() {
        const count = _selectedLayers.size;
        const countEl = document.getElementById('select-count');
        if (countEl) countEl.textContent = count;
        _showActionBar(count > 0);
    }

    function _showActionBar(show) {
        if (_actionBar) {
            _actionBar.style.display = show ? 'flex' : 'none';
        }
    }

    function isActive() { return _active; }

    return { init, toggle, activate, deactivate, toggleFeature, clearSelection, isActive };
})();
