const historyTable = document.getElementById("historyTable");
const clearBtn = document.getElementById("clearBtn");
const exportHistoryBtn = document.getElementById("exportHistoryBtn");

async function loadHistory() {
  try {
    const response = await fetch("/api/history/");
    const payload = await response.json();
    if (!payload.data.length) {
      historyTable.innerHTML = '<tr><td colspan="7" class="table-empty">暂无历史记录</td></tr>';
      return;
    }

    historyTable.innerHTML = payload.data.map((item, index) => `
      <tr>
        <td>${index + 1}</td>
        <td>${item.rock_type}</td>
        <td>${Number(item.porosity).toFixed(2)}</td>
        <td>${Number(item.permeability).toFixed(2)}</td>
        <td><img src="data:image/jpeg;base64,${item.image}" alt="岩心缩略图"></td>
        <td>${item.created_at}</td>
        <td><button class="row-action" onclick="deleteRecord(${item.id})">删除</button></td>
      </tr>
    `).join("");
  } catch (error) {
    historyTable.innerHTML = '<tr><td colspan="7" class="table-empty">历史记录加载失败</td></tr>';
  }
}

async function deleteRecord(id) {
  if (!confirm("确定删除这条记录吗？")) return;
  await fetch("/api/history/delete/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  loadHistory();
}

clearBtn.addEventListener("click", async () => {
  if (!confirm("确定清空全部历史记录吗？")) return;
  await fetch("/api/history/clear/", { method: "POST" });
  loadHistory();
});

exportHistoryBtn.addEventListener("click", async () => {
  const response = await fetch("/api/export/history-xlsx/", { method: "POST" });
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "岩心历史记录.xlsx";
  link.click();
  URL.revokeObjectURL(link.href);
});

loadHistory();
