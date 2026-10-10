const byId = (id) => document.getElementById(id);
const previewUrls = [];
let selectedFiles = [];
let currentResult = null;
let resultChart = null;
let chartMode = "comparison";
let busy = false;
const colors = ["#2457c5", "#16866b", "#aa7020", "#b74f67", "#78828e"];
const format = (value) => Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const metricNames = { porosity: "孔隙度 (%)", permeability: "渗透率 (mD)" };
const chartTitles = { comparison: "样本孔渗对比", scatter: "孔隙度与渗透率关系", distribution: "样本数值分布", grades: "物性参考等级占比" };

window.lucide?.createIcons();
byId("dropArea").addEventListener("click", () => { if (!busy) byId("imageUpload").click(); });
["dragenter", "dragover", "dragleave", "drop"].forEach((name) => {
  byId("dropArea").addEventListener(name, (event) => event.preventDefault());
});
byId("dropArea").addEventListener("drop", (event) => handleFiles(event.dataTransfer.files));
byId("imageUpload").addEventListener("change", (event) => handleFiles(event.target.files));

function handleFiles(files) {
  if (busy) return;
  selectedFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
  previewUrls.splice(0).forEach((url) => URL.revokeObjectURL(url));
  byId("fileCount").textContent = selectedFiles.length ? `已选择 ${selectedFiles.length} 张图片` : "尚未选择图片";
  byId("previewGrid").replaceChildren();
  selectedFiles.forEach((file) => {
    const img = document.createElement("img");
    const url = URL.createObjectURL(file);
    previewUrls.push(url);
    img.src = url;
    img.alt = file.name;
    byId("previewGrid").appendChild(img);
  });
}

function showMessage(id, message) {
  byId(id).textContent = message;
  byId(id).classList.toggle("hidden", !message);
}

async function readResponse(response) {
  if (response.redirected || !response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("登录状态已失效或服务暂不可用，请刷新页面后重试。");
  }
  const payload = await response.json();
  if (!response.ok || payload.code !== 200) throw new Error(payload.msg || "操作失败，请重试。");
  return payload;
}

byId("submitBtn").addEventListener("click", async () => {
  if (!selectedFiles.length) return showMessage("errorTip", "请先上传岩心图像");
  const formData = new FormData();
  formData.append("rock_type", byId("rockType").value || "通用模型");
  selectedFiles.forEach((file) => formData.append("images", file));
  busy = true;
  ["submitBtn", "imageUpload", "rockType"].forEach((id) => { byId(id).disabled = true; });
  showMessage("errorTip", "");
  byId("emptyState").classList.add("hidden");
  byId("resultState").classList.add("hidden");
  byId("loadingState").classList.remove("hidden");
  byId("submitBtn").textContent = "识别中...";
  try {
    const payload = await readResponse(await fetch("/api/predict/", { method: "POST", body: formData }));
    currentResult = payload.data;
    byId("outliersOnly").checked = false;
    renderResult(currentResult);
  } catch (error) {
    showMessage("errorTip", error.message);
    byId("resultState").classList.toggle("hidden", !currentResult);
    byId("emptyState").classList.toggle("hidden", !!currentResult);
  } finally {
    busy = false;
    ["submitBtn", "imageUpload", "rockType"].forEach((id) => { byId(id).disabled = false; });
    byId("submitBtn").textContent = "开始识别";
    byId("loadingState").classList.add("hidden");
  }
});

function renderResult(data) {
  const s = data.summary;
  byId("resultState").classList.remove("hidden");
  const modelLabel = data.model_context?.label || data.rock_type;
  byId("resultMode").textContent = `${data.is_batch ? "批量" : "单张"}分析 · ${modelLabel}`;
  byId("porosityValue").textContent = format(s.avg_porosity);
  byId("permeabilityValue").textContent = format(s.avg_permeability);
  byId("reservoirClass").textContent = data.evaluation.reservoir_class;
  byId("analysisText").textContent = `按批次均值：${data.evaluation.porosity_desc}、${data.evaluation.permeability_desc}。逐样本等级见占比图和明细。`;
  byId("batchStats").classList.remove("hidden");
  byId("statCount").textContent = `${s.count} 张`;
  byId("statPoroRange").textContent = `${format(s.min_porosity)} ~ ${format(s.max_porosity)}%`;
  byId("statPermRange").textContent = `${format(s.min_permeability)} ~ ${format(s.max_permeability)} mD`;
  byId("statStd").textContent = `${format(s.std_porosity)}% / ${format(s.std_permeability)} mD`;
  byId("sampleBadge").textContent = `${s.count} 个样本 · ${s.outlier_indices.length} 个统计异常`;
  byId("demoNotice").classList.toggle("hidden", !data.model_context?.is_demo);
  byId("summaryInsights").replaceChildren(...s.insights.map((text) => {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    return paragraph;
  }));
  byId("analysisNote").textContent = s.analysis_note;
  const rows = Object.entries(s.metrics).map(([key, stats]) => makeRow([
    metricNames[key], format(stats.median), format(stats.std), stats.cv === null ? "不适用" : `${format(stats.cv * 100)}%`,
  ]));
  byId("statisticsBody").replaceChildren(...rows);
  showMessage("exportError", "");
  renderSamples();
  drawChart();
}

