// Dataset config module — band assignment, stretch controls
const DatasetConfig = (() => {
    let _config = null;
    let _collapsed = true;
    let _onChangeCallback = null;

    async function init() {
        const resp = await fetch('/api/dataset-config');
        _config = await resp.json();
        _render();
        _bindEvents();
    }

    function onChange(cb) {
        _onChangeCallback = cb;
    }

    function _render() {
        const panel = document.getElementById('dataset-config-panel');
        if (!panel || !_config) return;

        const bandCount = _config.band_count;
        const bandNames = _config.band_names || [];
        const displayBands = _config.display_bands || [1, 2, 3];
        const stretch = _config.stretch || {};

        // Build band options HTML
        const bandOptions = (selected) => {
            let html = '';
            for (let i = 1; i <= bandCount; i++) {
                const name = bandNames[i - 1] || `Band ${i}`;
                const sel = i === selected ? ' selected' : '';
                html += `<option value="${i}"${sel}>${i}: ${name}</option>`;
            }
            return html;
        };

        const channels = ['R', 'G', 'B'];
        const channelColors = ['#e74c3c', '#27ae60', '#2980b9'];

        let bandsHTML = '<div class="dc-band-selectors">';
        channels.forEach((ch, idx) => {
            const val = displayBands[idx] || 1;
            bandsHTML += `
                <div class="dc-band-row">
                    <span class="dc-channel-label" style="color:${channelColors[idx]}">${ch}</span>
                    <select class="dc-band-select" data-channel="${idx}">
                        ${bandOptions(val)}
                    </select>
                </div>`;
        });
        bandsHTML += '</div>';

        // Stretch controls
        const methods = [
            { value: 'none', label: 'None (uint8)' },
            { value: 'clip255', label: 'Clip 0-255' },
            { value: 'percentile', label: 'Percentile' },
            { value: 'minmax', label: 'Min / Max' },
            { value: 'stddev', label: 'Std Dev' },
        ];

        let stretchHTML = `
            <div class="dc-stretch-row">
                <label>Stretch</label>
                <select id="dc-stretch-method">
                    ${methods.map(m =>
                        `<option value="${m.value}"${m.value === stretch.method ? ' selected' : ''}>${m.label}</option>`
                    ).join('')}
                </select>
            </div>`;

        // Percentile controls (only shown for percentile method)
        const showPercentile = stretch.method === 'percentile';
        stretchHTML += `
            <div class="dc-percentile-row" style="display:${showPercentile ? 'flex' : 'none'}">
                <label>Range</label>
                <input type="number" id="dc-pmin" value="${stretch.percentile_min || 2}" min="0" max="49" step="1" title="Lower percentile" />
                <span class="dc-pct-sep">-</span>
                <input type="number" id="dc-pmax" value="${stretch.percentile_max || 98}" min="51" max="100" step="1" title="Upper percentile" />
                <span class="dc-pct-unit">%</span>
            </div>`;

        // Band min/max display
        const bandMins = stretch.band_mins || [];
        const bandMaxs = stretch.band_maxs || [];
        stretchHTML += '<div class="dc-band-ranges">';
        channels.forEach((ch, idx) => {
            const bMin = bandMins[idx] != null ? bandMins[idx].toFixed(1) : '?';
            const bMax = bandMaxs[idx] != null ? bandMaxs[idx].toFixed(1) : '?';
            stretchHTML += `
                <div class="dc-range-row">
                    <span class="dc-channel-label" style="color:${channelColors[idx]}">${ch}</span>
                    <span class="dc-range-value">${bMin} - ${bMax}</span>
                </div>`;
        });
        stretchHTML += '</div>';

        panel.innerHTML = `
            <div class="dc-header" id="dc-toggle">
                <span class="dc-toggle-icon">${_collapsed ? '\u25B6' : '\u25BC'}</span>
                <span>Band / Stretch</span>
                <span class="dc-band-summary">${_collapsed ? _getSummary() : ''}</span>
            </div>
            <div class="dc-body" style="display:${_collapsed ? 'none' : 'block'}">
                <div class="dc-section-label">Display Bands</div>
                ${bandsHTML}
                <div class="dc-section-label">Stretch</div>
                ${stretchHTML}
                <div class="dc-actions">
                    <button id="dc-apply" class="dc-btn dc-apply-btn">Apply</button>
                    <button id="dc-redetect" class="dc-btn dc-redetect-btn">Re-detect</button>
                </div>
            </div>`;

        _bindEvents();
    }

    function _getSummary() {
        if (!_config) return '';
        const db = _config.display_bands || [];
        const names = _config.band_names || [];
        const parts = db.map(b => names[b - 1] || `B${b}`);
        return parts.join(', ');
    }

    function _bindEvents() {
        const toggle = document.getElementById('dc-toggle');
        if (toggle) {
            toggle.addEventListener('click', () => {
                _collapsed = !_collapsed;
                _render();
            });
        }

        const applyBtn = document.getElementById('dc-apply');
        if (applyBtn) {
            applyBtn.addEventListener('click', _applyChanges);
        }

        const redetectBtn = document.getElementById('dc-redetect');
        if (redetectBtn) {
            redetectBtn.addEventListener('click', _redetect);
        }

        const stretchMethod = document.getElementById('dc-stretch-method');
        if (stretchMethod) {
            stretchMethod.addEventListener('change', () => {
                const pctRow = document.querySelector('.dc-percentile-row');
                if (pctRow) {
                    pctRow.style.display = stretchMethod.value === 'percentile' ? 'flex' : 'none';
                }
            });
        }
    }

    async function _applyChanges() {
        const selects = document.querySelectorAll('.dc-band-select');
        const displayBands = Array.from(selects).map(s => parseInt(s.value));

        const method = document.getElementById('dc-stretch-method').value;
        const pmin = parseInt(document.getElementById('dc-pmin').value) || 2;
        const pmax = parseInt(document.getElementById('dc-pmax').value) || 98;

        const update = {
            display_bands: displayBands,
            stretch: {
                method: method,
                percentile_min: pmin,
                percentile_max: pmax,
            },
        };

        const applyBtn = document.getElementById('dc-apply');
        applyBtn.textContent = 'Applying...';
        applyBtn.disabled = true;

        try {
            const resp = await fetch('/api/dataset-config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(update),
            });
            _config = await resp.json();
            _render();
            App.toast('Display settings updated', 'success');
            if (_onChangeCallback) _onChangeCallback();
        } catch (err) {
            App.toast('Failed to update settings', 'error');
        } finally {
            const btn = document.getElementById('dc-apply');
            if (btn) {
                btn.textContent = 'Apply';
                btn.disabled = false;
            }
        }
    }

    async function _redetect() {
        const btn = document.getElementById('dc-redetect');
        btn.textContent = 'Detecting...';
        btn.disabled = true;

        try {
            const resp = await fetch('/api/dataset-config/redetect', { method: 'POST' });
            _config = await resp.json();
            _render();
            App.toast('Dataset re-detected', 'success');
            if (_onChangeCallback) _onChangeCallback();
        } catch (err) {
            App.toast('Re-detection failed', 'error');
        } finally {
            const b = document.getElementById('dc-redetect');
            if (b) {
                b.textContent = 'Re-detect';
                b.disabled = false;
            }
        }
    }

    return { init, onChange };
})();
