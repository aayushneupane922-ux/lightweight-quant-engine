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

  document.addEventListener("DOMContentLoaded", function () {
    var kill = document.getElementById("kill-btn");
    if (kill) {
      kill.addEventListener("click", function () {
        control(kill.classList.contains("armed") ? "CLEAR_KILL" : "KILL");
      });
    }
    // keyboard-first mode switching (F1..F6 -> nav hrefs)
    document.addEventListener("keydown", function (e) {
      var map = { F1: "/", F2: "/catalog", F3: "/research", F5: "/risk", F6: "/daily" };
      if (map[e.key]) { e.preventDefault(); location.href = map[e.key]; }
    });
    connect();
  });
})();