function makeRow(values) {
  const row = document.createElement("tr");
  values.forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.appendChild(cell);
  });
  return row;
}

function renderSamples() {
  const s = currentResult.summary;
  const filtered = currentResult.list.filter((item) => !byId("outliersOnly").checked || s.outlier_indices.includes(item.section_index));
  const rows = filtered.map((item) => {
    const flags = Object.entries(s.metrics).filter(([, stats]) => stats.outlier_indices.includes(item.section_index)).map(([key]) => key === "porosity" ? "孔隙度" : "渗透率");
    const row = makeRow([
      `#${item.section_index} ${item.filename}`, format(item.porosity), format(item.permeability),
      item.evaluation.reservoir_class, flags.length ? `${flags.join("、")}异常` : (s.count < 4 ? "样本不足，未筛查" : "未标记"),
    ]);
    row.classList.toggle("outlier-row", flags.length > 0);
    return row;
  });
  if (!rows.length) {
    const row = makeRow(["本批没有统计异常样本"]);
    row.firstChild.colSpan = 5;
    rows.push(row);
  }
  byId("sampleBody").replaceChildren(...rows);
}
byId("outliersOnly").addEventListener("change", renderSamples);

const tabs = Array.from(document.querySelectorAll("[data-chart-mode]"));
tabs.forEach((button, index) => {
  button.addEventListener("click", () => {
    chartMode = button.dataset.chartMode;
    tabs.forEach((tab) => {
      tab.setAttribute("aria-selected", String(tab === button));
      tab.tabIndex = tab === button ? 0 : -1;
    });
    byId("chartPanel").setAttribute("aria-labelledby", button.id);
    if (currentResult) drawChart();
  });
  button.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); tabs[next].focus(); tabs[next].click(); }
  });
});
byId("logScale").addEventListener("change", drawChart);
byId("distributionMetric").addEventListener("change", drawChart);

function histogram(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return { labels: [format(min)], counts: [values.length] };
  const bins = Math.min(10, Math.ceil(Math.sqrt(values.length)));
  const width = (max - min) / bins;
  const counts = new Array(bins).fill(0);
  values.forEach((value) => { counts[Math.min(bins - 1, Math.floor((value - min) / width))]++; });
  const edge = (value) => Number(value.toPrecision(6)).toString();
  return {
    labels: counts.map((_, i) => `[${edge(min + i * width)}, ${edge(min + (i + 1) * width)}${i === bins - 1 ? "]" : ")"}`),
    counts,
  };
}

