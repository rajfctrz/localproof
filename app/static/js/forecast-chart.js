// Renders the forecast chart from the JSON block on the result page.
// Colours come from the CSS custom properties so the chart follows the theme.
(function () {
  "use strict";

  const canvas = document.getElementById("forecast-chart");
  const dataEl = document.getElementById("chart-data");
  if (!canvas || !dataEl || typeof Chart === "undefined") return;

  const data = JSON.parse(dataEl.textContent);
  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(name).trim();
  const ink = token("--ink");
  const inkSoft = token("--ink-soft");
  const rule = token("--rule");
  const accent = token("--accent");
  const accentWash = token("--accent-wash");
  const figures = token("--font-figures");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

  new Chart(canvas, {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        // Band: upper fills down to lower (dataset index 1).
        { label: "High", data: data.upper, borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: accentWash },
        { label: "Low", data: data.lower, borderWidth: 0, pointRadius: 0, fill: false },
        { label: "Actual", data: data.actual, borderColor: ink, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.25 },
        { label: "Forecast", data: data.forecast, borderColor: accent, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 4, tension: 0.25 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: reduceMotion ? false : { duration: 400 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => item.raw !== null,
          titleFont: { family: figures },
          bodyFont: { family: figures },
          callbacks: { label: (item) => ` ${item.dataset.label}: ${number.format(item.raw)}` },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: inkSoft },
          ticks: { color: inkSoft, font: { family: figures, size: 11 }, maxRotation: 0, autoSkipPadding: 16 },
        },
        y: {
          grid: { color: rule },
          border: { display: false },
          ticks: { color: inkSoft, font: { family: figures, size: 11 }, callback: (v) => compact.format(v) },
        },
      },
    },
  });
})();
