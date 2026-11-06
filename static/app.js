(() => {
  const articoli = Array.isArray(window.__INITIAL_ARTICOLI__)
    ? window.__INITIAL_ARTICOLI__.map((a) => ({ ...a }))
    : [];

  const $ = (id) => document.getElementById(id);
  const tbody = document.querySelector("#tabella tbody");
  const emptyMsg = $("emptyMsg");
  let scontoEuroManuale = false;

  function num(v) {
    const n = parseFloat(String(v ?? "0").replace(",", "."));
    return Number.isFinite(n) ? n : 0;
  }

  function euro(n) {
    return `${n.toFixed(2)} €`;
  }

  function render() {
    tbody.innerHTML = "";
    articoli.forEach((a, i) => {
      const tr = document.createElement("tr");
      tr.dataset.index = i;
      tr.innerHTML = `
        <td class="drag-cell"><button type="button" class="drag-handle" aria-label="Sposta riga" title="Sposta riga">☰</button></td>
        <td><input class="line-qty" type="number" min="1" step="1" value="${a.qty}"></td>
        <td><input class="line-desc" type="text" value="${escapeHtml(a.desc)}"></td>
        <td class="num"><input class="line-price" type="text" inputmode="decimal" value="${a.prezzo}"></td>
        <td class="num line-total">${euro(a.totale)}</td>
        <td><button type="button" class="btn btn-danger" data-i="${i}">Elimina</button></td>`;
      tbody.appendChild(tr);
    });
    emptyMsg.style.display = articoli.length ? "none" : "block";
    tbody.querySelectorAll("[data-i]").forEach((btn) => {
      btn.addEventListener("click", () => {
        articoli.splice(Number(btn.getAttribute("data-i")), 1);
        render();
      });
    });
    tbody.querySelectorAll("tr").forEach((tr) => {
      const i = Number(tr.dataset.index);
      tr.querySelector(".line-qty").addEventListener("input", (event) => {
        const qty = parseInt(event.target.value, 10);
        articoli[i].qty = Number.isFinite(qty) && qty > 0 ? qty : 0;
        articoli[i].totale = articoli[i].qty * articoli[i].prezzo;
        tr.querySelector(".line-total").textContent = euro(articoli[i].totale);
        aggiornaTotali();
      });
      tr.querySelector(".line-desc").addEventListener("input", (event) => {
        articoli[i].desc = event.target.value;
      });
      tr.querySelector(".line-price").addEventListener("input", (event) => {
        articoli[i].prezzo = num(event.target.value);
        articoli[i].totale = articoli[i].qty * articoli[i].prezzo;
        tr.querySelector(".line-total").textContent = euro(articoli[i].totale);
        aggiornaTotali();
      });
      const handle = tr.querySelector(".drag-handle");
      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        let draggedIndex = i;
        tr.classList.add("dragging");
        handle.setPointerCapture(event.pointerId);

        const move = (moveEvent) => {
          const target = document
            .elementFromPoint(moveEvent.clientX, moveEvent.clientY)
            ?.closest("tr");
          if (!target || target.parentElement !== tbody) return;
          const targetIndex = Number(target.dataset.index);
          if (!Number.isInteger(targetIndex) || targetIndex === draggedIndex) return;

          const insertAfter = moveEvent.clientY > target.getBoundingClientRect().top
            + target.getBoundingClientRect().height / 2;
          const [moved] = articoli.splice(draggedIndex, 1);
          const nextIndex = insertAfter && targetIndex > draggedIndex
            ? targetIndex
            : insertAfter ? targetIndex + 1 : targetIndex;
          articoli.splice(nextIndex, 0, moved);
          const rows = [...tbody.querySelectorAll("tr")];
          const movedRow = rows[draggedIndex];
          tbody.insertBefore(
            movedRow,
            insertAfter ? target.nextElementSibling : target
          );
          [...tbody.querySelectorAll("tr")].forEach((row, index) => {
            row.dataset.index = index;
          });
          draggedIndex = nextIndex;
        };
        const end = () => {
          tr.classList.remove("dragging");
          document.removeEventListener("pointermove", move);
          document.removeEventListener("pointerup", end);
          document.removeEventListener("pointercancel", end);
          render();
        };
        document.addEventListener("pointermove", move);
        document.addEventListener("pointerup", end, { once: true });
        document.addEventListener("pointercancel", end, { once: true });
      });
    });
    aggiornaTotali();
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function aggiornaTotali() {
    const imponibile = articoli.reduce((s, a) => s + a.totale, 0);
    const iva = num($("iva").value);
    if (scontoEuroManuale) {
      const totaleBase = imponibile * (1 + iva / 100);
      $("sconto").value = totaleBase > 0
        ? Math.round((num($("scontoEuro").value) / totaleBase) * 100)
        : "0";
    }
    const sconto = num($("sconto").value);
    const acconto = num($("acconto").value);
    const valoreIva = imponibile * (iva / 100);
    const totale = imponibile + valoreIva;
    const valoreSconto = totale * (sconto / 100);
    const totaleScontato = totale - valoreSconto;
    const valoreAcconto = totaleScontato * (acconto / 100);
    const saldo = totaleScontato - valoreAcconto;
    $("mImp").textContent = euro(imponibile);
    $("mTot").textContent = euro(totale);
    $("mScont").textContent = euro(totaleScontato);
    $("mSaldo").textContent = euro(saldo);
  }

  function payload() {
    const idVal = $("preventivoId").value;
    return {
      id: idVal ? Number(idVal) : null,
      cliente: $("cliente").value.trim(),
      data: $("data").value.trim(),
      consegna: $("consegna").value.trim(),
      pagamento: $("pagamento").value.trim(),
      iva: $("iva").value,
      sconto: $("sconto").value,
      sconto_euro: $("scontoEuro").value,
      acconto: $("acconto").value,
      articoli,
    };
  }

  function resetForm() {
    articoli.length = 0;
    $("preventivoId").value = "";
    $("cliente").value = "";
    $("data").value = new Date().toLocaleDateString("it-IT");
    $("consegna").value = "CONSEGNA ENTRO...";
    $("pagamento").value = "DA CONCORDARE";
    $("iva").value = "0";
    $("sconto").value = "0";
    $("scontoEuro").value = "0";
    scontoEuroManuale = false;
    $("acconto").value = "0";
    $("saveStatus").textContent = "";
    render();
  }

  function fillFrom(data) {
    if (!data) return;
    $("cliente").value = data.cliente || "";
    $("data").value = data.data || $("data").value;
    $("consegna").value = data.consegna || "";
    $("pagamento").value = data.pagamento || "";
    $("iva").value = data.iva ?? "0";
    $("sconto").value = data.sconto ?? "0";
    $("scontoEuro").value = data.sconto_euro ?? "0";
    $("acconto").value = data.acconto ?? "0";
    articoli.length = 0;
    (data.articoli || []).forEach((a) => {
      articoli.push({
        qty: Number(a.qty),
        desc: a.desc,
        prezzo: Number(a.prezzo),
        totale: Number(a.totale ?? Number(a.qty) * Number(a.prezzo)),
      });
    });
    render();
  }

  $("btnAdd").addEventListener("click", () => {
    const qty = parseInt($("qty").value, 10);
    const desc = $("desc").value.trim();
    const prezzo = num($("prezzo").value);
    if (!qty || !desc || !Number.isFinite(prezzo)) {
      alert("Dati articolo non validi. Controlla Q.tà e Prezzo.");
      return;
    }
    articoli.push({ qty, desc, prezzo, totale: qty * prezzo });
    $("qty").value = "";
    $("desc").value = "";
    $("prezzo").value = "";
    render();
  });

  ["iva", "acconto"].forEach((id) => {
    $(id).addEventListener("input", aggiornaTotali);
  });
  $("sconto").addEventListener("input", () => {
    scontoEuroManuale = false;
    const imponibile = articoli.reduce((s, a) => s + a.totale, 0);
    const totale = imponibile * (1 + num($("iva").value) / 100);
    $("scontoEuro").value = (totale * num($("sconto").value) / 100).toFixed(2);
    aggiornaTotali();
  });
  $("scontoEuro").addEventListener("input", () => {
    scontoEuroManuale = true;
    if (!String($("scontoEuro").value).trim() || num($("scontoEuro").value) <= 0) {
      $("sconto").value = "0";
      aggiornaTotali();
      return;
    }
    const imponibile = articoli.reduce((s, a) => s + a.totale, 0);
    const totale = imponibile * (1 + num($("iva").value) / 100);
    const euroSconto = num($("scontoEuro").value);
    $("sconto").value = totale > 0 ? Math.round((euroSconto / totale) * 100) : "0";
    aggiornaTotali();
  });

  $("btnNuovo").addEventListener("click", () => {
    if (articoli.length && !confirm("Azzerare il preventivo corrente?")) return;
    resetForm();
  });

  $("btnSalva").addEventListener("click", async () => {
    if (!articoli.length) {
      alert("Nessun prodotto inserito.");
      return;
    }
    $("saveStatus").textContent = "Salvataggio...";
    try {
      const res = await fetch("/api/preventivi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Errore");
      $("preventivoId").value = data.id;
      if (data.drive && data.drive_ok) {
        $("saveStatus").textContent = `Salvato su Google Drive (${data.file})`;
      } else if (data.drive && data.drive_error) {
        $("saveStatus").textContent = `Salvato in archivio, ma Drive ha fallito: ${data.drive_error}`;
      } else {
        $("saveStatus").textContent = `Salvato · PDF e .prev in File manager (${data.file})`;
      }
    } catch (e) {
      $("saveStatus").textContent = "";
      alert(e.message || "Errore salvataggio");
    }
  });

  $("btnPdf").addEventListener("click", async () => {
    if (!articoli.length) {
      alert("Preventivo vuoto.");
      return;
    }
    const res = await fetch("/api/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    if (!res.ok) {
      alert("Errore generazione PDF");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `preventivo_${($("cliente").value || "tmp").replace(/\s+/g, "_")}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  });

  async function maybeLoadDraft() {
    if (window.__LOAD_DRAFT__ !== true && window.__LOAD_DRAFT__ !== "true") return;
    const res = await fetch("/api/draft");
    const data = await res.json();
    if (data && data.articoli) fillFrom(data);
  }

  render();
  maybeLoadDraft();
})();