function drawChart() {
  if (!currentResult) return;
  if (resultChart) { resultChart.destroy(); resultChart = null; }
  byId("downloadChartBtn").disabled = true;
  byId("chartTitle").textContent = chartTitles[chartMode];
  byId("distributionControl").classList.toggle("hidden", chartMode !== "distribution");
  byId("logControl").classList.toggle("hidden", !["comparison", "scatter"].includes(chartMode));
  const items = currentResult.list;
  const s = currentResult.summary;
  const hasZero = items.some((item) => item.permeability <= 0);
  byId("logScale").disabled = hasZero;
  byId("logControl").title = hasZero ? "存在零渗透率，采用线性轴保留全部样本" : "";
  if (hasZero) byId("logScale").checked = false;
  const log = byId("logScale").checked;
  const scale = (title, position = "left", logarithmic = false) => ({
    type: logarithmic ? "logarithmic" : "linear", position, beginAtZero: !logarithmic,
    title: { display: true, text: title }, grid: { drawOnChartArea: position !== "right", color: "#edf0f3" },
    ticks: { maxTicksLimit: 6 },
  });
  const config = { type: "bar", data: {}, options: {
    responsive: true, maintainAspectRatio: false, animation: false,
    layout: { padding: 8 },
    plugins: {
      legend: { position: "bottom", labels: { boxWidth: 12, padding: 14 } },
      title: { display: true, text: chartTitles[chartMode], color: "#263340", font: { size: 14 } },
      subtitle: { display: true, text: `${s.count} 个样本 · ${currentResult.model_context?.label || currentResult.rock_type}${currentResult.model_context?.is_demo ? " · 演示数据" : ""}`, padding: { bottom: 16 } },
      tooltip: { callbacks: {} },
    },
  } };
  let caption = "";
  if (chartMode === "comparison") {
    config.data = {
      labels: items.map((item) => `#${item.section_index}`),
      datasets: [
        { label: metricNames.porosity, data: items.map((item) => item.porosity), backgroundColor: colors[0], yAxisID: "poro", maxBarThickness: 30 },
        { label: metricNames.permeability, data: items.map((item) => item.permeability), backgroundColor: colors[1], yAxisID: "perm", maxBarThickness: 30 },
      ],
    };
    config.options.scales = {
      x: { title: { display: true, text: "样本编号（上传顺序）" }, ticks: { maxTicksLimit: 12, maxRotation: 0 }, grid: { display: false } },
      poro: scale(metricNames.porosity), perm: scale(metricNames.permeability, "right", log),
    };
    config.options.plugins.tooltip.callbacks = {
      title: (points) => `#${items[points[0].dataIndex].section_index} ${items[points[0].dataIndex].filename}`,
      label: (context) => `${context.dataset.label}: ${format(context.raw)}`,
    };
    caption = "左轴为孔隙度，右轴为渗透率，柱高不能跨指标直接比较。样本编号仅表示上传顺序。";
  } else if (chartMode === "scatter") {
    config.type = "scatter";
    config.data = { datasets: [{
      label: "岩心样本", data: items.map((item) => ({ x: item.porosity, y: item.permeability })),
      backgroundColor: items.map((item) => s.outlier_indices.includes(item.section_index) ? colors[3] : colors[1]),
      pointRadius: 6, pointHoverRadius: 9,
    }] };
    config.options.scales = { x: scale(metricNames.porosity, "bottom"), y: scale(metricNames.permeability, "left", log) };
    config.options.plugins.legend.display = false;
    config.options.plugins.tooltip.callbacks = {
      label: (context) => {
        const item = items[context.dataIndex];
        return [`#${item.section_index} ${item.filename}`, `孔隙度: ${format(item.porosity)}%`, `渗透率: ${format(item.permeability)} mD`];
      },
    };
    caption = `${s.correlation === null ? "当前样本量不足或数值恒定，相关系数不适用。" : `Pearson r = ${s.correlation.toFixed(3)}（按原始数值计算），相关性不代表因果关系。`} 重合点可能对应多个样本，详见明细。`;
  } else if (chartMode === "distribution") {
    const metric = byId("distributionMetric").value;
    const bins = histogram(items.map((item) => item[metric]));
    config.data = { labels: bins.labels, datasets: [{ label: "样本数", data: bins.counts, backgroundColor: metric === "porosity" ? colors[0] : colors[1] }] };
    config.options.scales = {
      x: { title: { display: true, text: metricNames[metric] }, ticks: { maxRotation: 35 }, grid: { display: false } },
      y: { ...scale("样本数"), ticks: { precision: 0 } },
    };
    config.options.plugins.legend.display = false;
    config.options.plugins.tooltip.callbacks.label = (context) => `${context.raw} 个样本（${(context.raw / s.count * 100).toFixed(1)}%）`;
    caption = s.count === 1 ? "当前仅有一个样本，不能据此推断总体分布。" : "等宽区间统计，区间左闭右开，末区间包含最大值；数值相同时合并为一个区间。";
  } else {
    config.type = "doughnut";
    const grades = s.grade_distribution;
    config.data = { labels: grades.map((grade) => grade.label), datasets: [{ data: grades.map((grade) => grade.count), backgroundColor: colors, borderWidth: 2, borderColor: "#ffffff" }] };
    config.options.cutout = "60%";
    config.options.plugins.tooltip.callbacks.label = (context) => `${context.label}: ${context.raw} 个（${grades[context.dataIndex].percent}%）`;
    caption = "按系统预设孔渗阈值对每个样本分别分级；占比与批次均值的等级含义不同。";
  }
  if (hasZero && ["comparison", "scatter"].includes(chartMode)) caption += " 存在零渗透率，已使用线性轴。";
  byId("chartCaption").textContent = caption;
  if (!window.Chart) {
    showMessage("chartError", "图表组件加载失败，请刷新页面；统计总结和样本明细仍可查看。");
    return;
  }
  try {
    config.plugins = [{ id: "whiteBackground", beforeDraw(chart) {
      const ctx = chart.ctx;
      ctx.save(); ctx.globalCompositeOperation = "destination-over";
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, chart.width, chart.height); ctx.restore();
    } }];
    resultChart = new Chart(byId("resultChart"), config);
    showMessage("chartError", "");
    byId("downloadChartBtn").disabled = false;
  } catch (error) {
    showMessage("chartError", "图表生成失败，统计总结和样本明细仍可查看。");
  }
}

function download(url, filename) {
  const link = document.createElement("a");
  link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
}
byId("downloadChartBtn").addEventListener("click", () => {
  if (!resultChart) return;
  download(resultChart.toBase64Image(), `${chartTitles[chartMode]}_${currentResult.summary.count}个样本.png`);
});
byId("exportBtn").addEventListener("click", async () => {
  if (!currentResult) return;
  byId("exportBtn").disabled = true;
  showMessage("exportError", "");
  try {
    const response = await fetch("/api/export/docx/", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentResult),
    });
    if (!response.ok || !response.headers.get("content-type")?.includes("wordprocessingml")) {
      if (response.headers.get("content-type")?.includes("application/json")) throw new Error((await response.json()).msg || "报告导出失败");
      throw new Error("报告导出失败，请检查登录状态后重试。");
    }
    const url = URL.createObjectURL(await response.blob());
    download(url, "岩心储层评价报告.docx");
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showMessage("exportError", error.message); }
  finally { byId("exportBtn").disabled = false; }
});
