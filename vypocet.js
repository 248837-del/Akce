function rozdelCenuHalere(cenaHalere, pocty) {
  if (!Number.isSafeInteger(cenaHalere) || cenaHalere < 0) {
    throw new TypeError("Cena musí být nezáporný počet haléřů.");
  }
  if (!Array.isArray(pocty) || !pocty.every(pocet => Number.isSafeInteger(pocet) && pocet >= 0)) {
    throw new TypeError("Počty musí být nezáporná celá čísla.");
  }

  const soucetPoctu = pocty.reduce((soucet, pocet) => soucet + pocet, 0);
  if (!Number.isSafeInteger(soucetPoctu)) {
    throw new TypeError("Součet počtů je příliš velký.");
  }
  if (soucetPoctu === 0) {
    return pocty.map(() => 0);
  }

  const podily = pocty.map((pocet, index) => {
    const presnyPodil = cenaHalere * pocet / soucetPoctu;
    const halere = Math.floor(presnyPodil);
    return { index, halere, zbytek: presnyPodil - halere };
  });
  let zbyvaHalere = cenaHalere - podily.reduce((soucet, podil) => soucet + podil.halere, 0);

  podily.sort((a, b) => b.zbytek - a.zbytek || a.index - b.index);
  for (let index = 0; index < zbyvaHalere; index += 1) {
    podily[index].halere += 1;
  }

  podily.sort((a, b) => a.index - b.index);
  return podily.map(podil => podil.halere);
}

if (typeof module === "object" && module.exports) {
  module.exports = { rozdelCenuHalere };
}

