fetch(window.apiUrl('/api/pages'))
  .then(response => {
    if (!response.ok) throw new Error('Seznam akcí se nepodařilo načíst.');
    return response.json();
  })
  .then(pages => {
    const menu = document.getElementById('pageMenu');
    if (!menu) return;

    pages.forEach(page => {
      const item = document.createElement('li');
      const link = document.createElement('a');

      link.className = 'menu-odkaz';
      link.href = window.apiUrl(page.path);
      link.textContent = page.title;

      item.appendChild(link);
      menu.appendChild(item);
    });
  })
  .catch(error => console.error('Chyba při načítání menu:', error));