// Map module — Leaflet map, basemap, image overlay management
const MapModule = (() => {
    let _map = null;
    let _imageOverlay = null;
    let _currentAreaId = null;
    let _firstLoad = true;

    function init() {
        _map = L.map('map', {
            center: [17.76, -64.61],
            zoom: 18,
            zoomSnap: 0.25,
            zoomDelta: 0.5,
            maxZoom: 30,
        });

        // Esri World Imagery basemap (free, no API key)
        L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {
                attribution: 'Tiles &copy; Esri',
                maxZoom: 30,
                maxNativeZoom: 19,
            }
        ).addTo(_map);

        // Add Fit button as a Leaflet control below zoom
        const FitControl = L.Control.extend({
            options: { position: 'topleft' },
            onAdd() {
                const btn = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                btn.innerHTML = '<a id="btn-fit" href="#" title="Fit image to window (W)" style="line-height:26px;width:26px;text-decoration:none;text-align:center;display:flex;align-items:center;justify-content:center;"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#333" stroke-width="1.5"><rect x="1" y="1" width="12" height="12" rx="1"/><polyline points="1,5 1,1 5,1"/><polyline points="9,1 13,1 13,5"/><polyline points="13,9 13,13 9,13"/><polyline points="5,13 1,13 1,9"/></svg></a>';
                L.DomEvent.disableClickPropagation(btn);
                btn.querySelector('a').addEventListener('click', (e) => {
                    e.preventDefault();
                    fitToImage();
                });
                return btn;
            },
        });
        new FitControl().addTo(_map);

        return _map;
    }

    function getMap() {
        return _map;
    }

    function getCurrentAreaId() {
        return _currentAreaId;
    }

    async function loadArea(areaId) {
        _currentAreaId = areaId;

        // Remove previous overlay
        if (_imageOverlay) {
            _map.removeLayer(_imageOverlay);
            _imageOverlay = null;
        }

        // Fetch bounds
        const resp = await fetch(`/api/tiff/${areaId}/bounds`);
        const data = await resp.json();
        const bounds = L.latLngBounds(data.bounds);

        // Add image overlay
        _imageOverlay = L.imageOverlay(`/api/tiff/${areaId}/image.png`, bounds, {
            opacity: 1,
            interactive: false,
        }).addTo(_map);

        // Always fit on first load; otherwise only if image is off-screen
        if (_firstLoad || !_map.getBounds().intersects(bounds)) {
            _map.fitBounds(bounds, { padding: [40, 40], maxZoom: 30 });
            _firstLoad = false;
        }
    }

    function fitToImage() {
        if (_imageOverlay) {
            _map.fitBounds(_imageOverlay.getBounds(), { padding: [40, 40], maxZoom: 30 });
        }
    }

    async function reloadArea(areaId) {
        // Reload the image overlay with a cache-busting param
        if (_imageOverlay) {
            _map.removeLayer(_imageOverlay);
            _imageOverlay = null;
        }

        const resp = await fetch(`/api/tiff/${areaId}/bounds`);
        const data = await resp.json();
        const bounds = L.latLngBounds(data.bounds);

        const cacheBust = Date.now();
        _imageOverlay = L.imageOverlay(
            `/api/tiff/${areaId}/image.png?t=${cacheBust}`, bounds, {
            opacity: 1,
            interactive: false,
        }).addTo(_map);
    }

    return { init, getMap, getCurrentAreaId, loadArea, reloadArea, fitToImage };
})();
