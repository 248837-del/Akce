window.API_BASE_URL =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? ""
    : "https://akce.onrender.com";
window.apiUrl = path => `${window.API_BASE_URL}${path}`;
