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

  var tapePainted = false;

  function paintTape(rows) {
    var body = document.getElementById("tape-body");
    if (!body) return;
    body.innerHTML = "";
    // stagger the reveal only on the tape's first paint (page load) --
    // every later poll rebuilds the same rows and shouldn't re-animate.
    var revealClass = tapePainted ? "" : " reveal-in";
    rows.slice().reverse().forEach(function (r) {
      var div = document.createElement("div");
      div.className = "tr" + revealClass;
      var t = (r.sim_ts || "").slice(11, 19);
      div.innerHTML =
        '<span class="t">' + t + "</span>" +
        '<span class="ty">' + r.type + "</span>" +
        '<span class="m">' + r.summary + "</span>" +
        '<span class="d">' + (r.detail || "") + "</span>";
      body.appendChild(div);
    });
    tapePainted = true;
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

  // -- blotter (docs/13 M20): live fill feedback + the Blotter view's own
  // table repaint. `handleBlotterFrame` runs on every page (Floor's model
  // cells can pulse from any view showing the rail); `paintBlotter` only
  // touches anything when `#blotter-body` exists.

  var lastBlotterSeq = null;

  function fmtSide(side) {
    return side === "BUY"
      ? '<span class="pos">&#9650; LONG</span>'
      : '<span class="neg">&#9660; SHORT</span>';
  }

  function verdictClass(v) {
    return v === "APPROVE" ? "pass" : v === "CLAMP" ? "warn" : "fail";
  }

  function fmtNum(x, digits) {
    return x === null || x === undefined ? "—" : Number(x).toFixed(digits);
  }

  function pulseModelCell(modelId) {
    var cell = document.querySelector('.cell[data-model="' + modelId + '"]');
    if (!cell) return;
    cell.classList.remove("pulse");
    void cell.offsetWidth; // restart the animation if it's already mid-run
    cell.classList.add("pulse");
  }

  function flashBlotterRow(seq) {
    var row = document.querySelector('.blotter-row[data-seq="' + seq + '"]');
    if (!row) return;
    row.classList.remove("flash");
    void row.offsetWidth;
    row.classList.add("flash");
  }

  function soundEnabled() {
    return !!(window.localStorage && window.localStorage.getItem("lqe-blotter-sound") === "1");
  }

  function playFillSound() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.value = 0.05;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.12);
      osc.onended = function () { ctx.close(); };
    } catch (e) { /* Web Audio unavailable -- sound is optional, never required */ }
  }

  function collectBlotterFilterOptions() {
    var modelSel = document.getElementById("blotter-filter-model");
    if (!modelSel) return;
    var symbolSel = document.getElementById("blotter-filter-symbol");
    var models = new Set();
    var symbols = new Set();
    document.querySelectorAll(".blotter-row").forEach(function (row) {
      models.add(row.dataset.model);
      symbols.add(row.dataset.symbol);
    });
    fillSelectOptions(modelSel, models);
    fillSelectOptions(symbolSel, symbols);
  }

  function fillSelectOptions(select, values) {
    var current = select.value;
    var opts = ['<option value="">All</option>'];
    Array.from(values).sort().forEach(function (v) {
      opts.push('<option value="' + v + '">' + v + "</option>");
    });
    select.innerHTML = opts.join("");
    select.value = current && values.has(current) ? current : "";
  }

  function applyBlotterFilters() {
    var modelSel = document.getElementById("blotter-filter-model");
    if (!modelSel) return;
    var model = modelSel.value;
    var symbol = document.getElementById("blotter-filter-symbol").value;
    var side = document.getElementById("blotter-filter-side").value;
    document.querySelectorAll(".blotter-row").forEach(function (row) {
      var visible =
        (!model || row.dataset.model === model) &&
        (!symbol || row.dataset.symbol === symbol) &&
        (!side || row.dataset.side === side);
      row.style.display = visible ? "" : "none";
    });
  }

  function paintBlotter(rows) {
    var body = document.getElementById("blotter-body");
    if (!body) return;
    var table = document.getElementById("blotter-table");
    var empty = document.getElementById("blotter-empty");
    if (rows.length && table && empty) {
      table.hidden = false;
      empty.hidden = true;
    }
    body.innerHTML = "";
    rows.slice().reverse().forEach(function (r) {
      var tr = document.createElement("tr");
      tr.className =
        "blotter-row" + (r.verdict !== "APPROVE" || r.fill_qty == null ? " blotter-lifecycle" : "");
      tr.dataset.model = r.model;
      tr.dataset.symbol = r.symbol;
      tr.dataset.side = r.side;
      tr.dataset.seq = r.seq;
      var t = (r.sim_ts || "").slice(11, 19);
      var qty = r.fill_qty != null ? r.fill_qty : r.intent_qty;
      var pnlClass = r.sim_pnl == null ? "" : Number(r.sim_pnl) >= 0 ? "pos" : "neg";
      var pnlText = r.sim_pnl == null ? "—" : (Number(r.sim_pnl) >= 0 ? "+" : "") + Number(r.sim_pnl).toFixed(2);
      tr.innerHTML =
        "<td>" + t + "</td>" +
        "<td>" + r.model + "</td>" +
        "<td>" + r.symbol + "</td>" +
        "<td>" + fmtSide(r.side) + "</td>" +
        '<td class="mono">' + fmtNum(qty, 4) + "</td>" +
        '<td class="mono">' + fmtNum(r.fill_px, 4) + "</td>" +
        '<td class="mono">' + fmtNum(r.fee, 4) + "</td>" +
        '<td class="mono">' + fmtNum(r.slippage_bps, 1) + "</td>" +
        '<td class="mono ' + pnlClass + '">' + pnlText + "</td>" +
        '<td class="' + verdictClass(r.verdict) + '" title="' + (r.rule_hits || []).join(", ") + '">' +
        r.verdict + (r.partial ? " (partial)" : "") + "</td>";
      body.appendChild(tr);
    });
    collectBlotterFilterOptions();
    applyBlotterFilters();
  }

  function handleBlotterFrame(rows) {
    if (!Array.isArray(rows) || !rows.length) return;
    paintBlotter(rows);
    var maxSeq = rows[rows.length - 1].seq;
    if (lastBlotterSeq === null) {
      lastBlotterSeq = maxSeq; // baseline on first frame -- don't alert for rows already on the page
      return;
    }
    var newFills = rows.filter(function (r) { return r.seq > lastBlotterSeq && r.fill_qty != null; });
    newFills.forEach(function (r) {
      toast(r.model + " " + r.side + " " + Number(r.fill_qty).toFixed(4) + " @ " + r.fill_px + " (sim)", "ok");
      pulseModelCell(r.model);
      flashBlotterRow(r.seq);
    });
    if (newFills.length && soundEnabled()) playFillSound();
    lastBlotterSeq = maxSeq;
  }

  function initBlotterFilters() {
    var modelSel = document.getElementById("blotter-filter-model");
    if (!modelSel) return;
    collectBlotterFilterOptions();
    ["blotter-filter-model", "blotter-filter-symbol", "blotter-filter-side"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", applyBlotterFilters);
    });
    var soundToggle = document.getElementById("blotter-sound-toggle");
    if (soundToggle) {
      soundToggle.checked = soundEnabled();
      soundToggle.addEventListener("change", function () {
        if (window.localStorage) {
          window.localStorage.setItem("lqe-blotter-sound", soundToggle.checked ? "1" : "0");
        }
      });
    }
  }

  // -- Engine Room conversation (Intel view, docs/13 M21) ----------------
  // A timeline scrubber replays the conversation exactly as it was at any
  // past seq -- same /api/graph?at_seq= pattern the Engine view already
  // uses, since runs are deterministic.

  function paintConversation(payload) {
    var feed = document.getElementById("convo-feed");
    if (!feed) return;
    var scrubber = document.getElementById("convo-scrubber");
    var label = document.getElementById("convo-seq-label");
    if (scrubber) { scrubber.max = payload.max_seq; scrubber.value = payload.at_seq; }
    if (label) label.textContent = "seq " + payload.at_seq + " / " + payload.max_seq;
    if (!payload.messages.length) {
      feed.innerHTML = '<div class="narr" id="convo-empty">No autonomy steps recorded yet ' +
        "— run <code>lqe autopilot</code> and point the desk at its audit log.</div>";
      return;
    }
    feed.innerHTML = "";
    payload.messages.forEach(function (m) {
      var div = document.createElement("div");
      var cls = "convo-msg convo-" + m.participant.toLowerCase();
      if (m.kind === "card") cls += " convo-card";
      if (m.verdict) cls += " convo-verdict-" + m.verdict.toLowerCase();
      div.className = cls;
      var detail = m.detail
        ? '<details><summary>Details</summary><div class="convo-detail">' + m.detail + "</div></details>"
        : "";
      div.innerHTML =
        '<span class="convo-who">' + m.participant + "</span>" +
        '<span class="convo-text">' + m.text + "</span>" + detail;
      feed.appendChild(div);
    });
  }

  function loadConversation(atSeq) {
    var url = "/api/conversation" + (atSeq != null ? "?at_seq=" + atSeq : "");
    fetch(url).then(function (r) { return r.json(); }).then(paintConversation);
  }

  function initConversationScrubber() {
    var scrubber = document.getElementById("convo-scrubber");
    if (!scrubber) return;
    scrubber.addEventListener("input", function () {
      loadConversation(parseInt(scrubber.value, 10));
    });
  }

  // Frames carry the reader's max seq; between live polls the server sends
  // the identical frame every 2s ping, so skip the tape/blotter DOM
  // rebuilds when nothing changed (perf phase 4). Session/kill paints stay
  // unconditional -- they're a few textContent writes and the kill state
  // must never be gated behind a stale-seq heuristic.
  var lastFrameSeq = null;

  function apply(payload) {
    if (payload.snapshot) {
      paintSession(payload.snapshot);
      paintKill(payload.snapshot);
    }
    var unchanged = payload.seq !== undefined && payload.seq === lastFrameSeq;
    if (payload.seq !== undefined) lastFrameSeq = payload.seq;
    if (unchanged) return;
    if (payload.tape) paintTape(payload.tape);
    if (payload.blotter) handleBlotterFrame(payload.blotter);
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

  // -- toasts (aria-live feedback, docs/13 M19) --------------------------
  // A structured component, not a console line -- the honesty/no-stdout
  // rule (docs/11 §11.9) applies to feedback toasts too.

  function toast(message, kind) {
    var host = document.getElementById("toasts");
    if (!host) return;
    var el = document.createElement("div");
    el.className = "toast" + (kind ? " " + kind : "");
    el.textContent = message;
    host.appendChild(el);
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 4000);
  }

  // calm, plain-language copy for the control toasts (V5 M26) instead of
  // echoing the raw command string back at the operator.
  var CONTROL_MESSAGES = {
    KILL: "Stopped. Nothing is running.",
    CLEAR_KILL: "Cleared — resuming normal operation.",
  };

  function control(command) {
    var operator = window.prompt("Operator name (required, human-only):", "");
    if (!operator) return;
    fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: command, operator: operator }),
    }).then(function () {
      toast(CONTROL_MESSAGES[command] || (command + " acknowledged."), "ok");
      setTimeout(function () { location.reload(); }, 700);
    });
  }

  var AUTOPILOT_MESSAGES = {
    AUTOPILOT_ON: "Autopilot engaged — I'll research and validate; take the wheel anytime.",
    AUTOPILOT_OFF: "Autopilot disengaged — you have the wheel.",
  };

  function autopilot(command) {
    // no operator prompt for a non-destructive toggle; the audited
    // ControlEvent records source=ui
    fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: command, operator: "desk-operator" }),
    }).then(function () {
      toast(AUTOPILOT_MESSAGES[command] || (command + " acknowledged."), "ok");
      setTimeout(function () { location.reload(); }, 700);
    });
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
      // the poll response is the source of truth -- always clears whatever
      // disabled/spinner state startOrStopLive set optimistically on click.
      toggleBtn.disabled = false;
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
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Stopping…'; }
      fetch("/api/jobs/live/stop", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (body) { toast(body.stopped ? "Live session stopped." : "Nothing was running.", "ok"); })
        .then(pollJobs);
      return;
    }
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Starting…'; }
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
    })
      .then(function () { toast("Live session starting…", "ok"); })
      .then(pollJobs);
  }

  function startIngest() {
    fetch("/api/jobs/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        adapter: "ccxt", exchange: "binance", symbol: "BTC-USDT", timeframe: "1m",
        root: "data",
      }),
    })
      .then(function () { toast("Ingest started.", "ok"); })
      .then(pollJobs);
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
    })
      .then(function () { toast("Backtest started.", "ok"); })
      .then(pollBacktest);
  }

  // weighty KILL (V5 M26): press-and-hold, not a single click, so it can't
  // fire from an accidental tap. `.kill-fill` (desk.css) visualizes the
  // hold; releasing early cancels with no action taken.
  var KILL_HOLD_MS = 550;

  function wireKillHold(kill) {
    var timer = null;
    var holding = false;

    function fire() {
      holding = false;
      kill.classList.remove("holding");
      var willKill = !kill.classList.contains("armed");
      var dot = document.getElementById("feed-dot");
      if (dot) dot.classList.toggle("off", willKill); // instant feedback; the reload confirms it
      control(willKill ? "KILL" : "CLEAR_KILL");
    }

    function start(e) {
      if (holding) return;
      holding = true;
      kill.classList.add("holding");
      timer = setTimeout(fire, KILL_HOLD_MS);
    }

    function cancel() {
      if (!holding) return;
      holding = false;
      clearTimeout(timer);
      kill.classList.remove("holding");
    }

    kill.addEventListener("mousedown", start);
    kill.addEventListener("touchstart", start, { passive: true });
    kill.addEventListener("mouseup", cancel);
    kill.addEventListener("mouseleave", cancel);
    kill.addEventListener("touchend", cancel);
    kill.addEventListener("touchcancel", cancel);
    kill.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); start(); }
    });
    kill.addEventListener("keyup", function (e) {
      if (e.key === "Enter" || e.key === " ") cancel();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var kill = document.getElementById("kill-btn");
    if (kill) wireKillHold(kill);
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
      var map = {
        F1: "/", F2: "/catalog", F3: "/research", F4: "/intel",
        F5: "/risk", F6: "/daily", F7: "/engine", F8: "/blotter",
      };
      if (map[e.key]) { e.preventDefault(); location.href = map[e.key]; }
    });
    initBlotterFilters();
    initConversationScrubber();
    connect();
  });
})();
