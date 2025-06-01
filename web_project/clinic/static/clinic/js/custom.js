/* clinic/static/clinic/js/custom.js */

// 1. Добавляем/убираем класс .scrolled для navbar при прокрутке
document.addEventListener('DOMContentLoaded', function () {
  const navbar = document.getElementById('mainNavbar');
  window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  });
});

// 2. Применяем анимацию .fade-in к нужным секциям при загрузке страницы (оставляем)
document.addEventListener('DOMContentLoaded', function () {
  const fadeElements = document.querySelectorAll('.fade-in');
  fadeElements.forEach((el, idx) => {
    el.style.animationDelay = `${idx * 0.2}s`;
    el.classList.add('animate__animated', 'animate__fadeInUp');
  });
});
