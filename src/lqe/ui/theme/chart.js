// Floor hero chart (docs/13 M19): candlestick price + streaming equity
// area, via vendored TradingView Lightweight Charts (theme/vendor/). A
// second, read-only poll loop -- /api/chart/price and /api/chart/equity,
// same StateReader the rest of the desk reads from. Degrades gracefully
// (no chart, no crash) if the vendored library or the chart panes aren't
// present; the accessible data-table fallback works either way.
(function () {
  "use strict";

  function toUnixTime(iso) {
    return Math.floor(new Date(iso).getTime() / 1000);
  }

  function fmtMoney(x) {
    return x === null || x === undefined || Number.isNaN(x) ? "—" : x.toFixed(2);
  }

  function chartOptions() {
    return {
      layout: { background: { color: "#0E131B" }, textColor: "#7A88A8", fontFamily: "JetBrains Mono, ui-monospace, monospace" },
      grid: { vertLines: { color: "#1E2836" }, horzLines: { color: "#1E2836" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#1E2836" },
      rightPriceScale: { borderColor: "#1E2836" },
      crosshair: { mode: 0 },
      autoSize: true,
    };
  }

  function paintTable(priceRows, equityRows) {
    var body = document.getElementById("chart-table-body");
    if (!body) return;
    var wrap = document.getElementById("chart-table-wrap");
    if (wrap && wrap.hidden) return; // fallback table hidden -- skip the repaint
    var n = Math.max(priceRows.length, equityRows.length);
    var rows = [];
    for (var i = 0; i < n; i++) {
      var p = priceRows[i];
      var e = equityRows[i];
      rows.push(
        "<tr><td>" + ((p && p.ts) || (e && e.ts) || "") + "</td>" +
        "<td>" + (p ? p.o : "—") + "</td><td>" + (p ? p.h : "—") + "</td>" +
        "<td>" + (p ? p.l : "—") + "</td><td>" + (p ? p.c : "—") + "</td>" +
        "<td>" + (e ? e.equity : "—") + "</td></tr>"
      );
    }
    body.innerHTML = rows.join("");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var priceEl = document.getElementById("price-chart");
    var equityEl = document.getElementById("equity-chart");
    var hasCharts = !!(window.LightweightCharts && priceEl && equityEl);

    var candleSeries = null;
    var equitySeries = null;
    if (hasCharts) {
      var priceChart = LightweightCharts.createChart(priceEl, chartOptions());
      // fill-vs-outline (docs/13 M19 a11y): bullish is hollow/outline-only,
      // bearish is solid-filled -- so the up/down distinction survives
      // colorblindness even if hue can't be told apart, not hue alone.
      candleSeries = priceChart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: "rgba(38,166,154,0.12)", downColor: "#EF5350",
        borderUpColor: "#26A69A", borderDownColor: "#EF5350", borderVisible: true,
        wickUpColor: "#26A69A", wickDownColor: "#EF5350",
      });
      var equityChart = LightweightCharts.createChart(equityEl, chartOptions());
      equitySeries = equityChart.addSeries(LightweightCharts.AreaSeries, {
        lineColor: "#7C7BF2", topColor: "rgba(124,123,242,.35)", bottomColor: "rgba(124,123,242,.02)",
      });
    }

    var paused = false;
    var lastPriceRows = [];
    var lastEquityRows = [];

    function setEmpty(id, empty) {
      var el = document.getElementById(id);
      if (el) el.style.display = empty ? "flex" : "none";
    }

    // Incremental repaint (perf phase 4): when a poll returns the same
    // series plus a few new tail rows, series.update() the tail instead of
    // a full setData() rebuild (no flicker, no full redraw). A changed
    // first timestamp or a shrunk series means downsampling re-strided the
    // data -- fall back to setData().
    function grewOnly(prev, rows) {
      return prev.length > 0 && rows.length >= prev.length &&
        rows[0].ts === prev[0].ts &&
        rows[prev.length - 1].ts === prev[prev.length - 1].ts;
    }

    function refresh() {
      if (paused) return;
      fetch("/api/chart/price")
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          var prev = lastPriceRows;
          lastPriceRows = rows;
          paintTable(lastPriceRows, lastEquityRows);
          setEmpty("price-chart-empty", rows.length === 0);
          if (!rows.length) return;
          var last = rows[rows.length - 1];
          var kpi = document.getElementById("hero-price");
          if (kpi) kpi.textContent = fmtMoney(+last.c);
          if (!candleSeries) return;
          var toCandle = function (b) {
            return { time: toUnixTime(b.ts), open: +b.o, high: +b.h, low: +b.l, close: +b.c };
          };
          if (grewOnly(prev, rows)) {
            // repaint the last previously-known bar too (it may have been
            // a still-forming bar that finalized), then the new tail
            rows.slice(prev.length - 1).forEach(function (b) {
              candleSeries.update(toCandle(b));
            });
          } else {
            candleSeries.setData(rows.map(toCandle));
          }
        })
        .catch(function () { /* transient -- next poll retries */ });

      fetch("/api/chart/equity")
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          var prev = lastEquityRows;
          lastEquityRows = rows;
          paintTable(lastPriceRows, lastEquityRows);
          setEmpty("equity-chart-empty", rows.length === 0);
          if (!rows.length) return;
          var last = rows[rows.length - 1];
          var kpi = document.getElementById("hero-equity");
          if (kpi) kpi.textContent = fmtMoney(+last.equity);
          if (!equitySeries) return;
          var toPoint = function (p) {
            return { time: toUnixTime(p.ts), value: +p.equity };
          };
          if (grewOnly(prev, rows)) {
            rows.slice(prev.length - 1).forEach(function (p) {
              equitySeries.update(toPoint(p));
            });
          } else {
            equitySeries.setData(rows.map(toPoint));
          }
        })
        .catch(function () { /* transient -- next poll retries */ });
    }

    var pauseBtn = document.getElementById("chart-pause-btn");
    if (pauseBtn) {
      pauseBtn.addEventListener("click", function () {
        paused = !paused;
        pauseBtn.textContent = paused ? "Resume" : "Pause";
        pauseBtn.setAttribute("aria-pressed", String(paused));
      });
    }
    var tableBtn = document.getElementById("chart-table-btn");
    var tableWrap = document.getElementById("chart-table-wrap");
    if (tableBtn && tableWrap) {
      tableBtn.addEventListener("click", function () {
        var showing = !tableWrap.hidden;
        tableWrap.hidden = showing;
        tableBtn.setAttribute("aria-expanded", String(!showing));
        tableBtn.textContent = showing ? "View as table" : "Hide table";
        // repaints are skipped while hidden -- catch up on reveal
        if (!tableWrap.hidden) paintTable(lastPriceRows, lastEquityRows);
      });
    }

    if (priceEl || equityEl) {
      refresh();
      setInterval(refresh, 3000);
    }
  });
})();
