// Browser port of src/recommender.py. Keep the two in sync.
// Rates are percent cash-equivalent; spend is monthly dollars per category.
(function (root) {
  "use strict";

  function rateFor(card, category) {
    let rate = Number(card.base_rate);
    for (const tier of card.tiers || []) {
      if (tier.categories.includes(category)) rate = Math.max(rate, Number(tier.rate));
    }
    const choose = card.choose;
    if (choose) {
      for (const cats of Object.values(choose.options)) {
        if (cats.includes(category)) rate = Math.max(rate, Number(choose.rate));
      }
    }
    return rate;
  }

  function chosenTiers(card, annual) {
    const choose = card.choose;
    if (!choose) return [];
    const sumOf = (cats) => cats.reduce((s, c) => s + (annual[c] || 0), 0);
    const ranked = Object.entries(choose.options)
      .map((entry, index) => ({ entry, index, total: sumOf(entry[1]) }))
      .sort((a, b) => b.total - a.total || a.index - b.index)
      .slice(0, Number(choose.n));
    return ranked
      .filter((r) => r.total > 0)
      .map((r) => ({ label: "Chosen: " + r.entry[0], categories: r.entry[1], rate: choose.rate }));
  }

  function evaluateCard(card, monthlySpend, excluded) {
    const skip = new Set(excluded || []);
    const annual = {};
    for (const [category, amount] of Object.entries(monthlySpend)) {
      if (!skip.has(category) && amount > 0) annual[category] = amount * 12;
    }
    const remaining = { ...annual };
    const base = Number(card.base_rate);
    const breakdown = {};

    const tiers = [...(card.tiers || []), ...chosenTiers(card, annual)]
      .map((tier, index) => ({ tier, index }))
      .sort((a, b) => Number(b.tier.rate) - Number(a.tier.rate) || a.index - b.index)
      .map((t) => t.tier);

    for (const tier of tiers) {
      const rate = Number(tier.rate);
      if (rate <= base) continue;
      let room = tier.annual_cap == null ? Infinity : Number(tier.annual_cap);
      for (const category of tier.categories) {
        const amount = Math.min(remaining[category] || 0, room);
        if (amount <= 0) continue;
        remaining[category] -= amount;
        room -= amount;
        breakdown[tier.label] = (breakdown[tier.label] || 0) + (amount * rate) / 100;
      }
    }

    const leftover = Object.values(remaining).reduce((s, v) => s + v, 0);
    if (leftover > 0) breakdown["Everything else"] = (leftover * base) / 100;

    const totalAnnual = Object.values(annual).reduce((s, v) => s + v, 0);
    const minSpend = Number(card.min_annual_spend || 0);
    const eligible = totalAnnual >= minSpend;
    let notes = String(card.notes || "");
    if (!eligible) {
      notes = `Needs $${minSpend.toLocaleString()}/yr card spend (you have $${Math.round(totalAnnual).toLocaleString()}). ` + notes;
    }
    const rewards = Object.values(breakdown).reduce((s, v) => s + v, 0);
    return {
      id: card.id,
      name: card.name,
      source: card.source,
      annualRewards: rewards,
      annualFee: Number(card.annual_fee),
      netValue: rewards - Number(card.annual_fee),
      eligible,
      breakdown,
      notes,
    };
  }

  function recommend(monthlySpend, data) {
    const excluded = data.excluded_categories || [];
    return data.cards
      .map((card, index) => ({ r: evaluateCard(card, monthlySpend, excluded), index }))
      .sort(
        (a, b) =>
          Number(b.r.eligible) - Number(a.r.eligible) ||
          b.r.netValue - a.r.netValue ||
          a.index - b.index
      )
      .map((x) => x.r);
  }

  function bestPair(monthlySpend, data) {
    const excluded = data.excluded_categories || [];
    const cards = data.cards;
    let best = null;
    for (let i = 0; i < cards.length; i++) {
      for (let j = i + 1; j < cards.length; j++) {
        const first = cards[i];
        const second = cards[j];
        const split = [{}, {}];
        for (const [category, amount] of Object.entries(monthlySpend)) {
          const target = rateFor(first, category) >= rateFor(second, category) ? 0 : 1;
          split[target][category] = amount;
        }
        const a = evaluateCard(first, split[0], excluded);
        const b = evaluateCard(second, split[1], excluded);
        if (!(a.eligible && b.eligible)) continue;
        if (!Object.keys(split[0]).length || !Object.keys(split[1]).length) continue;
        const combo = {
          cards: [a, b],
          split,
          annualRewards: a.annualRewards + b.annualRewards,
          annualFee: a.annualFee + b.annualFee,
        };
        combo.netValue = combo.annualRewards - combo.annualFee;
        if (!best || combo.netValue > best.netValue) best = combo;
      }
    }
    return best;
  }

  const api = { rateFor, evaluateCard, recommend, bestPair };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CardRecommender = api;
})(typeof window !== "undefined" ? window : globalThis);