if (typeof document !== "undefined") {
  const tabulka = document.querySelector(".checklist");
  if (!tabulka || !tabulka.tHead || !tabulka.tBodies.length) {
    throw new Error("Tabulka účastníků nemá očekávanou strukturu.");
  }
  const rozlozeni = tabulka.closest(".rozlozeni");
  if (!rozlozeni) {
    throw new Error("Tabulka účastníků není uvnitř rozložení akce.");
  }

  const hlavicka = tabulka.tHead.rows[0];
  if (!hlavicka || hlavicka.cells.length < 3) {
    throw new Error("V tabulce chybí sloupce produktu, množství a ceny.");
  }

  const pocetUcastniku = hlavicka.cells.length - 3;
  const radekSouctu = tabulka.createTFoot().insertRow();
  const popisekSouctu = document.createElement("th");
  popisekSouctu.scope = "row";
  popisekSouctu.textContent = "Celkem k úhradě";
  radekSouctu.append(popisekSouctu);
  radekSouctu.insertCell();
  radekSouctu.insertCell();
  const bunkySouctu = Array.from({ length: pocetUcastniku }, () => {
    const bunka = radekSouctu.insertCell();
    const castka = document.createElement("span");
    castka.className = "celkem-castka";
    bunka.append(castka);
    return bunka;
  });
  const vystupySouctu = bunkySouctu.map(bunka => bunka.querySelector(".celkem-castka"));

  const shrnuti = document.createElement("p");
  shrnuti.className = "souhrn-vypoctu";
  shrnuti.setAttribute("role", "status");
  shrnuti.setAttribute("aria-live", "polite");
  rozlozeni.append(shrnuti);

  const stavUlozeni = document.createElement("p");
  stavUlozeni.className = "stav-ulozeni";
  stavUlozeni.setAttribute("role", "status");
  stavUlozeni.setAttribute("aria-live", "polite");
  rozlozeni.append(stavUlozeni);

  const eventSlug = decodeURIComponent(window.location.pathname.split("/").pop())
    .replace(/\.html$/i, "");
  const klicUlozeni = `podily-akce:${eventSlug}`;
  const staryKlicUlozeni = `podily-akce:${window.location.pathname}`;
  const adresaSdilenehoStavu = window.apiUrl(
    `/api/state/${encodeURIComponent(eventSlug)}`
  );
  const cekajiciZmeny = new Map();
  let casovacUlozeni;
  let nacitaniSdilenehoStavu = false;
  let sdileniAktivni = false;
  let chybaSdileniZobrazena = false;
  let sdileneHodnotyInicializovany = false;

  function ulozPodily() {
    const vstupy = Array.from(tabulka.tBodies[0].querySelectorAll("input.podil-kolecko"));
    const hodnoty = vstupy.map(input => input.value);
    try {
      localStorage.setItem(klicUlozeni, JSON.stringify(hodnoty));
      if (!sdileniAktivni) {
        stavUlozeni.classList.remove("chyba");
        stavUlozeni.textContent = "Vyplněné podíly jsou uložené v tomto prohlížeči.";
      }
    } catch (error) {
      stavUlozeni.classList.add("chyba");
      stavUlozeni.textContent = "Vyplněné podíly se nepodařilo uložit.";
      console.error(error);
    }
  }

  function obnovPodily() {
    let ulozene;
    try {
      const soubor = localStorage.getItem(klicUlozeni) ??
        (staryKlicUlozeni !== klicUlozeni
          ? localStorage.getItem(staryKlicUlozeni)
          : null);
      ulozene = soubor === null ? null : JSON.parse(soubor);
    } catch (error) {
      stavUlozeni.classList.add("chyba");
      stavUlozeni.textContent = "Uložené podíly se nepodařilo načíst.";
      console.error(error);
      return;
    }

    if (!Array.isArray(ulozene)) {
      return;
    }

    const vstupy = Array.from(tabulka.tBodies[0].querySelectorAll("input.podil-kolecko"));
    vstupy.forEach((input, index) => {
      if (typeof ulozene[index] === "string") {
        input.value = ulozene[index];
      }
    });
  }

  function klicBunky(input) {
    const radky = Array.from(tabulka.tBodies[0].rows);
    const indexRadku = radky.indexOf(input.closest("tr"));
    return `${indexRadku}:${input.dataset.participantIndex}`;
  }

  function nastavStavSdileni(zprava, chyba = false) {
    stavUlozeni.classList.toggle("chyba", chyba);
    stavUlozeni.textContent = zprava;
  }

  function hodnotyPocatecnihoSdileni(sharedValues) {
    const values = {};
    tabulka.tBodies[0].querySelectorAll("input.podil-kolecko").forEach(input => {
      const cellKey = klicBunky(input);
      if (input.value !== "0" && !Object.prototype.hasOwnProperty.call(sharedValues, cellKey)) {
        values[cellKey] = input.value;
      }
    });
    return values;
  }

  async function odpovedApi(response) {
    let result;
    try {
      result = await response.json();
    } catch (error) {
      throw new Error("Server vrátil neplatnou odpověď.");
    }
    if (!response.ok) {
      throw new Error(result.error || "Sdílený stav se nepodařilo uložit.");
    }
    return result;
  }

  async function ulozCekajiciZmeny() {
    if (!sdileniAktivni || cekajiciZmeny.size === 0) {
      return;
    }

    const zmeny = Array.from(cekajiciZmeny.entries());
    try {
      for (const [cellKey, value] of zmeny) {
        await odpovedApi(await fetch(adresaSdilenehoStavu, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cell_key: cellKey, value }),
        }));
        if (cekajiciZmeny.get(cellKey) === value) {
          cekajiciZmeny.delete(cellKey);
        }
      }
      if (cekajiciZmeny.size === 0) {
        nastavStavSdileni("Změny jsou uložené a sdílené s ostatními.");
      }
    } catch (error) {
      if (!chybaSdileniZobrazena) {
        console.error("Sdílení počítadel se nepodařilo:", error);
        chybaSdileniZobrazena = true;
      }
      nastavStavSdileni(
        "Změnu se nepodařilo sdílet; zkusíme ji znovu. Zatím je uložená v tomto prohlížeči.",
        true
      );
    }
  }

  function naplanujUlozeniSdileneZmeny(input) {
    if (!input.validity.valid || (input.value !== "" && Number(input.value) > 999)) {
      return;
    }
    cekajiciZmeny.set(klicBunky(input), input.value);
    clearTimeout(casovacUlozeni);
    casovacUlozeni = setTimeout(ulozCekajiciZmeny, 350);
  }

  async function synchronizujSdilenePodily() {
    if (nacitaniSdilenehoStavu || document.hidden) {
      return;
    }
    nacitaniSdilenehoStavu = true;
    try {
      const response = await fetch(adresaSdilenehoStavu, { cache: "no-store" });
      const result = await odpovedApi(response);
      const sharedValues = result.values;
      if (!sharedValues || typeof sharedValues !== "object" || Array.isArray(sharedValues)) {
        throw new Error("Server vrátil neplatný sdílený stav.");
      }

      sdileniAktivni = true;
      chybaSdileniZobrazena = false;
      nastavStavSdileni("Sdílení je aktivní — změny ostatních se průběžně načítají.");

      if (!sdileneHodnotyInicializovany) {
        sdileneHodnotyInicializovany = true;
        const initialValues = hodnotyPocatecnihoSdileni(sharedValues);
        if (Object.keys(initialValues).length > 0) {
          await odpovedApi(await fetch(adresaSdilenehoStavu, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ values: initialValues }),
          }));
        }
      }

      let updated = false;
      tabulka.tBodies[0].querySelectorAll("input.podil-kolecko").forEach(input => {
        const cellKey = klicBunky(input);
        const sharedValue = sharedValues[cellKey];
        if (
          !cekajiciZmeny.has(cellKey) &&
          typeof sharedValue === "string" &&
          (sharedValue === "" || /^\d{1,3}$/.test(sharedValue)) &&
          input.value !== sharedValue
        ) {
          input.value = sharedValue;
          updated = true;
        }
      });
      if (updated) {
        aktualizujVysledek();
        ulozPodily();
      }
      await ulozCekajiciZmeny();
    } catch (error) {
      sdileniAktivni = false;
      if (!chybaSdileniZobrazena) {
        console.error("Sdílený stav se nepodařilo načíst:", error);
        chybaSdileniZobrazena = true;
      }
      nastavStavSdileni(
        "Sdílení není dostupné; změny se zatím ukládají jen v tomto prohlížeči.",
        true
      );
    } finally {
      nacitaniSdilenehoStavu = false;
    }
  }

  const formatujCenu = halere =>
    `${new Intl.NumberFormat("cs-CZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(halere / 100)} Kč`;

  function aktualizujVysledek() {
    const poctyPodleVstupu = new Map();
    let neplatnyVstup = false;

    tabulka.tBodies[0].querySelectorAll("input.podil-kolecko").forEach(input => {
      if (input.value.trim() === "") {
        input.removeAttribute("aria-invalid");
        poctyPodleVstupu.set(input, 0);
        return;
      }

      const pocet = Number(input.value);
      if (!input.validity.valid || !Number.isSafeInteger(pocet) || pocet < 0) {
        input.setAttribute("aria-invalid", "true");
        neplatnyVstup = true;
        return;
      }

      input.removeAttribute("aria-invalid");
      poctyPodleVstupu.set(input, pocet);
    });

    if (neplatnyVstup) {
      bunkySouctu.forEach((bunka, index) => {
        bunka.removeAttribute("data-total-halere");
        vystupySouctu[index].textContent = "—";
      });
      shrnuti.classList.add("chyba");
      shrnuti.textContent = "Oprav neplatné hodnoty počítadel; součty zatím nejsou k dispozici.";
      tabulka.dispatchEvent(new Event("totalsupdated"));
      return;
    }

    const celkemNaOsobu = Array(pocetUcastniku).fill(0);
    let nerozdelenaCena = 0;

    Array.from(tabulka.tBodies[0].rows).forEach(radek => {
      const cenaHalere = Number(radek.dataset.totalHalere);
      if (!Number.isSafeInteger(cenaHalere) || cenaHalere < 0) {
        throw new Error("Řádek produktu nemá platnou cenu v haléřích.");
      }

      const vstupy = Array.from(radek.querySelectorAll("input.podil-kolecko"));
      if (vstupy.length !== pocetUcastniku) {
        throw new Error("Počet počítadel neodpovídá počtu účastníků.");
      }

      const pocty = Array(pocetUcastniku).fill(0);
      const pouziteIndexy = new Set();
      vstupy.forEach(input => {
        const index = Number(input.dataset.participantIndex);
        if (!Number.isSafeInteger(index) || index < 0 || index >= pocetUcastniku || pouziteIndexy.has(index)) {
          throw new Error("Počítadlo nemá platný index účastníka.");
        }
        pouziteIndexy.add(index);
        pocty[index] = poctyPodleVstupu.get(input);
      });

      if (pocty.every(pocet => pocet === 0)) {
        nerozdelenaCena += cenaHalere;
        return;
      }

      const rozdeleneCeny = rozdelCenuHalere(cenaHalere, pocty);
      rozdeleneCeny.forEach((halere, index) => {
        celkemNaOsobu[index] += halere;
      });
    });

    celkemNaOsobu.forEach((halere, index) => {
      bunkySouctu[index].dataset.totalHalere = String(halere);
      vystupySouctu[index].textContent = formatujCenu(halere);
    });
    shrnuti.classList.remove("chyba");
    shrnuti.textContent = `Nerozděleno: ${formatujCenu(nerozdelenaCena)}`;
    tabulka.dispatchEvent(new Event("totalsupdated"));
  }

  obnovPodily();
  tabulka.addEventListener("input", event => {
    aktualizujVysledek();
    ulozPodily();
    if (event.target instanceof HTMLInputElement && event.target.matches("input.podil-kolecko")) {
      naplanujUlozeniSdileneZmeny(event.target);
    }
  });
  tabulka.addEventListener("wheel", event => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches("input.podil-kolecko")) {
      return;
    }

    event.preventDefault();
    const aktualniPocet = Number(input.value) || 0;
    const zmena = event.deltaY < 0 ? 1 : -1;
    input.value = String(Math.max(0, Math.min(9, aktualniPocet + zmena)));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, { passive: false });

  aktualizujVysledek();
  synchronizujSdilenePodily();
  window.setInterval(synchronizujSdilenePodily, 2500);
}
