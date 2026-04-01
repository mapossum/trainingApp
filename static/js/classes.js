// Class selector module — manages annotation class selection
const Classes = (() => {
    let _classes = [];
    let _activeIndex = 0;
    let _eraseActive = false;

    function init(classes) {
        _classes = classes;
        _activeIndex = 0;
        _eraseActive = false;
        _render();
    }

    function _render() {
        const container = document.getElementById('class-selector');
        container.innerHTML = '';
        _classes.forEach((cls, i) => {
            const btn = document.createElement('button');
            btn.className = 'class-btn' + (i === _activeIndex && !_eraseActive ? ' active' : '');
            btn.textContent = cls.name;
            btn.style.backgroundColor = cls.color;
            btn.title = `${cls.name} (${i + 1})`;
            btn.addEventListener('click', () => setActive(i));
            container.appendChild(btn);
        });

        // Erase button
        const eraseBtn = document.createElement('button');
        eraseBtn.className = 'class-btn erase-btn' + (_eraseActive ? ' active' : '');
        eraseBtn.textContent = 'Erase';
        eraseBtn.title = 'Erase mode (0)';
        eraseBtn.addEventListener('click', () => setErase());
        container.appendChild(eraseBtn);
    }

    function setActive(index) {
        if (index >= 0 && index < _classes.length) {
            _activeIndex = index;
            _eraseActive = false;
            _render();
        }
    }

    function setErase() {
        _eraseActive = true;
        _render();
    }

    function isEraseActive() {
        return _eraseActive;
    }

    function getActive() {
        if (_eraseActive) {
            return { name: "Erase", value: -1, color: "#ff0000" };
        }
        return _classes[_activeIndex] || null;
    }

    function getAll() {
        return _classes;
    }

    function getByValue(value) {
        return _classes.find(c => c.value === value) || null;
    }

    return { init, setActive, setErase, isEraseActive, getActive, getAll, getByValue };
})();
