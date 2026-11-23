(() => {
  const tabulka = document.querySelector(".checklist");
  if (!tabulka || !tabulka.tFoot || !tabulka.tHead) {
    throw new Error("QR platbu nelze připojit k tabulce účastníků.");
  }
  const rozlozeni = tabulka.closest(".rozlozeni");
  if (!rozlozeni) {
    throw new Error("Tabulka účastníků není uvnitř rozložení akce.");
  }

  const ucastnici = Array.from(tabulka.tHead.rows[0].cells)
    .slice(3)
    .map(bunka => bunka.textContent.trim());
  const bunkySouctu = Array.from(tabulka.tFoot.rows[0].cells).slice(3);
  if (bunkySouctu.length !== ucastnici.length) {
    throw new Error("Součty účastníků neodpovídají záhlaví tabulky.");
  }

  const nadpisAkce = document.querySelector("h1");
  if (!nadpisAkce) {
    throw new Error("Na stránce chybí název akce.");
  }
  const nazevAkce = nadpisAkce.textContent.trim().replace(/\s*-\s*$/, "");
  const ucetPlatce = document.body.dataset.account || "";
  const platceNakupu = document.body.dataset.payer;
  const obal = document.createElement("section");
  obal.className = "qr-platba";

  const nadpis = document.createElement("h2");
  nadpis.textContent = platceNakupu
    ? `QR platba pro plátce ${platceNakupu}`
    : "QR platba";
  const informaceUctu = document.createElement("p");
  informaceUctu.setAttribute("role", "status");
  informaceUctu.textContent = ucetPlatce
    ? `Platby budou odeslány na účet plátce${platceNakupu ? ` ${platceNakupu}` : ""}.`
    : "Účet plátce nebyl při vytváření akce zadán; QR platby nejsou dostupné.";

  obal.append(nadpis, informaceUctu);
  rozlozeni.append(obal);

  const qrUrl = new WeakMap();
  const requestTokens = new WeakMap();
  const tlacitka = [];

  function smazQr(bunka) {
    requestTokens.set(bunka, (requestTokens.get(bunka) || 0) + 1);
    const predchoziUrl = qrUrl.get(bunka);
    if (predchoziUrl) {
      URL.revokeObjectURL(predchoziUrl);
      qrUrl.delete(bunka);
    }
    bunka.querySelector(".qr-vysledek").replaceChildren();
    const tlacitko = bunka.querySelector("button");
    if (tlacitko) {
      tlacitko.textContent = "QR";
    }
  }

  bunkySouctu.forEach((bunka, index) => {
    const tlacitko = document.createElement("button");
    tlacitko.type = "button";
    tlacitko.textContent = "QR";
    tlacitko.disabled = true;

    const vysledek = document.createElement("div");
    vysledek.className = "qr-vysledek";
    vysledek.setAttribute("role", "status");
    bunka.append(tlacitko, vysledek);
    tlacitka.push(tlacitko);

    tlacitko.addEventListener("click", async () => {
      if (qrUrl.has(bunka)) {
        const obrazek = vysledek.querySelector("img");
        if (obrazek) {
          obrazek.hidden = !obrazek.hidden;
          obrazek.style.display = obrazek.hidden ? "none" : "";
          tlacitko.textContent = obrazek.hidden ? "Zobrazit QR" : "Skrýt QR";
        }
        return;
      }

      const castkaHalere = Number(bunka.dataset.totalHalere);
      const reference = `${nazevAkce} - ${ucastnici[index]}`;
      if (reference.length > 60) {
        vysledek.textContent = "Název akce a účastníka je příliš dlouhý pro zprávu QR platby.";
        return;
      }

      smazQr(bunka);
      const requestToken = requestTokens.get(bunka);
      tlacitko.disabled = true;
      vysledek.textContent = "Generuji QR kód…";
      try {
        const response = await fetch(window.apiUrl("/api/qr"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            account: ucetPlatce,
            amount_halere: castkaHalere,
            reference,
          }),
        });

        if (requestTokens.get(bunka) !== requestToken) {
          return;
        }
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || "QR kód se nepodařilo vytvořit.");
        }

        if (!(response.headers.get("Content-Type") || "").includes("image/svg+xml")) {
          throw new Error("Server nevrátil platný obrázek QR kódu.");
        }

        const blob = await response.blob();
        if (requestTokens.get(bunka) !== requestToken) {
          return;
        }
        const imageUrl = URL.createObjectURL(blob);
        qrUrl.set(bunka, imageUrl);
        const image = document.createElement("img");
        image.src = imageUrl;
        image.alt = `QR platba pro ${ucastnici[index]}, ${castkaHalere / 100} Kč`;
        vysledek.replaceChildren(image);
        tlacitko.textContent = "Skrýt QR";
      } catch (error) {
        if (requestTokens.get(bunka) === requestToken) {
          vysledek.textContent = error.message;
        }
      } finally {
        aktualizujTlacitka();
      }
    });
  });

  function aktualizujTlacitka() {
    bunkySouctu.forEach((bunka, index) => {
      const castkaHalere = Number(bunka.dataset.totalHalere);
      tlacitka[index].disabled =
        !ucetPlatce || !Number.isSafeInteger(castkaHalere) || castkaHalere <= 0;
    });
  }

  function zneplatniQr() {
    bunkySouctu.forEach(smazQr);
    aktualizujTlacitka();
  }

  tabulka.addEventListener("input", zneplatniQr);
  tabulka.addEventListener("totalsupdated", aktualizujTlacitka);
  aktualizujTlacitka();
})();
