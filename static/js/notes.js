// Notes module — slide-out panel for image notes and annotation list
const Notes = (() => {
    let _currentAreaId = null;
    let _open = false;

    function init() {
        _createPanel();
    }

    function _createPanel() {
        const panel = document.createElement('div');
        panel.id = 'notes-panel';
        panel.innerHTML = `
            <div id="notes-tab" title="Toggle notes panel">Notes</div>
            <div id="notes-content">
                <div id="notes-image-section">
                    <div class="notes-section-label">Image Note</div>
                    <textarea id="notes-image-textarea" placeholder="Notes about this image..."></textarea>
                </div>
                <div id="notes-annotations-section">
                    <div class="notes-section-label">Annotations</div>
                    <div id="notes-annotation-list"></div>
                </div>
            </div>
        `;
        document.getElementById('map-container').appendChild(panel);
        document.getElementById('notes-tab').addEventListener('click', _toggle);
    }

    function _toggle() {
        _open = !_open;
        document.getElementById('notes-panel').classList.toggle('open', _open);
    }

    async function loadForArea(areaId) {
        _currentAreaId = areaId;

        const resp = await fetch('/api/state');
        const state = await resp.json();
        const note = (state.image_notes && state.image_notes[areaId]) || '';

        const textarea = document.getElementById('notes-image-textarea');
        if (textarea) {
            textarea.value = note;
            textarea.onblur = () => {
                const val = textarea.value.trim();
                fetch('/api/state', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image_notes: { [_currentAreaId]: val } }),
                });
                Sidebar.updateImageNote(_currentAreaId, val.length > 0);
            };
        }

        refreshAnnotations();
    }

    function refreshAnnotations() {
        const list = document.getElementById('notes-annotation-list');
        if (!list) return;

        const fc = Annotations.getFeatureCollection();
        list.innerHTML = '';

        if (!fc.features || fc.features.length === 0) {
            list.innerHTML = '<div class="notes-empty">No annotations</div>';
            return;
        }

        fc.features.forEach(feature => {
            const props = feature.properties;
            const cls = Classes.getByValue(props.class_value);
            const color = cls ? cls.color : '#888';

            const row = document.createElement('div');
            row.className = 'notes-annotation-row';

            const swatch = document.createElement('span');
            swatch.className = 'notes-ann-color';
            swatch.style.background = color;

            const name = document.createElement('span');
            name.className = 'notes-ann-name';
            name.textContent = props.class_name || 'Unknown';

            row.appendChild(swatch);
            row.appendChild(name);

            if (props.note) {
                const noteSpan = document.createElement('span');
                noteSpan.className = 'notes-ann-note';
                noteSpan.textContent = props.note;
                noteSpan.title = props.note;
                row.appendChild(noteSpan);
            }

            row.addEventListener('click', () => {
                Annotations.openPopupForId(props.id);
            });

            list.appendChild(row);
        });
    }

    return { init, loadForArea, refreshAnnotations };
})();
