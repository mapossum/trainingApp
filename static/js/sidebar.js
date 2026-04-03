// Sidebar module — training area list, sorting, navigation
const Sidebar = (() => {
    let _areas = [];
    let _sortedAreas = [];
    let _currentIndex = -1;
    let _sortBy = 'ortho_name';
    let _imageNotes = {};

    function init(areas, state) {
        _areas = areas;
        _sortBy = (state && state.sort_by) || 'ortho_name';
        _imageNotes = (state && state.image_notes) || {};

        // Set initial sort button state
        document.getElementById('sort-name').classList.toggle('active', _sortBy === 'ortho_name');
        document.getElementById('sort-oid').classList.toggle('active', _sortBy === 'oid');

        document.getElementById('sort-name').addEventListener('click', () => _setSort('ortho_name'));
        document.getElementById('sort-oid').addEventListener('click', () => _setSort('oid'));
        document.getElementById('btn-prev').addEventListener('click', prev);
        document.getElementById('btn-next').addEventListener('click', next);
        document.getElementById('btn-export').addEventListener('click', _exportCurrent);
        document.getElementById('btn-export-complete').addEventListener('click', _exportComplete);
        document.getElementById('btn-export-all').addEventListener('click', _exportAll);
        document.getElementById('chk-complete').addEventListener('change', _toggleComplete);
        document.getElementById('btn-share').addEventListener('click', () => App.shareCurrentArea());

        _sort();
        _render();
    }

    function _setSort(sortBy) {
        _sortBy = sortBy;
        document.getElementById('sort-name').classList.toggle('active', _sortBy === 'ortho_name');
        document.getElementById('sort-oid').classList.toggle('active', _sortBy === 'oid');
        _sort();
        _render();
        // Save sort preference
        fetch('/api/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sort_by: _sortBy }),
        });
    }

    function _sort() {
        _sortedAreas = [..._areas];
        if (_sortBy === 'oid') {
            _sortedAreas.sort((a, b) => a.oid - b.oid || a.ortho_name.localeCompare(b.ortho_name));
        } else {
            _sortedAreas.sort((a, b) => a.ortho_name.localeCompare(b.ortho_name) || a.oid - b.oid);
        }
    }

    function _render() {
        const list = document.getElementById('area-list');
        list.innerHTML = '';

        _sortedAreas.forEach((area, idx) => {
            const div = document.createElement('div');
            div.className = 'area-item' + (idx === _currentIndex ? ' active' : '');
            div.dataset.index = idx;

            const oidSpan = document.createElement('span');
            oidSpan.className = 'oid';
            oidSpan.textContent = area.oid;

            const nameSpan = document.createElement('span');
            nameSpan.className = 'name';
            nameSpan.textContent = area.ortho_name;
            nameSpan.title = area.id;

            const badge = document.createElement('span');
            badge.className = 'badge' + (area.annotation_count > 0 ? ' has-annotations' : '');
            badge.textContent = area.annotation_count || '0';

            div.appendChild(oidSpan);
            div.appendChild(nameSpan);
            div.appendChild(badge);

            if (_imageNotes[area.id]) {
                const dot = document.createElement('span');
                dot.className = 'note-dot';
                dot.title = 'Has image note';
                div.appendChild(dot);
            }

            if (area.complete) {
                const check = document.createElement('span');
                check.className = 'complete-icon';
                check.textContent = '\u2713';
                div.appendChild(check);
            }

            div.addEventListener('click', () => _goToIndex(idx));
            list.appendChild(div);
        });
    }

    function _goToIndex(idx) {
        if (idx < 0 || idx >= _sortedAreas.length) return;
        _currentIndex = idx;
        const area = _sortedAreas[idx];
        _render();
        _scrollToActive();
        _updateCompleteCheckbox(area);
        App.loadArea(area.id);
    }

    function _scrollToActive() {
        const active = document.querySelector('.area-item.active');
        if (active) {
            active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }

    function prev() {
        if (_currentIndex > 0) {
            _goToIndex(_currentIndex - 1);
        }
    }

    function next() {
        if (_currentIndex < _sortedAreas.length - 1) {
            _goToIndex(_currentIndex + 1);
        }
    }

    function goToArea(areaId) {
        const idx = _sortedAreas.findIndex(a => a.id === areaId);
        if (idx >= 0) {
            _goToIndex(idx);
        }
    }

    function _updateCompleteCheckbox(area) {
        document.getElementById('chk-complete').checked = area.complete || false;
    }

    function _toggleComplete() {
        if (_currentIndex < 0) return;
        const area = _sortedAreas[_currentIndex];
        area.complete = document.getElementById('chk-complete').checked;
        fetch('/api/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ complete: { [area.id]: area.complete } }),
        });
        _render();
    }

    async function _exportCurrent() {
        if (_currentIndex < 0) return;
        const area = _sortedAreas[_currentIndex];
        try {
            const resp = await fetch(`/api/export/${area.id}`, { method: 'POST' });
            const data = await resp.json();
            if (data.error) {
                App.toast(data.error, 'error');
            } else {
                App.toast(`Exported ${area.id}`, 'success');
            }
        } catch (err) {
            App.toast('Export failed', 'error');
        }
    }

    async function _exportComplete() {
        try {
            const resp = await fetch('/api/export/complete', { method: 'POST' });
            const data = await resp.json();
            if (data.count === 0) {
                App.toast('No complete areas to export', 'info');
            } else {
                App.toast(`Exported ${data.count} complete areas`, 'success');
            }
        } catch (err) {
            App.toast('Export complete failed', 'error');
        }
    }

    async function _exportAll() {
        try {
            const resp = await fetch('/api/export/all', { method: 'POST' });
            const data = await resp.json();
            App.toast(`Exported ${data.count} areas`, 'success');
        } catch (err) {
            App.toast('Export all failed', 'error');
        }
    }

    function updateAnnotationCount(areaId, count) {
        const area = _areas.find(a => a.id === areaId);
        if (area) {
            area.annotation_count = count;
            // Also update in sorted list
            const sorted = _sortedAreas.find(a => a.id === areaId);
            if (sorted) sorted.annotation_count = count;
            _render();
        }
    }

    function getCurrentArea() {
        if (_currentIndex >= 0 && _currentIndex < _sortedAreas.length) {
            return _sortedAreas[_currentIndex];
        }
        return null;
    }

    function updateImageNote(areaId, hasNote) {
        if (hasNote) {
            _imageNotes[areaId] = true;
        } else {
            delete _imageNotes[areaId];
        }
        _render();
    }

    return { init, prev, next, goToArea, updateAnnotationCount, getCurrentArea, updateImageNote };
})();
