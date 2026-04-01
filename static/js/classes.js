// Class selector module — manages annotation class selection
const Classes = (() => {
    let _classes = [];
    let _activeIndex = 0;

    function init(classes) {
        _classes = classes;
        _activeIndex = 0;
        _render();
    }

    function _render() {
        const container = document.getElementById('class-selector');
        container.innerHTML = '';
        _classes.forEach((cls, i) => {
            const btn = document.createElement('button');
            btn.className = 'class-btn' + (i === _activeIndex ? ' active' : '');
            btn.textContent = cls.name;
            btn.style.backgroundColor = cls.color;
            btn.title = `${cls.name} (${i + 1})`;
            btn.addEventListener('click', () => setActive(i));
            container.appendChild(btn);
        });
    }

    function setActive(index) {
        if (index >= 0 && index < _classes.length) {
            _activeIndex = index;
            _render();
        }
    }

    function getActive() {
        return _classes[_activeIndex] || null;
    }

    function getAll() {
        return _classes;
    }

    function getByValue(value) {
        return _classes.find(c => c.value === value) || null;
    }

    return { init, setActive, getActive, getAll, getByValue };
})();
