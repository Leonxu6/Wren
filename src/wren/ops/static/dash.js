// W8.1 echarts init — 总览页 4 大 KPI sparkline + 6 mini + 6 大图表
(function () {
  var d = window.__dash || {};

  function sparkLine(id, data, color) {
    var el = document.getElementById(id);
    if (!el || !window.echarts) return;
    if (!data || data.length === 0) {
      el.innerHTML = '<div style="text-align:center;color:#d1d5db;font-size:11px;padding-top:8px">无数据</div>';
      return;
    }
    var c = echarts.init(el);
    c.setOption({
      grid: { left: 0, right: 0, top: 4, bottom: 0 },
      xAxis: { type: "category", show: false, data: data.map(function (_, i) { return i; }) },
      yAxis: { type: "value", show: false },
      tooltip: { show: true, formatter: function (p) { return p[0].data; } },
      series: [{
        data: data, type: "line", smooth: true, symbol: "none",
        lineStyle: { color: color || "#3b82f6", width: 2 },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: (color || "#3b82f6") + "33" }, { offset: 1, color: (color || "#3b82f6") + "00" }] } },
      }],
    });
  }

  // KPI top row sparkline (small under-card chart)
  sparkLine("spark-total", d.spark_turns, "#3b82f6");
  sparkLine("spark-active", d.spark_user_msgs, "#10b981");
  sparkLine("spark-lv2", d.spark_user_msgs, "#7c3aed");
  sparkLine("spark-cost", d.spark_tokens, "#f59e0b");

  // mini row sparkline
  sparkLine("mini-new", d.spark_user_msgs, "#3b82f6");
  sparkLine("mini-activation", d.spark_user_msgs, "#10b981");
  sparkLine("mini-d7", d.spark_silence, "#f59e0b");
  sparkLine("mini-turns", d.spark_turns, "#3b82f6");
  sparkLine("mini-silence", d.spark_silence, "#ef4444");

  // === Big chart: 等级分布(环形)===
  (function () {
    var el = document.getElementById("chart-levels");
    if (!el || !window.echarts) return;
    var dist = d.level_distribution || [];
    if (dist.length === 0) {
      el.innerHTML = '<div style="display:flex;height:100%;align-items:center;justify-content:center;color:#9ca3af">无用户数据</div>';
      return;
    }
    var c = echarts.init(el);
    var lvColors = ["#94a3b8", "#94a3b8", "#3b82f6", "#3b82f6", "#7c3aed", "#7c3aed", "#ec4899"];
    c.setOption({
      tooltip: { trigger: "item" },
      legend: { bottom: 0, type: "scroll", textStyle: { fontSize: 11 } },
      series: [{
        type: "pie",
        radius: ["45%", "70%"],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 4, borderColor: "#fff", borderWidth: 2 },
        label: { formatter: "{b}\n{c} 人", fontSize: 11 },
        data: dist.map(function (r) { return { name: "Lv" + r.lv, value: r.users, itemStyle: { color: lvColors[r.lv] || "#94a3b8" } }; }),
      }],
    });
  })();

  // === Big chart: 每晚跃迁(柱状堆叠)===
  (function () {
    var el = document.getElementById("chart-transitions");
    if (!el || !window.echarts) return;
    var rows = d.level_transitions || [];
    if (rows.length === 0) {
      el.innerHTML = '<div style="display:flex;height:100%;align-items:center;justify-content:center;color:#9ca3af">无夜结算记录</div>';
      return;
    }
    var c = echarts.init(el);
    c.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      grid: { left: 30, right: 12, top: 16, bottom: 36 },
      xAxis: { type: "category", data: rows.map(function (r) { return String(r.night).slice(5, 10); }), axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", axisLabel: { fontSize: 11 } },
      series: [
        { name: "升级", type: "bar", stack: "lv", data: rows.map(function (r) { return r.promotions || 0; }), itemStyle: { color: "#10b981" } },
        { name: "降级", type: "bar", stack: "lv", data: rows.map(function (r) { return -(r.regressions || 0); }), itemStyle: { color: "#f59e0b" } },
        { name: "冻结", type: "bar", stack: "lv", data: rows.map(function (r) { return -(r.new_freezes || 0); }), itemStyle: { color: "#ef4444" } },
        { name: "解冻", type: "bar", stack: "lv", data: rows.map(function (r) { return r.thaws || 0; }), itemStyle: { color: "#3b82f6" } },
      ],
    });
  })();

  // === Big chart: 每天 user_msgs(折线 14d)===
  (function () {
    var el = document.getElementById("chart-engagement");
    if (!el || !window.echarts) return;
    var rows = d.engagement_history || [];
    if (rows.length === 0) {
      el.innerHTML = '<div style="display:flex;height:100%;align-items:center;justify-content:center;color:#9ca3af">无活跃记录</div>';
      return;
    }
    var c = echarts.init(el);
    c.setOption({
      tooltip: { trigger: "axis" },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      grid: { left: 32, right: 32, top: 16, bottom: 36 },
      xAxis: { type: "category", data: rows.map(function (r) { return String(r.day).slice(5, 10); }), axisLabel: { fontSize: 11 } },
      yAxis: [
        { type: "value", name: "msgs", axisLabel: { fontSize: 11 } },
        { type: "value", name: "silence %", axisLabel: { fontSize: 11, formatter: "{value}%" }, splitLine: { show: false } },
      ],
      series: [
        { name: "user_msgs", type: "line", smooth: true, data: rows.map(function (r) { return r.user_msgs || 0; }), itemStyle: { color: "#3b82f6" }, areaStyle: { opacity: 0.15 } },
        { name: "silence_pct", type: "line", smooth: true, yAxisIndex: 1, data: rows.map(function (r) { return r.silence_pct || 0; }), itemStyle: { color: "#ef4444" } },
      ],
    });
  })();

  // === Big chart: 每天 cost(柱状 14d)===
  (function () {
    var el = document.getElementById("chart-cost");
    if (!el || !window.echarts) return;
    var rows = d.cost_history || [];
    var capRaw = (d.daily_cap || {}).cap || 0;
    if (rows.length === 0) {
      el.innerHTML = '<div style="display:flex;height:100%;align-items:center;justify-content:center;color:#9ca3af">无 cost 记录</div>';
      return;
    }
    var c = echarts.init(el);
    var series = [{
      name: "turns", type: "bar", data: rows.map(function (r) { return r.turns || 0; }),
      itemStyle: { color: "#f59e0b", borderRadius: [3, 3, 0, 0] },
    }];
    if (capRaw > 0) {
      series.push({
        name: "DAILY_CAP", type: "line", data: rows.map(function () { return capRaw; }),
        symbol: "none", lineStyle: { color: "#ef4444", type: "dashed", width: 1.5 },
      });
    }
    c.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      grid: { left: 32, right: 16, top: 16, bottom: 36 },
      xAxis: { type: "category", data: rows.map(function (r) { return String(r.day).slice(5, 10); }), axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", axisLabel: { fontSize: 11 } },
      series: series,
    });
  })();

  // === Big chart: 来源归因(横向柱)===
  (function () {
    var el = document.getElementById("chart-sources");
    if (!el || !window.echarts) return;
    var rows = d.sources_distribution || [];
    if (rows.length === 0) {
      el.innerHTML = '<div style="display:flex;height:100%;align-items:center;justify-content:center;color:#9ca3af">无来源记录</div>';
      return;
    }
    var c = echarts.init(el);
    c.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 80, right: 24, top: 16, bottom: 16 },
      xAxis: { type: "value", axisLabel: { fontSize: 11 } },
      yAxis: { type: "category", data: rows.map(function (r) { return r.source; }), axisLabel: { fontSize: 11 } },
      series: [{
        name: "new_users", type: "bar", data: rows.map(function (r) { return r.new_users || 0; }),
        itemStyle: { color: "#7c3aed", borderRadius: [0, 4, 4, 0] }, barWidth: 18,
        label: { show: true, position: "right", fontSize: 10 },
      }],
    });
  })();

  // === Big chart: 延迟 p50/p95(折线 7d)===
  (function () {
    var el = document.getElementById("chart-latency");
    if (!el || !window.echarts) return;
    var rows = d.latency_history || [];
    if (rows.length === 0) {
      el.innerHTML = '<div style="display:flex;height:100%;align-items:center;justify-content:center;color:#9ca3af">无延迟记录</div>';
      return;
    }
    var c = echarts.init(el);
    c.setOption({
      tooltip: { trigger: "axis" },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      grid: { left: 40, right: 16, top: 16, bottom: 36 },
      xAxis: { type: "category", data: rows.map(function (r) { return String(r.day).slice(5, 10); }), axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", axisLabel: { fontSize: 11, formatter: "{value}ms" } },
      series: [
        { name: "step1 p50", type: "line", smooth: true, data: rows.map(function (r) { return r.s1_p50 || 0; }), itemStyle: { color: "#3b82f6" } },
        { name: "step1 p95", type: "line", smooth: true, data: rows.map(function (r) { return r.s1_p95 || 0; }), itemStyle: { color: "#ef4444" }, lineStyle: { type: "dashed" } },
      ],
    });
  })();

  // window resize → echart resize
  window.addEventListener("resize", function () {
    document.querySelectorAll(".echart, .spark").forEach(function (el) {
      var inst = echarts.getInstanceByDom(el);
      if (inst) inst.resize();
    });
  });
})();
