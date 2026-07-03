// The neural-web scene (docs/05 §5.5, docs/10 M10). Renders the read-only
// GraphPayload from /api/graph as a force-directed web.
//
// Implementation note (a deliberate, flagged deviation — see
// viz3d/vendor/README.md): the spec names three.js + 3d-force-graph. Those
// are not vendorable in this offline build and the app is localhost-only
// with no CDN, so this is a dependency-free <canvas> force-graph that
// delivers the same acceptance criteria (real audit state, deterministic
// timeline replay, sandbox vs tracked visually distinct, honesty overlays,
// reduced-motion). Drop a real three.js/3d-force-graph bundle into
// viz3d/vendor/ and swap the renderer if the full WebGL scene is wanted.
(function () {
  "use strict";

  var COLORS = {
    LONG: "#35C08B", SHORT: "#F0524D", FIRED: "#F0A62A", HALTED: "#F0524D",
    ARMED: "#6B7A90", meta: "#7C7BF2", regime: "#6B7A90",
  };

  var canvas = document.getElementById("web");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var view = { x: 0, y: 0, scale: 1 };
  var nodes = [];
  var links = [];
  var byId = {};
  var hover = null;
  var selected = null;
  var maxSeq = 0;

  function resize() {
    var r = canvas.parentElement.getBoundingClientRect();
    canvas.width = r.width;
    canvas.height = r.height;
  }

  function nodeColor(n) {
    if (n.kind === "meta") return COLORS.meta;
    if (n.kind === "regime") return COLORS.regime;
    return COLORS[n.state] || COLORS.ARMED;
  }
  function nodeRadius(n) {
    if (n.kind === "meta") return 16;
    if (n.kind === "regime") return 12;
    return 7 + n.conviction * 9;
  }

  // seed positions: tracked core on the right (bright), sandbox swarm left
  function seed() {
    var w = canvas.width, h = canvas.height;
    nodes.forEach(function (n, i) {
      var region = n.kind === "tracked" ? 0.72 : n.kind === "meta" ? 0.5 : n.kind === "regime" ? 0.15 : 0.32;
      n.x = w * region + (Math.random() - 0.5) * 120;
      n.y = h * (0.2 + 0.6 * ((i % 7) / 6)) + (Math.random() - 0.5) * 60;
      n.vx = 0; n.vy = 0;
    });
  }

  function step() {
    // a light force sim: repulsion between nodes, spring along links, and a
    // gentle pull toward each node's region anchor x
    var w = canvas.width;
    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
      for (var j = i + 1; j < nodes.length; j++) {
        var b = nodes[j];
        var dx = a.x - b.x, dy = a.y - b.y;
        var d2 = dx * dx + dy * dy + 0.01;
        var f = 900 / d2;
        var d = Math.sqrt(d2);
        a.vx += (dx / d) * f; a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
      }
    }
    links.forEach(function (l) {
      var a = byId[l.source], b = byId[l.target];
      if (!a || !b) return;
      var dx = b.x - a.x, dy = b.y - a.y;
      var d = Math.sqrt(dx * dx + dy * dy) + 0.01;
      var f = (d - 120) * 0.008 * (0.4 + l.weight);
      a.vx += (dx / d) * f; a.vy += (dy / d) * f;
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    });
    nodes.forEach(function (n) {
      var anchor = n.kind === "tracked" ? 0.72 : n.kind === "meta" ? 0.5 : n.kind === "regime" ? 0.15 : 0.32;
      n.vx += (w * anchor - n.x) * 0.002;
      n.x += n.vx * 0.85; n.y += n.vy * 0.85;
      n.vx *= 0.86; n.vy *= 0.86;
    });
  }

  function draw() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(view.scale, 0, 0, view.scale, view.x, view.y);

    // region backdrops: dim sandbox (left), bright tracked (right)
    ctx.fillStyle = "rgba(124,123,242,0.03)";
    ctx.fillRect(canvas.width * 0.58, 0, canvas.width, canvas.height);

    links.forEach(function (l) {
      var a = byId[l.source], b = byId[l.target];
      if (!a || !b) return;
      ctx.strokeStyle = l.kind === "promotion" ? "rgba(53,192,139,0.55)"
        : l.kind === "attention" ? "rgba(124,123,242,0.4)" : "rgba(107,122,144,0.25)";
      ctx.lineWidth = 0.6 + l.weight * 2;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    });

    nodes.forEach(function (n) {
      var r = nodeRadius(n);
      if (n.status === "validated") {
        ctx.beginPath(); ctx.arc(n.x, n.y, r + 5, 0, 7); ctx.fillStyle = "rgba(53,192,139,0.15)"; ctx.fill();
      }
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7);
      ctx.fillStyle = nodeColor(n);
      ctx.globalAlpha = n.kind === "sandbox" ? 0.75 : 1;
      ctx.fill(); ctx.globalAlpha = 1;
      if (selected && selected.id === n.id) { ctx.strokeStyle = "#E9EEF5"; ctx.lineWidth = 1.5; ctx.stroke(); }
      ctx.fillStyle = "#9aa6b6"; ctx.font = "10px monospace";
      ctx.fillText(n.label, n.x + r + 3, n.y + 3);
    });
  }

  var ticks = 0;
  function loop() {
    if (!reduced && ticks < 400) { step(); ticks++; }
    draw();
    requestAnimationFrame(loop);
  }

  function screenToWorld(px, py) {
    return { x: (px - view.x) / view.scale, y: (py - view.y) / view.scale };
  }
  function nodeAt(px, py) {
    var p = screenToWorld(px, py);
    for (var i = nodes.length - 1; i >= 0; i--) {
      var n = nodes[i], dx = p.x - n.x, dy = p.y - n.y;
      if (dx * dx + dy * dy <= Math.pow(nodeRadius(n) + 3, 2)) return n;
    }
    return null;
  }

  function inspect(n) {
    var box = document.getElementById("inspector-body");
    if (!box) return;
    if (!n) { box.innerHTML = '<div class="mute">Hover or click a node.</div>'; return; }
    box.innerHTML =
      '<div class="im">' + n.label + '</div>' +
      '<div class="ik">' + n.kind + " · " + n.family + "</div>" +
      '<table class="kv2">' +
      row("State", n.state) + row("Status", n.status) +
      row("Sim return", n.sim_return.toFixed(2) + "%") +
      row("Sample (n)", n.n_trades) +
      row("Conviction", n.conviction.toFixed(2)) + "</table>";
  }
  function row(k, v) { return "<tr><td>" + k + "</td><td>" + v + "</td></tr>"; }

  function apply(payload) {
    nodes = payload.nodes.map(function (n) { return Object.assign({}, n); });
    links = payload.links;
    byId = {}; nodes.forEach(function (n) { byId[n.id] = n; });
    maxSeq = payload.max_seq;
    var sc = document.getElementById("scrubber");
    if (sc) { sc.max = maxSeq; sc.value = payload.at_seq; }
    var lbl = document.getElementById("seq-label");
    if (lbl) lbl.textContent = "seq " + payload.at_seq + " / " + maxSeq;
    ticks = 0; resize(); seed();
  }

  function load(atSeq) {
    var url = "/api/graph" + (atSeq != null ? "?at_seq=" + atSeq : "");
    fetch(url).then(function (r) { return r.json(); }).then(apply);
  }

  // interaction: pan (drag empty), zoom (wheel), hover/click a node
  var dragging = false, last = null;
  canvas.addEventListener("mousedown", function (e) {
    var n = nodeAt(e.offsetX, e.offsetY);
    if (n) { selected = n; inspect(n); } else { dragging = true; last = { x: e.offsetX, y: e.offsetY }; }
  });
  window.addEventListener("mouseup", function () { dragging = false; });
  canvas.addEventListener("mousemove", function (e) {
    if (dragging && last) { view.x += e.offsetX - last.x; view.y += e.offsetY - last.y; last = { x: e.offsetX, y: e.offsetY }; }
    else { var n = nodeAt(e.offsetX, e.offsetY); if (n !== hover) { hover = n; if (n) inspect(n); } }
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    var f = e.deltaY < 0 ? 1.1 : 0.9;
    view.scale = Math.max(0.3, Math.min(3, view.scale * f));
  }, { passive: false });

  var scrubber = document.getElementById("scrubber");
  if (scrubber) scrubber.addEventListener("input", function () { load(parseInt(scrubber.value, 10)); });

  window.addEventListener("resize", function () { resize(); });
  resize();
  load(null);
  loop();
})();
