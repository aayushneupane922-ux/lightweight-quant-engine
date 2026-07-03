// Obsidian Desk client. Read via WebSocket/JSON; the only mutating call is
// POST /api/control (the whitelisted ControlPlane). No console output, no
// raw log rendering — every update repaints structured components.
(function () {
  "use strict";

  function fmtPct(x) {
    if (x === null || x === undefined) return "—";
    var s = x >= 0 ? "+" : "";
    return s + x.toFixed(2) + "%";
  }

  function badgeClass(state) {
    return "badge b-" + state.toLowerCase();
  }

  function paintTape(rows) {
    var body = document.getElementById("tape-body");
    if (!body) return;
    body.innerHTML = "";
    rows.slice().reverse().forEach(function (r) {
      var div = document.createElement("div");
      div.className = "tr";
      var t = (r.sim_ts || "").slice(11, 19);
      div.innerHTML =
        '<span class="t">' + t + "</span>" +
        '<span class="ty">' + r.type + "</span>" +
        '<span class="m">' + r.summary + "</span>" +
        '<span class="d">' + (r.detail || "") + "</span>";
      body.appendChild(div);
    });
  }

  function paintSession(snap) {
    var s = snap.session;
    if (!s) return;
    var pnl = document.getElementById("session-pnl");
    if (pnl) {
      pnl.textContent = fmtPct(s.pnl_pct);
      pnl.className = "v mono " + (s.pnl_pct >= 0 ? "pos" : "neg");
    }
    var exp = document.getElementById("session-exposure");
    if (exp) exp.textContent = s.exposure.toFixed(2) + "×";
    var dd = document.getElementById("session-dd");
    if (dd) dd.textContent = "−" + (s.drawdown * 100).toFixed(1) + "%";
  }

  function paintKill(snap) {
    var btn = document.getElementById("kill-btn");
    var dot = document.getElementById("feed-dot");
    if (btn) btn.classList.toggle("armed", !!snap.kill_active);
    if (dot) dot.classList.toggle("off", !!snap.kill_active);
  }

  function apply(payload) {
    if (payload.snapshot) {
      paintSession(payload.snapshot);
      paintKill(payload.snapshot);
    }
    if (payload.tape) paintTape(payload.tape);
  }

  function connect() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    var sock;
    try {
      sock = new WebSocket(proto + "://" + location.host + "/ws");
    } catch (e) {
      return;
    }
    sock.onmessage = function (ev) {
      try { apply(JSON.parse(ev.data)); } catch (e) { /* ignore malformed frame */ }
    };
    // periodic read-only refresh ping (server replies with a fresh snapshot)
    sock.onopen = function () {
      setInterval(function () {
        if (sock.readyState === 1) sock.send("refresh");
      }, 2000);
    };
  }

  function control(command) {
    var operator = window.prompt("Operator name (required, human-only):", "");
    if (!operator) return;
    fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: command, operator: operator }),
    }).then(function () { location.reload(); });
  }

  function autopilot(command) {
    // no operator prompt for a non-destructive toggle; the audited
    // ControlEvent records source=ui
    fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: command, operator: "desk-operator" }),
    }).then(function () { location.reload(); });
  }

  // -- GUI job triggers (docs/13 M18): ingest / live start-stop. A second,
  // separate surface from /api/control above -- these kick off a
  // background job (JobManager) rather than flip a control flag.
  var DEFAULT_LIVE_OUT = "runs/live-session.jsonl";

  function paintJobs(rows) {
    var byName = {};
    rows.forEach(function (r) { byName[r.name] = r; });

    var live = byName.live;
    var liveEl = document.getElementById("live-status");
    var toggleBtn = document.getElementById("live-toggle-btn");
    if (live && liveEl) {
      liveEl.textContent = live.state + " · " + live.message;
      liveEl.className = "control-status " + (live.state === "error" ? "error" : live.state);
    }
    if (toggleBtn && live) {
      var running = live.state === "running";
      toggleBtn.textContent = running ? "Stop Live" : "Start Live";
      toggleBtn.className = "ctl-btn" + (running ? " stop" : "");
    }

    var ingest = byName.ingest;
    var ingestEl = document.getElementById("ingest-status");
    if (ingest && ingestEl) {
      ingestEl.textContent = "ingest: " + ingest.state + " · " + ingest.message;
    }
  }

  function pollJobs() {
    var panel = document.getElementById("control-panel");
    if (!panel) return;
    fetch("/api/jobs")
      .then(function (r) { return r.json(); })
      .then(function (rows) { if (Array.isArray(rows)) paintJobs(rows); })
      .catch(function () { /* transient -- next poll will retry */ });
  }

  function startOrStopLive() {
    var btn = document.getElementById("live-toggle-btn");
    var resuming = btn && btn.textContent.indexOf("Stop") !== -1;
    if (resuming) {
      fetch("/api/jobs/live/stop", { method: "POST" }).then(pollJobs);
      return;
    }
    var resumeChecked = document.getElementById("resume-check");
    var body = {
      adapter: "ccxt", exchange: "binance", symbol: "BTC-USDT", timeframe: "1m",
      poll_seconds: 60, lookback_bars: 300, starting_cash: 10000,
      autonomy_every: 5, n_trials: 8, min_periods: 200, use_llm: false,
    };
    if (resumeChecked && resumeChecked.checked) body.out_path = DEFAULT_LIVE_OUT;
    fetch("/api/jobs/live/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(pollJobs);
  }

  function startIngest() {
    fetch("/api/jobs/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        adapter: "ccxt", exchange: "binance", symbol: "BTC-USDT", timeframe: "1m",
        root: "data",
      }),
    }).then(pollJobs);
  }

  function pollBacktest() {
    var panel = document.getElementById("backtest-panel");
    if (!panel) return;
    fetch("/api/jobs")
      .then(function (r) { return r.json(); })
      .then(function (rows) {
        var row = rows.filter(function (r) { return r.name === "backtest"; })[0];
        var el = document.getElementById("backtest-status");
        if (row && el) el.textContent = "backtest: " + row.state + " · " + row.message;
      })
      .catch(function () { /* transient -- next poll will retry */ });
  }

  function startBacktest() {
    var bundle = document.getElementById("bt-bundle");
    var symbol = document.getElementById("bt-symbol");
    fetch("/api/jobs/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        root: "data", bundle: bundle ? bundle.value : "",
        symbol: symbol ? symbol.value : "BTC-USDT",
      }),
    }).then(pollBacktest);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var kill = document.getElementById("kill-btn");
    if (kill) {
      kill.addEventListener("click", function () {
        control(kill.classList.contains("armed") ? "CLEAR_KILL" : "KILL");
      });
    }
    var ap = document.getElementById("autopilot-btn");
    if (ap) {
      ap.addEventListener("click", function () {
        // toggling OFF is "take the wheel"; ON engages autonomous management
        autopilot(ap.classList.contains("on") ? "AUTOPILOT_OFF" : "AUTOPILOT_ON");
      });
    }
    var liveBtn = document.getElementById("live-toggle-btn");
    if (liveBtn) liveBtn.addEventListener("click", startOrStopLive);
    var ingestBtn = document.getElementById("ingest-btn");
    if (ingestBtn) ingestBtn.addEventListener("click", startIngest);
    if (document.getElementById("control-panel")) {
      pollJobs();
      setInterval(pollJobs, 2000);
    }
    var backtestBtn = document.getElementById("backtest-btn");
    if (backtestBtn) backtestBtn.addEventListener("click", startBacktest);
    if (document.getElementById("backtest-panel")) {
      pollBacktest();
      setInterval(pollBacktest, 2000);
    }
    // keyboard-first mode switching (F1..F6 -> nav hrefs)
    document.addEventListener("keydown", function (e) {
      var map = { F1: "/", F2: "/catalog", F3: "/research", F4: "/intel", F5: "/risk", F6: "/daily", F7: "/engine" };
      if (map[e.key]) { e.preventDefault(); location.href = map[e.key]; }
    });
    connect();
  });
})();
