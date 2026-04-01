// Map module — Leaflet map, basemap, image overlay management
const MapModule = (() => {
    let _map = null;
    let _imageOverlay = null;
    let _currentAreaId = null;

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

        // Fit to bounds with padding
        _map.fitBounds(bounds, { padding: [40, 40], maxZoom: 30 });
    }

    return { init, getMap, getCurrentAreaId, loadArea };
})();
