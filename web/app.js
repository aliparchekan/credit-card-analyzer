(function () {
  "use strict";

  // Form fields → analyzer categories used in data/cards.json.
  const FIELDS = [
    { category: "Groceries", label: "Groceries", start: 650 },
    { category: "Restaurants", label: "Restaurants & takeout", start: 300 },
    { category: "Coffee", label: "Coffee shops", start: 40 },
    { category: "Gas / EV Charging", label: "Gas & EV charging", start: 180 },
    { category: "Phone / Internet", label: "Phone & internet", start: 120 },
    { category: "Utilities", label: "Utilities", start: 150 },
    { category: "Subscriptions", label: "Streaming & subscriptions", start: 45 },
    { category: "Travel", label: "Travel & transit", start: 100 },
    { category: "Health", label: "Pharmacy & health", start: 0 },
    { category: "Shopping", label: "Shopping", start: 250 },
    { category: "Car / Insurance", label: "Car & insurance", start: 0 },
    { category: "Education", label: "Education", start: 0 },
    { category: "Other", label: "Everything else", start: 0 },
  ];
  const LABEL = Object.fromEntries(FIELDS.map((f) => [f.category, f.label]));

  const money = (v, cents = false) =>
    "$" + v.toLocaleString("en-CA", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });

  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const fieldsEl = document.getElementById("fields");
  const totalEl = document.getElementById("total");
  const resultsEl = document.getElementById("results");
  let cardsData = null;

  function buildForm() {
    fieldsEl.innerHTML = FIELDS.map(
      (f, i) => `
      <label class="field" for="f${i}">
        <span class="field-label">${esc(f.label)}</span>
        <span class="money-input">
          <span aria-hidden="true">$</span>
          <input id="f${i}" data-category="${esc(f.category)}" type="number" inputmode="decimal"
                 min="0" step="10" value="${f.start || ""}" placeholder="0">
        </span>
      </label>`
    ).join("");
  }

  function readSpend() {
    const spend = {};
    for (const input of fieldsEl.querySelectorAll("input")) {
      const v = parseFloat(input.value);
      if (v > 0) spend[input.dataset.category] = v;
    }
    return spend;
  }

  function breakdownList(breakdown) {
    return Object.entries(breakdown)
      .sort((a, b) => b[1] - a[1])
      .map(([label, v]) => `<li><span>${esc(label)}</span><span>${money(v, true)}</span></li>`)
      .join("");
  }

  function render() {
    const spend = readSpend();
    const monthly = Object.values(spend).reduce((s, v) => s + v, 0);
    totalEl.textContent = money(monthly);
    if (!cardsData) return;
    if (monthly <= 0) {
      resultsEl.innerHTML = `<p class="empty">Enter some monthly spending to see which card earns the most.</p>`;
      return;
    }

    const { recommend, bestPair } = window.CardRecommender;
    const results = recommend(spend, cardsData);
    const top = results[0];
    const pair = bestPair(spend, cardsData);
    const annual = monthly * 12;

    let pairHtml = "";
    if (pair && pair.netValue > top.netValue + 1) {
      const [a, b] = pair.cards;
      const cats = (i) => Object.keys(pair.split[i]).map((c) => esc(LABEL[c] || c)).join(", ");
      pairHtml = `
        <section class="panel pair">
          <h3>Or use two cards: ${money(pair.netValue)}/yr</h3>
          <p>That's ${money(pair.netValue - top.netValue)} more than the best single card.</p>
          <ul class="pair-list">
            <li><strong>${esc(a.name)}</strong><span>${cats(0)}</span></li>
            <li><strong>${esc(b.name)}</strong><span>${cats(1)}</span></li>
          </ul>
        </section>`;
    }

    const rows = results
      .map((r, i) => {
        const rate = annual ? (100 * r.netValue) / annual : 0;
        return `
        <tr class="${r.eligible ? "" : "ineligible"}">
          <td class="rank">${i + 1}</td>
          <td><a href="${esc(r.source || "#")}" target="_blank" rel="noopener">${esc(r.name)}</a>
            ${r.eligible ? "" : '<span class="tag">not eligible</span>'}</td>
          <td class="num">${money(r.annualRewards)}</td>
          <td class="num">${r.annualFee ? money(r.annualFee) : "Free"}</td>
          <td class="num strong">${money(r.netValue)}</td>
          <td class="num muted">${rate.toFixed(1)}%</td>
        </tr>`;
      })
      .join("");

    resultsEl.innerHTML = `
      <section class="panel best">
        <p class="eyebrow">Best single card</p>
        <h2>${esc(top.name)}</h2>
        <p class="headline"><strong>${money(top.netValue)}</strong> a year after fees</p>
        <p class="sub">${money(top.annualRewards, true)} in rewards − ${top.annualFee ? money(top.annualFee, true) + " annual fee" : "no annual fee"}</p>
        <ul class="breakdown">${breakdownList(top.breakdown)}</ul>
        ${top.notes ? `<p class="note">${esc(top.notes)}</p>` : ""}
      </section>
      ${pairHtml}
      <section class="panel">
        <h3>All cards compared</h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Card</th><th class="num">Rewards/yr</th><th class="num">Fee</th><th class="num">Net/yr</th><th class="num">Net rate</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </section>`;
  }

  buildForm();
  fieldsEl.addEventListener("input", render);
  document.getElementById("clear").addEventListener("click", () => {
    for (const input of fieldsEl.querySelectorAll("input")) input.value = "";
    render();
    fieldsEl.querySelector("input").focus();
  });
  document.getElementById("spend-form").addEventListener("submit", (e) => e.preventDefault());

  fetch("data/cards.json")
    .then((r) => {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    })
    .then((data) => {
      cardsData = data;
      document.getElementById("disclaimer").textContent =
        `Earn rates last checked against issuer websites on ${data.last_reviewed}, but they change often. ` +
        "Points are valued at 1 cent each. This is an estimate, not financial advice. Confirm the terms with the issuer before you apply.";
      render();
    })
    .catch(() => {
      resultsEl.innerHTML = `<p class="empty">Couldn't load card data. If you opened this file directly, serve the folder instead (for example <code>python3 -m http.server</code>).</p>`;
    });
  render();
})();
