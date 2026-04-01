// Main application module — initialization and orchestration
const App = (() => {
    let _map = null;

    async function init() {
        // Initialize map
        _map = MapModule.init();

        // Fetch config and training areas in parallel
        const [configResp, areasResp, stateResp, sam2StatusResp] = await Promise.all([
            fetch('/api/config'),
            fetch('/api/training-areas'),
            fetch('/api/state'),
            fetch('/api/sam2/status').catch(() => ({ json: () => ({ available: false }) })),
        ]);

        const classes = await configResp.json();
        const areas = await areasResp.json();
        const state = await stateResp.json();

        // Initialize modules
        Classes.init(classes);
        Annotations.init(_map);
        Drawing.init(_map);
        await SAM.init(_map);
        Sidebar.init(areas, state);

        // Track annotation changes for badge updates
        Annotations.onChange(() => {
            const areaId = MapModule.getCurrentAreaId();
            if (areaId) {
                const fc = Annotations.getFeatureCollection();
                Sidebar.updateAnnotationCount(areaId, fc.features.length);
            }
        });

        // Load last viewed area or first area
        if (state.last_viewed && areas.find(a => a.id === state.last_viewed)) {
            Sidebar.goToArea(state.last_viewed);
        } else if (areas.length > 0) {
            Sidebar.goToArea(areas[0].id);
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', _onKeyDown);
    }

    async function loadArea(areaId) {
        // Deactivate all tools
        Drawing.deactivateAll();
        if (SAM.isActive()) SAM.deactivate();

        await MapModule.loadArea(areaId);
        await Annotations.loadForArea(areaId);

        // Save last viewed
        fetch('/api/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ last_viewed: areaId }),
        });
    }

    function _onKeyDown(e) {
        // Ignore if typing in an input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        switch (e.key) {
            case 'ArrowLeft':
                e.preventDefault();
                Sidebar.prev();
                break;
            case 'ArrowRight':
                e.preventDefault();
                Sidebar.next();
                break;
            case 'd':
            case 'D':
                Drawing.toggleDraw();
                break;
            case 'f':
            case 'F':
                Drawing.toggleFreehand();
                break;
            case 'e':
            case 'E':
                Drawing.toggleEdit();
                break;
            case 'x':
            case 'X':
                Drawing.toggleDelete();
                break;
            case 's':
            case 'S':
                SAM.toggle();
                break;
            case 'Enter':
                if (SAM.isActive()) {
                    SAM.acceptCurrent();
                } else if (Drawing.isEditActive()) {
                    Drawing.toggleEdit();
                }
                break;
            case 'Escape':
                Drawing.deactivateAll();
                if (SAM.isActive()) SAM.deactivate();
                break;
            case 'z':
            case 'Z':
                if (SAM.isActive()) {
                    SAM.undoLastPoint();
                }
                break;
            case '1':
            case '2':
            case '3':
            case '4':
            case '5':
            case '6':
            case '7':
            case '8':
            case '9':
                Classes.setActive(parseInt(e.key) - 1);
                break;
        }
    }

    function toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }

    // Start
    document.addEventListener('DOMContentLoaded', init);

    return { loadArea, toast };
})();
