(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("data").textContent);
  var REDUCE = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var $ = function (id) { return document.getElementById(id); };
  var cssv = function (n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); };
  var rgb = function (n, a) { return "rgb(" + cssv(n) + (a == null ? "" : " / " + a) + ")"; };
  var V = function (n, a) { return "rgb(var(" + n + ")" + (a == null ? "" : " / " + a) + ")"; };
  var fmt = function (n) { return Math.round(n).toLocaleString("en-US"); };
  var clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  var ease = function (t) { return 1 - Math.pow(1 - t, 3); };
  var FEMA = ["No damage", "Affected", "Minor", "Major", "Destroyed"];
  var FKEY = ["no_damage", "affected", "minor", "major", "destroyed"];
  var FVAR = ["--f0", "--f1", "--f2", "--f3", "--f4"];
  var NS = "http://www.w3.org/2000/svg";

  function h(tag, attrs, parent, text) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) { if (k === "style") e.style.cssText = attrs[k]; else if (k === "class") e.className = attrs[k]; else e.setAttribute(k, attrs[k]); }
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  // SVG element; colours go through style so CSS variables resolve in every browser
  function s(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs || {}) {
      var v = attrs[k];
      if ((k === "fill" || k === "stroke") && String(v).indexOf("var(") >= 0) e.style[k] = v; else e.setAttribute(k, v);
    }
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  // run fn the first time node is on screen (straight away when that cannot be observed)
  function onView(node, fn) {
    if (REDUCE || !("IntersectionObserver" in window)) return;
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { io.disconnect(); fn(); } });
    }, { threshold: 0.25 });
    io.observe(node);
  }
  // bars are drawn at their final size, then replay a grow-in when first seen
  function grow(nodes, prop, values) {
    nodes.forEach(function (n, i) { n.style[prop] = values[i]; });
    if (!nodes.length) return;
    onView(nodes[0].parentNode, function () {
      nodes.forEach(function (n) { n.style.transition = "none"; n.style[prop] = "0"; });
      void nodes[0].offsetWidth;
      nodes.forEach(function (n, i) { n.style.transition = ""; n.style[prop] = values[i]; });
    });
  }
  var redraws = [];
  function redrawAll() { redraws.forEach(function (f) { f(); }); }

  /* ================= hero: the read, replayed over Old Fort ================= */
  (function field() {
    var c = $("field"), ctx = c.getContext("2d"), hero = c.parentElement;
    var W = 0, H = 0, pts = [], cols = [], t0 = performance.now(), visible = true, raf = 0;
    var SWEEP = 7500, HOLD = 3800, FADE = 900;
    function size() {
      var dpr = Math.min(2, window.devicePixelRatio || 1);
      W = hero.clientWidth; H = hero.clientHeight;
      c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // cover the hero with the town's bounding box, centred on the town itself
      var fw = Math.max(W, H * D.aspect) * 1.04, fh = fw / D.aspect;
      var ox = (W - fw) / 2 + W * 0.07, oy = clamp(H / 2 - 0.36 * fh, H - fh, 0);
      pts = D.S.map(function (p) { return [ox + p[0] / 1000 * fw, oy + p[1] / 1000 * fh, p[2]]; });
      cols = FVAR.map(function (v) { return cssv(v).split(" ").join(","); });
    }
    function draw(now) {
      var t = (now - t0) % (SWEEP + HOLD + FADE);
      var sx = REDUCE ? W * 2 : t < SWEEP ? -40 + (W + 120) * (t / SWEEP) : W * 2;
      var out = REDUCE ? 1 : t > SWEEP + HOLD ? 1 - (t - SWEEP - HOLD) / FADE : 1;
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i], k = clamp((sx - p[0]) / 46, 0, 1) * out;
        if (p[1] < -4 || p[1] > H + 4) continue;
        if (k <= 0) { ctx.fillStyle = "rgba(236,237,235,0.14)"; ctx.fillRect(p[0] - 0.8, p[1] - 0.8, 1.6, 1.6); continue; }
        var lv = p[2], flare = k < 1 ? Math.sin(k * Math.PI) * 4.5 : 0;
        var r = (lv >= 3 ? 2.7 : lv >= 1 ? 2.1 : 1.5) + flare;
        ctx.fillStyle = "rgba(" + (lv < 0 ? "150,156,168" : cols[lv]) + "," + (lv < 1 ? 0.5 : 0.92) * Math.min(1, k * 1.5) + ")";
        ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 6.2832); ctx.fill();
      }
      if (!REDUCE && t < SWEEP) {
        var g = ctx.createLinearGradient(sx - 120, 0, sx, 0);
        g.addColorStop(0, "rgba(96,148,255,0)"); g.addColorStop(1, "rgba(96,148,255,0.16)");
        ctx.fillStyle = g; ctx.fillRect(sx - 120, 0, 120, H);
        ctx.fillStyle = "rgba(96,148,255,0.95)"; ctx.fillRect(sx - 1, 0, 2, H);
      }
    }
    function loop(now) { if (visible && !document.hidden) draw(now); raf = requestAnimationFrame(loop); }
    size(); draw(t0 + SWEEP + 10);
    window.addEventListener("resize", function () { size(); draw(performance.now()); });
    if (!REDUCE) {
      if ("IntersectionObserver" in window) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }).observe(hero);
      raf = requestAnimationFrame(loop);
    }
  })();

  // hero figures count up once
  if (!REDUCE) Array.prototype.forEach.call(document.querySelectorAll(".hero-stats .n"), function (n) {
    var to = +n.getAttribute("data-to"), pre = n.getAttribute("data-prefix") || "", suf = n.getAttribute("data-suffix") || "", t0 = performance.now();
    (function tick(now) { var k = clamp((now - t0) / 1300, 0, 1); n.textContent = pre + fmt(to * ease(k)) + suf; if (k < 1) requestAnimationFrame(tick); })(t0);
  });

  /* ================= hero: pipeline with a travelling pulse ================= */
  (function pipe() {
    var svg = $("pipe"), N = 7, w = 116, gap = 23, y = 12, hh = 58;
    var labs = ["point + event", "before / after", "every structure", "outline to roof", "four readings", "five probabilities", "review + outputs"];
    var kick = ["REQUEST", "IMAGERY", "STRUCTURES", "ALIGN", "EVIDENCE", "FUSION", "CALL"];
    var nodes = [];
    var f = function (i) { return "rgb(" + cssv(FVAR[i]) + ")"; };
    for (var i = 0; i < N; i++) {
      var x = 8 + i * (w + gap), g = s("g", { class: "node" }, svg);
      s("rect", { class: "box", x: x, y: y, width: w, height: hh, rx: 6 }, g);
      s("text", { x: x, y: 8 }, g, kick[i]);
      s("text", { class: "lab", x: x + w / 2, y: y + hh + 18, "text-anchor": "middle" }, g, labs[i]);
      var cx = x + w / 2, cy = y + hh / 2, a = "rgb(96,148,255)", d = "rgb(160,164,172)";
      if (i === 0) { s("circle", { cx: cx, cy: cy - 4, r: 9, fill: "none", stroke: a, "stroke-width": 2 }, g); s("circle", { cx: cx, cy: cy - 4, r: 2.6, fill: a }, g); s("path", { d: "M" + (cx - 5) + " " + (cy + 4) + " L" + cx + " " + (cy + 15) + " L" + (cx + 5) + " " + (cy + 4), fill: "none", stroke: a, "stroke-width": 2 }, g); }
      if (i === 1) { s("rect", { x: cx - 40, y: cy - 14, width: 36, height: 28, rx: 2, fill: d, opacity: 0.35, stroke: "none" }, g); s("rect", { x: cx + 4, y: cy - 14, width: 36, height: 28, rx: 2, fill: d, opacity: 0.75, stroke: "none" }, g); }
      if (i === 2) [[-36, -12, 18, 12], [-10, -4, 14, 16], [12, -14, 20, 12], [-30, 6, 14, 10], [18, 4, 16, 12]].forEach(function (r) { s("rect", { x: cx + r[0], y: cy + r[1], width: r[2], height: r[3], fill: "none", stroke: a, "stroke-width": 1.5 }, g); });
      if (i === 3) { s("rect", { x: cx - 22, y: cy - 4, width: 34, height: 20, fill: "none", stroke: "rgb(255,214,64)", "stroke-width": 1.4, "stroke-dasharray": "4 3" }, g); s("rect", { x: cx - 12, y: cy - 14, width: 34, height: 20, fill: "rgba(96,148,255,0.18)", stroke: a, "stroke-width": 1.8 }, g); }
      if (i === 4) [0, 1, 2, 3].forEach(function (k) { [8, 14, 20, 11, 6].forEach(function (hgt, j) { s("rect", { x: cx - 44 + k * 23 + j * 4, y: cy + 14 - ((hgt + k * 5 + j * 3) % 22 + 4), width: 3, height: (hgt + k * 5 + j * 3) % 22 + 4, fill: f(j), stroke: "none", opacity: k === 3 ? 0.3 : 1 }, g); }); });
      if (i === 5) { var xx = cx - 42; [0.05, 0.21, 0.66, 0.08].forEach(function (p, j) { s("rect", { x: xx, y: cy - 8, width: 84 * p, height: 16, fill: f(j + 1), stroke: "none" }, g); xx += 84 * p; }); }
      if (i === 6) { s("circle", { cx: cx - 20, cy: cy, r: 11, fill: "none", stroke: a, "stroke-width": 2 }, g); s("path", { d: "M" + (cx - 25) + " " + cy + " l4 4 l7 -8", fill: "none", stroke: a, "stroke-width": 2 }, g); s("rect", { x: cx + 6, y: cy - 13, width: 20, height: 26, rx: 2, fill: "none", stroke: d, "stroke-width": 1.5 }, g); s("path", { d: "M" + (cx + 10) + " " + (cy - 5) + " h12 M" + (cx + 10) + " " + cy + " h12 M" + (cx + 10) + " " + (cy + 5) + " h8", stroke: d, "stroke-width": 1.3, fill: "none" }, g); }
      if (i < N - 1) s("path", { class: "conn", d: "M" + (x + w + 3) + " " + cy + " H" + (x + w + gap - 3) }, svg);
      nodes.push(g);
    }
    var pulse = s("circle", { r: 3.6, fill: "rgb(96,148,255)", cy: y + hh / 2, cx: -10 }, svg);
    if (REDUCE) { nodes.forEach(function (n) { n.classList.add("lit"); }); return; }
    var t0 = performance.now(), LEG = 620, total = LEG * N + 1500;
    (function tick(now) {
      var t = (now - t0) % total, pos = t / LEG;
      nodes.forEach(function (n, i) { n.classList.toggle("lit", pos >= i + 0.3); });
      var i0 = Math.min(N - 1, Math.floor(pos)), fr = clamp(pos - i0, 0, 1);
      // rest on a node, then travel to the next one
      pulse.setAttribute("cx", pos >= N ? -10 : 8 + i0 * (w + gap) + w * 0.5 + (i0 < N - 1 ? (w + gap) * clamp((fr - 0.45) / 0.55, 0, 1) : 0));
      requestAnimationFrame(tick);
    })(t0);
  })();

  /* ================= 01 timings + job replay ================= */
  (function timings() {
    var names = { cnn: "Classifier reads every roof", evidence: "Change, tarps, cloud and canopy checks", align: "Outlines moved onto roofs", process: "Images co-registered", collect: "Structures collected", fusion: "Evidence fused", plan: "Dates checked" };
    var rows = Object.keys(D.timings).map(function (k) { return [k, D.timings[k]]; }).sort(function (a, b) { return b[1] - a[1]; });
    var total = rows.reduce(function (t, r) { return t + r[1]; }, 0), op = [1, 0.78, 0.6, 0.45, 0.34, 0.26, 0.2];
    var segs = rows.map(function (r, i) {
      var sp = h("span", { style: "opacity:" + op[i] }, $("tbar"));
      var d = h("div", {}, $("tlist")); h("i", { style: "opacity:" + op[i] }, d); h("span", {}, d, names[r[0]]); h("b", {}, d, (r[1] < 1 ? r[1].toFixed(2) : r[1].toFixed(1)) + " s");
      return sp;
    });
    grow(segs, "width", rows.map(function (r) { return Math.max(0.4, r[1] / total * 100) + "%"; }));
    $("tcap").textContent = "timings_sec in runs/" + D.run.id + "/manifest.json · total " + total.toFixed(1) + " s for " + fmt(D.assessed) + " structures with outlines";
  })();

  (function job() {
    var box = $("job"), steps = ["choosing imagery", "fetching imagery", "assessing structures", "estimating people", "writing brief"], dur = [900, 2300, 3400, 1200, 900, 2400];
    var hd = h("div", { class: "hd" }, box); h("b", {}, hd, "Old Fort"); var stat = h("span", {}, hd, "");
    var st = h("div", { class: "st" }, box, "");
    var ol = h("ol", {}, box), lis = steps.map(function (t) { return h("li", {}, ol, t); });
    var bar = h("div", {}, h("div", { class: "bar" }, box));
    function show(i, frac) {
      lis.forEach(function (li, k) { li.className = k < i ? "past" : k === i ? "now" : ""; });
      var done = i >= steps.length;
      stat.textContent = done ? "complete" : "running";
      st.textContent = done ? "Complete · Maxar Open Data satellite" : i === 0 ? "Running" : "Running · Maxar Open Data satellite";
      bar.style.width = Math.min(100, (i + frac) / steps.length * 100) + "%";
    }
    if (REDUCE) { show(steps.length, 0); return; }
    var total = dur.reduce(function (a, b) { return a + b; }, 0), t0 = performance.now();
    (function tick(now) {
      var t = (now - t0) % total, i = 0;
      while (i < dur.length - 1 && t > dur[i]) { t -= dur[i]; i++; }
      show(i, i < steps.length ? t / dur[i] : 0);
      requestAnimationFrame(tick);
    })(t0);
  })();

  /* ================= 02 the windows on a timeline ================= */
  (function time() {
    var svg = $("time"), day = 86400000, inc = Date.parse(D.dates.incident), X0 = 46, XB = 520, X1 = 856, Y = 126;
    // two scales, joined at the incident: years of "before", months of "after"
    var x = function (iso) { var d = (Date.parse(iso) - inc) / day; return d < 0 ? XB + d / 1500 * (XB - X0) : XB + d / 250 * (X1 - XB); };
    s("rect", { x: X0, y: Y - 9, width: XB - X0 - 1, height: 18, rx: 3, fill: V("--ink-faint", 0.22) }, svg);
    s("rect", { x: XB + 1, y: Y - 9, width: X1 - XB - 1, height: 18, rx: 3, fill: V("--accent", 0.22) }, svg);
    s("text", { x: X0, y: 22, class: "t-b" }, svg, "Pre-event window");
    s("text", { x: X0, y: 40, class: "t-d" }, svg, "up to 1,500 days before, never the day itself");
    s("text", { x: X1, y: 22, class: "t-b", "text-anchor": "end" }, svg, "Post-event window");
    s("text", { x: X1, y: 40, class: "t-d", "text-anchor": "end" }, svg, "day 0 to day 250");
    s("line", { x1: XB, y1: 14, x2: XB, y2: Y + 22, stroke: V("--f3"), "stroke-width": 2 }, svg);
    s("text", { x: XB - 9, y: 66, class: "t-b", "text-anchor": "end" }, svg, "incident begins 25 Sep 2024");
    s("text", { x: XB - 9, y: 82, class: "t-d", "text-anchor": "end" }, svg, "from OpenFEMA, DR-4827-NC");
    ["2021", "2022", "2023", "2024"].forEach(function (yr) { var xx = x(yr + "-01-01"); s("line", { x1: xx, y1: Y + 9, x2: xx, y2: Y + 15, stroke: V("--ink-faint") }, svg); s("text", { x: xx, y: Y + 28, class: "t-m", "text-anchor": "middle" }, svg, yr); });
    [["2025-01-01", "Jan 2025"], ["2025-04-01", "Apr"]].forEach(function (m) { var xx = x(m[0]); s("line", { x1: xx, y1: Y + 9, x2: xx, y2: Y + 15, stroke: V("--ink-faint") }, svg); s("text", { x: xx, y: Y + 28, class: "t-m", "text-anchor": "middle" }, svg, m[1]); });
    var mark = function (iso, label, sub, anchor) {
      var xx = x(iso), tx = anchor === "start" ? xx + 10 : xx;
      s("line", { x1: xx, y1: Y + (anchor === "start" ? 7 : 34), x2: xx, y2: Y + (anchor === "start" ? 66 : 44), stroke: V("--ink-dim"), "stroke-dasharray": "2 3" }, svg);
      s("circle", { cx: xx, cy: Y, r: 6, fill: V("--surface"), stroke: V("--ink"), "stroke-width": 2 }, svg);
      s("text", { x: tx, y: Y + 58, class: "t-b", "text-anchor": anchor || "middle" }, svg, label);
      s("text", { x: tx, y: Y + 74, class: "t-d", "text-anchor": anchor || "middle" }, svg, sub);
    };
    mark(D.dates.pre, "Old Fort before", "Maxar, 7 Jan 2022");
    mark(D.dates.post, "Old Fort after", "Maxar, 2 Oct 2024, day 7", "start");
    s("rect", { x: x("2025-01-01"), y: Y - 4, width: x("2025-05-31") - x("2025-01-01"), height: 8, rx: 2, fill: V("--accent") }, svg);
    s("text", { x: x("2025-03-15"), y: Y - 20, class: "t-d", "text-anchor": "middle" }, svg, "NC OneMap post-Helene orthos, Jan to May 2025");
    ["2022-02-10", "2023-02-14", "2023-02-18"].forEach(function (d) { s("rect", { x: x(d) - 1.5, y: Y - 6, width: 3, height: 12, fill: V("--ink-dim") }, svg); });
    s("text", { x: x("2022-10-01"), y: Y - 20, class: "t-d", "text-anchor": "middle" }, svg, "NC OneMap statewide orthos, 2022 to 2023");
  })();

  (function pair() {
    var p = D.pair, t = function (k, n, sub) { var d = h("div", { class: "tile" }, $("pair")); h("div", { class: "k" }, d, k); h("div", { class: "n" }, d, n); h("div", { class: "s" }, d, sub); };
    t("View angle differs by", p.off_nadir_diff_deg.toFixed(1) + "°", "buildings lean differently in the two images; limit 15°");
    t("Sun elevation differs by", p.sun_elev_diff_deg.toFixed(1) + "°", "shadows fall differently; limit 15°");
    t("Season", "Jan/Oct", "leaf-off against early fall: vegetation change is not damage");
    t("Cloud in the after image", Math.round(p.post_clouds_pct) + "%", "checked roof by roof, never assumed clear");
    t("Co-registration residual", D.coreg.residual_px.toFixed(1) + " px", "one shift cannot line these two images up");
    t("Change evidence keeps", Math.round(p.e2_geometry_weight * 100) + "%", "of its weight: 0.6 becomes " + (0.6 * p.e2_geometry_weight).toFixed(2));
  })();

  /* ================= 03 sources + alignment ================= */
  (function sources() {
    var f = D.footprints, tot = f.usa + f.osm + f.nsi_only;
    var rows = [["FEMA USA Structures outlines", f.usa, V("--accent")], ["OpenStreetMap, gap-fill only", f.osm, V("--accent", 0.6)], ["Inventory points with no outline: counted, not assessed", f.nsi_only, V("--fna")]];
    var segs = rows.map(function (r) { var sp = h("span", { style: "background:" + r[2] }, $("srcbar"), fmt(r[1])); var k = h("span", {}, $("srckey")); h("i", { style: "background:" + r[2] }, k); k.appendChild(document.createTextNode(r[0] + " ")); h("b", {}, k, fmt(r[1])); return sp; });
    grow(segs, "width", rows.map(function (r) { return r[1] / tot * 100 + "%"; }));
  })();

  function chip(parent, src, ring, tag, extra) {
    var c = h("div", { class: "chip" }, parent);
    h("img", { src: src, alt: "", loading: "lazy" }, c);
    var sv = s("svg", { viewBox: "0 0 1 1", preserveAspectRatio: "none", "aria-hidden": "true" }, c);
    if (extra) s("polygon", { class: "outline-raw", points: extra.map(function (p) { return p.join(","); }).join(" ") }, sv);
    var poly = ring ? s("polygon", { class: "outline", points: ring.map(function (p) { return p.join(","); }).join(" ") }, sv) : null;
    if (tag) h("span", { class: "tag" }, c, tag);
    return { el: c, poly: poly };
  }

  (function align() {
    var a = D.alignex, box = $("alchip");
    box.classList.remove("chip");
    var c = chip(box, a.post, a.post_ring, "after image");
    var ghost = s("polygon", { class: "outline-raw", points: "" }, c.poly.parentNode);
    c.poly.parentNode.insertBefore(ghost, c.poly);
    var cur = 1, anim = 0, auto = !REDUCE;
    var setPts = function (k) { c.poly.setAttribute("points", a.post_ring.map(function (p, i) { var r = a.post_raw[i]; return (r[0] + (p[0] - r[0]) * k) + "," + (r[1] + (p[1] - r[1]) * k); }).join(" ")); };
    function go(to) {
      $("al-raw").setAttribute("aria-pressed", String(to === 0)); $("al-fit").setAttribute("aria-pressed", String(to === 1));
      ghost.setAttribute("points", (to === 1 ? a.post_raw : a.post_ring).map(function (p) { return p.join(","); }).join(" "));
      ghost.style.opacity = to === 1 ? "0.9" : "0.45";
      cancelAnimationFrame(anim);
      if (REDUCE) { cur = to; setPts(to); return; }
      var from = cur, t0 = performance.now();
      (function tick(now) { var k = clamp((now - t0) / 520, 0, 1); cur = from + (to - from) * ease(k); setPts(cur); if (k < 1) anim = requestAnimationFrame(tick); })(t0);
    }
    $("al-raw").onclick = function () { auto = false; go(0); };
    $("al-fit").onclick = function () { auto = false; go(1); };
    go(1);
    if (auto) { var flip = 1; setInterval(function () { if (!auto || document.hidden) return; flip = 1 - flip; go(flip); }, 2600); }
    var dx = a.al.dx_m, dy = a.al.dy_m;
    $("alread").innerHTML = "moved <b>" + Math.abs(dx).toFixed(1) + " m " + (dx < 0 ? "west" : "east") + "</b>, <b>" + Math.abs(dy).toFixed(1) + " m " + (dy < 0 ? "south" : "north") + "</b><br>roof-edge score at the new position: <b>×" + a.al.gain.toFixed(1) + "</b>";

    var cv = $("alplot"), ctx = cv.getContext("2d"), con = D.align_consensus["usa_structures:post"];
    function draw() {
      var dpr = Math.min(2, window.devicePixelRatio || 1), W = cv.clientWidth, H = cv.clientHeight;
      cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var R = 9, sc = Math.min(W, H) / (2 * R + 2), cx = W / 2, cy = H / 2;
      ctx.fillStyle = rgb("--surface-2"); ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = rgb("--line-strong"); ctx.lineWidth = 1; ctx.font = "11px " + cssv("--font-mono"); ctx.fillStyle = rgb("--ink-faint");
      [3, 6, 9].forEach(function (r) { ctx.beginPath(); ctx.arc(cx, cy, r * sc, 0, 6.2832); ctx.stroke(); ctx.fillText(r + " m", cx + r * sc + 3, cy - 3); });
      ctx.beginPath(); ctx.moveTo(cx - R * sc, cy); ctx.lineTo(cx + R * sc, cy); ctx.moveTo(cx, cy - R * sc); ctx.lineTo(cx, cy + R * sc); ctx.stroke();
      ctx.fillText("north", cx + 4, cy - R * sc + 10); ctx.fillText("east", cx + R * sc - 26, cy + 13);
      D.align_pts.forEach(function (p) { ctx.fillStyle = p[2] ? rgb("--ink-faint", 0.35) : rgb("--accent", 0.55); ctx.beginPath(); ctx.arc(cx + p[0] * sc, cy - p[1] * sc, 2.2, 0, 6.2832); ctx.fill(); });
      var px = cx + con.dx_m * sc, py = cy - con.dy_m * sc;
      ctx.strokeStyle = rgb("--ink"); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(px, py, 9, 0, 6.2832); ctx.moveTo(px - 14, py); ctx.lineTo(px + 14, py); ctx.moveTo(px, py - 14); ctx.lineTo(px, py + 14); ctx.stroke();
      ctx.fillStyle = rgb("--ink"); ctx.font = "600 12px " + cssv("--font-sans"); ctx.fillText("shared offset", px + 16, py - 8);
    }
    draw(); redraws.push(draw);
    $("alcap").textContent = "each dot: how far one USA Structures outline had to move in the after image (a sample of " + D.align_pts.length + ") · shared offset " + Math.abs(con.dx_m).toFixed(1) + " m west, " + con.dy_m.toFixed(1) + " m north · " + (D.context.FOOTPRINT_ALIGNMENT_WEAK || 0) + " outlines never found a crisp roof edge: they keep the shared offset and are flagged";
  })();

  /* ================= 04 scale strip + fusion explorer ================= */
  (function scale() {
    D.ex.slice(0, 5).forEach(function (e, i) {
      var l = h("div", { class: "lvl", style: "--c:" + V(FVAR[i]) }, $("scale")), im = h("div", { class: "imgs" }, l);
      chip(im, e.pre, e.pre_ring, "before"); chip(im, e.post, e.post_ring, "after");
      var m = h("div", { class: "meta" }, l); h("div", { class: "lab" }, m, FEMA[i]); h("div", { class: "cnt" }, m, fmt(D.counts[FKEY[i]]) + " structures");
    });
  })();

  (function explorer() {
    var WHY = { POSSIBLE_CLOUD_OR_HAZE: "cloud or haze over the roof in the after image", POSSIBLE_CLOUD: "cloud over the roof", IMAGE_NODATA: "the image has no data here", NO_WSE_SOURCE_ON_REACH: "no water-surface source on this reach", MISREGISTERED: "the two images do not line up here" };
    var REV = function (r) { return r.indexOf("LOW_CONFIDENCE") === 0 ? "top level under 50%" : r.indexOf("KEY_CHANNEL") === 0 ? "no classifier reading" : r.indexOf("UNCALIBRATED") === 0 ? "severe call before calibration" : r.indexOf("NONADJACENT") === 0 ? "top two levels are not neighbours" : r.toLowerCase(); };
    var NAME = { E1: "E1 · damage classifier", E2: "E2 · pixel change", E4: "E4 · blue tarps", E5: "E5 · flood depth" };
    var rows = [{ id: "P" }].concat(D.ex[0].ch.map(function (c) { return { id: c.id }; }));
    rows.forEach(function (r) {
      var row = h("div", { class: "chrow" }, $("fxrows")), a = h("div", {}, row);
      r.nm = h("div", { class: "nm" }, a, r.id === "P" ? "Prior" : NAME[r.id]); r.ds = h("div", { class: "ds" }, a, "");
      r.bars = h("div", { class: "bars5" }, row); r.b = FVAR.map(function (v) { return h("i", { style: "background:" + V(v) }, r.bars); });
      r.wt = h("div", { class: "wt" }, row, "");
    });
    var fb = FVAR.map(function (v) { return h("i", { style: "background:" + V(v) }, $("fxfused")); });
    var fl = FEMA.map(function (n) { var d = h("div", {}, $("fxlbl")); var b = h("b", {}, d, ""); d.appendChild(document.createTextNode(n)); return b; });
    var btns = D.ex.map(function (e, i) {
      var b = h("button", { type: "button", "aria-pressed": "false" }, $("picker")); h("img", { src: e.post, alt: "" }, b); h("span", {}, b, e.tag);
      b.onclick = function () { pick(i); }; return b;
    });
    function setBars(nodes, vals, full) { nodes.forEach(function (n, k) { n.style.height = (vals ? clamp(vals[k] / 0.8, 0, 1) * full : 0) + "px"; }); }
    function pick(i) {
      var e = D.ex[i];
      btns.forEach(function (b, k) { b.setAttribute("aria-pressed", String(k === i)); });
      var pr = $("fxpair"); pr.textContent = ""; chip(pr, e.pre, e.pre_ring, "before · 7 Jan 2022"); chip(pr, e.post, e.post_ring, "after · 2 Oct 2024");
      var v = $("fxverdict"); v.textContent = "";
      var lv = h("div", { class: "lv" }, v); h("i", { style: "background:" + V(FVAR[e.level]) }, lv); lv.appendChild(document.createTextNode(FEMA[e.level] + " · " + Math.round(e.conf * 100) + "%"));
      h("p", {}, v, e.note);
      if (e.review.length) e.review.forEach(function (r) { h("span", { class: "pill rev" }, v, "to review: " + REV(r)); }); else h("span", { class: "pill ok" }, v, "not sent to review");
      rows.forEach(function (r) {
        if (r.id === "P") { r.ds.textContent = "class mix assumed before any evidence"; setBars(r.b, D.prior, 44); r.wt.textContent = "start"; return; }
        var c = e.ch.filter(function (x) { return x.id === r.id; })[0], silent = c.ok && c.w === 0;
        r.bars.classList.toggle("off", !c.ok || silent);
        setBars(r.b, c.ok ? c.L : null, 44);
        r.wt.textContent = !c.ok ? "unavailable" : "weight " + (+c.w).toFixed(2).replace(/0$/, "");
        r.ds.textContent = !c.ok ? (WHY[c.why] || c.why.toLowerCase().replace(/_/g, " "))
          : r.id === "E1" ? "CNN read the after image as \"" + c.xbd.replace("-", " ") + "\""
          : r.id === "E2" ? "change is " + (c.z >= 0 ? "+" : "") + c.z.toFixed(1) + " robust deviations from the town's baseline"
          : silent ? "no new tarp: not evidence of no damage" : "new blue tarp on the roof";
      });
      setBars(fb, e.probs, 110);
      fl.forEach(function (b, k) { b.textContent = Math.round(e.probs[k] * 100) + "%"; });
    }
    pick(3);
  })();

  function hbars(host, rows, color) {
    var max = Math.max.apply(null, rows.map(function (r) { return r[1]; }));
    var fills = rows.map(function (r) { var row = h("div", { class: "row" }, host); h("span", { class: "lab" }, row, r[0]); var f = h("span", { class: "fill", style: "background:" + (r[2] || color) }, h("span", { class: "track" }, row)); h("span", { class: "val" }, row, fmt(r[1])); return f; });
    grow(fills, "width", rows.map(function (r) { return r[1] / max * 100 + "%"; }));
  }
  hbars($("cnnbars"), [["no damage", D.cnn["no-damage"]], ["minor damage", D.cnn["minor-damage"]], ["major damage", D.cnn["major-damage"]], ["destroyed", D.cnn["destroyed"]]], V("--meter"));
  hbars($("revbars"), [["Top level under 50%", D.review_reasons.LOW_CONFIDENCE], ["No classifier reading (cloud, haze, no data)", D.review_reasons.KEY_CHANNEL_E1_UNAVAILABLE], ["Major, before calibration", D.review_reasons.UNCALIBRATED_SEVERE_CALL_MAJOR], ["Destroyed, before calibration", D.review_reasons.UNCALIBRATED_SEVERE_CALL_DESTROYED]], V("--accent"));

  // a histogram with marked thresholds
  function hist(svg, data, x0, x1, marks, ticks, colorOf) {
    var W = 420, H = 190, L = 34, R = 10, T = 14, B = 34, max = Math.max.apply(null, data), bw = (W - L - R) / data.length;
    var X = function (v) { return L + (v - x0) / (x1 - x0) * (W - L - R); };
    s("line", { x1: L, y1: H - B, x2: W - R, y2: H - B, stroke: V("--line-strong") }, svg);
    [0.5, 1].forEach(function (k) { var y = H - B - (H - T - B) * k; s("line", { x1: L, y1: y, x2: W - R, y2: y, stroke: V("--line"), "stroke-dasharray": "2 4" }, svg); s("text", { x: L - 6, y: y + 4, class: "t-m", "text-anchor": "end" }, svg, fmt(max * k)); });
    data.forEach(function (v, i) { var hh = v / max * (H - T - B), mid = x0 + (i + 0.5) / data.length * (x1 - x0); s("rect", { x: L + i * bw + 0.6, y: H - B - hh, width: Math.max(1, bw - 1.2), height: hh, fill: colorOf(mid), rx: 1 }, svg); });
    marks.forEach(function (m) { s("line", { x1: X(m[0]), y1: T - 4, x2: X(m[0]), y2: H - B, stroke: V("--ink"), "stroke-width": 1.4, "stroke-dasharray": m[2] ? "" : "4 3" }, svg); if (m[1]) s("text", { x: X(m[0]) + 5, y: T + 6, class: "t-b" }, svg, m[1]); });
    ticks.forEach(function (t) { s("text", { x: X(t[0]), y: H - B + 16, class: "t-m", "text-anchor": "middle" }, svg, t[1]); });
  }
  hist($("zhist"), D.z_hist, -3, 9, [[1, ""], [2, ""], [3.5, ""]], [[-2, "−2"], [0, "0"], [1, "1"], [2, "2"], [3.5, "3.5"], [6, "6"], [8.5, "9+"]],
    function (z) { return V("--accent", z < 1 ? 0.3 : z < 2 ? 0.5 : z < 3.5 ? 0.75 : 1); });
  s("text", { x: 227, y: 186, class: "t-d", "text-anchor": "middle" }, $("zhist"), "robust deviations above the town median · four bands, four likelihood rows");
  hist($("confhist"), D.conf_hist, 0.2, 1, [[0.5, "review below 50%", 1]], [[0.2, "20%"], [0.5, "50%"], [0.75, "75%"], [1, "100%"]],
    function (c) { return c < 0.5 ? V("--accent") : V("--meter", 0.75); });

  /* ================= 05 census + map + expected counts ================= */
  (function census() {
    var host = $("census"), order = D.S.slice().sort(function (a, b) { return (b[2] - a[2]) || (b[3] - a[3]); });
    var frag = document.createDocumentFragment();
    order.forEach(function (p) { var i = document.createElement("i"); i.style.background = p[2] < 0 ? V("--fna") : V(FVAR[p[2]]); if (p[3]) i.className = "r"; frag.appendChild(i); });
    host.appendChild(frag);
    var key = $("cenkey");
    [4, 3, 2, 1, 0].forEach(function (i) { var k = h("span", {}, key); h("i", { style: "background:" + V(FVAR[i]) }, k); k.appendChild(document.createTextNode(FEMA[i] + " ")); h("b", {}, k, fmt(D.counts[FKEY[i]])); });
    var k = h("span", {}, key); h("i", { style: "background:" + V("--fna") }, k); k.appendChild(document.createTextNode("Not assessed ")); h("b", {}, k, fmt(D.not_assessed.total));
    var mode = function (rev) { host.classList.toggle("rev", rev); $("cz-level").setAttribute("aria-pressed", String(!rev)); $("cz-rev").setAttribute("aria-pressed", String(rev)); };
    $("cz-level").onclick = function () { mode(false); }; $("cz-rev").onclick = function () { mode(true); };
  })();

  (function map() {
    var cv = $("map"), ctx = cv.getContext("2d"), mode = "level";
    function draw() {
      var dpr = Math.min(2, window.devicePixelRatio || 1), W = cv.clientWidth, H = cv.clientHeight;
      cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var pad = 14, fh = H - 2 * pad, fw = fh * D.aspect; if (fw > W - 2 * pad) { fw = W - 2 * pad; fh = fw / D.aspect; }
      var ox = (W - fw) / 2, oy = (H - fh) / 2, cols = FVAR.map(function (v) { return cssv(v).split(" ").join(","); });
      ctx.clearRect(0, 0, W, H);
      var pass = function (front) {
        D.S.forEach(function (p) {
          var hot = mode === "level" ? p[2] >= 1 : mode === "review" ? p[3] === 1 : p[2] < 0;
          if (hot !== front) return;
          var x = ox + p[0] / 1000 * fw, y = oy + p[1] / 1000 * fh, col, r = 2;
          if (mode === "level") { col = p[2] < 0 ? "rgba(120,126,138,0.45)" : "rgba(" + cols[p[2]] + "," + (p[2] === 0 ? 0.55 : 0.95) + ")"; r = p[2] >= 3 ? 3 : 2.2; }
          else if (mode === "review") { col = p[3] ? "rgba(96,148,255,0.95)" : "rgba(150,156,168,0.28)"; r = p[3] ? 2.5 : 1.8; }
          else { col = p[2] < 0 ? "rgba(236,237,235,0.95)" : "rgba(150,156,168,0.25)"; r = p[2] < 0 ? 2.6 : 1.8; }
          ctx.fillStyle = col; ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
        });
      };
      pass(false); pass(true);
      $("mapn").textContent = mode === "level" ? fmt(D.n) + " structures · Old Fort, about 5 km across" : mode === "review" ? fmt(D.review) + " of " + fmt(D.assessed) + " assessed structures sent to a person" : fmt(D.not_assessed.total) + " inventory structures with no outline: counted, never read from imagery";
    }
    Array.prototype.forEach.call(cv.closest("figure").querySelectorAll("[data-mode]"), function (b) {
      b.onclick = function () { mode = b.getAttribute("data-mode"); Array.prototype.forEach.call(b.parentNode.children, function (o) { o.setAttribute("aria-pressed", String(o === b)); }); draw(); };
    });
    draw(); redraws.push(draw);
  })();

  (function expected() {
    var svg = $("expchart"), L = 110, R = 262, W = 860, top = 14, rh = 38, max = 800, X = function (v) { return L + v / max * (W - L - R); };
    [0, 200, 400, 600, 800].forEach(function (v) { s("line", { x1: X(v), y1: top - 4, x2: X(v), y2: top + rh * 5, stroke: V("--line") }, svg); s("text", { x: X(v), y: top + rh * 5 + 16, class: "t-m", "text-anchor": "middle" }, svg, v); });
    FKEY.forEach(function (k, i) {
      var y = top + i * rh + 6, e = D.expected[k], r = D.range[k], c = D.counts[k];
      s("text", { x: L - 12, y: y + 17, class: "t-b", "text-anchor": "end" }, svg, FEMA[i]);
      s("rect", { x: L, y: y, width: X(e) - L, height: 24, rx: 3, fill: V(FVAR[i]) }, svg);
      s("line", { x1: X(r[0]), y1: y + 12, x2: X(r[1]), y2: y + 12, stroke: V("--ink"), "stroke-width": 2 }, svg);
      [r[0], r[1]].forEach(function (v) { s("line", { x1: X(v), y1: y + 6, x2: X(v), y2: y + 18, stroke: V("--ink"), "stroke-width": 2 }, svg); });
      s("path", { d: "M" + X(c) + " " + (y - 3) + " v30", stroke: V("--ink-dim"), "stroke-width": 1.5, "stroke-dasharray": "3 3", fill: "none" }, svg);
      s("circle", { cx: X(c), cy: y - 3, r: 3, fill: V("--ink-dim") }, svg);
      s("text", { x: Math.max(X(c), X(r[1])) + 12, y: y + 17, class: "t-m" }, svg, "~" + fmt(e) + "  (" + r[0] + " to " + r[1] + ") · " + fmt(c) + " labels");
    });
  })();

  /* ================= 06 people ================= */
  (function people() {
    var svg = $("pplchart"), im = D.impact, L = 30, W = 860, R = 30, x0 = 220, x1 = 450, X = function (v) { return L + (v - x0) / (x1 - x0) * (W - L - R); };
    s("line", { x1: L, y1: 112, x2: W - R, y2: 112, stroke: V("--line-strong") }, svg);
    [250, 300, 350, 400, 450].forEach(function (v) { s("line", { x1: X(v), y1: 108, x2: X(v), y2: 116, stroke: V("--line-strong") }, svg); s("text", { x: X(v), y: 132, class: "t-m", "text-anchor": "middle" }, svg, v + " people"); });
    var band = function (lo, mid, hi, y, hgt, fill, label, strong) {
      s("rect", { x: X(lo), y: y, width: X(hi) - X(lo), height: hgt, rx: hgt / 2, fill: fill }, svg);
      s("circle", { cx: X(mid), cy: y + hgt / 2, r: strong ? 8 : 5, fill: V("--surface"), stroke: V("--ink"), "stroke-width": 2 }, svg);
      s("text", { x: X(mid), y: y - 8, class: strong ? "t-b" : "t-d", "text-anchor": "middle" }, svg, label);
    };
    var s0 = im.sensitivity_w_minor["0.0"], s1 = im.sensitivity_w_minor["0.25"], e = im.expected_displaced;
    band(s0[0], s0[1], s0[2], 78, 10, V("--meter", 0.3), "if Minor never displaces: ~" + fmt(s0[1]));
    band(s1[0], s1[1], s1[2], 78, 10, V("--meter", 0.3), "if a quarter of Minor does: ~" + fmt(s1[1]));
    band(e.p10, e.median, e.p90, 36, 18, V("--accent", 0.45), "~" + fmt(e.median) + " likely displaced (80% range " + fmt(e.p10) + " to " + fmt(e.p90) + ")", true);
    var t = $("tracts");
    im.tracts.forEach(function (tr) { var d = h("div", { class: "tile" }, t); h("div", { class: "k" }, d, tr.location.split(";")[0]); h("div", { class: "n" }, d, "~" + fmt(tr.expected_displaced)); h("div", { class: "s" }, d, fmt(tr.structures) + " homes assessed · social vulnerability " + tr.svi_percentile.toFixed(2) + " · need index " + fmt(tr.need_index)); });
    var d = h("div", { class: "tile" }, t); h("div", { class: "k" }, d, "Homes that could not be assessed"); h("div", { class: "n" }, d, fmt(im.unassessed_residential.structures)); h("div", { class: "s" }, d, "about " + fmt(im.unassessed_residential.occupants_nsi) + " residents, reported beside the estimate");
    d = h("div", { class: "tile" }, t); h("div", { class: "k" }, d, "Need index"); h("div", { class: "n" }, d, "× (1 + SVI)"); h("div", { class: "s" }, d, "displaced people scaled by the tract's CDC social vulnerability percentile");
  })();

  /* ================= 07 health ================= */
  (function health() {
    var NAMES = { damage_model: "damage model", usgs_water: "USGS water", nwps: "NOAA NWPS", nws_alerts: "NWS alerts", openfema: "OpenFEMA", nsi: "USACE NSI", usa_structures: "USA Structures", nc_orthos: "NC OneMap orthos", noaa_eri: "NOAA ERI", google_earth_engine: "Google Earth Engine", nasa_earthdata: "NASA Earthdata" };
    var col = { ok: V("--public"), stale: V("--f1"), down: V("--f3"), unconfigured: V("--ink-faint") }, word = { ok: "ok", stale: "stale", down: "down", unconfigured: "not set up" };
    D.health.filter(function (x) { return x.s !== "usgs_waterservices_legacy"; }).forEach(function (x) { var d = h("div", {}, $("health")); h("i", { style: "background:" + col[x.st] }, d); h("span", {}, d, NAMES[x.s] || x.s.replace(/_/g, " ")); h("b", {}, d, x.ms != null ? x.ms + " ms" : word[x.st]); });
    $("healthcap").textContent = "the data-source board as probed " + D.health_at.replace("T", " ").replace("Z", " UTC") + " · served from the last check while a new one runs in the background";
  })();

  (function store() {
    var S = D.store, MB = function (b) { return b >= 1e6 ? fmt(b / 1048576) + " MB" : b >= 1024 ? fmt(b / 1024) + " KB" : b + " bytes"; };
    var rows = [["raw/ imagery", S.raw, V("--meter", 0.75)], ["cache/ source responses", S.cache, V("--meter", 0.5)], ["output/ops/ results", S["output/ops"], V("--accent")]];
    var tot = rows.reduce(function (t, r) { return t + r[1]; }, 0), small = (S["ops_registry.yaml"] || 0) + (S["audit.log"] || 0) + (S["jobs.json"] || 0) + (S.labels || 0);
    var segs = rows.map(function (r) { var sp = h("span", { style: "background:" + r[2] }, $("storebar"), r[1] / tot > 0.08 ? MB(r[1]) : ""); var k = h("span", {}, $("storekey")); h("i", { style: "background:" + r[2] }, k); k.appendChild(document.createTextNode(r[0] + " ")); h("b", {}, k, MB(r[1])); return sp; });
    grow(segs, "width", rows.map(function (r) { return r[1] / tot * 100 + "%"; }));
    $("sliver").textContent = "Cannot be rebuilt: " + MB(small);
    h("small", {}, $("sliver"), "registry + audit log, " + (small / tot * 100).toFixed(4) + "% of the folder");
    $("storecap").textContent = "the data folder on the development machine, " + D.store_at + " · no analyst labels are recorded yet, and they will be the smallest and most valuable files here · run.py ops-backup archives labels, registry, audit log and results into one tar file";
  })();

  /* ================= 08 eight towns ================= */
  (function towns() {
    var svg = $("towns"), L = 168, W = 860, R = 250, top = 10, rh = 34, max = 280, X = function (v) { return L + v / max * (W - L - R); };
    [0, 100, 200].forEach(function (v) { s("line", { x1: X(v), y1: top, x2: X(v), y2: top + rh * D.areas.length, stroke: V("--line") }, svg); s("text", { x: X(v), y: top + rh * D.areas.length + 16, class: "t-m", "text-anchor": "middle" }, svg, v); });
    D.areas.forEach(function (a, i) {
      var y = top + i * rh + 6;
      s("text", { x: L - 12, y: y + 15, class: "t-b", "text-anchor": "end" }, svg, a.name);
      s("rect", { x: 4, y: y + 1, width: 44, height: 18, rx: 9, fill: a.role === "TEST" ? V("--ink-faint", 0.16) : a.role === "TUNE" ? V("--accent", 0.14) : V("--public", 0.16) }, svg);
      s("text", { x: 26, y: y + 14, class: "t-m", "text-anchor": "middle" }, svg, a.role.toLowerCase());
      s("rect", { x: L, y: y, width: Math.max(2, X(a.sev) - L), height: 20, rx: 3, fill: V("--f3") }, svg);
      s("line", { x1: X(a.lo), y1: y + 10, x2: X(a.hi), y2: y + 10, stroke: V("--ink"), "stroke-width": 2 }, svg);
      [a.lo, a.hi].forEach(function (v) { s("line", { x1: X(v), y1: y + 4, x2: X(v), y2: y + 16, stroke: V("--ink"), "stroke-width": 2 }, svg); });
      s("text", { x: X(a.hi) + 12, y: y + 15, class: "t-m" }, svg, "~" + a.sev + " of " + fmt(a.n) + " · " + fmt(a.review) + " to review · " + Math.round(a.rt) + " s");
    });
    var tot = D.areas.reduce(function (t, a) { return { n: t.n + a.n, s: t.s + a.sev, r: t.r + a.review }; }, { n: 0, s: 0, r: 0 });
    $("townscap").textContent = "expected structures at Major or Destroyed, with 80% range · all eight: " + fmt(tot.n) + " structures, ~" + fmt(tot.s) + " likely Major or Destroyed, " + fmt(tot.r) + " awaiting review · only the assessed ground, not county totals · tune areas may inform calibration, test areas are held out, ops areas are operational";
  })();

  $("foot").textContent = "Every figure is read from run " + D.run.id + " (generated " + D.run.generated.slice(0, 10) + ", code " + D.run.git + ") and the files beside it. Weights and thresholds are marked provisional in the config until analyst labels exist.";

  /* rail + theme */
  if ("IntersectionObserver" in window) {
    var links = {}; Array.prototype.forEach.call(document.querySelectorAll(".rail a"), function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { for (var k in links) links[k].classList.toggle("active", k === e.target.id); } }); }, { rootMargin: "-30% 0px -60% 0px" });
    Array.prototype.forEach.call(document.querySelectorAll("section.act"), function (sec) { io.observe(sec); });
  }
  new MutationObserver(redrawAll).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  if (window.matchMedia) { var mq = window.matchMedia("(prefers-color-scheme: dark)"); if (mq.addEventListener) mq.addEventListener("change", redrawAll); }
  window.addEventListener("resize", redrawAll);
})();
