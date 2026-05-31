// movies/static/js/script.js
let lastScrollTop = 0;
const navbar = document.querySelector('.sticky-navbar');

if (!navbar) {
    console.error('Navbar element not found!');
} else {
    // Начальное состояние: навбар виден
    navbar.classList.add('visible');
    navbar.classList.remove('hidden');

    window.addEventListener('scroll', function() {
        let currentScroll = window.pageYOffset || document.documentElement.scrollTop;

        if (currentScroll > lastScrollTop && currentScroll > 100) {
            // Прокрутка вниз — скрываем навбар
            navbar.classList.add('hidden');
            navbar.classList.remove('visible');
        } else if (currentScroll < lastScrollTop) {
            // Прокрутка вверх — показываем навбар
            navbar.classList.add('visible');
            navbar.classList.remove('hidden');
        }

        lastScrollTop = currentScroll <= 0 ? 0 : currentScroll;
    });
}